#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixtoor ağ tanısı — veri kaynaklarının sağlığını ölçer ve raporlar.

Bot canlı veriyi çekemediğinde "sessizce eski veriye dön" davranışı sorunu
gizliyordu. Bu modül iki iş yapar:

1. ``hedef_iste``  — tek bir URL'yi farklı User-Agent/host kombinasyonlarıyla
   dener; HTTP durumunu, gövde örneğini, yanıt sürelerini ve WAF imzalarını
   kaydeder.
2. ``ag_tanisi``   — ESPN uçlarını, yedek sağlayıcıları ve DNS'i tarayıp kısa,
   depoya yazılabilir bir JSON raporu üretir (``data/tani.json``).

Rapor kasıtlı olarak küçüktür: GitHub Pages'te yayınlanır, sayfadaki "veri
kaynağı durumu" rozeti ve Actions çıktısı bunu okur. Hiçbir gizli anahtar
içermez.

Kullanım::

    python3 bot/fiktoor.py --tani          # raporu üret ve data/tani.json'a yaz
"""

from __future__ import annotations

import gzip
import io
import json
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
TANI_DOSYA = "tani.json"
TANI_ZAMAN_ASIMI = 12          # tek istek için saniye
TANI_TOPLAM_BUTCE = 75         # tüm tarama için saniye bütçesi

# Farklı WAF/CDN katmanları farklı User-Agent'lara farklı davranıyor. Gerçek
# arıza anında hangisinin geçtiğini bilmek, botu tahmin yürütmeden onarmanın
# tek yolu.
UA_ADAYLARI = (
    ("bot", "FixtoorBot/1.1 (+https://github.com/inadinatv/Fixtoor)"),
    ("chrome", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    ("firefox", "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"),
    ("curl", "curl/8.5.0"),
    ("python", "Python-urllib/3.12"),
)

# Bilinen WAF/engel gövde imzaları: arızanın "kimden" geldiğini söyler.
WAF_IMZALARI = (
    ("akamai", ("akamai", "reference #", "access denied")),
    ("cloudflare", ("cloudflare", "cf-ray", "attention required")),
    ("fastly", ("fastly",)),
    ("incapsula", ("incapsula", "imperva")),
    ("datadome", ("datadome",)),
    ("perimeterx", ("perimeterx", "px-captcha")),
    ("aws-waf", ("aws waf", "request blocked")),
)

ESPN_HOSTLARI = (
    "site.api.espn.com",
    "site.web.api.espn.com",
    "cdn.espn.com",
    "sports.core.api.espn.com",
    "now.core.api.espn.com",
)

DNS_HEDEFLERI = ESPN_HOSTLARI + (
    "www.thesportsdb.com",
    "api.github.com",
    "www.sporekrani.com",
)


def _waf_imzasi(metin: str) -> str:
    k = (metin or "").casefold()
    for ad, anahtarlar in WAF_IMZALARI:
        if any(a in k for a in anahtarlar):
            return ad
    return ""


def hedef_iste(url: str, ua: tuple = UA_ADAYLARI[0], *, referer: str = "",
               accept: str = "application/json", timeout: int = TANI_ZAMAN_ASIMI) -> dict:
    """Tek bir isteği ölçer; asla istisna fırlatmaz, her şeyi sözlüğe yazar."""
    ad, ua_metin = ua
    baslikler = {
        "Accept": accept,
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    }
    if ua_metin:
        baslikler["User-Agent"] = ua_metin
    if referer:
        baslikler["Referer"] = referer
        baslikler["Origin"] = referer.split("/")[0] + "//" + referer.split("/")[2]

    basla = time.time()
    kayit = {"url": url, "ua": ad, "durum": 0, "ms": 0, "bayt": 0}
    try:
        istek = urllib.request.Request(url, headers=baslikler)
        with urllib.request.urlopen(istek, timeout=timeout) as yanit:
            ham = yanit.read()
            if (yanit.headers.get("Content-Encoding") or "").lower() == "gzip":
                try:
                    ham = gzip.GzipFile(fileobj=io.BytesIO(ham)).read()
                except OSError:
                    pass
            kayit["durum"] = getattr(yanit, "status", 200)
            kayit["bayt"] = len(ham)
            kayit["cors"] = yanit.headers.get("Access-Control-Allow-Origin", "")
            kayit["sunucu"] = yanit.headers.get("Server", "")
            kayit["cache"] = yanit.headers.get("Cache-Control", "")
            metin = ham.decode("utf-8", "replace")
            kayit["ornek"] = metin[:220]
            try:
                veri = json.loads(metin)
                kayit["json"] = True
                if isinstance(veri, dict):
                    kayit["anahtarlar"] = list(veri.keys())[:12]
                    olaylar = veri.get("events")
                    if isinstance(olaylar, list):
                        kayit["event"] = len(olaylar)
                        if olaylar and isinstance(olaylar[0], dict):
                            kayit["ilk"] = str(olaylar[0].get("date") or "")[:20]
            except Exception:
                kayit["json"] = False
            kayit["waf"] = _waf_imzasi(metin[:4000])
    except urllib.error.HTTPError as e:
        govde = ""
        try:
            govde = (e.read() or b"")[:800].decode("utf-8", "replace")
        except Exception:
            pass
        kayit["durum"] = e.code
        kayit["hata"] = f"HTTP {e.code} {e.reason}"
        kayit["govde"] = govde[:220]
        kayit["waf"] = _waf_imzasi(govde)
        try:
            kayit["sunucu"] = e.headers.get("Server", "") if e.headers else ""
            kayit["cf-ray"] = e.headers.get("CF-RAY", "") if e.headers else ""
            kayit["retry-after"] = e.headers.get("Retry-After", "") if e.headers else ""
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001 - tanı aracı hiçbir koşulda çökmemeli
        kayit["durum"] = 0
        kayit["hata"] = f"{type(e).__name__}: {str(e)[:160]}"
    kayit["ms"] = int((time.time() - basla) * 1000)
    return kayit


def dns_tara(hedefler=DNS_HEDEFLERI) -> dict:
    """Runner'ın DNS çözümlemesini test eder (IP engeli mi, DNS mi ayrımı için)."""
    cikti = {}
    for ad in hedefler:
        basla = time.time()
        try:
            kayitlar = socket.getaddrinfo(ad, 443, proto=socket.IPPROTO_TCP)
            ipler = sorted({k[4][0] for k in kayitlar})
            cikti[ad] = {"ip": ipler[:3], "ms": int((time.time() - basla) * 1000)}
        except Exception as e:  # noqa: BLE001
            cikti[ad] = {"hata": f"{type(e).__name__}: {str(e)[:120]}"}
    return cikti


def dis_ip() -> str:
    """Runner'ın çıkış IP'si — ESPN tarafında IP bazlı engel olup olmadığını söyler."""
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip",
                "https://api.github.com/zen"):
        r = hedef_iste(url, UA_ADAYLARI[1], accept="text/plain", timeout=8)
        if r.get("durum") == 200 and r.get("ornek"):
            return r["ornek"].strip()[:60]
    return ""


def ag_tanisi(slug: str = "tur.1", *, kapsam: str = "tam") -> dict:
    """Tüm kaynakları tarar ve JSON'a dökülebilir bir rapor döndürür.

    ``kapsam='hizli'`` yalnızca birincil ESPN ucunu ve tek UA'yı dener; canlı
    moddaki hata yolunda işi yavaşlatmamak için kullanılır.
    """
    butce_basla = time.time()
    slug_q = urllib_quote(slug)
    scoreboard = "scoreboard"

    hedefler = [
        ("site.api", f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug_q}/{scoreboard}"),
        ("site.web", f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/{slug_q}/{scoreboard}"),
    ]
    ua_liste = [UA_ADAYLARI[0], UA_ADAYLARI[1]] if kapsam == "hizli" else list(UA_ADAYLARI)

    testler = []
    for ad, url in hedefler:
        for ua in ua_liste:
            if time.time() - butce_basla > TANI_TOPLAM_BUTCE:
                break
            testler.append({"hedef": ad, **hedef_iste(url, ua)})

    if kapsam != "hizli":
        ek = [
            ("cdn.core", f"https://cdn.espn.com/core/soccer/scoreboard?league={slug_q}&xhr=1"),
            ("sports.core", f"https://sports.core.api.espn.com/v2/soccer/leagues/{slug_q}"
                            f"/seasons/2026/types/1/scoreboard"),
            ("standings.web", f"https://site.web.api.espn.com/apis/v2/sports/soccer/{slug_q}"
                              f"/standings?season=2026"),
            ("standings.site", f"https://site.api.espn.com/apis/v2/sports/soccer/{slug_q}/standings"),
            ("summary.site", f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug_q}"
                             f"/summary?event=401888285"),
            ("thesportsdb.next", "https://www.thesportsdb.com/api/v1/json/3/"
                                 "eventsnextleague.php?id=4335"),
            ("thesportsdb.past", "https://www.thesportsdb.com/api/v1/json/3/"
                                 "eventspastleague.php?id=4335"),
            ("thesportsdb.table", "https://www.thesportsdb.com/api/v1/json/3/"
                                  "lookuptable.php?l=4335&s=2026-2027"),
            ("sporekrani", "https://www.sporekrani.com/home/league/trendyol-super-lig"),
            ("livesoccertv", "https://www.livesoccertv.com/competitions/turkey/super-lig/"),
        ]
        for ad, url in ek:
            if time.time() - butce_basla > TANI_TOPLAM_BUTCE:
                break
            accept = ("text/html,application/xhtml+xml" if ad in ("sporekrani", "livesoccertv")
                      else "application/json")
            testler.append({"hedef": ad, **hedef_iste(url, UA_ADAYLARI[1], accept=accept)})

        # Referer/Origin başlığıyla bir deneme daha (bazı WAF'ler bunu ister)
        testler.append({
            "hedef": "site.api+referer",
            **hedef_iste(hedefler[0][1], UA_ADAYLARI[1],
                         referer="https://www.espn.com/soccer/scoreboard/_/league/" + slug_q),
        })

    calisan = [t for t in testler if t.get("durum") == 200 and t.get("json")]
    rapor = {
        "uretim": datetime.now(timezone.utc).isoformat(),
        "kapsam": kapsam,
        "slug": slug,
        "host": socket.gethostname(),
        "dns": dns_tara() if kapsam != "hizli" else {},
        "cikis_ip": dis_ip() if kapsam != "hizli" else "",
        "sure_ms": int((time.time() - butce_basla) * 1000),
        "calisan_kaynaklar": sorted({t["hedef"] for t in calisan}),
        "testler": testler,
    }
    return rapor


def urllib_quote(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(str(s), safe=".")


def ozet_satir(rapor: dict) -> str:
    """Raporu tek satır insan-okur özete indirger (Actions log'u için)."""
    parcalar = []
    for t in rapor.get("testler", []):
        durum = t.get("durum")
        isaret = "OK" if durum == 200 else f"HATA-{durum}"
        ek = ""
        if t.get("hata"):
            ek = f" ({t['hata']})"
        elif t.get("waf"):
            ek = f" [waf:{t['waf']}]"
        parcalar.append(f"{t.get('hedef')}/{t.get('ua')}={isaret}{ek}")
    return "; ".join(parcalar)


def tani_yaz(data_dir: str, rapor: dict) -> str:
    """Raporu atomik olarak ``data/tani.json`` dosyasına yazar."""
    os.makedirs(data_dir, exist_ok=True)
    yol = os.path.join(data_dir, TANI_DOSYA)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(gecici, yol)
    try:
        os.chmod(yol, 0o644)
    except OSError:
        pass
    return yol


def tani_oku(data_dir: str):
    try:
        with open(os.path.join(data_dir, TANI_DOSYA), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Fixtoor ağ tanısı")
    p.add_argument("--league", default="tur.1")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--hizli", action="store_true", help="kısa tarama")
    a = p.parse_args()
    rep = ag_tanisi(a.league, kapsam="hizli" if a.hizli else "tam")
    yol = tani_yaz(a.data_dir, rep)
    print(f"[tani] yazıldı: {yol}  süre={rep['sure_ms']}ms  çıkış_ip={rep['cikis_ip']}")
    print("[tani] çalışan kaynaklar:", rep["calisan_kaynaklar"] or "YOK")
    for satir in ozet_satir(rep).split("; "):
        print("  -", satir)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fixtoor Bot — Süper Lig fikstür, maç özeti ve puan durumu üreten statik site botu.

Veri kaynağı : ESPN gizli (ücretsiz, anahtarsız) API
Çıktılar     : data/*.json (ham veri) + index.html (hazır sayfa)

Kullanım:
    python3 bot/fiktoor.py                # API'den çek, veri + HTML üret
    python3 bot/fiktoor.py --offline      # elimizdeki veriden HTML üret (ağ yoksa)
    python3 bot/fiktoor.py --league eng.1 # başka lig (isteğe bağlı)
"""

import argparse
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------------
# Sabitler
# ----------------------------------------------------------------------------
SITE_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}"
WEB_API = "https://site.web.api.espn.com/apis/v2/sports/soccer/{slug}"
TR_TZ = ZoneInfo("Europe/Istanbul")

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
# Takvim kısaltmaları: Cuma/Cumartesi ("Cum") ve Pazar/Pazartesi ("Paz") karışmasın diye ayrı liste
GUNLER_KISA = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]

HTTP_TIMEOUT = 25
HTTP_DENE = 3

LIG_ADLARI = {
    "tur.1": "Trendyol Süper Lig",
    "tur.2": "TFF 1. Lig",
    "eng.1": "Premier Lig",
    "esp.1": "La Liga",
}


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[fixtoor] {msg}", flush=True)


def http_get_json(url: str) -> dict:
    """URL'den JSON çeker; basit yeniden deneme mantığıyla."""
    son_hata = None
    for deneme in range(1, HTTP_DENE + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FixtoorBot/1.0 (+github)"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            son_hata = e
            log(f"istek başarısız ({deneme}/{HTTP_DENE}): {url} -> {e}")
            time.sleep(2 * deneme)
    raise RuntimeError(f"API'ye ulaşılamadı: {url} ({son_hata})")


def esc(s) -> str:
    return html_mod.escape(str(s if s is not None else ""), quote=True)


def tr_tarih(dt: datetime, saat_dahil: bool = True) -> str:
    """UTC datetime -> 'Cmt, 29 Ağu 19:00' (İstanbul saati)."""
    yerel = dt.astimezone(TR_TZ)
    metin = f"{GUNLER_KISA[yerel.weekday()]}, {yerel.day} {AYLAR[yerel.month - 1]}"
    if saat_dahil:
        metin += f" {yerel.hour:02d}:{yerel.minute:02d}"
    return metin


def parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ----------------------------------------------------------------------------
# Veri çekme
# ----------------------------------------------------------------------------
def fetch_lig_bilgisi(slug: str) -> dict:
    data = http_get_json(f"{SITE_API.format(slug=slug)}/scoreboard")
    lig = (data.get("leagues") or [{}])[0]
    sezon = lig.get("season") or {}
    return {
        "slug": lig.get("slug", slug),
        "ad": LIG_ADLARI.get(slug, lig.get("name", slug)),
        "api_adi": lig.get("name", ""),
        "sezon_yili": sezon.get("year"),
        "sezon_adi": sezon.get("displayName", ""),
        "baslangic": sezon.get("startDate", ""),
        "bitis": sezon.get("endDate", ""),
        "logo": ((lig.get("logos") or [{}])[0].get("href", "")),
        "takvim": [d[:10] for d in lig.get("calendar") or []],
    }


def fetch_sezon_maclar(slug: str, baslangic: str, bitis: str) -> list:
    """Sezonun tamamını 25 günlük pencereler halinde çekip tek listede birleştirir."""
    mac_sonu = []
    gorulen = set()
    d0 = parse_utc(baslangic).date() if baslangic else datetime.now(timezone.utc).date()
    d1 = parse_utc(bitis).date() if bitis else d0 + timedelta(days=300)
    pencere = d0
    while pencere <= d1:
        a = pencere
        b = min(pencere + timedelta(days=24), d1)
        url = (
            f"{SITE_API.format(slug=slug)}/scoreboard"
            f"?dates={a.strftime('%Y%m%d')}-{b.strftime('%Y%m%d')}&limit=300"
        )
        data = http_get_json(url)
        for ev in data.get("events") or []:
            if ev.get("id") not in gorulen:
                gorulen.add(ev.get("id"))
                mac_sonu.append(ev)
        log(f"pencere {a}..{b}: toplam {len(mac_sonu)} maç")
        pencere = b + timedelta(days=1)
    return mac_sonu


def fetch_puan_durumu(slug: str, sezon_yili) -> list:
    url = f"{WEB_API.format(slug=slug)}/standings?season={sezon_yili}"
    data = http_get_json(url)
    satirlar = []
    for cocuk in data.get("children") or []:
        for ent in cocuk.get("standings", {}).get("entries") or []:
            ist = {s.get("name"): s.get("displayValue", "") for s in ent.get("stats") or []}
            takim = ent.get("team") or {}
            logo = ""
            for l in takim.get("logos") or []:
                if l.get("href"):
                    logo = l["href"]
                    break
            satirlar.append({
                "sira": int(float(ist.get("rank") or 0)),
                "takim_id": takim.get("id", ""),
                "takim": takim.get("displayName", ""),
                "kisa": takim.get("abbreviation", ""),
                "logo": logo,
                "o": ist.get("gamesPlayed", "0"),
                "g": ist.get("wins", "0"),
                "b": ist.get("ties", "0"),
                "m": ist.get("losses", "0"),
                "attigi": ist.get("pointsFor", "0"),
                "yedigi": ist.get("pointsAgainst", "0"),
                "averaj": ist.get("pointDifferential", "0"),
                "puan": ist.get("points", "0"),
                "form": ist.get("overall", ""),
                "not": (ent.get("note") or {}).get("description", ""),
                "not_renk": (ent.get("note") or {}).get("color", ""),
            })
    satirlar.sort(key=lambda x: x["sira"])
    return satirlar


# ----------------------------------------------------------------------------
# Yayın kanalı verisi (Spor Ekranı + LiveSoccerTV)
# ----------------------------------------------------------------------------
TR_HARF = str.maketrans("çÇğĞıİöÖşŞüÜ", "cCgGiIoOsSuU")

# Lig -> yayın akışı sayfası (Spor Ekranı)
SPOREKRANI_LIG = {
    "tur.1": "https://www.sporekrani.com/home/league/trendyol-super-lig",
    "tur.2": "https://www.sporekrani.com/home/league/tff-1-lig",
}
# Lig -> LiveSoccerTV sayfası
LIVESOCCERTV_LIG = {
    "tur.1": "https://www.livesoccertv.com/competitions/turkey/super-lig/",
    "tur.2": "https://www.livesoccertv.com/competitions/turkey/1-lig/",
}


def takim_norm(ad: str) -> str:
    """Takım adını karşılaştırılabilir hale getirir: 'Çaykur Rizespor' -> 'caykurrizespor'."""
    s = (ad or "").casefold().translate(TR_HARF)
    return re.sub(r"[^a-z0-9]", "", s)


# Kaynak sitelerdeki adlar -> ESPN adları (normalize edilmiş biçimde)
TAKIM_TAKMA = {
    "amedspor": "amedsfk", "amedsk": "amedsfk",
    "erzurumspor": "erzurumbb", "bberzurumspor": "erzurumbb", "erzurumsporbb": "erzurumbb",
    "rizespor": "caykurrizespor", "corumspor": "corumfk",
    "basaksehir": "istanbulbasaksehir", "istanbulbb": "istanbulbasaksehir",
    "goztepespor": "goztepe",
}


def takim_coz(ad: str, espn_adlari: set):
    """Kaynak sitedeki takım adını ESPN takım adına eşler (yoksa None)."""
    n = takim_norm(ad)
    if not n:
        return None
    if n in espn_adlari:
        return n
    if TAKIM_TAKMA.get(n) in espn_adlari:
        return TAKIM_TAKMA[n]
    for e in espn_adlari:  # kısmi eşleşme: 'rizespor' <-> 'caykurrizespor'
        if len(n) >= 5 and len(e) >= 5 and (n in e or e in n):
            return e
    return None


def kanal_norm(ad: str) -> str:
    """Kanal adını standartlaştırır: 'Bein Sports 1' -> 'beIN Sports 1'."""
    s = re.sub(r"\s+", " ", ad or "").strip()
    m = re.match(r"(?i)^be\.?\s?-?\s?in\s?sports?\s*(\d+)$", s)
    if m:
        return f"beIN Sports {m.group(1)}"
    if re.match(r"(?i)^be\.?\s?-?\s?in\s*connect", s):
        return "beIN Connect"
    return s


def http_get_text(url: str) -> str:
    """URL'den HTML metni çeker (basit yeniden deneme ile)."""
    son_hata = None
    for deneme in range(1, HTTP_DENE + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Fixtoor/1.0 (+github)",
                "Accept-Language": "tr,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            son_hata = e
            time.sleep(2 * deneme)
    raise RuntimeError(f"sayfaya ulaşılamadı: {url} ({son_hata})")


def _mac_anahtari(ev_norm: str, dep_norm: str) -> str:
    return "|".join(sorted((ev_norm, dep_norm)))


def scrape_sporekrani(espn_adlari: set, espn_ciftler: set, slug: str) -> dict:
    """Spor Ekranı yayın akışından maç -> kanal eşleşmelerini çıkarır."""
    html = http_get_text(SPOREKRANI_LIG.get(slug, SPOREKRANI_LIG["tur.1"]))
    sonuc = {}
    bloklar = re.findall(
        r'<a[^>]+href="https://www\.sporekrani\.com/home/match/[^"]+"[^>]*>(.*?)</a>',
        html, re.S)
    for blok in bloklar:
        kanallar = []
        for alt in re.findall(r'alt="([^"]+)"', blok):
            a = alt.strip()
            if not a or a.casefold() in ("futbol", "basketbol", "tenis", "yayın yok"):
                continue
            if a not in kanallar:
                kanallar.append(a)
        if not kanallar:
            continue
        metin = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", blok))
        m = re.search(r"([A-Za-zÇĞİÖŞÜçğıöşü0-9.'()+&]+)\s+-\s+([A-Za-zÇĞİÖŞÜçğıöşü0-9.'()+&]+)", metin)
        if not m:
            continue
        ev, dep = takim_coz(m.group(1), espn_adlari), takim_coz(m.group(2), espn_adlari)
        if ev and dep and frozenset((ev, dep)) in espn_ciftler:
            sonuc[_mac_anahtari(ev, dep)] = kanal_norm(kanallar[0])
    return sonuc


def scrape_livesoccertv(espn_adlari: set, espn_ciftler: set, slug: str) -> dict:
    """LiveSoccerTV maç listesinden Türk yayın kanallarını çıkarır."""
    html = http_get_text(LIVESOCCERTV_LIG.get(slug, LIVESOCCERTV_LIG["tur.1"]))
    sonuc = {}
    for satir in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "Repeat" in satir or "/match/" not in satir:
            continue
        m = re.search(r'<a[^>]+href="[^"]*/match/[^"]+"[^>]*>([^<]+?)\s+vs\.?\s+([^<]+?)</a>', satir)
        if not m:
            continue
        basliklar = [b.strip() for b in re.findall(
            r'<a[^>]+href="[^"]*/channels/[^"]+"[^>]*title="([^"]+)"', satir)]
        tr_kanallar = [b for b in basliklar
                       if "turkey" in b.casefold() or b.casefold() in ("tod", "digiturk play")]
        if not tr_kanallar:
            continue
        sec = next((k for k in tr_kanallar if re.search(r"(?i)be\.?\s?in\s?sports?\s*\d", k)),
                   tr_kanallar[0])
        ev, dep = takim_coz(m.group(1), espn_adlari), takim_coz(m.group(2), espn_adlari)
        if ev and dep and frozenset((ev, dep)) in espn_ciftler:
            sonuc[_mac_anahtari(ev, dep)] = kanal_norm(sec.replace(" Turkey", ""))
    return sonuc


def fetch_yayin_kanallari(maclar: list, slug: str, data_dir: str) -> dict:
    """İki kaynağı kazır, elle düzeltme dosyasıyla birleştirir.
    Dönen anahtar biçimi: 'evnorm|depnorm' (alfabetik)."""
    espn_adlari = {takim_norm(t["ad"]) for m in maclar for t in (m["ev"], m["dep"])}
    espn_ciftler = {frozenset((takim_norm(m["ev"]["ad"]), takim_norm(m["dep"]["ad"])))
                    for m in maclar}
    kanallar = {}
    for kaynak in (scrape_sporekrani, scrape_livesoccertv):
        try:
            veri = kaynak(espn_adlari, espn_ciftler, slug)
            log(f"yayın kanalları ({kaynak.__name__}): {len(veri)} maç")
            for k, v in veri.items():
                kanallar.setdefault(k, v)
        except Exception as e:  # kaynak düşerse diğerleriyle devam
            log(f"UYARI: {kaynak.__name__} okunamadı: {e}")

    # Elle düzeltme dosyası (varsa kazımadan üstün gelir)
    manuel_yol = os.path.join(data_dir, "yayin-kanallari.json")
    if os.path.exists(manuel_yol):
        try:
            with open(manuel_yol, encoding="utf-8") as f:
                manuel = json.load(f)
            for k, v in manuel.items():
                if not k.startswith("_") and v:
                    kanallar[k] = kanal_norm(v)
            log(f"yayın kanalları: {os.path.basename(manuel_yol)} ile birleştirildi")
        except (OSError, json.JSONDecodeError) as e:
            log(f"UYARI: yayin-kanallari.json okunamadı: {e}")
    return kanallar


# ----------------------------------------------------------------------------
# Ayrıştırma
# ----------------------------------------------------------------------------
def mac_ayristir(ev: dict) -> dict:
    """ESPN event -> sade maç sözlüğü."""
    comp = (ev.get("competitions") or [{}])[0]
    durum = (comp.get("status") or {})
    durum_tip = (durum.get("type") or {})

    ev_sahibi, deplasman = {}, {}
    for rakip in comp.get("competitors") or []:
        hedef = ev_sahibi if rakip.get("homeAway") == "home" else deplasman
        takim = rakip.get("team") or {}
        hedef.update({
            "id": takim.get("id", ""),
            "ad": takim.get("displayName", ""),
            "kisa": takim.get("abbreviation", ""),
            "logo": takim.get("logo", ""),
            "renk": "#" + (takim.get("color") or "353a40"),
            "skor": rakip.get("score") or None,
            "kazandi": bool(rakip.get("winner")),
            "form": rakip.get("form", ""),
        })
        # istatistikler (oynanmış maçlarda gelir)
        ist = {}
        for s in rakip.get("statistics") or []:
            ist[s.get("name", "")] = s.get("displayValue", "")
        hedef["istatistik"] = ist

    # Maç olayları: goller ve kartlar
    goller, kirmizi, sarilar = [], [], []
    for d in comp.get("details") or []:
        oyuncular = ", ".join(a.get("displayName", "") for a in d.get("athletesInvolved") or [])
        saat = (d.get("clock") or {}).get("displayValue", "")
        olay = {
            "dakika": saat,
            "oyuncu": oyuncular,
            "takim_id": (d.get("team") or {}).get("id", ""),
            "penalti": bool(d.get("penaltyKick")),
            "kendi_kalesine": bool(d.get("ownGoal")),
        }
        if d.get("scoringPlay"):
            goller.append(olay)
        elif d.get("redCard"):
            kirmizi.append(olay)
        elif d.get("yellowCard"):
            sarilar.append(olay)

    stadyum = (comp.get("venue") or {})
    return {
        "id": ev.get("id", ""),
        "utc": comp.get("date") or ev.get("date", ""),
        "durum": durum_tip.get("state", ""),          # pre | in | post
        "durum_metin": durum_tip.get("shortDetail") or durum_tip.get("detail") or "",
        "saat_gostergesi": durum.get("displayClock", ""),
        "ev": ev_sahibi,
        "dep": deplasman,
        "stadyum": stadyum.get("fullName", ""),
        "sehir": (stadyum.get("address") or {}).get("city", ""),
        "goller": goller,
        "kirmizi_kartlar": kirmizi,
        "sari_kartlar": sarilar,
    }


def haftalara_ayir(maclar: list) -> list:
    """Maçları kronolojik olarak turlara (haftalara) ayırır.
    Kural: bir takım o hafta tekrar oynuyorsa yeni hafta başlar."""
    sirali = sorted(maclar, key=lambda m: m["utc"])
    haftalar, mevcut, takimlar = [], [], set()
    for m in sirali:
        anahtarlar = {m["ev"]["id"], m["dep"]["id"]}
        if anahtarlar & takimlar:
            haftalar.append(mevcut)
            mevcut, takimlar = [], set()
        mevcut.append(m)
        takimlar |= anahtarlar
    if mevcut:
        haftalar.append(mevcut)
    return haftalar


# ----------------------------------------------------------------------------
# HTML üretimi
# ----------------------------------------------------------------------------
CSS = """
:root{--bg:#0b0f14;--kart:#141b24;--kart2:#1b2430;--cizgi:#263242;--metin:#e7edf5;
--soluk:#8b98a9;--yesil:#22c55e;--kirmizi:#ef4444;--sari:#eab308;--mavi:#38bdf8}
*{box-sizing:border-box;margin:0;padding:0}
body{color:var(--metin);font:15px/1.55 -apple-system,'Segoe UI',Roboto,Arial,sans-serif;
background:radial-gradient(1100px 480px at 85% -10%,rgba(56,189,248,.08),transparent 60%),
radial-gradient(900px 420px at 8% -5%,rgba(34,197,94,.07),transparent 55%),var(--bg)}
body::before{content:'';position:fixed;top:0;left:0;right:0;height:3px;z-index:10;
background:linear-gradient(90deg,#22c55e,#38bdf8,#a78bfa)}
::selection{background:rgba(34,197,94,.35)}
.kapsayici{max-width:980px;margin:0 auto;padding:22px 16px 40px;animation:giris .45s ease}
@keyframes giris{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
header.ust{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:4px;
background:linear-gradient(180deg,rgba(56,189,248,.07),rgba(34,197,94,.05));
border:1px solid var(--cizgi);border-radius:18px;padding:18px 20px}
header.ust>img{width:56px;height:56px;filter:drop-shadow(0 6px 16px rgba(0,0,0,.45))}
.logo-seridi{padding:4px 10px 0;margin-bottom:12px;text-align:center}
.logo-seridi img{display:inline-block;width:100%;max-width:520px;height:auto;max-height:150px;
object-fit:contain;filter:drop-shadow(0 6px 18px rgba(0,0,0,.45))}
header.ust.sade{justify-content:center;text-align:center}
header.ust.sade .lig-etiket{margin-left:0}
h1{font-size:26px;letter-spacing:.4px;display:inline}
h1 span{background:linear-gradient(90deg,#22c55e,#38bdf8);
-webkit-background-clip:text;background-clip:text;color:transparent}
.lig-etiket{display:inline-block;margin-left:10px;padding:3px 12px;border-radius:99px;font-size:13px;
font-weight:700;color:#cfe9ff;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);
vertical-align:middle;white-space:nowrap}
.alt-bilgi{color:var(--soluk);font-size:13px;margin-top:6px}
.canli{background:var(--kirmizi);color:#fff;font-size:11px;font-weight:700;padding:2px 8px;
border-radius:99px;animation:nabiz 1.2s infinite}
@keyframes nabiz{50%{opacity:.55}}
nav.sekmeler{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 20px}
nav.sekmeler button{background:var(--kart);color:var(--soluk);border:1px solid var(--cizgi);
padding:9px 16px;border-radius:12px;cursor:pointer;font-size:14px;font-weight:600;
transition:transform .15s,color .15s,border-color .15s,box-shadow .15s}
nav.sekmeler button:hover{color:var(--metin);border-color:#3b4c61;transform:translateY(-1px)}
nav.sekmeler button.aktif{background:linear-gradient(135deg,#22c55e,#16a34a);color:#04220e;
border-color:#22c55e;box-shadow:0 6px 20px rgba(34,197,94,.28)}
html.js .sekme-icerik{display:none}
html.js .sekme-icerik.aktif{display:block}
h2{font-size:19px;margin:22px 0 12px;display:flex;align-items:center;gap:8px}
h2::before{content:'';width:4px;height:18px;background:var(--yesil);border-radius:2px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:14px;padding:14px 16px;margin-bottom:12px;
transition:border-color .15s,transform .15s,box-shadow .15s}
.kart:hover{border-color:#33465c;transform:translateY(-2px);box-shadow:0 12px 26px rgba(0,0,0,.35)}
.skor,.tv-zaman .saat,table.puan{font-variant-numeric:tabular-nums}
.mac{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px}
.takim{display:flex;align-items:center;gap:10px;min-width:0;font-weight:600}
.takim.dep{flex-direction:row-reverse;text-align:right}
.takim img{width:30px;height:30px;object-fit:contain;flex-shrink:0}
.takim .isim{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rozet{width:30px;height:30px;border-radius:50%;background:var(--kart2);color:var(--soluk);
display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0}
.skor{font-size:22px;font-weight:800;text-align:center;min-width:64px}
.skor.onaylanmadi{color:var(--soluk);font-size:15px;font-weight:600}
.skor .kazanan{color:var(--yesil)}
.mac-alt{display:flex;justify-content:space-between;gap:10px;color:var(--soluk);
font-size:12.5px;margin-top:9px;border-top:1px dashed var(--cizgi);padding-top:8px;flex-wrap:wrap}
.durum-ms{color:var(--yesil);font-weight:700}
.durum-canli{color:var(--kirmizi);font-weight:700}
.cipsler{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 14px}
.cipsler button{background:var(--kart);border:1px solid var(--cizgi);color:var(--soluk);
border-radius:99px;padding:5px 12px;font-size:12.5px;cursor:pointer}
.cipsler button.aktif{background:var(--mavi);border-color:var(--mavi);color:#04263a;font-weight:700}
html.js .hafta{display:none}
html.js .hafta.aktif{display:block}
.ozet-govde{display:grid;grid-template-columns:1fr 1fr;gap:4px 18px;margin-top:10px;
font-size:13.5px;color:var(--soluk)}
.ozet-govde .gol{color:var(--metin)}
.ozet-govde .dep-kolon{text-align:right}
.gol-turu{font-size:11px;color:var(--sari)}
.ist{margin-top:12px;display:grid;gap:7px}
.ist-satir{display:grid;grid-template-columns:38px 1fr 38px;gap:10px;align-items:center;font-size:12.5px;color:var(--soluk)}
.ist-satir .deger{font-weight:700;color:var(--metin)}
.ist-satir .orta{text-align:center}
.bar{background:var(--kart2);border-radius:99px;height:7px;position:relative;overflow:hidden}
.bar i{position:absolute;top:0;bottom:0;border-radius:99px}
.bar .ev{left:0;background:var(--yesil)}
.bar .dep{right:0;background:var(--mavi)}
table.puan{width:100%;border-collapse:collapse;font-size:13.5px}
table.puan th{color:var(--soluk);font-weight:600;text-align:center;padding:8px 6px;border-bottom:1px solid var(--cizgi)}
table.puan th:first-child,table.puan td:first-child{text-align:left}
table.puan td{padding:8px 6px;text-align:center;border-bottom:1px solid #1a2330}
table.puan tr:last-child td{border-bottom:none}
table.puan tbody tr{transition:background .12s}
table.puan tbody tr:hover td{background:rgba(56,189,248,.055)}
table.puan .takim-hucre{display:flex;align-items:center;gap:9px;min-width:0}
table.puan .takim-hucre img{width:22px;height:22px;object-fit:contain}
table.puan .puan{font-weight:800;font-size:15px}
.nokta{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
footer{margin-top:46px;padding:32px 16px 26px;text-align:center;border-top:1px solid var(--cizgi);position:relative}
footer::before{content:'';position:absolute;top:-1px;left:50%;transform:translateX(-50%);
width:220px;height:2px;background:linear-gradient(90deg,transparent,#22c55e,#38bdf8,transparent)}
.marka{display:inline-flex;align-items:center;gap:11px;filter:drop-shadow(0 0 18px rgba(56,189,248,.3))}
.marka img{height:clamp(26px,5vw,38px);width:auto;max-width:160px;object-fit:contain}
.marka .itv-ad{font-size:22px;font-weight:800;letter-spacing:.4px;color:var(--metin)}
.marka .itv-ad b{color:var(--mavi)}
.telif{margin-top:10px;color:var(--soluk);font-size:12.5px}
.grid2{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:720px){.grid2{grid-template-columns:1fr 1fr}}
.bos{color:var(--soluk);padding:26px;text-align:center;background:var(--kart);
border:1px dashed var(--cizgi);border-radius:14px}
.kanal{display:inline-flex;align-items:center;gap:4px;background:linear-gradient(135deg,#20395c,#16283e);
color:#cfe9ff;border:1px solid #315071;border-radius:9px;padding:2px 10px;font-size:12px;font-weight:700;
white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.skor-inline{color:var(--yesil);font-weight:800;margin-left:4px}
.tv-kart{display:grid;grid-template-columns:78px 1fr auto;gap:14px;align-items:center;
background:linear-gradient(180deg,var(--kart),#111823);border:1px solid var(--cizgi);border-radius:14px;
padding:14px 16px;margin-bottom:12px;transition:border-color .15s,transform .15s,box-shadow .15s}
.tv-kart:hover{border-color:#33465c;transform:translateY(-2px);box-shadow:0 12px 26px rgba(0,0,0,.35)}
.tv-zaman{text-align:center;border-right:1px dashed var(--cizgi);padding-right:12px}
.tv-zaman .gun{font-size:11px;color:var(--soluk);text-transform:uppercase;letter-spacing:.5px}
.tv-zaman .saat{font-size:19px;font-weight:800}
.tv-zaman .tarih{font-size:10.5px;color:var(--soluk);margin-top:1px}
.tv-mac .takimlar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-weight:600;font-size:15px}
.tv-mac .takimlar img{width:26px;height:26px;object-fit:contain}
.tv-mac .takimlar .ayrac{color:var(--soluk);font-weight:400}
.tv-mac .alt{color:var(--soluk);font-size:12.5px;margin-top:5px}
.tv-kanal{justify-self:end}
.tv-kanal .kanal{font-size:13px;padding:6px 12px}
@media(max-width:560px){.tv-kart{grid-template-columns:1fr;gap:10px}
.tv-zaman{border-right:none;border-bottom:1px dashed var(--cizgi);padding:0 0 10px;
display:flex;gap:10px;align-items:baseline;justify-content:center}
.tv-kanal{justify-self:center}}
"""

JS = """
document.documentElement.classList.add('js');
// Sekmeler
var sekmeler=document.querySelectorAll('nav.sekmeler button');
sekmeler.forEach(function(b){b.addEventListener('click',function(){
  sekmeler.forEach(function(x){x.classList.remove('aktif')});
  document.querySelectorAll('.sekme-icerik').forEach(function(s){s.classList.remove('aktif')});
  b.classList.add('aktif');
  document.getElementById('sekme-'+b.dataset.sekme).classList.add('aktif');
});});
// Hafta cipleri
function haftaSec(b){
  document.querySelectorAll('.cipsler button').forEach(function(x){x.classList.remove('aktif')});
  document.querySelectorAll('.hafta').forEach(function(h){h.classList.remove('aktif')});
  b.classList.add('aktif');
  document.getElementById('hafta-'+b.dataset.hafta).classList.add('aktif');
}
document.querySelectorAll('.cipsler button').forEach(function(b){
  b.addEventListener('click',function(){haftaSec(b)});
});
"""


def takim_logolu(t: dict, dep: bool = False) -> str:
    isim = esc(t.get("ad", "?"))
    if t.get("logo"):  # logolar ESPN CDN'inden gelir
        gorunum = f'<img src="{esc(t["logo"])}" alt="" loading="lazy">'
    else:
        kisa = esc(t.get("kisa") or (t.get("ad") or "?")[:3].upper())
        gorunum = f'<span class="rozet">{kisa}</span>'
    return f'<div class="takim{" dep" if dep else ""}">{gorunum}<span class="isim">{isim}</span></div>'


def tv_karti(m: dict) -> str:
    """'Haftanın Maçları' bölümü için tek maçlık TV yayın akışı kartı."""
    ev, dep = m["ev"], m["dep"]
    oynandi, canli = m["durum"] == "post", m["durum"] == "in"
    yerel = parse_utc(m["utc"]).astimezone(TR_TZ) if m["utc"] else None

    def logo(t: dict) -> str:
        if t.get("logo"):
            return f'<img src="{esc(t["logo"])}" alt="" loading="lazy">'
        return (f'<span class="rozet" style="width:26px;height:26px;font-size:10px">'
                f'{esc((t.get("kisa") or "?")[:3])}</span>')

    skor_html = ""
    if oynandi or canli:
        skor_html = (f' <span class="skor-inline">({esc(ev.get("skor") or 0)} - '
                     f'{esc(dep.get("skor") or 0)})</span>')
    takimlar = (f'{logo(ev)}<span>{esc(ev["ad"])}</span>'
                f'<span class="ayrac">—</span>'
                f'<span>{esc(dep["ad"])}</span>{logo(dep)}{skor_html}')

    gun = GUNLER_KISA[yerel.weekday()] if yerel else ""
    saat = f"{yerel.hour:02d}:{yerel.minute:02d}" if yerel else "--:--"
    tarih = f"{yerel.day} {AYLAR[yerel.month - 1]}" if yerel else ""
    if canli:
        durum = '<div class="durum-canli" style="font-size:11px">CANLI</div>'
    elif oynandi:
        durum = '<div class="durum-ms" style="font-size:11px">MS</div>'
    else:
        durum = ""

    yer = " · ".join(x for x in [m.get("stadyum"), m.get("sehir")] if x)
    kanal = (m.get("kanal") or "").strip()
    if kanal:
        kanal_html = f'<span class="kanal">📺 {esc(kanal)}</span>'
    else:
        kanal_html = '<span class="kanal" style="opacity:.45">📺 —</span>'
    return f'''<div class="tv-kart">
<div class="tv-zaman"><div class="gun">{gun}</div><div class="saat">{saat}</div><div class="tarih">{tarih}</div>{durum}</div>
<div class="tv-mac"><div class="takimlar">{takimlar}</div><div class="alt">{esc(yer)}</div></div>
<div class="tv-kanal">{kanal_html}</div>
</div>'''


def mac_satiri(m: dict) -> str:
    ev, dep = m["ev"], m["dep"]
    oynandi = m["durum"] == "post"
    canli = m["durum"] == "in"

    if oynandi and ev.get("skor") is not None:
        evs = f'<span class="{"kazanan" if ev.get("kazandi") else ""}">{esc(ev["skor"])}</span>'
        deps = f'<span class="{"kazanan" if dep.get("kazandi") else ""}">{esc(dep["skor"])}</span>'
        skor_html = f"{evs} : {deps}"
    elif canli:
        skor_html = f'{esc(ev.get("skor") or 0)} : {esc(dep.get("skor") or 0)}'
    else:
        yerel = parse_utc(m["utc"]).astimezone(TR_TZ) if m["utc"] else None
        skor_html = f"{yerel.hour:02d}:{yerel.minute:02d}" if yerel else "&nbsp;"

    if canli:
        durum_html = f'<span class="durum-canli">● CANLI {esc(m.get("saat_gostergesi", ""))}</span>'
    elif oynandi:
        durum_html = f'<span class="durum-ms">{esc(m.get("durum_metin") or "MS")}</span>'
    else:
        durum_html = ""

    yer = " · ".join(x for x in [m.get("stadyum"), m.get("sehir")] if x)
    kanal = (m.get("kanal") or "").strip()
    kanal_cipi = f' · <span class="kanal">📺 {esc(kanal)}</span>' if kanal else ""
    return f'''<div class="kart"><div class="mac">
  {takim_logolu(ev)}
  <div class="skor{" onaylanmadi" if not (oynandi or canli) else ""}">{skor_html}</div>
  {takim_logolu(dep, dep=True)}
</div>
<div class="mac-alt"><span>{esc(tr_tarih(parse_utc(m["utc"]))) if m["utc"] else ""}</span>
<span>{durum_html}{" · " if durum_html and yer else ""}{esc(yer)}{kanal_cipi}</span></div></div>'''


def istatistik_bar(baslik: str, ev_d: str, dep_d: str, yuzde: bool = False) -> str:
    try:
        ev_f, dep_f = float(ev_d or 0), float(dep_d or 0)
    except ValueError:
        ev_f, dep_f = 0.0, 0.0
    toplam = ev_f + dep_f or 1
    ev_w = int(ev_f / toplam * 100)
    birim = "%" if yuzde else ""
    return f'''<div class="ist-satir"><span class="deger">{esc(ev_d or 0)}{birim}</span>
<div><div class="bar"><i class="ev" style="width:{ev_w}%"></i></div>
<div class="orta">{esc(baslik)}</div></div>
<span class="deger" style="text-align:right">{esc(dep_d or 0)}{birim}</span></div>'''


def ozet_karti(m: dict) -> str:
    ev, dep = m["ev"], m["dep"]

    def gol_listesi(takim_id: str, takim: dict) -> str:
        satirlar = []
        for g in m.get("goller", []):
            if g["takim_id"] != takim_id:
                continue
            etiket = " (P)" if g["penalti"] else (" (KK)" if g["kendi_kalesine"] else "")
            satirlar.append(
                f'<div class="gol">⚽ {esc(g["oyuncu"])} {esc(g["dakika"])}'
                f'<span class="gol-turu">{etiket}</span></div>'
            )
        for k in m.get("kirmizi_kartlar", []):
            if k["takim_id"] == takim_id:
                satirlar.append(f'<div>🟥 {esc(k["oyuncu"])} {esc(k["dakika"])}</div>')
        return "\n".join(satirlar) or "<div style='opacity:.4'>—</div>"

    ie, idp = ev.get("istatistik", {}), dep.get("istatistik", {})
    ist_html = ""
    if ie or idp:
        ist_html = '<div class="ist">' + "".join([
            istatistik_bar("Topla oynama", ie.get("possessionPct", "0"), idp.get("possessionPct", "0"), True),
            istatistik_bar("Şut", ie.get("totalShots", "0"), idp.get("totalShots", "0")),
            istatistik_bar("İsabetli şut", ie.get("shotsOnTarget", "0"), idp.get("shotsOnTarget", "0")),
            istatistik_bar("Korner", ie.get("wonCorners", "0"), idp.get("wonCorners", "0")),
            istatistik_bar("Faul", ie.get("foulsCommitted", "0"), idp.get("foulsCommitted", "0")),
        ]) + "</div>"

    return f'''<div class="kart">
<div class="mac">
  {takim_logolu(ev)}
  <div class="skor">{esc(ev.get("skor") or 0)} : {esc(dep.get("skor") or 0)}</div>
  {takim_logolu(dep, dep=True)}
</div>
<div class="mac-alt"><span>{esc(tr_tarih(parse_utc(m["utc"])) if m["utc"] else "")}</span>
<span class="durum-ms">{esc(m.get("durum_metin") or "MS")}{" · " + esc(m["stadyum"]) if m.get("stadyum") else ""}</span></div>
<div class="ozet-govde">
  <div>{gol_listesi(ev["id"], ev)}</div>
  <div class="dep-kolon">{gol_listesi(dep["id"], dep)}</div>
</div>
{ist_html}
</div>'''


NOT_TR = {
    "Champions League": "Şampiyonlar Ligi",
    "Champions League qualifying": "ŞL eleme",
    "Europa League": "Avrupa Ligi",
    "Europa League qualifying": "AVL eleme",
    "Europa Conference League qualifying": "Konferans Ligi eleme",
    "Conference League qualifying": "Konferans Ligi eleme",
    "Relegation": "Küme düşme hattı",
    "Relegated": "Küme düşme hattı",
    "Champions": "Şampiyon",
}


def puan_tablosu(satirlar: list) -> str:
    if not satirlar:
        return '<div class="bos">Puan durumu henüz hazır değil.</div>'
    govde = []
    for s in satirlar:
        if s["logo"]:
            logo = f'<img src="{esc(s["logo"])}" alt="" loading="lazy">'
        else:
            logo = f'<span class="rozet" style="width:22px;height:22px;font-size:10px">{esc(s["kisa"][:3])}</span>'
        not_tr = NOT_TR.get(s["not"], s["not"])
        isaret = f'<span class="nokta" style="background:{esc(s["not_renk"] or "#555")}"></span>' if s["not"] else ""
        govde.append(f'''<tr><td><span class="takim-hucre">{isaret}{logo}{esc(s["takim"])}</span></td>
<td>{esc(s["o"])}</td><td>{esc(s["g"])}</td><td>{esc(s["b"])}</td><td>{esc(s["m"])}</td>
<td>{esc(s["attigi"])}</td><td>{esc(s["yedigi"])}</td><td>{esc(s["averaj"])}</td>
<td class="puan">{esc(s["puan"])}</td><td style="color:var(--soluk)">{esc(not_tr)}</td></tr>''')
    return f'''<div class="kart" style="overflow-x:auto"><table class="puan">
<thead><tr><th>Takım</th><th>O</th><th>G</th><th>B</th><th>M</th><th>A</th><th>Y</th>
<th>AV</th><th>P</th><th></th></tr></thead><tbody>{"".join(govde)}</tbody></table></div>'''


def render_html(veri: dict, cikti: str) -> None:
    lig = veri["lig"]
    haftalar = veri["haftalar"]
    puan = veri.get("puan_durumu") or []
    simdi = veri["uretim"]

    canli_var = any(m["durum"] == "in" for h in haftalar for m in h["maclar"])

    # --- varsayılan aktif hafta: içinde oynanmamış maç olan ilk hafta ---
    aktif_hafta = haftalar[-1]["no"] if haftalar else 0
    for h in haftalar:
        if any(m["durum"] != "post" for m in h["maclar"]):
            aktif_hafta = h["no"]
            break

    cips_html = "".join(
        f'<button data-hafta="{h["no"]}" class="{"aktif" if h["no"] == aktif_hafta else ""}">{h["no"]}</button>'
        for h in haftalar
    )

    hafta_bloklari = []
    for h in haftalar:
        mac_html = "".join(mac_satiri(m) for m in h["maclar"])
        tarih_araligi = ""
        if h["maclar"]:
            i0 = tr_tarih(parse_utc(h["maclar"][0]["utc"]), saat_dahil=False)
            i1 = tr_tarih(parse_utc(h["maclar"][-1]["utc"]), saat_dahil=False)
            tarih_araligi = i0 if i0 == i1 else f"{i0} – {i1}"
        hafta_bloklari.append(
            f'<div class="hafta{" aktif" if h["no"] == aktif_hafta else ""}" id="hafta-{h["no"]}">'
            f'<h2>{h["no"]}. Hafta <small style="color:var(--soluk);font-weight:400">· {esc(tarih_araligi)}</small></h2>'
            f'<div class="grid2">{mac_html}</div></div>'
        )

    # --- haftanın maçları (TV yayın akışı) ---
    haftanin = next((h for h in haftalar if h["no"] == aktif_hafta), None) or \
        (haftalar[-1] if haftalar else None)
    tv_html, tv_alt_baslik = "", ""
    if haftanin:
        dizi = sorted(haftanin["maclar"], key=lambda x: x["utc"])
        tv_html = "".join(tv_karti(m) for m in dizi)
        if dizi:
            i0 = tr_tarih(parse_utc(dizi[0]["utc"]), saat_dahil=False)
            i1 = tr_tarih(parse_utc(dizi[-1]["utc"]), saat_dahil=False)
            aralik = i0 if i0 == i1 else f"{i0} – {i1}"
            tv_alt_baslik = f'{haftanin["no"]}. Hafta · {aralik}'
        else:
            tv_alt_baslik = f'{haftanin["no"]}. Hafta'
    if not tv_html:
        tv_html = '<div class="bos">Bu hafta için maç bilgisi yok.</div>'

    # --- özetler: son 14 günde biten maçlar ---
    simdi_dt = parse_utc(simdi)
    ozetler = [
        m for h in haftalar for m in h["maclar"]
        if m["durum"] == "post" and m["utc"] and parse_utc(m["utc"]) >= simdi_dt - timedelta(days=14)
    ]
    ozetler.sort(key=lambda m: m["utc"], reverse=True)
    ozet_html = "".join(ozet_karti(m) for m in ozetler[:16]) or \
        '<div class="bos">Son 14 günde oynanmış maç yok.</div>'

    # --- yaklaşan maçlar ---
    yaklasan = [m for h in haftalar for m in h["maclar"] if m["durum"] == "pre"]
    yaklasan.sort(key=lambda m: m["utc"])
    yaklasan_html = "".join(mac_satiri(m) for m in yaklasan[:6]) or \
        '<div class="bos">Kalan maç yok — sezon tamamlandı. 🏆</div>'

    canli_rozet = ' <span class="canli">CANLI</span>' if canli_var else ""

    # İnadına TV markası: depoda logo dosyası varsa üstte tam genişlik şerit olarak
    # ve altta o kullanılır; yoksa üstte lig logosu, altta yerleşik SVG amblem gösterilir
    kok = os.path.dirname(os.path.abspath(cikti))
    logo_dosya = next((ad for ad in ("logo.png", "logo.svg", "logo.jpg", "logo.webp",
                                     "assets/logo.png", "assets/logo.svg")
                       if os.path.exists(os.path.join(kok, ad))), "")
    if logo_dosya:
        # Logo tam genişlik, üst şerit hâlinde, ortada gösterilir; başlık sadeleşir
        logo_seridi = (f'<div class="logo-seridi">'
                       f'<img src="{esc(logo_dosya)}" alt="İnadına TV"></div>')
        ust_logo_html = ""
        ust_sinif = "ust sade"
        marka_html = f'<span class="marka"><img src="{esc(logo_dosya)}" alt="İnadına TV"></span>'
    else:
        logo_seridi = ""
        ust_sinif = "ust"
        ust_logo_html = f'<img src="{esc(lig["logo"])}" alt="lig logosu">' if lig.get("logo") else ""
        marka_html = ('<span class="marka">'
                      '<svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">'
                      '<defs><linearGradient id="itvg" x1="0" y1="0" x2="1" y2="1">'
                      '<stop offset="0" stop-color="#22c55e"/><stop offset="1" stop-color="#38bdf8"/>'
                      '</linearGradient></defs>'
                      '<rect x="2" y="2" width="36" height="36" rx="11" fill="url(#itvg)"/>'
                      '<path d="M16.5 12.8v14.4L29 20z" fill="#0b0f14"/></svg>'
                      '<span class="itv-ad">inadına <b>TV</b></span></span>')
    sayfa = f'''<!DOCTYPE html>
<html lang="tr" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{esc(lig["ad"])} fikstürü, maç özetleri, puan durumu ve TV yayın akışı — Fixtoor">
<title>Fixtoor · {esc(lig["ad"])} {esc(lig.get("sezon_adi", ""))}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<style>{CSS}</style>
</head>
<body>
<div class="kapsayici">
{logo_seridi}
<header class="{ust_sinif}">{ust_logo_html}
<div><h1>Fix<span>toor</span></h1><span class="lig-etiket">⚽ {esc(lig["ad"])}</span>
<div class="alt-bilgi">{esc(lig.get("sezon_adi", ""))} · Fikstür · Maç Özetleri · Puan Durumu · Yayın Akışı{canli_rozet}</div>
<div class="alt-bilgi">Son güncelleme: {esc(tr_tarih(parse_utc(simdi)))} (İstanbul)</div>
</div></header>

<nav class="sekmeler">
<button class="aktif" data-sekme="hafta">📺 Haftanın Maçları</button>
<button data-sekme="ozetler">📋 Özetler</button>
<button data-sekme="fikstur">📅 Fikstür</button>
<button data-sekme="puan">🏆 Puan Durumu</button>
</nav>

<section class="sekme-icerik aktif" id="sekme-hafta">
<h2>Haftanın Maçları <small style="color:var(--soluk);font-weight:400">· {esc(tv_alt_baslik)}</small></h2>
{tv_html}
</section>

<section class="sekme-icerik" id="sekme-ozetler">
<h2>Son Maç Özetleri</h2>
<div class="grid2">{ozet_html}</div>
<h2>Yaklaşan Maçlar</h2>
<div class="grid2">{yaklasan_html}</div>
</section>

<section class="sekme-icerik" id="sekme-fikstur">
<h2>Sezon Fikstürü</h2>
<div class="cipsler">{cips_html}</div>
{"".join(hafta_bloklari)}
</section>

<section class="sekme-icerik" id="sekme-puan">
<h2>Puan Durumu</h2>
{puan_tablosu(puan)}
</section>

<footer>
{marka_html}
<div class="telif">© 2026 İnadına TV · Fixtoor</div>
</footer>
</div>
<script>{JS}</script>
</body>
</html>'''
    with open(cikti, "w", encoding="utf-8") as f:
        f.write(sayfa)
    log(f"HTML yazıldı: {cikti} ({len(sayfa) / 1024:.0f} KB)")


# ----------------------------------------------------------------------------
# Ana akış
# ----------------------------------------------------------------------------
def calistir(args) -> None:
    data_dir = args.data_dir
    os.makedirs(data_dir, exist_ok=True)

    if args.offline:
        log("offline mod: mevcut verilerden HTML üretiliyor")
        with open(os.path.join(data_dir, "site-verisi.json"), encoding="utf-8") as f:
            veri = json.load(f)
    else:
        lig = fetch_lig_bilgisi(args.league)
        log(f"lig: {lig['api_adi']} — sezon {lig['sezon_adi']}")
        olaylar = fetch_sezon_maclar(args.league, lig["baslangic"], lig["bitis"])
        maclar = [mac_ayristir(ev) for ev in olaylar]
        log(f"toplam {len(maclar)} maç ayrıştırıldı")

        # takım kaydı
        takimlar = {}
        for m in maclar:
            for t in (m["ev"], m["dep"]):
                takimlar[t["id"]] = {"ad": t["ad"], "kisa": t["kisa"], "logo": t["logo"], "renk": t["renk"]}

        # yayın kanalı bilgisi (Spor Ekranı / LiveSoccerTV + elle düzeltme dosyası)
        kanal_harita = fetch_yayin_kanallari(maclar, args.league, data_dir)
        for m in maclar:
            m["kanal"] = kanal_harita.get(
                _mac_anahtari(takim_norm(m["ev"]["ad"]), takim_norm(m["dep"]["ad"])), "")

        hafta_listesi = haftalara_ayir(maclar)
        haftalar = [
            {"no": i + 1, "maclar": sorted(h, key=lambda m: m["utc"])}
            for i, h in enumerate(hafta_listesi)
        ]
        log(f"{len(haftalar)} hafta oluşturuldu")

        puan = []
        try:
            puan = fetch_puan_durumu(args.league, lig["sezon_yili"])
            log(f"puan durumu: {len(puan)} takım")
        except Exception as e:  # puan durumu düşerse sayfa yine üretilsin
            log(f"UYARI: puan durumu alınamadı: {e}")

        simdi_dt = datetime.now(timezone.utc)
        ozetler = [
            m for m in maclar if m["durum"] == "post"
            and m["utc"] and parse_utc(m["utc"]) >= simdi_dt - timedelta(days=14)
        ]
        ozetler.sort(key=lambda m: m["utc"], reverse=True)

        veri = {
            "uretim": simdi_dt.isoformat(),
            "lig": lig,
            "takimlar": takimlar,
            "haftalar": [{"no": h["no"], "maclar": h["maclar"]} for h in haftalar],
            "puan_durumu": puan,
        }

        # --- veri dosyaları ---
        def yazdir(ad, icerik):
            yol = os.path.join(data_dir, ad)
            with open(yol, "w", encoding="utf-8") as f:
                json.dump(icerik, f, ensure_ascii=False, indent=1, sort_keys=True)
        yazdir("site-verisi.json", veri)
        yazdir("fikstur.json", veri["haftalar"])
        yazdir("puan-durumu.json", puan)
        yazdir("ozetler.json", ozetler[:16])
        yazdir("takimlar.json", takimlar)
        log(f"veri dosyaları yazıldı: {data_dir}/")

    render_html(veri, args.out)
    log("tamam ✅")


def main() -> None:
    p = argparse.ArgumentParser(description="Fixtoor — Süper Lig botu")
    p.add_argument("--league", default="tur.1", help="lig kodu (örn. tur.1, tur.2, eng.1)")
    p.add_argument("--data-dir", default="data", help="veri dosyalarının dizini")
    p.add_argument("--out", default="index.html", help="çıktı HTML dosyası")
    p.add_argument("--offline", action="store_true", help="ağ olmadan, mevcut veriden HTML üret")
    calistir(p.parse_args())


if __name__ == "__main__":
    main()

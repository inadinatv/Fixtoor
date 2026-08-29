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
    """UTC datetime -> 'Cum, 29 Ağu 19:00' (İstanbul saati)."""
    yerel = dt.astimezone(TR_TZ)
    metin = f"{GUNLER[yerel.weekday()][:3]}, {yerel.day} {AYLAR[yerel.month - 1]}"
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
body{background:var(--bg);color:var(--metin);font:15px/1.55 -apple-system,'Segoe UI',Roboto,Arial,sans-serif}
.kapsayici{max-width:960px;margin:0 auto;padding:20px 16px 60px}
header.ust{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:6px}
header.ust img{width:52px;height:52px}
h1{font-size:26px;letter-spacing:.3px}
h1 span{color:var(--yesil)}
.alt-bilgi{color:var(--soluk);font-size:13px;margin-bottom:18px}
.canli{background:var(--kirmizi);color:#fff;font-size:11px;font-weight:700;padding:2px 8px;
border-radius:99px;animation:nabiz 1.2s infinite}
@keyframes nabiz{50%{opacity:.55}}
nav.sekmeler{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 20px}
nav.sekmeler button{background:var(--kart);color:var(--soluk);border:1px solid var(--cizgi);
padding:9px 16px;border-radius:10px;cursor:pointer;font-size:14px;font-weight:600}
nav.sekmeler button.aktif{background:var(--yesil);color:#06220f;border-color:var(--yesil)}
html.js .sekme-icerik{display:none}
html.js .sekme-icerik.aktif{display:block}
h2{font-size:19px;margin:22px 0 12px;display:flex;align-items:center;gap:8px}
h2::before{content:'';width:4px;height:18px;background:var(--yesil);border-radius:2px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:14px;padding:14px 16px;margin-bottom:12px}
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
table.puan .takim-hucre{display:flex;align-items:center;gap:9px;min-width:0}
table.puan .takim-hucre img{width:22px;height:22px;object-fit:contain}
table.puan .puan{font-weight:800;font-size:15px}
.nokta{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
footer{margin-top:36px;color:var(--soluk);font-size:12.5px;text-align:center;line-height:1.9}
footer a{color:var(--mavi);text-decoration:none}
.grid2{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:720px){.grid2{grid-template-columns:1fr 1fr}}
.bos{color:var(--soluk);padding:26px;text-align:center;background:var(--kart);
border:1px dashed var(--cizgi);border-radius:14px}
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
        durum_html = esc(m.get("durum_metin") or "")

    yer = " · ".join(x for x in [m.get("stadyum"), m.get("sehir")] if x)
    return f'''<div class="kart"><div class="mac">
  {takim_logolu(ev)}
  <div class="skor{" onaylanmadi" if not (oynandi or canli) else ""}">{skor_html}</div>
  {takim_logolu(dep, dep=True)}
</div>
<div class="mac-alt"><span>{esc(tr_tarih(parse_utc(m["utc"]))) if m["utc"] else ""}</span>
<span>{durum_html}{" · " if durum_html and yer else ""}{esc(yer)}</span></div></div>'''


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
<span class="durum-ms">{esc(m.get("durum_metin") or "MS")}{(" · " + esc(m["stadyum"])) if m.get("stadyum") else ""}</span></div>
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
    "Relegation": "Küme düşme",
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

    logo_html = f'<img src="{esc(lig["logo"])}" alt="lig logosu">' if lig.get("logo") else ""
    canli_rozet = ' <span class="canli">CANLI</span>' if canli_var else ""
    sayfa = f'''<!DOCTYPE html>
<html lang="tr" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{esc(lig["ad"])} fikstürü, maç özetleri ve puan durumu — Fixtoor Bot">
<title>Fixtoor · {esc(lig["ad"])} {esc(lig.get("sezon_adi", ""))}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<style>{CSS}</style>
</head>
<body>
<div class="kapsayici">
<header class="ust">{logo_html}
<div><h1>Fix<span>toor</span> ⚽ {esc(lig["ad"])}</h1>
<div class="alt-bilgi">{esc(lig.get("sezon_adi", ""))} · Fikstür · Maç Özetleri · Puan Durumu{canli_rozet}</div>
<div class="alt-bilgi">Son güncelleme: {esc(tr_tarih(parse_utc(simdi)))} (İstanbul) · Veri: ESPN API</div>
</div></header>

<nav class="sekmeler">
<button class="aktif" data-sekme="ozetler">📋 Özetler</button>
<button data-sekme="fikstur">📅 Fikstür</button>
<button data-sekme="puan">🏆 Puan Durumu</button>
</nav>

<section class="sekme-icerik aktif" id="sekme-ozetler">
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
Fixtoor Bot tarafından <a href="https://github.com/inadinatv/Fixtoor">inadinatv/Fixtoor</a>
deposunda otomatik üretildi · Veriler <a href="https://www.espn.com/soccer/league/_/name/tur.1">ESPN</a>'den alınmıştır<br>
<a href="data/fikstur.json">fikstur.json</a> · <a href="data/puan-durumu.json">puan-durumu.json</a> ·
<a href="data/ozetler.json">ozetler.json</a>
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Maç istatistikleri: ESPN yanıtını normalize eder, 0 ile 'veri yok' ayrımını korur.

Frontend her zaman şu yapıyı görür:

    {
      "possession": {"home": 55.0, "away": 45.0},   # yoksa None
      "shots": {"home": 10, "away": 7},
      "shotsOnTarget": {"home": 4, "away": 3},
      "corners": {"home": 6, "away": 2},
      "fouls": {"home": 11, "away": 14},
      "kaynak": "summary" | "scoreboard" | None,
      "durum": "ok" | "yok" | "hata",
    }

Eksik alan asla 0'a çevrilmez. API gerçekten 0 döndürdüyse 0 kalır.
"""

from __future__ import annotations

import re
from typing import Any, Optional

ISTATISTIK_ALANLARI = ("possession", "shots", "shotsOnTarget", "corners", "fouls")

ISTATISTIK_ETIKET = {
    "possession": ("Topla oynama", True),
    "shots": ("Şut", False),
    "shotsOnTarget": ("İsabetli şut", False),
    "corners": ("Korner", False),
    "fouls": ("Faul", False),
}

# ESPN ve benzeri kaynaklardaki isim çeşitleri (normalize edilmiş, alfanümerik)
ISTATISTIK_ANAHTARLAR = {
    "possession": (
        "possessionpct", "possession", "ballpossession", "ballpossessionpct",
        "possessionpercentage", "ballpossessionpercentage", "poss", "pos",
        "possessionpercent", "ballpossessionpercent", "toplaoynama",
    ),
    "shots": (
        "totalshots", "shotstotal", "shots", "totalshot", "shot",
        "attempts", "totalattempts", "shotsattempts", "totalattemptsontargetofftarget",
        "sut",
    ),
    "shotsOnTarget": (
        "shotsontarget", "shotsongoal", "ontarget", "shotstarget",
        "shotsongoaltarget", "shotsonbar", "sog", "sot", "isabetlisut",
    ),
    "corners": (
        "woncorners", "cornerkicks", "corners", "corner", "cornerswon",
        "cornerkick", "korner",
    ),
    "fouls": (
        "foulscommitted", "fouls", "totalfouls", "foul", "faul",
        "foulsagainst",
    ),
}

_BOS_METIN = {"", "-", "—", "–", "n/a", "na", "null", "none", "undefined", "nil"}


def _ist_anahtar(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").casefold())


def _ist_sayi(val: Any) -> Optional[float]:
    """API değerini sayıya çevirir. Yoksa None — asla varsayılan 0 üretmez."""
    if val is None or val is False or val is True:
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, bool):
            return None
        if val != val:  # NaN
            return None
        return float(val)
    s = str(val).strip()
    if not s or s.casefold() in _BOS_METIN:
        return None
    s = s.replace("%", "").replace("\u00a0", " ").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None


def _ist_goster_sayi(val: Optional[float]) -> Optional[str]:
    if val is None:
        return None
    if abs(val - round(val)) < 0.05:
        return str(int(round(val)))
    return f"{val:.1f}"


def istatistik_bos_yapi(kaynak: Optional[str] = None, durum: str = "yok") -> dict:
    out = {k: {"home": None, "away": None} for k in ISTATISTIK_ALANLARI}
    out["kaynak"] = kaynak
    out["durum"] = durum
    return out


def istatistik_listeden_harita(istat: Any) -> dict:
    """ESPN statistics dizisi / iç içe yapı / düz sözlük -> {ad: değer}."""
    sonuc: dict = {}
    if not istat:
        return sonuc
    if isinstance(istat, dict):
        splits = istat.get("splits")
        if isinstance(splits, dict):
            for cat in splits.get("categories") or []:
                if isinstance(cat, dict):
                    sonuc.update(istatistik_listeden_harita(cat.get("stats") or []))
            return sonuc
        if isinstance(istat.get("stats"), list) or isinstance(istat.get("statistics"), list):
            sonuc.update(istatistik_listeden_harita(istat.get("stats") or istat.get("statistics")))
            return sonuc
        for k, v in istat.items():
            if k in ("splits", "stats", "statistics", "team", "name", "keys",
                     "labels", "displayNames", "descriptions", "abbreviations"):
                continue
            if isinstance(v, (dict, list)):
                continue
            sonuc[str(k)] = v
        return sonuc
    if not isinstance(istat, list):
        return sonuc
    for s in istat:
        if not isinstance(s, dict):
            continue
        alt = s.get("stats") if isinstance(s.get("stats"), list) else None
        if alt is None and isinstance(s.get("statistics"), list):
            alt = s.get("statistics")
        if alt:
            sonuc.update(istatistik_listeden_harita(alt))
            continue
        deger = s.get("displayValue")
        if deger is None:
            deger = s.get("value")
        for ad in (s.get("name"), s.get("abbreviation"), s.get("displayName"),
                   s.get("label"), s.get("shortDisplayName")):
            if ad and str(ad) not in sonuc:
                sonuc[str(ad)] = deger
    return sonuc


def istatistik_normalize(ham: Any) -> dict:
    """Çeşitli alan adlarını standart anahtarlara map eder. Eksik = None."""
    ham = ham or {}
    if not isinstance(ham, dict):
        ham = istatistik_listeden_harita(ham)
    indeks = {}
    for k, v in ham.items():
        nk = _ist_anahtar(k)
        if nk and nk not in indeks:
            indeks[nk] = v
    out = {}
    for hedef, adaylar in ISTATISTIK_ANAHTARLAR.items():
        val = None
        for a in adaylar:
            if a in indeks and indeks[a] is not None and indeks[a] != "":
                val = _ist_sayi(indeks[a])
                break
        out[hedef] = val
    return out


def istatistik_standart(ev_ham: Any, dep_ham: Any,
                       kaynak: Optional[str] = None, durum: str = "ok") -> dict:
    ev = istatistik_normalize(ev_ham)
    dep = istatistik_normalize(dep_ham)
    out = istatistik_bos_yapi(kaynak, durum)
    for k in ISTATISTIK_ALANLARI:
        out[k] = {"home": ev.get(k), "away": dep.get(k)}
    if istatistik_hepsi_bos_mu(out):
        out["durum"] = "yok"
    return out


def istatistik_hepsi_bos_mu(st: Optional[dict]) -> bool:
    """Hiçbir alanda sayı yok (None). 0 dolu alan 'bos' sayılmaz."""
    if not isinstance(st, dict):
        return True
    for k in ISTATISTIK_ALANLARI:
        cift = st.get(k) or {}
        if not isinstance(cift, dict):
            continue
        if cift.get("home") is not None or cift.get("away") is not None:
            return False
    return True


def istatistik_sablon_sifir_mi(st: Optional[dict]) -> bool:
    """Scoreboard 'stub': bütün alanlar 0 veya boş — gerçek maç istatistiği değil."""
    if not isinstance(st, dict):
        return True
    for k in ISTATISTIK_ALANLARI:
        cift = st.get(k) or {}
        if not isinstance(cift, dict):
            continue
        for taraf in ("home", "away"):
            v = cift.get(taraf)
            if v is None:
                continue
            try:
                if float(v) != 0:
                    return False
            except (TypeError, ValueError):
                return False
    return True


def istatistik_kismi_var_mi(st: Optional[dict]) -> bool:
    if not isinstance(st, dict):
        return False
    return any(
        isinstance(st.get(k), dict) and (
            (st[k].get("home") is not None) or (st[k].get("away") is not None)
        )
        for k in ISTATISTIK_ALANLARI
    )


def ozetten_rakip_istatistik(data: Any) -> tuple:
    """ESPN summary JSON -> (ev_ham, dep_ham, meta). Takım id / homeAway ile eşler."""
    if not isinstance(data, dict):
        return {}, {}, {}
    header = data.get("header") or {}
    comps = header.get("competitions") or []
    comp = comps[0] if comps else {}
    durum = ((comp.get("status") or data.get("header") or {}).get("type")
             if False else ((comp.get("status") or {}).get("type") or {}))
    if not isinstance(durum, dict):
        durum = {}
    meta = {
        "durum": durum.get("state") or "",
        "durum_metin": durum.get("shortDetail") or durum.get("detail") or "",
        "durum_ad": durum.get("name") or "",
        "saat": (comp.get("status") or {}).get("displayClock") or "",
        "id": str(header.get("id") or comp.get("id") or ""),
    }
    home_id, away_id = "", ""
    header_ist = {"home": {}, "away": {}}
    for t in comp.get("competitors") or []:
        if not isinstance(t, dict):
            continue
        tid = str((t.get("team") or {}).get("id") or t.get("id") or "")
        ham = istatistik_listeden_harita(t.get("statistics") or [])
        if t.get("homeAway") == "home":
            home_id = tid
            header_ist["home"] = ham
        else:
            away_id = tid
            header_ist["away"] = ham

    box = data.get("boxscore") or {}
    ev_ham, dep_ham = {}, {}
    teams = box.get("teams") if isinstance(box, dict) else None
    for t in teams or []:
        if not isinstance(t, dict):
            continue
        team = t.get("team") or {}
        tid = str(team.get("id") or "")
        ham = istatistik_listeden_harita(t.get("statistics") or [])
        ha = t.get("homeAway")
        if ha == "home" or (home_id and tid == home_id):
            ev_ham = ham
        elif ha == "away" or (away_id and tid == away_id):
            dep_ham = ham

    if not ev_ham:
        ev_ham = header_ist["home"]
    if not dep_ham:
        dep_ham = header_ist["away"]
    return ev_ham, dep_ham, meta


def _cift_oku(cift: Any) -> dict:
    if not isinstance(cift, dict):
        return {"home": None, "away": None}
    return {"home": _ist_sayi(cift.get("home")), "away": _ist_sayi(cift.get("away"))}


def mac_istatistik_al(m: Optional[dict]) -> dict:
    """Maç sözlüğünden standart istatistik üretir.

    Scoreboard'dan gelen 0-0-0-0-0 şablonunu gerçek veri saymaz (durum='yok').
    Summary kaynağındaki gerçek 0 değerleri korunur.
    """
    m = m or {}
    st = m.get("istatistik")
    if isinstance(st, dict) and any(k in st for k in ISTATISTIK_ALANLARI):
        out = istatistik_bos_yapi(st.get("kaynak"), st.get("durum") or "ok")
        for k in ISTATISTIK_ALANLARI:
            out[k] = _cift_oku(st.get(k))
        kaynak = out.get("kaynak")
        if kaynak != "summary" and istatistik_sablon_sifir_mi(out):
            return istatistik_bos_yapi(kaynak, "yok")
        if istatistik_hepsi_bos_mu(out):
            out["durum"] = "yok"
        elif not out.get("durum"):
            out["durum"] = "ok"
        return out
    ev_ham = (m.get("ev") or {}).get("istatistik") or {}
    dep_ham = (m.get("dep") or {}).get("istatistik") or {}
    out = istatistik_standart(ev_ham, dep_ham, kaynak="scoreboard", durum="ok")
    if istatistik_sablon_sifir_mi(out):
        return istatistik_bos_yapi("scoreboard", "yok")
    return out


def takim_istatistik_yaz(m: dict, st: dict) -> None:
    """Standart yapıyı ev/dep.istatistik ESPN adlarıyla da yazar (eski okuyucular)."""
    isim = {
        "possession": "possessionPct",
        "shots": "totalShots",
        "shotsOnTarget": "shotsOnTarget",
        "corners": "wonCorners",
        "fouls": "foulsCommitted",
    }
    for taraf, key in (("ev", "home"), ("dep", "away")):
        if taraf not in m or not isinstance(m[taraf], dict):
            continue
        ham = dict(m[taraf].get("istatistik") or {})
        for std, espn in isim.items():
            val = (st.get(std) or {}).get(key)
            if val is None:
                ham.pop(espn, None)
            else:
                ham[espn] = _ist_goster_sayi(val)
        m[taraf]["istatistik"] = ham


def mac_ertelendi_mi(durum_ad: Any, durum_metin: Any = "") -> bool:
    n = f"{durum_ad or ''} {durum_metin or ''}".casefold()
    return any(x in n for x in ("postpon", "cancel", "abandon", "ertele", "iptal"))


def mac_canli_mi(durum: Any, durum_ad: Any = "", durum_metin: Any = "") -> bool:
    if mac_ertelendi_mi(durum_ad, durum_metin):
        return False
    d = str(durum or "").casefold()
    if d == "in":
        return True
    kisa = str(durum_metin or "").strip().upper()
    return kisa in {"LIVE", "1H", "HT", "2H", "ET", "PEN", "P"}


def mac_polling_dursun_mu(durum: Any, durum_ad: Any = "", durum_metin: Any = "") -> bool:
    if mac_ertelendi_mi(durum_ad, durum_metin):
        return True
    d = str(durum or "").casefold()
    kisa = str(durum_metin or "").strip().upper()
    if d == "post" or kisa in {"FT", "AET", "FT-PEN", "FINAL"}:
        return True
    return False


def bar_genislikleri(ev: Optional[float], dep: Optional[float]) -> tuple:
    """İki taraf da sayıysa oransal genişlik; veri yoksa (0, 0) — %50-%50 uydurma."""
    if ev is None or dep is None:
        return 0, 0
    toplam = ev + dep
    if toplam > 0:
        ev_w = int(round(ev / toplam * 100))
        return ev_w, 100 - ev_w
    return 0, 0

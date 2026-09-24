#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""İstatistik normalizasyonu ve 0 / 'veri yok' ayrımı testleri."""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Testler çevrimdışı ve hızlı kalmalı: ağ tanısı taraması ve istatistik
# istekleri arasındaki nezaket beklemeleri test ortamında atlanır.
os.environ.setdefault("FIXTOOR_TEST", "1")
os.environ.setdefault("FIXTOOR_TANI", "0")

import istatistik as ist  # noqa: E402
import fiktoor  # noqa: E402


SUMMARY_ORNEK = {
    "header": {
        "id": "401888300",
        "competitions": [{
            "id": "401888300",
            "status": {
                "displayClock": "90'+4'",
                "type": {"state": "post", "shortDetail": "FT", "name": "STATUS_FULL_TIME"},
            },
            "competitors": [
                {"homeAway": "home", "id": "995", "score": "1",
                 "team": {"id": "995", "displayName": "Kocaelispor"}},
                {"homeAway": "away", "id": "11429", "score": "0",
                 "team": {"id": "11429", "displayName": "Samsunspor"}},
            ],
        }],
    },
    "boxscore": {
        "teams": [
            {
                "team": {"id": "995", "displayName": "Kocaelispor"},
                "homeAway": "home",
                "statistics": [
                    {"name": "possessionPct", "displayValue": "48.2", "label": "Possession"},
                    {"name": "totalShots", "displayValue": "9", "label": "Shots"},
                    {"name": "shotsOnTarget", "displayValue": "3", "label": "Shots on Goal"},
                    {"name": "wonCorners", "displayValue": "4", "label": "Corner Kicks"},
                    {"name": "foulsCommitted", "displayValue": "12", "label": "Fouls"},
                ],
            },
            {
                "team": {"id": "11429"},
                "homeAway": "away",
                "statistics": [
                    {"name": "possessionPct", "displayValue": "51.8%", "label": "Ball Possession"},
                    {"name": "shotsTotal", "displayValue": "11", "label": "Total Shots"},
                    {"name": "shotsOnGoal", "displayValue": "2", "label": "On Target"},
                    {"name": "cornerKicks", "displayValue": "5", "label": "Corners"},
                    {"name": "fouls", "displayValue": "14", "label": "Total Fouls"},
                ],
            },
        ]
    },
}

SCOREBOARD_STUB = {
    "appearances": "0",
    "foulsCommitted": "0",
    "goalAssists": "0",
    "possessionPct": "0",
    "shotAssists": "0",
    "shotsOnTarget": "0",
    "totalGoals": "1",
    "totalShots": "0",
    "wonCorners": "0",
}


class SayiAyiklama(unittest.TestCase):
    def test_yuzde_string(self):
        self.assertEqual(ist._ist_sayi("56%"), 56.0)
        self.assertEqual(ist._ist_sayi("44.3%"), 44.3)

    def test_bos_none_kalir(self):
        for v in (None, "", "-", "—", "N/A", "null"):
            self.assertIsNone(ist._ist_sayi(v), msg=repr(v))

    def test_sifir_sifirdir(self):
        self.assertEqual(ist._ist_sayi("0"), 0.0)
        self.assertEqual(ist._ist_sayi(0), 0.0)
        self.assertEqual(ist._ist_sayi("0%"), 0.0)

    def test_or_sifir_kullanilmaz(self):
        self.assertIsNone(ist._ist_sayi(None))
        self.assertNotEqual(ist._ist_sayi(None) or 0, "gerçek veri")


class EsnekEsleme(unittest.TestCase):
    def test_farkli_isimler(self):
        ham = {
            "Ball Possession %": "56%",
            "Total Shots": 10,
            "Shots on Target": "4",
            "Corner Kicks": "6",
            "Fouls": 11,
        }
        n = ist.istatistik_normalize(ham)
        self.assertEqual(n["possession"], 56.0)
        self.assertEqual(n["shots"], 10.0)
        self.assertEqual(n["shotsOnTarget"], 4.0)
        self.assertEqual(n["corners"], 6.0)
        self.assertEqual(n["fouls"], 11.0)

    def test_espn_name_alanlari(self):
        n = ist.istatistik_normalize({
            "possessionPct": "64.4",
            "totalShots": "38",
            "shotsOnTarget": "13",
            "wonCorners": "8",
            "foulsCommitted": "11",
        })
        self.assertEqual(n["possession"], 64.4)
        self.assertEqual(n["shots"], 38.0)

    def test_eksik_alan_none(self):
        n = ist.istatistik_normalize({"totalShots": "5"})
        self.assertEqual(n["shots"], 5.0)
        self.assertIsNone(n["possession"])
        self.assertIsNone(n["fouls"])


class ListeHarita(unittest.TestCase):
    def test_ic_ice_stats(self):
        ham = [{
            "name": "team",
            "stats": [
                {"name": "possessionPct", "displayValue": "40.1"},
                {"name": "totalShots", "value": 17},
            ],
        }]
        h = ist.istatistik_listeden_harita(ham)
        self.assertEqual(h["possessionPct"], "40.1")
        self.assertEqual(h["totalShots"], 17)

    def test_splits_kategorileri(self):
        ham = {
            "splits": {
                "categories": [{
                    "name": "offensive",
                    "stats": [{"name": "wonCorners", "displayValue": "2"}],
                }]
            }
        }
        h = ist.istatistik_listeden_harita(ham)
        self.assertEqual(h["wonCorners"], "2")


class SummaryParse(unittest.TestCase):
    def test_home_away_id_ile(self):
        ev, dep, meta = ist.ozetten_rakip_istatistik(SUMMARY_ORNEK)
        st = ist.istatistik_standart(ev, dep, kaynak="summary")
        self.assertEqual(st["possession"]["home"], 48.2)
        self.assertEqual(st["possession"]["away"], 51.8)
        self.assertEqual(st["shots"]["home"], 9.0)
        self.assertEqual(st["shots"]["away"], 11.0)
        self.assertEqual(st["shotsOnTarget"]["home"], 3.0)
        self.assertEqual(st["corners"]["away"], 5.0)
        self.assertEqual(st["fouls"]["home"], 12.0)
        self.assertEqual(meta["durum"], "post")
        self.assertEqual(meta["id"], "401888300")
        self.assertEqual(st["kaynak"], "summary")
        self.assertEqual(st["durum"], "ok")

    def test_takim_id_karismaz(self):
        # boxscore sırası ters: önce away
        data = {
            "header": SUMMARY_ORNEK["header"],
            "boxscore": {"teams": list(reversed(SUMMARY_ORNEK["boxscore"]["teams"]))},
        }
        ev, dep, _ = ist.ozetten_rakip_istatistik(data)
        st = ist.istatistik_standart(ev, dep)
        self.assertEqual(st["shots"]["home"], 9.0)
        self.assertEqual(st["shots"]["away"], 11.0)

    def test_bos_summary(self):
        ev, dep, _ = ist.ozetten_rakip_istatistik({"boxscore": {"teams": []}, "header": {}})
        st = ist.istatistik_standart(ev, dep, kaynak="summary")
        self.assertTrue(ist.istatistik_hepsi_bos_mu(st))
        self.assertEqual(st["durum"], "yok")

    def test_null_malformed(self):
        ev, dep, _ = ist.ozetten_rakip_istatistik(None)
        self.assertEqual(ev, {})
        ev, dep, _ = ist.ozetten_rakip_istatistik("nope")
        self.assertEqual(dep, {})


class SifirVeYok(unittest.TestCase):
    def test_scoreboard_stub_yok_sayilir(self):
        m = {
            "ev": {"istatistik": SCOREBOARD_STUB},
            "dep": {"istatistik": dict(SCOREBOARD_STUB, totalGoals="0")},
        }
        st = ist.mac_istatistik_al(m)
        self.assertTrue(ist.istatistik_hepsi_bos_mu(st))
        self.assertEqual(st["durum"], "yok")
        self.assertIsNone(st["possession"]["home"])
        self.assertIsNone(st["shots"]["away"])

    def test_summary_gercek_sifir_korunur(self):
        st = ist.istatistik_bos_yapi("summary", "ok")
        st["shots"] = {"home": 6.0, "away": 15.0}
        st["shotsOnTarget"] = {"home": 0.0, "away": 7.0}
        st["possession"] = {"home": 58.2, "away": 41.8}
        st["corners"] = {"home": 1.0, "away": 6.0}
        st["fouls"] = {"home": 13.0, "away": 18.0}
        m = {"istatistik": st}
        al = ist.mac_istatistik_al(m)
        self.assertEqual(al["shotsOnTarget"]["home"], 0.0)
        self.assertEqual(al["shotsOnTarget"]["away"], 7.0)
        self.assertEqual(al["durum"], "ok")

    def test_summary_tamamen_sifir_stub_sayilir(self):
        st = ist.istatistik_bos_yapi("summary", "ok")
        for alan in ist.ISTATISTIK_ALANLARI:
            st[alan] = {"home": 0.0, "away": 0.0}
        sonuc = ist.mac_istatistik_al({"istatistik": st})
        self.assertTrue(ist.istatistik_hepsi_bos_mu(sonuc))
        self.assertEqual(sonuc["durum"], "yok")

    def test_kismi_istatistik(self):
        st = ist.istatistik_standart(
            {"possessionPct": "60", "totalShots": "8"},
            {"possessionPct": "40", "totalShots": "5"},
            kaynak="summary",
        )
        self.assertEqual(st["possession"]["home"], 60.0)
        self.assertEqual(st["shots"]["away"], 5.0)
        self.assertIsNone(st["fouls"]["home"])
        self.assertIsNone(st["corners"]["away"])
        self.assertFalse(ist.istatistik_hepsi_bos_mu(st))

    def test_sahte_veri_uretilmez(self):
        st = ist.istatistik_normalize({})
        self.assertIsNone(st["possession"])
        self.assertIsNone(st["shots"])


class PollingKurallari(unittest.TestCase):
    def test_canli_durumlar(self):
        self.assertTrue(ist.mac_canli_mi("in", "", "1H"))
        self.assertTrue(ist.mac_canli_mi("in", "", "HT"))
        self.assertTrue(ist.mac_canli_mi("in", "", "2H"))
        self.assertTrue(ist.mac_canli_mi("in", "", "ET"))
        self.assertFalse(ist.mac_canli_mi("pre"))
        self.assertFalse(ist.mac_canli_mi("post", "", "FT"))

    def test_bitince_dur(self):
        self.assertTrue(ist.mac_polling_dursun_mu("post", "", "FT"))
        self.assertFalse(ist.mac_polling_dursun_mu("in", "", "2H"))

    def test_erteleme(self):
        self.assertTrue(ist.mac_ertelendi_mi("STATUS_POSTPONED"))
        self.assertTrue(ist.mac_polling_dursun_mu("pre", "STATUS_POSTPONED"))
        self.assertFalse(ist.mac_canli_mi("in", "STATUS_POSTPONED"))

    def test_baslamamis(self):
        self.assertFalse(ist.mac_canli_mi("pre", "", "20:00"))
        self.assertFalse(ist.mac_polling_dursun_mu("pre"))


class BarGenislik(unittest.TestCase):
    def test_oran(self):
        self.assertEqual(ist.bar_genislikleri(60, 40), (60, 40))
        self.assertEqual(ist.bar_genislikleri(0, 0), (0, 0))

    def test_veri_yokken_elli_elli_yok(self):
        self.assertEqual(ist.bar_genislikleri(None, None), (0, 0))
        self.assertEqual(ist.bar_genislikleri(55, None), (0, 0))


class HtmlCikti(unittest.TestCase):
    def test_stub_em_dash(self):
        m = {
            "id": "401888300",
            "utc": "2026-09-06T17:00Z",
            "durum": "post",
            "durum_metin": "FT",
            "stadyum": "Test",
            "goller": [],
            "kirmizi_kartlar": [],
            "ev": {"id": "1", "ad": "Ev", "istatistik": SCOREBOARD_STUB, "skor": "1"},
            "dep": {"id": "2", "ad": "Dep", "istatistik": SCOREBOARD_STUB, "skor": "0"},
        }
        html = fiktoor.ozet_karti(m)
        self.assertIn("data-mac-id=\"401888300\"", html)
        self.assertIn("data-ist-kok", html)
        self.assertIn("data-ist-durum=\"yok\"", html)
        self.assertIn("—", html)
        self.assertNotIn(">0%<", html)
        self.assertIn("Topla oynama", html)

    def test_gercek_degerler(self):
        m = {
            "id": "x",
            "utc": "2026-08-31T18:30Z",
            "durum": "post",
            "durum_metin": "FT",
            "stadyum": "Park",
            "goller": [],
            "kirmizi_kartlar": [],
            "istatistik": {
                "kaynak": "summary", "durum": "ok",
                "possession": {"home": 40.1, "away": 59.9},
                "shots": {"home": 17, "away": 8},
                "shotsOnTarget": {"home": 7, "away": 5},
                "corners": {"home": 2, "away": 5},
                "fouls": {"home": 18, "away": 10},
            },
            "ev": {"id": "1", "ad": "Amed", "skor": "2"},
            "dep": {"id": "2", "ad": "Trabzon", "skor": "1"},
        }
        html = fiktoor.ozet_karti(m)
        self.assertIn("40.1%", html)
        self.assertIn("59.9%", html)
        self.assertIn(">17<", html)
        self.assertIn("data-ist=\"possession\"", html)

    def test_canli_kart(self):
        m = {
            "id": "live1",
            "utc": "2026-09-07T17:00Z",
            "durum": "in",
            "durum_metin": "2H",
            "saat_gostergesi": "67'",
            "stadyum": "Stadyum",
            "goller": [],
            "kirmizi_kartlar": [],
            "istatistik": ist.istatistik_bos_yapi(None, "yok"),
            "ev": {"id": "1", "ad": "Rize", "skor": "0"},
            "dep": {"id": "2", "ad": "Alanya", "skor": "0"},
        }
        html = fiktoor.ozet_karti(m)
        self.assertIn("CANLI", html)
        self.assertTrue("67'" in html or "67&#x27;" in html)
        self.assertIn("data-ist-durum=\"yok\"", html)


class HttpHataYol(unittest.TestCase):
    def test_fetch_summary_404_none(self):
        cagrilar = []

        def fake_http(url, zorunlu=True, timeout=25):
            cagrilar.append(url)
            return None

        data = fiktoor.fetch_mac_summary("tur.1", "999", http=fake_http)
        self.assertIsNone(data)
        self.assertGreaterEqual(len(cagrilar), 2)
        self.assertIn("/summary?event=999", cagrilar[0])

    def test_doldur_hata_uygulamayi_kilitlemez(self):
        maclar = [{
            "id": "401",
            "durum": "in",
            "durum_metin": "1H",
            "utc": "2026-09-07T17:00Z",
            "ev": {"id": "1", "ad": "A", "istatistik": {}},
            "dep": {"id": "2", "ad": "B", "istatistik": {}},
        }]

        def fake_http(url, zorunlu=True, timeout=25):
            raise RuntimeError("timeout")

        # monkeypatch
        eski = fiktoor.http_get_json
        try:
            fiktoor.http_get_json = fake_http  # type: ignore
            fiktoor.mac_istatistiklerini_doldur("tur.1", maclar, "/tmp")
        finally:
            fiktoor.http_get_json = eski
        self.assertIn("istatistik", maclar[0])
        self.assertTrue(ist.istatistik_hepsi_bos_mu(maclar[0]["istatistik"]))


class BotGuvenilirlik(unittest.TestCase):
    def test_espn_ikincil_host_denenir(self):
        cagrilar = []
        eski = fiktoor.http_get_json

        def fake_http(url, zorunlu=False, timeout=25):
            cagrilar.append(url)
            if "site.api.espn.com" in url:
                return None
            return {
                "leagues": [{
                    "slug": "tur.1",
                    "name": "Turkish Super Lig",
                    "season": {
                        "year": 2026,
                        "displayName": "2026-27 Turkish Super Lig",
                        "startDate": "2026-07-01T04:00Z",
                        "endDate": "2027-07-01T03:59Z",
                    },
                }]
            }

        try:
            fiktoor.http_get_json = fake_http  # type: ignore
            lig = fiktoor.fetch_lig_bilgisi("tur.1")
        finally:
            fiktoor.http_get_json = eski
        self.assertEqual(lig["sezon_yili"], 2026)
        self.assertEqual(len(cagrilar), 2)
        self.assertIn("site.web.api.espn.com", cagrilar[1])

    def test_atomik_json_yazimi(self):
        with tempfile.TemporaryDirectory() as td:
            yol = os.path.join(td, "veri.json")
            fiktoor.json_yaz_atomik(yol, {"ok": True, "deger": "çalışıyor"})
            with open(yol, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["ok"], True)
            self.assertEqual(
                [ad for ad in os.listdir(td) if ad.endswith(".tmp")], []
            )

    def test_gecerli_onbellek_api_hatasinda_kullanilir(self):
        cache = {
            "uretim": "2026-09-16T12:00:00+00:00",
            "lig": {"slug": "tur.1", "ad": "Trendyol Süper Lig"},
            "takimlar": {},
            "haftalar": [{
                "no": 1,
                "maclar": [{
                    "id": "1",
                    "utc": "2026-09-01T17:00:00Z",
                    "durum": "post",
                    "ev": {"id": "10", "ad": "Ev"},
                    "dep": {"id": "20", "ad": "Dep"},
                }],
            }],
            "puan_durumu": [],
        }
        with tempfile.TemporaryDirectory() as td:
            fiktoor.json_yaz_atomik(os.path.join(td, "site-verisi.json"), cache)
            eski_uret = fiktoor._veri_yeni_uret
            eski_render = fiktoor.render_html
            gorulen = []
            try:
                def patlayan_uret(*args, **kwargs):
                    raise RuntimeError("ESPN kapalı")

                fiktoor._veri_yeni_uret = patlayan_uret  # type: ignore
                fiktoor.render_html = lambda veri, out: gorulen.append(veri)  # type: ignore
                fiktoor.calistir(SimpleNamespace(
                    data_dir=td, out=os.path.join(td, "index.html"),
                    league="tur.1", offline=False, strict=False,
                ))
            finally:
                fiktoor._veri_yeni_uret = eski_uret
                fiktoor.render_html = eski_render
            self.assertEqual(gorulen, [cache])

    def test_strict_api_hatasini_gizlemez(self):
        eski_uret = fiktoor._veri_yeni_uret
        try:
            fiktoor._veri_yeni_uret = lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("ESPN kapalı")
            )  # type: ignore
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(RuntimeError):
                    fiktoor.calistir(SimpleNamespace(
                        data_dir=td, out=os.path.join(td, "index.html"),
                        league="tur.1", offline=False, strict=True,
                    ))
        finally:
            fiktoor._veri_yeni_uret = eski_uret


class CanliYenileme(unittest.TestCase):
    def _paket(self):
        mac = {
            "id": "live-1",
            "utc": "2026-09-19T17:00:00Z",
            "durum": "pre",
            "durum_metin": "Scheduled",
            "durum_ad": "STATUS_SCHEDULED",
            "saat_gostergesi": "",
            "ev": {"id": "1", "ad": "Ev", "kisa": "EV", "logo": "", "skor": "0",
                   "istatistik": {}},
            "dep": {"id": "2", "ad": "Dep", "kisa": "DEP", "logo": "", "skor": "0",
                    "istatistik": {}},
            "stadyum": "Test",
            "sehir": "",
            "goller": [], "kirmizi_kartlar": [], "sari_kartlar": [],
            "kanal": "beIN Sports 1",
        }
        return {
            "uretim": "2026-09-19T16:00:00+00:00",
            "lig": {"slug": "tur.1", "ad": "Lig"},
            "takimlar": {
                "1": {"ad": "Ev", "kisa": "EV", "logo": "", "renk": "#353a40"},
                "2": {"ad": "Dep", "kisa": "DEP", "logo": "", "renk": "#353a40"},
            },
            "haftalar": [{"no": 1, "maclar": [mac]}],
            "puan_durumu": [],
        }

    def test_canli_skor_degisimini_birlestirir_ve_kanali_korur(self):
        eski = self._paket()
        yeni = fiktoor.copy.deepcopy(eski)
        yeni["haftalar"][0]["maclar"][0]["durum"] = "in"
        yeni["haftalar"][0]["maclar"][0]["durum_metin"] = "1H"
        yeni["haftalar"][0]["maclar"][0]["saat_gostergesi"] = "23'"
        yeni["haftalar"][0]["maclar"][0]["ev"]["skor"] = "1"
        yeni["haftalar"][0]["maclar"][0]["dep"]["skor"] = "0"
        eski_fetch = fiktoor.fetch_canli_maclar
        eski_stats = fiktoor.mac_istatistiklerini_doldur
        try:
            fiktoor.fetch_canli_maclar = lambda slug, simdi=None: [yeni["haftalar"][0]["maclar"][0]]
            fiktoor.mac_istatistiklerini_doldur = lambda *args, **kwargs: None
            sonuc, degisti = fiktoor.canli_veri_guncelle(
                "tur.1", "/tmp", eski,
                simdi=fiktoor.parse_utc("2026-09-19T16:05:00Z"),
            )
        finally:
            fiktoor.fetch_canli_maclar = eski_fetch
            fiktoor.mac_istatistiklerini_doldur = eski_stats
        mac = sonuc["haftalar"][0]["maclar"][0]
        self.assertTrue(degisti)
        self.assertEqual(mac["durum"], "in")
        self.assertEqual(mac["ev"]["skor"], "1")
        self.assertEqual(mac["kanal"], "beIN Sports 1")
        self.assertEqual(sonuc["uretim"], "2026-09-19T16:05:00+00:00")

    def test_degisiklik_yoksa_zaman_damgasi_ilerlemez(self):
        eski = self._paket()
        eski_fetch = fiktoor.fetch_canli_maclar
        eski_stats = fiktoor.mac_istatistiklerini_doldur
        try:
            fiktoor.fetch_canli_maclar = lambda slug, simdi=None: []
            fiktoor.mac_istatistiklerini_doldur = lambda *args, **kwargs: None
            sonuc, degisti = fiktoor.canli_veri_guncelle(
                "tur.1", "/tmp", eski,
                simdi=fiktoor.parse_utc("2026-09-19T16:05:00Z"),
            )
        finally:
            fiktoor.fetch_canli_maclar = eski_fetch
            fiktoor.mac_istatistiklerini_doldur = eski_stats
        self.assertFalse(degisti)
        self.assertEqual(sonuc["uretim"], eski["uretim"])

    def test_canli_json_uretilir(self):
        with tempfile.TemporaryDirectory() as td:
            veri = self._paket()
            fiktoor.veri_paketini_yaz(td, veri)
            yol = os.path.join(td, "canli.json")
            self.assertTrue(os.path.exists(yol))
            with open(yol, encoding="utf-8") as f:
                canli = json.load(f)
            self.assertIn("maclar", canli)
            self.assertIn("live-1", canli["maclar"])


class CanliVeriKaynagiTestleri(unittest.TestCase):
    """2026-09'da siteyi 9 gün bayat bırakan gerçek arızaların regresyon testleri.

    Ölçülen kök nedenler:
      1. ESPN ``dates=A-B`` aralık sorgusu HTTP 200 gövdesinde
         ``{"code":400,"message":"Failed to get events endpoint."}`` döndürüyor.
      2. ``site.api.espn.com`` (Akamai) bazı User-Agent'ları 403 ile reddediyor.
      3. Canlı mod bayat paketi yenilemeden koruyordu; tam senkronizasyon
         cron'u hiç tetiklenmediğinde site günlerce eski kalıyordu.
    """

    def test_hata_govdesi_taninir(self):
        self.assertTrue(fiktoor.espn_hata_govdesi_mi(
            {"code": 400, "message": "Failed to get events endpoint."}))
        self.assertTrue(fiktoor.espn_hata_govdesi_mi(
            {"code": "500", "message": "iç hata"}))
        self.assertFalse(fiktoor.espn_hata_govdesi_mi({"events": []}))
        self.assertFalse(fiktoor.espn_hata_govdesi_mi({"code": 200, "message": "ok"}))
        self.assertFalse(fiktoor.espn_hata_govdesi_mi([1, 2, 3]))

    def test_hata_govdesi_host_degistirir(self):
        """200 içinde hata gövdesi 'başarılı istek' sayılmamalı."""
        cagrilar = []
        eski = fiktoor.http_get_json

        def fake(url, zorunlu=True, timeout=25, ua=""):
            cagrilar.append(url)
            if "site.api.espn.com" in url:
                return {"code": 400, "message": "Failed to get events endpoint."}
            return {"events": [{"id": "1"}], "leagues": [{"slug": "tur.1"}]}

        try:
            fiktoor.http_get_json = fake
            veri = fiktoor.espn_json_al(
                "tur.1", "scoreboard?dates=20260924",
                dogrula=lambda x: isinstance(x.get("events"), list))
        finally:
            fiktoor.http_get_json = eski
            fiktoor._ESPN_HOST_BELLEK["taban"] = None
        self.assertEqual(len(veri["events"]), 1)
        self.assertEqual(len(cagrilar), 2)
        self.assertIn("site.web.api.espn.com", cagrilar[1])

    def test_calisan_host_hatirlanir(self):
        eski = fiktoor.http_get_json
        fiktoor._ESPN_HOST_BELLEK["taban"] = None

        def fake(url, zorunlu=True, timeout=25, ua=""):
            return {"events": []}

        try:
            fiktoor.http_get_json = fake
            fiktoor.espn_json_al("tur.1", "scoreboard",
                                 dogrula=lambda x: isinstance(x.get("events"), list))
            self.assertEqual(fiktoor._ESPN_HOST_BELLEK["taban"], fiktoor.SITE_API)
            fiktoor._ESPN_HOST_BELLEK["taban"] = fiktoor.SITE_WEB_API
            self.assertEqual(fiktoor._host_sirasi()[0], fiktoor.SITE_WEB_API)
        finally:
            fiktoor.http_get_json = eski
            fiktoor._ESPN_HOST_BELLEK["taban"] = None

    def test_waf_403_user_agent_rotasyonu(self):
        """403 kalıcı sayılmamalı; havuzdaki başka User-Agent denenmeli."""
        gorulen_ua = []
        eski_urlopen = fiktoor.urllib.request.urlopen
        eski_bellek = dict(fiktoor._HTTP_UA_BELLEK)

        class Yanit:
            status = 200
            headers = {}

            def read(self):
                return b'{"events": []}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            gorulen_ua.append(req.get_header("User-agent"))
            if len(gorulen_ua) < 3:
                raise fiktoor.urllib.error.HTTPError(
                    req.full_url, 403, "Forbidden", {}, None)
            return Yanit()

        try:
            fiktoor.urllib.request.urlopen = fake_urlopen
            veri = fiktoor.http_get_json("https://site.api.espn.com/x", zorunlu=False)
        finally:
            fiktoor.urllib.request.urlopen = eski_urlopen
            fiktoor._HTTP_UA_BELLEK.update(**eski_bellek)
        self.assertEqual(veri, {"events": []})
        self.assertEqual(len(gorulen_ua), 3)
        self.assertEqual(len(set(gorulen_ua)), 3, "aynı UA tekrar denendi")

    def test_kalici_404_icin_ua_donusumu_yapilmaz(self):
        gorulen = []
        eski_urlopen = fiktoor.urllib.request.urlopen

        def fake_urlopen(req, timeout=None):
            gorulen.append(req.get_header("User-agent"))
            raise fiktoor.urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        try:
            fiktoor.urllib.request.urlopen = fake_urlopen
            veri = fiktoor.http_get_json("https://site.api.espn.com/yok", zorunlu=False)
        finally:
            fiktoor.urllib.request.urlopen = eski_urlopen
        self.assertIsNone(veri)
        self.assertEqual(len(gorulen), 1)

    def test_canli_pencere_gun_gun_cekilir(self):
        """Canlı mod aralık sorgusu kullanmamalı; gün gün istek atmalı."""
        yollar = []
        eski = fiktoor.espn_json_al

        def fake(slug, yol, **kw):
            yollar.append(yol)
            return {"events": [{"id": "e1", "date": "2026-09-24T17:00Z",
                                "competitions": [{"date": "2026-09-24T17:00Z",
                                                  "status": {"type": {"state": "pre"}},
                                                  "competitors": []}]}]}

        try:
            fiktoor.espn_json_al = fake
            fiktoor.ESPN_ARALIK_DESTEKLIYOR = False   # aralık bozuk senaryosu
            maclar = fiktoor.fetch_canli_maclar(
                "tur.1", fiktoor.parse_utc("2026-09-24T12:00:00Z"))
        finally:
            fiktoor.espn_json_al = eski
            fiktoor.ESPN_ARALIK_DESTEKLIYOR = None
        beklenen = fiktoor.CANLI_GUN_GERI + fiktoor.CANLI_GUN_ILERI + 1
        self.assertEqual(len(yollar), beklenen)
        import re
        for yol in yollar:
            self.assertRegex(yol, r"^scoreboard\?dates=\d{8}(&|$)")
            self.assertNotRegex(yol, r"dates=\d{8}-\d{8}")
        self.assertEqual(len(maclar), beklenen)

    def test_aralik_calisiyorsa_tek_istek_yeter(self):
        yollar = []
        eski = fiktoor.espn_json_al

        def fake(slug, yol, **kw):
            yollar.append(yol)
            return {"events": []}

        try:
            fiktoor.espn_json_al = fake
            fiktoor.ESPN_ARALIK_DESTEKLIYOR = None
            fiktoor.fetch_canli_maclar("tur.1", fiktoor.parse_utc("2026-09-24T12:00:00Z"))
        finally:
            fiktoor.espn_json_al = eski
            fiktoor.ESPN_ARALIK_DESTEKLIYOR = None
        self.assertEqual(len(yollar), 1)
        self.assertIn("dates=20260922-20260926", yollar[0])

    def test_aralik_bozulursa_gun_modeuna_duser(self):
        yollar = []
        eski = fiktoor.espn_json_al

        def fake(slug, yol, **kw):
            yollar.append(yol)
            if "-" in yol.split("dates=")[-1].split("&")[0]:
                raise RuntimeError("Failed to get events endpoint.")
            return {"events": []}

        try:
            fiktoor.espn_json_al = fake
            fiktoor.ESPN_ARALIK_DESTEKLIYOR = None
            fiktoor.fetch_canli_maclar("tur.1", fiktoor.parse_utc("2026-09-24T12:00:00Z"))
            self.assertFalse(fiktoor.ESPN_ARALIK_DESTEKLIYOR)
        finally:
            fiktoor.espn_json_al = eski
            fiktoor.ESPN_ARALIK_DESTEKLIYOR = None
        self.assertEqual(len(yollar), 6)   # 1 aralık denemesi + 5 gün

    def test_sezon_gunleri_takvimden_suzulur(self):
        takvim = ["2026-09-20", "2026-09-24", "2026-10-09", "2027-05-23"]
        gunler = fiktoor.sezon_gunleri("2026-09-01T00:00Z", "2026-10-31T00:00Z", takvim)
        self.assertEqual([g.isoformat() for g in gunler], ["2026-09-20", "2026-09-24", "2026-10-09"])
        # Takvim yoksa her gün taranır
        gunler = fiktoor.sezon_gunleri("2026-09-01T00:00Z", "2026-09-05T00:00Z", None)
        self.assertEqual(len(gunler), 5)

    def test_paket_yasi_ve_bayat_esigi(self):
        simdi = fiktoor.datetime.now(fiktoor.timezone.utc)
        taze = {"uretim": simdi.isoformat()}
        eski = {"uretim": (simdi - fiktoor.timedelta(hours=9)).isoformat()}
        self.assertLess(fiktoor.veri_yasi_saat(taze), 0.01)
        self.assertAlmostEqual(fiktoor.veri_yasi_saat(eski), 9.0, delta=0.05)
        self.assertIsNone(fiktoor.veri_yasi_saat({"uretim": "bozuk"}))
        self.assertIsNone(fiktoor.veri_yasi_saat(None))
        self.assertGreater(fiktoor.veri_yasi_saat(eski), fiktoor.TAM_ESIK_SAAT)

    def test_bayat_paket_canli_modu_tam_senkrona_yukseltir(self):
        """Canlı mod, paket eşikten eskiyse tam senkronizasyona geçmeli."""
        with tempfile.TemporaryDirectory() as td:
            veri = CanliYenileme()._paket()
            eski_zaman = fiktoor.datetime.now(fiktoor.timezone.utc) - fiktoor.timedelta(hours=12)
            veri["uretim"] = eski_zaman.isoformat()
            veri["lig"] = {"slug": "tur.1", "ad": "Trendyol Süper Lig", "sezon_yili": 2026}
            fiktoor.veri_paketini_yaz(td, veri)
            # yazım üretim damgasını değiştirmez; dosyadaki paketi elle bayatla
            yol = os.path.join(td, "site-verisi.json")
            with open(yol, encoding="utf-8") as f:
                paket = json.load(f)
            paket["uretim"] = eski_zaman.isoformat()
            with open(yol, "w", encoding="utf-8") as f:
                json.dump(paket, f, ensure_ascii=False)

            cagrilar = []
            eski_canli = fiktoor.canli_veri_guncelle
            eski_tam = fiktoor._veri_yeni_uret
            try:
                fiktoor.canli_veri_guncelle = lambda *a, **k: cagrilar.append("canli") or (veri, False)
                fiktoor._veri_yeni_uret = lambda *a, **k: cagrilar.append("tam") or veri
                fiktoor.calistir(SimpleNamespace(
                    league="tur.1", data_dir=td, out=os.path.join(td, "index.html"),
                    offline=False, live=True, strict=False, tani=False))
            finally:
                fiktoor.canli_veri_guncelle = eski_canli
                fiktoor._veri_yeni_uret = eski_tam
            self.assertEqual(cagrilar, ["tam"])

    def test_taze_paket_canli_modda_kalir(self):
        with tempfile.TemporaryDirectory() as td:
            veri = CanliYenileme()._paket()
            veri["lig"] = {"slug": "tur.1", "ad": "Trendyol Süper Lig", "sezon_yili": 2026}
            veri["uretim"] = fiktoor.datetime.now(fiktoor.timezone.utc).isoformat()
            fiktoor.veri_paketini_yaz(td, veri)
            yol = os.path.join(td, "site-verisi.json")
            with open(yol, encoding="utf-8") as f:
                paket = json.load(f)
            paket["uretim"] = veri["uretim"]
            with open(yol, "w", encoding="utf-8") as f:
                json.dump(paket, f, ensure_ascii=False)

            cagrilar = []
            eski_canli = fiktoor.canli_veri_guncelle
            eski_tam = fiktoor._veri_yeni_uret
            try:
                fiktoor.canli_veri_guncelle = lambda *a, **k: cagrilar.append("canli") or (veri, False)
                fiktoor._veri_yeni_uret = lambda *a, **k: cagrilar.append("tam") or veri
                fiktoor.calistir(SimpleNamespace(
                    league="tur.1", data_dir=td, out=os.path.join(td, "index.html"),
                    offline=False, live=True, strict=False, tani=False))
            finally:
                fiktoor.canli_veri_guncelle = eski_canli
                fiktoor._veri_yeni_uret = eski_tam
            self.assertEqual(cagrilar, ["canli"])


if __name__ == "__main__":
    unittest.main()

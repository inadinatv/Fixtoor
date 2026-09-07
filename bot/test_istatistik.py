#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""İstatistik normalizasyonu ve 0 / 'veri yok' ayrımı testleri."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


if __name__ == "__main__":
    unittest.main()

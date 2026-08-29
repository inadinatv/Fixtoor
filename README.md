# Fixtoor ⚽

**Trendyol Süper Lig** fikstürü, maç özetleri ve puan durumunu ESPN API'sinden
çekip statik bir HTML sayfası olarak yayınlayan bot.

## Nasıl çalışır?

```
ESPN API ──▶ bot/fiktoor.py ──▶ data/*.json + index.html ──▶ GitHub Pages
```

1. **`bot/fiktoor.py`** — saf Python (bağımlılıksız) bot:
   - Sezonun **tüm fikstürünü** çeker (tarih, saat, stadyum)
   - Oynanmış maçlar için **maç özeti** üretir: goller (dakika + oyuncu, penaltı/KK),
     kırmızı kartlar ve maç istatistikleri (topla oynama, şut, korner, faul)
   - **Puan durumu** tablosunu çeker (avrupa / küme bölgeleri renkli)
   - Bunları `data/*.json` olarak kaydeder ve `index.html` sayfasını üretir
2. **`.github/workflows/bot.yml`** — GitHub Actions iş akışı:
   - Günde 6 kez otomatik çalışır (maç günlerinde skorlar kendiliğinden düşer)
   - Yeni veriyi depoya işler (`🤖 Fixtoor veri güncellemesi` commit'leri)
   - Sayfayı **GitHub Pages**'e yayınlar
3. **Canlı site:** <https://inadinatv.github.io/Fixtoor/> *(PR main'e birleştirildikten sonra)*

## Sayfada ne var?

| Sekme | İçerik |
|---|---|
| 📋 Özetler | Son 14 günün maç özetleri (goller, kartlar, istatistikler) + yaklaşan maçlar, canlı maç rozeti |
| 📅 Fikstür | Tüm sezon, hafta hafta; oynanmayanlar saat, oynananlar skor ile |
| 🏆 Puan Durumu | O, G, B, M, A, Y, AV, P + Şampiyonlar Ligi / Avrupa / küme işaretleri |

Tüm saatler **Türkiye saati (TRT)** ile gösterilir.

## Kullanım

```bash
# API'den çekip sayfayı üret
python3 bot/fiktoor.py

# Ağ olmadan, eldeki son veriden HTML üret
python3 bot/fiktoor.py --offline

# Başka bir lig (ör. TFF 1. Lig, Premier Lig)
python3 bot/fiktoor.py --league tur.2
```

Botu elle çalıştırmak için: **Actions → Fixtoor Bot → Run workflow**.

## JSON veri uçları

Yayınlanan sayfanın verileri sitenin kendisinden çekilebilir:

- `data/fikstur.json` — haftalara göre tüm maçlar
- `data/ozetler.json` — son maç özetleri
- `data/puan-durumu.json` — puan cetveli
- `data/takimlar.json` — takım listesi (logo, renk)

## Kaynak

Veriler [ESPN](https://www.espn.com/soccer/league/_/name/tur.1)'in herkese açık
API'sinden alınmaktadır. Bu proje eğitim amaçlıdır.

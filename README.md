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
   - Her saat otomatik çalışır (maç günlerinde skorlar kendiliğinden düşer)
   - Kod testlerini ve üretilen veri paketini doğrular
   - Yeni veriyi depoya işler (`🤖 Fixtoor veri güncellemesi` commit'leri)
   - Sayfayı **GitHub Pages**'e yayınlar
   - ESPN geçici olarak erişilemezse son sağlam paketi korur ve bir sonraki çalıştırmada yeniden dener

> Gerçek Actions dosyası `.github/workflows/bot.yml` altındadır. `kurulum/bot.yml`
> aynı dosyanın güncel bir kopyasıdır; GitHub Actions'ın çalışması için dosyanın
> `.github/workflows/` altında bulunması gerekir.

Botun son çalışmasını **Actions → Fixtoor Bot** bölümünden kontrol edebilirsin.
Bir API arızasında botun mutlaka hata vermesini istiyorsan yerelde `--strict`
parametresini kullanabilirsin; normal otomatik çalıştırma mevcut veriyi koruyarak
başarılı şekilde tamamlanır. Dosya yazımları da atomiktir; yarım kalmış JSON
önbelleği oluşturulmaz.
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

# API geçici olarak düşerse önbelleğe dönme; hatayı görünür biçimde al
python3 bot/fiktoor.py --strict

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

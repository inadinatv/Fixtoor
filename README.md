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
   - **Her 5 dakikada** yakın maçların skor/durum değişikliklerini küçük bir
     scoreboard penceresiyle kontrol eder (`--live`)
   - Canlı maç sırasında sayfa açık olan tarayıcı yaklaşık **15 saniyede** ESPN'i
     kontrol eder; API/CORS sorunu olursa `data/canli.json` aynı-origin yedeğine döner
   - Sezon fikstürü, puan durumu, istatistikler, yayın kanalları ve video aramaları
     gibi ağır tam senkronizasyonu **6 saatte bir** yapar
   - Her çalışmada testleri ve veri sözleşmesini doğrular; yalnızca gerçekten veri
     değiştiğinde commit atar
   - Yeni veriyi depoya işler (`🤖 Fixtoor veri güncellemesi` commit'leri) ve
     **GitHub Pages**'e yayınlar
   - ESPN geçici olarak erişilemezse son sağlam paketi korur ve sonraki canlı
     çalıştırmada yeniden dener

> GitHub schedule sunucuların yoğunluğunda birkaç dakika gecikebilir; bu nedenle
> beş dakikayı mutlak gerçek-zaman garantisi olarak değil, ücretsiz altyapıdaki
> en sık güvenli yenileme aralığı olarak düşün. Daha düşük gecikme için sayfa içi
> tarayıcı döngüsü canlı maçta devrededir.

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
# Tam senkronizasyon: sezon, puan, istatistik, yayın ve video verisi
python3 bot/fiktoor.py

# Canlı çalışma: yalnızca yakın maçları yeniler, sezonu baştan çekmez
python3 bot/fiktoor.py --live

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
- `data/canli.json` — küçük ve sık yenilenen canlı skor/istatistik paketi

`data/site-verisi.json` tam kaynak paketidir; `data/canli.json` tarayıcıların
sık kontrol etmesi için özellikle küçültülmüş bir uçtur. Tüm JSON dosyaları
atomik yazıldığı için Actions yarıda kesilse bile siteye yarım dosya çıkmaz.

## Kaynak

Veriler [ESPN](https://www.espn.com/soccer/league/_/name/tur.1)'in herkese açık
API'sinden alınmaktadır. Bu proje eğitim amaçlıdır.

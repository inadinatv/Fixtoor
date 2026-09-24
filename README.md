# Fixtoor ⚽

**Trendyol Süper Lig** fikstürü, maç özetleri, puan durumu ve TV yayın akışını
ESPN API'sinden çekip **canlı** yayınlayan statik site + bot.

Sayfa iki katmanlı çalışır:

1. **Statik paket** — botun ürettiği `data/*.json` + `index.html` (ilk çizim,
   çevrimdışı bile açılır).
2. **Canlı motor** — sayfa açıkken tarayıcı doğrudan ESPN'e bağlanır; skorlar
   **canlı maçta 5 saniyede bir**, yakın maçta 15 saniyede, boşta 60 saniyede
   bir yenilenir. Fikstür ve puan durumu 3 dakikada bir tazelenir. Yani
   GitHub Actions'ın ne sıklıkta çalıştığından **bağımsız** olarak sayfa güncel
   kalır.

## Nasıl çalışır?

```
                 ┌──────────────── tarayıcı (canlı motor) ────────────────┐
ESPN API ───────▶│ site.web → site.api → data/canli.json  (5-60 sn)       │
     │           └────────────────────────────────────────────────────────┘
     └──▶ bot/fiktoor.py ──▶ data/*.json + index.html ──▶ GitHub Pages
              (Actions: 5 dk canlı / bayatsa tam senkron)
```

1. **`bot/fiktoor.py`** — saf Python (bağımlılıksız) bot:
   - Sezonun **tüm fikstürünü** çeker (tarih, saat, stadyum)
   - Oynanmış maçlar için **maç özeti** üretir: goller (dakika + oyuncu,
     penaltı/KK), kırmızı kartlar ve maç istatistikleri
   - **Puan durumu** tablosunu çeker (Avrupa / küme bölgeleri renkli)
   - TV yayın kanallarını ve video özetlerini bulur
   - Bunları `data/*.json` olarak kaydeder ve `index.html` sayfasını üretir
2. **`bot/tani.py`** — ağ tanısı: hangi host, hangi User-Agent, hangi HTTP
   durumu, hangi WAF imzası. Arıza anında `data/tani.json` dosyasına yazılır
   ve Actions iş özetinde gösterilir.
3. **`.github/workflows/bot.yml`** — GitHub Actions iş akışı:
   - **5 dakikada bir** canlı pencere yenilemesi (`--live`)
   - Paket eşikten (varsayılan **6 saat**) eskiyse bot canlı modu kendiliğinden
     **tam senkronizasyona** yükseltir; 6 saatlik cron hiç tetiklenmese bile
     site bayat kalmaz
   - Her çalışmada testleri, veri sözleşmesini ve **veri tazeliğini** doğrular;
     veri bayatsa iş "yeşil" görünse bile Actions arayüzünde uyarı çıkar
   - Yalnızca gerçekten veri değiştiğinde commit atar ve Pages'e yayınlar

> **GitHub cron gerçeği:** `*/5 * * * *` istense de GitHub zamanlanmış
> işleri yoğunlukta seyreltir (bu depoda pratikte birkaç saatte bir
> tetikleniyor). Bu yüzden dakika/saniye düzeyindeki tazelik sayfada,
> tarayıcının canlı motoruyla sağlanır; Actions yalnızca statik paketi
> taze tutar.

## 2026-09 arızası: site neden 9 gün bayat kaldı?

Ölçülen kök nedenler (Actions adım süreleri + uç uç nokta testleriyle doğrulandı):

| # | Arıza | Kanıt | Çözüm |
|---|---|---|---|
| 1 | ESPN'in `scoreboard?dates=A-B` **aralık** sorgusu bozuldu: HTTP **200** gövdesinde `{"code":400,"message":"Failed to get events endpoint."}` dönüyor | Bot adımı maç günlerinde bile **0-1 saniyede** bitiyordu; tek gün sorgusu (`dates=YYYYMMDD`) 200 + `events` dönüyor | Bot ve tarayıcı artık **gün gün** çeker; lig takvimindeki maç günleri kullanılır. Aralık ucu yeniden çalışırsa otomatik hızlı moda döner |
| 2 | "HTTP 200 ama hata gövdesi" **başarılı istek** sayılıyordu | `dogrula` fonksiyonu `events` arıyordu ama hata gövdesi sessizce "veri yok" gibi işleniyordu | `espn_hata_govdesi_mi()` eklendi; bu gövdeler istek reddi sayılıp **host değiştiriliyor** |
| 3 | `site.api.espn.com` (Akamai) bazı User-Agent'ları **403** ile reddediyor; 403 "kalıcı hata" sayılıp **hiç yeniden denenmiyordu** | 403 → anında `break` → <1 sn'de pes | User-Agent havuzu (curl / requests / okhttp / chrome / bot) + çalışan kimliğin belleğe alınması |
| 4 | Sessiz geri düşme (`CI_GERI_DUS`) arızayı **gizliyordu**: iş yeşil, site bayat | 15-24 Eylül arası 40+ başarılı koşu, sıfır veri commit'i | `data/tani.json` + Actions uyarı notu + iş özeti; veri tazeliği artık ölçülüyor |
| 5 | Tarayıcı canlı döngüsü yalnızca **statik pakette zaten var olan** maçları güncelliyordu ve bozuk aralık sorgusunu kullanıyordu | Gömülü snapshot 15 Eylül'de kalmıştı; yeni maçlar hiç görünmüyordu | Canlı motor yeniden yazıldı: yeni maçlar da keşfedilir, fikstür/puan durumu ağdan tazelenir, `localStorage` ile kalıcı |
| 6 | 6 saatlik tam senkronizasyon cron'u hiç tetiklenmiyordu | 15 Eylül'den beri `full` mod koşusu yok | Canlı mod **bayatlığa bakarak** kendini tam senkrona yükseltiyor |

## Sayfada ne var?

| Sekme | İçerik |
|---|---|
| 📺 Haftanın Maçları | TV yayın akışı + canlı skor |
| 📋 Özetler | Son 14 günün maç özetleri (goller, kartlar, istatistikler) + yaklaşan maçlar |
| 📅 Fikstür | Tüm sezon, hafta hafta; oynanmayanlar saat, oynananlar skor ile |
| 🏆 Puan Durumu | O, G, B, M, A, Y, AV, P + Şampiyonlar Ligi / Avrupa / küme işaretleri |

Üstteki **canlı durum çubuğu** şunları gösterir: kullanılan kaynak
(`site.web` / `site.api`), son güncelleme, bir sonraki yenilemeye kalan saniye
ve elle **⟳ Yenile** düğmesi. Canlı maç varsa sayfanın üstünde ayrı bir
**canlı panel** açılır ve gollerde bildirim çıkar. Tüm saatler **TRT**'dir.

## Kullanım

```bash
# Tam senkronizasyon: sezon, puan, istatistik, yayın ve video verisi
python3 bot/fiktoor.py

# Canlı çalışma: yalnızca yakın maç günlerini yeniler (paket bayatsa tam senkrona yükselir)
python3 bot/fiktoor.py --live

# Ağ olmadan, eldeki son veriden HTML üret
python3 bot/fiktoor.py --offline

# Veri kaynaklarının erişilebilirliğini ölç ve data/tani.json'a yaz
python3 bot/fiktoor.py --tani
python3 bot/tani.py --hizli

# API geçici olarak düşerse önbelleğe dönme; hatayı görünür biçimde al
python3 bot/fiktoor.py --strict

# Başka bir lig (ör. TFF 1. Lig, Premier Lig)
python3 bot/fiktoor.py --league tur.2
```

Ortam değişkenleri:

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `FIXTOOR_TAM_ESIK_SAAT` | `6` | Canlı modun tam senkrona yükselme eşiği (saat) |
| `FIXTOOR_CI_GERI_DUS` | `1` | API arızasında son sağlam paketi koru |
| `FIXTOOR_TANI` | `1` | Arıza anında `data/tani.json` üret |
| `FIXTOOR_DEBUG` | `0` | Ayrıntılı günlük (kaynak/UA değişiklikleri, istatistik ham verisi) |

Botu elle çalıştırmak için: **Actions → Fixtoor Bot → Run workflow**.

> ⚠️ **İş akışı dosyası:** Bu depodaki otomatik ajanın `.github/workflows/`
> altına yazma yetkisi yok. Güncel iş akışı `kurulum/bot.yml` içindedir;
> içeriğini `.github/workflows/bot.yml` dosyasına kopyalaman yeterli. Kopyalamasan
> da bot tarafındaki düzeltmeler (gün gün çekim, UA/host rotasyonu, bayatlıkta
> tam senkrona yükselme) mevcut iş akışıyla çalışır — yalnızca "veri bayat"
> uyarısı ve iş özeti eklenmez.

## JSON veri uçları

Yayınlanan sayfanın verileri sitenin kendisinden çekilebilir:

- `data/fikstur.json` — haftalara göre tüm maçlar
- `data/ozetler.json` — son maç özetleri
- `data/puan-durumu.json` — puan cetveli
- `data/takimlar.json` — takım listesi (logo, renk)
- `data/canli.json` — küçük ve sık yenilenen canlı skor/istatistik paketi
  (+ `sezon`, `takvim`: tarayıcının kendi canlı motoru için)
- `data/tani.json` — son kaynak arızasının ağ tanısı (yalnızca arızada üretilir)

`data/site-verisi.json` tam kaynak paketidir; `data/canli.json` tarayıcıların
sık kontrol etmesi için özellikle küçültülmüş bir uçtur. Tüm dosyalar atomik
yazıldığı için Actions yarıda kesilse bile siteye yarım dosya çıkmaz.

## Testler

```bash
python3 -m unittest discover -s bot -p 'test_*.py' -v   # 48 birim testi
```

Testler çevrimdışıdır ve şu regresyonları kilitler: hata gövdesi tanıma,
host/User-Agent rotasyonu, gün gün canlı pencere, aralık uç desteği ölçümü,
bayat paketin tam senkrona yükseltilmesi, atomik yazım.

Tarayıcı canlı motoru ayrıca gerçek sayfa üzerinde (jsdom + taklit ESPN)
iki senaryoyla doğrulandı: `site.api` 403 → `site.web`'e geçiş ve
`site.web` hata gövdesi → `site.api`'ye geçiş. Her ikisinde de skorlar,
CANLI etiketi, canlı panel, puan durumu ve `localStorage` güncelleniyor;
bozuk `dates=A-B` aralık sorgusu hiç kullanılmıyor.

## Kaynak

Veriler [ESPN](https://www.espn.com/soccer/league/_/name/tur.1)'in herkese açık
API'sinden alınmaktadır. Bu proje eğitim amaçlıdır.

# BIST Telegram Ajanı

BIST hakkında serbest Türkçe soruları cevaplayan bir Telegram botu ve onu
besleyen MCP sunucusu.

- `bist_mcp/` — **16 araçlı MCP sunucusu**; veri İş Yatırım, KAP, yfinance ve
  TCMB EVDS'ten gelir.
- `ajan/` — Telegram botu ve NVIDIA function-calling döngüsü. Bot MCP
  sunucusunu alt süreç olarak başlatır.

Tasarım: `docs/superpowers/specs/2026-09-05-bist-telegram-agent-design.md`

## Kurulum

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env    # sonra .env'i doldur — GERÇEK ANAHTARLAR .env.example'A YAZILMAZ
```

## Telegram botunu çalıştırma

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m ajan.model_karsilastir   # bir kez: kazanan modeli .env'e yaz
python -m ajan.bot
```

`.env` içindeki zorunlu alanlar: `TELEGRAM_BOT_TOKEN`, `NVIDIA_API_KEY`,
`ADMIN_USER_ID`, `NVIDIA_MODEL`.

Bot **yalnızca** `ADMIN_USER_ID`'ye cevap verir; başka herkesin mesajı sessizce
reddedilir ve log'a bir satır düşer.

MCP sunucusu bot tarafından alt süreç olarak başlatılır ve bot kapanana kadar
ayakta kalır — ayrıca çalıştırmak gerekmez. Bu bilinçli: sunucu açılışta
tarama tablosunu kuruyor, çağrı başına bağlanmak o işi her seferinde
tetiklerdi. Aynı sebeple oturumu tek bir sahip task açıp kapatıyor; `stdio_client`
girildiği task'te kapatılmazsa `RuntimeError: Attempted to exit cancel scope
in a different task` veriyor ve alt süreç sızıyor (ölçüldü).

## Test

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m pytest                 # 184 hızlı test, ağ ve LLM yok
python -m pytest -m network      # canlı veri kaynağı testleri
python -m pytest ajan/ -m llm    # gerçek NVIDIA çağrısı yapan uçtan uca testler
```

Windows konsolu cp1252 kullandığı için `PYTHONIOENCODING` gerekir; yoksa
Türkçe karakterler log'a yazılırken `UnicodeEncodeError` verir.

## Claude Desktop'a bağlama

`claude_desktop_config.json`. **`python` yerine mutlak yol kullan** — ölçüldü,
Windows'ta PATH'teki `python` Microsoft Store'un sahte `python.exe`'sine
düşebiliyor ve sunucu "Server disconnected" ile anında ölüyor:

```json
{
  "mcpServers": {
    "bist": {
      "command": "C:/Users/Taha/AppData/Local/Programs/Python/Python313/python.exe",
      "args": ["-m", "bist_mcp.sunucu"],
      "cwd": "C:/Users/Taha/Desktop/Borsa Agent v2",
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": "C:/Users/Taha/Desktop/Borsa Agent v2"
      }
    }
  }
}
```

## Araçlar

**Hisse (9):** `hisse_ara` · `anlik_fiyat` · `gecmis_fiyat` · `sirket_profili` ·
`finansal_tablo` · `finansal_oranlar` · `temettu_gecmisi` · `kap_bildirimleri` ·
`kap_bildirim_detay`

**Analiz (5):** `teknik_analiz` · `hisse_karsilastir` · `sektor_karsilastirma` ·
`hisse_tarama` · `endeks_verisi`

**Makro (2):** `doviz_altin` · `makro_gosterge`

## Ölçümden gelen veri kuralları

Her kural canlı ölçülmüş bir hataya karşılık gelir ve regresyon testi vardır.

1. **Oranlar TL bazında hesaplanır**, hazır alan okunmaz. yfinance'in
   `priceToBook`, `trailingPE`, `dividendYield` alanları ve `news` yasak
   listede. Gerekçe: THYAO finansallarını **USD** raporluyor, hissesi TRY
   işlem görüyor; yfinance TL fiyatı USD defter değerine bölüp `priceToBook`
   için **18,64** diyor — gerçek değer **0,38**, yani 49 kat hata.

   Uçtan uca doğrulandı: THYAO'da 49 kat ayrışıyoruz, EREGL/TUPRS/GARAN/
   ASELS'te yfinance ile uyumluyuz. Yani katman rastgele değil, tam olarak
   para birimi uyuşmazlığının olduğu yerde ayrışıyor.

2. **Özkaynak STOK, net kâr AKIŞ — dönem mantıkları farklı.** Özkaynak bir
   bakiye, o anki değeri geçerli → **en güncel bilanço** kullanılır. Net kâr
   bir akış → **son 12 ay (TTM)** hesaplanır:
   `TTM = geçen yıl yıllık − geçen yıl aynı kümülatif + bu yıl kümülatif`.

   Ölçüldü (BETAE, 06.09.2026) — gerçek değerler PD/DD 5,59 / F/K 44,27:

   | Girdi | Yanlış (yıllık) | Doğru | Sonuç |
   |---|---|---|---|
   | Özkaynak | 3,60 mlr (2025) | 5,85 mlr (2026/6) | PD/DD 9,08 → **5,59** |
   | Net kâr | 1,08 mlr (2025) | 739 mn (TTM) | F/K 30,32 → **44,27** |

   İkisini de yıllık almak her hisseyi etkiliyordu; şirket büyüdükçe PD/DD
   şişiyor, kâr daraldıkça F/K olduğundan düşük görünüyordu.

3. **Şirket tipine göre DÖRT ayrı hesap planı var.** Aynı kavramın adı değişiyor:

   | Tip | Özkaynak | Net kâr |
   |---|---|---|
   | Sanayi/ticaret | `Özkaynaklar` | `DÖNEM KARI (ZARARI)` |
   | Banka (BDDK) | `XVI. ÖZKAYNAKLAR` | `XXIII. NET DÖNEM KARI/ZARARI` |
   | Sigorta | `Özsermaye Toplamı` | `F-Dönem Net Karı` |
   | Katılım bankası | `ÖZKAYNAK` (tekil) | `XVIII. NET DÖNEM KARI/ZARARI` |

   Katılım bankasının Roma rakamı bankadan farklı (XVIII vs XXIII) — kolayca
   gözden kaçıyor. Sigorta ve katılım adları eklenmeden ANSGR, TURSG, ALBRK
   gibi hisselerde oranlar **tamamen boş** dönüyordu.

   Tüm evren tarandı: 630 işlem gören hissenin **609'u** çözülüyor. Kalan
   21'inin İş Yatırım'da hiç finansal tablosu yok (çoğu faktoring ve finansal
   kiralama: GARFA, VAKFA, ISFIN, QNBFK…). Bu bizim eksiğimiz değil, kaynakta
   veri yok — `finansal_oranlar` bu durumu açıkça belirtiyor ki model "0" ya
   da "düşük" diye sunmasın.

4. **Oranlar ANA ORTAKLIK payı üzerinden hesaplanır.** Piyasa değeri yalnızca
   ana ortaklığın hissedarlarını temsil eder; konsolide toplamın içinde bağlı
   ortaklıkların başkalarına ait payları vardır.

   Ölçüldü (AHGAZ) — gerçek PD/DD 1,72 / F/K 18,22: toplam özkaynak 93,24 mlr,
   içinde **33,30 mlr azınlık payı**; ana ortaklık 59,94 mlr. Toplamla PD/DD
   1,08 (yanlış). Çıkarım sırası: doğrudan ana ortaklık satırı → toplam eksi
   azınlık → toplam.

   **`Azınlık Payları` HEM bilançoda HEM gelir tablosunda geçiyor** (AHGAZ'da
   33,3 mlr ve 1,5 mlr). Düz ad araması ikisini karıştırıp net kârı eksiye
   düşürüyordu; arama bölüm bazlı yapılır.

5. **Hisse adedi ödenmiş sermayeden alınır, yfinance'ten değil.** BIST'te
   nominal 1 TL. yfinance geri alınmış payları düşüyor ve düşük kalıyor.

   Tüm evren denetlendi, 28 hissede iki kaynak %10'dan fazla ayrışıyor. KAP'ın
   kendi ödenmiş sermayesi üçüncü kaynak olarak soruldu: kontrol edilebilen
   **6 vakanın 6'sında da İş Yatırım doğru** (FLAP'ta yfinance 625 kat
   yanılıyor). İlk sürümdeki "çok saparsa yfinance'e dön" kontrolü tam da bu
   vakalarda yanlışı seçiyordu — kaldırıldı.

6. **Çoklu hisse sınıfında oran verilmez.** ISATR/ISBTR/ISCTR/ISKUR/TIB KAP'ta
   **tek kayıt** (Türkiye İş Bankası), ödenmiş sermaye 10 mlr TL. Bu sermayenin
   tamamını her sınıfa atayınca ISATR'da PD/DD 272.562 çıkıyordu. O sınıfa
   düşen hisse adedi güvenilir belirlenemediği için `finansal_oranlar` sayı
   yerine açık bir uyarı döndürüyor.

7. **İş Yatırım MaliTablo TAM 4 DÖNEM istiyor.** 2 ya da 3 dönemle istek
   hata vermiyor, sessizce **boş liste** dönüyor. `_getir` eksik pencereyi
   otomatik dolduruyor ki hiçbir çağıran bu tuzağa düşmesin.

8. **KAP OID'si toplu şirket listesinden çözülür.** `member/filter` bir
   **isim aramasıdır**: `member/filter/GARAN` sekiz sonuç döndürüyor ve ilki
   "GARANTİ BBVA OPERASYONEL KİRALAMA"; doğru banka sekizinci sırada.

9. **`stockCode` virgüllü çoklu kod tutar** (`"GARAN, TGB"`). Bölünmeden
   eşleştirilirse GARAN, YKBNK, VAKBN, HALKB, ISCTR kaybolur.
   757 şirket → **807 ticker**.

10. **Dönem takvimle hesaplanamaz.** 2026-09-05'te `2026/12` ve `2026/9` boş
   döner (henüz yayımlanmadı). Aday dönemler istenir, tamamen boş slotlar
   atılır. Değerler satır bazında değil **slot bazında** hizalanır.

11. **İş Yatırım değerleri STRING döner** (`'1073081134047'`). Çevrilmezse
   oran hesabı bölemez ve `'0' != 0` olduğu için sıfır satırları atılmaz.

12. **Bilanço/gelir/nakit tek listede gelir**, ayrı tablolar halinde değil.
   Bölme işaretleri: `TOPLAM KAYNAKLAR` (sanayi) / `PASİF TOPLAMI` (banka)
   bilançonun sonu, `İşletme Faaliyetlerinden Kaynaklanan Net Nakit` nakit
   akışının başı. **Bankalarda nakit akış tablosu yoktur.**

13. **Hız sınırlayıcı kilitli olmalı.** Kilitsiz sürüm eşzamanlılıkta hiç
   sınırlamıyordu: ölçüldü, 20 eşzamanlı istek 2 istek/sn yerine 0,50 sn'de
   ateşliyordu. 630 hisselik kurulumda bu, kaynak siteye yüzlerce eşzamanlı
   istek demekti. `hiz_sinir.HizSinirlayici` bekleme ve damgayı atomik yapar.

14. **KAP bildirim sorgusu en fazla 365 gün kabul eder.** Ölçüldü
   (2026-09-06, THYAO ve MEKAG): 365 günlük aralık HTTP 200 ve 88/98 kayıt
   döndürüyor, **366 gün HTTP 500**. `temettu_gecmisi` bir temettü döngüsünü
   görmek için 400 gün istediğinden her çağrıda kırılıyordu. Daha uzun geçmiş
   üst üste binmeyen parçalara bölünüp birleştiriliyor; kayıtlar
   `disclosureIndex` ile tekilleştirilip yeniden eskiye sıralanıyor.

15. **Tarama evreni BIST geneli**, elle yazılmış bir liste değil. KAP dizini
   807 ticker veriyor, 630'unda fiyat verisi var; kalanı işlem görmeyen ya da
   GARAN'ın `TGB`'si gibi ikincil kodlar ve toplu indirmede kendiliğinden
   düşüyor.

## Hız sınırları

KAP ve İş Yatırım için **2 istek/sn**. KAP'ta API çağrısından önce
`/tr/bildirim-sorgu`'ya GET ile oturum çerezi alınır; yoksa WAF bağlantıyı
~6 saniyede düşürür.

Önbellek **tembeldir**: hiçbir şeyi kendiliğinden çekmez, yalnızca sorulduğunda
çeker ve TTL boyunca saklar. Tek istisna tarama tablosudur (aşağıda).

## Tarama tablosu (arka plan)

`hisse_tarama` ve `sektor_karsilastirma` tüm evrenin verisine ihtiyaç duyar;
her soruda 630 şirketi çekmek imkânsız. Bu yüzden sunucu içinde arka plan
görevi tabloyu iki kademede taze tutar:

| Kademe | Süre | İstek | Ne çeker |
|---|---|---|---|
| Günlük | ~40 sn | 1 | Fiyat + temettü + hacim (tek toplu indirme) |
| Haftalık | ~7 dk | ~700 | Üstüne İş Yatırım finansalları + hisse adedi/sektör |

Bu bedel arka planda ödenir. Soru sorduğunda tablo zaten hazırdır ve
`hisse_tarama` doğrudan SQLite'a `SELECT` atar — gün içinde kaç kez sorarsan
sor, hiçbir şey yeniden çekilmez.

### Likidite filtresi

Evren BIST'in tamamı olduğu için içinde günde birkaç lot işlem gören kabuk
şirketler var. Bunlar "F/K'sı düşük" diye listenin başına çıkar ama alınıp
satılamaz. `ortalama_hacim_tl` sütunu (son 60 işlem gününün ortalama TL işlem
hacmi) bunun için var; `hisse_tarama` aracının `hacim_min` parametresiyle
süzülür. Likidite ölçüsü olarak adet değil **TL** kullanılır: 1 TL'lik
hisseden 100.000 adet ile 400 TL'lik hisseden 100.000 adet aynı likidite
değildir.

### Çok düşük F/K bir tuzaktır

Tam evren kurulumunda ölçüldü: "F/K < 10" sorgusunun başını holdingler, GYO'lar
ve yatırım ortaklıkları dolduruyor. Örnek — ISGSY'nin F/K'sı **0,21**; piyasa
değeri 1,08 milyar TL iken net kârı 5,23 milyar TL görünüyor, çünkü bir girişim
sermayesi ortaklığı ve "kâr"ı portföy yeniden değerleme kazancı, nakit kâr
değil. Hesap doğru, yorum yanıltıcı.

Bu satırlar gizlenmiyor (veri gerçek), ama `hisse_tarama` aracının açıklaması
modeli uyarıyor: F/K'sı 2'nin altındaki şirketi ucuz diye sunma, ne iş
yaptığına bak ve rakamın neden düşük olduğunu açıkla. İşletme kârlılığı aranan
taramalarda `fk_min=3` gibi bir alt sınır daha anlamlı sonuç verir.

KAP'ın `financialType` alanıyla şirket tipini eleyemiyoruz: 807 ticker'ın
315'inde boş ve ISGSY de o boşlardan biri.

## Tam evren denetimi (630 işlem gören hisse)

| Durum | Sayı |
|---|---|
| Sağlıklı | **566** |
| Kaynakta finansal tablo yok | 21 |
| İki kaynak hisse adedinde ayrışıyor (İş Yatırım seçilir) | 28 |
| Oran olağandışı — uyarı notuyla döner | 15 |

Denetim betiği tekrar koşulabilir: her hissede çekim başarısı, ana ortaklık
tutarlılığı, hisse adedi uyumu ve oran makullüğü kontrol edilir.

## Bilinen eksikler

- **`makro_gosterge` şu an çalışmıyor — sebebi anahtar değil, TCMB'nin API
  değişikliği.** Gerçek bir EVDS anahtarıyla ölçüldü (06.09.2026):
  `evds2.tcmb.gov.tr` artık `evds3`'e 302 yönlendiriyor ve
  `evds3.tcmb.gov.tr/service/evds/...` yolu JSON yerine web uygulamasının
  HTML'ini döndürüyor. Beş farklı başlık adı (`key`, `apikey`, `ApiKey`,
  `X-API-KEY`, `Authorization`) ve anahtarsız istek denendi — hepsi aynı
  HTML. Yani kimlik doğrulama değil, **servis yolu değişmiş**.

  Araç çökmüyor: durumu açıklayan bir mesaj döndürüyor ve diğer 15 araç
  etkilenmiyor. v3'ün doğru servis yolu bulununca `bist_mcp/kaynaklar/tcmb.py`
  içindeki `EVDS_KOK` güncellenmeli; seri kodları da o zaman doğrulanabilir.

  **Enflasyon/faiz dışındaki her şey etkilenmiyor** — döviz, altın ve emtia
  `doviz_altin` aracından yfinance üzerinden anahtarsız geliyor.
- **İlk açılışta tarama tablosu ~7 dakika kurulur.** O bitene kadar
  `hisse_tarama` "tablo henüz kurulmadı" der; diğer 15 araç hemen çalışır.
- Döviz/altın EVDS değil **yfinance** kullanır, yani anahtarsız çalışır.
  Gram altın ons fiyatı × USD/TRY ÷ 31,1035 ile hesaplanır; dayanak değerler
  cevapta yer alır.

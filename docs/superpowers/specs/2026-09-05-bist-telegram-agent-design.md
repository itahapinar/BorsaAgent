# BIST Telegram Ajanı (v2) — Tasarım

**Tarih:** 2026-09-05
**Durum:** Tasarım onay bekliyor
**Önceki iş:** `Desktop/Borsa Agent` (v1) referans alınmadı. Kod, mimari ve veri
kaynağı sıfırdan seçildi. v1'in kullandığı üçüncü parti `borsa.surucu.dev` MCP
sunucusu bilinçli olarak dışarıda bırakıldı.

---

## 1. Amaç

BIST hisseleri hakkında serbest Türkçe soru sorulabilen, tek kullanıcılık bir
Telegram botu. Veri katmanı kendi yazdığımız bir MCP sunucusudur; model
araçları MCP üzerinden çağırır.

**Hedef sorular:**

- "THYAO kaç TL?"
- "ASELS'i detaylı analiz et"
- "GARAN'ın temettü tarihleri neler?"
- "ASELS'in son KAP açıklamaları ne diyor?"
- "F/K'sı 10'un altında temettü veren hisseler hangileri?"

## 2. Kapsam

**Dahil:** BIST hisseleri (fiyat, geçmiş fiyat, şirket profili, finansal tablo,
oranlar, temettü, KAP bildirimleri, teknik analiz, karşılaştırma, tarama),
endeksler (XU100, XU030, sektör), döviz/altın ve TCMB makro göstergeleri.

**Hariç:** TEFAS fonları, kripto, ABD hisseleri, çoklu kullanıcı, fiyat alarmı,
zamanlanmış bülten, portföy takibi.

**Kullanıcı:** Tek kişi. Bot `ADMIN_USER_ID` dışındaki herkesi sessizce reddeder.

---

## 3. Kararlar ve gerekçeleri

Kararlar bu oturumda yapılan canlı ölçümlere dayanıyor. Tahmin yok.

### 3.1 Veri kaynağı: kendi MCP sunucumuz

Hazır MCP sunucularının tamamı yfinance ya da FMP üstüne kurulu. yfinance
BIST üzerinde ölçüldü (THYAO, GARAN, ASELS):

| Ölçüt | Sonuç |
|---|---|
| Anlık fiyat | Doğru (296,00 / 131,40 / 388,25 TL) |
| THYAO PD/DD | **18,64** — gerçek değer 0,38 |
| THYAO F/K | `None` — hiç yok |
| ASELS haberleri | **0 haber** |
| THYAO haberleri | 10 haber, hepsi İngilizce ajans; **KAP yok** |

**PD/DD hatasının kökü tespit edildi:** THYAO finansallarını USD raporluyor
(`financialCurrency: USD`), hissesi TRY işlem görüyor. yfinance 296 TL fiyatı
15,53 **dolarlık** defter değerine bölüyor.

**Kapsam düzeltmesi (uygulama sırasında ölçüldü):** Bu spec'in ilk halinde
"EREGL, TUPRS vb." de USD raporlayan örnekler olarak gösterilmişti; **yanlıştı**.
15 büyük BIST hissesi tarandı, `financialCurrency != currency` olan **yalnızca
THYAO** çıktı. Uçtan uca karşılaştırma:

| Hisse | Bizim PD/DD | yfinance | Sapma |
|---|---|---|---|
| **THYAO** | **0,38** | **18,64** | **49x** |
| EREGL | 0,71 | 0,78 | ~1x |
| TUPRS | 1,72 | 1,64 | ~1x |
| GARAN | 1,24 | 1,13 | ~1x |
| ASELS | 5,97 | 5,77 | ~1x |

Hata dar ama gerçek ve BIST-100'ün en çok işlem gören hisselerinden birini
vuruyor. Tablo aynı zamanda oran katmanının doğruluk kanıtı: yfinance'ten
rastgele değil, **tam olarak para birimi uyuşmazlığının olduğu yerde**
ayrışıyor. Oranları kendimiz hesaplama kararı ayrıca zorunlu, çünkü TL
finansal tablolar (banka bilançosu dahil) zaten İş Yatırım'dan geliyor.

Gerçek değer İş Yatırım'dan doğrulandı: özkaynak **1.073.081.134.047 TL**,
hisse adedi 1.372.283.353 → defter değeri 781,96 TL → PD/DD = **0,38**.
yfinance'in sapması **49 kat**.

**Türk kaynakları canlı test edildi ve çalışıyor:**

| Kaynak | Test | Sonuç |
|---|---|---|
| İş Yatırım | THYAO bilanço | 147 kalem, TL |
| İş Yatırım | GARAN bilanço | 192 kalem, BDDK banka formatı |
| KAP | 3 günlük bildirim | HTTP 200, 909 kayıt |
| KAP | ASELS 120 gün (OID filtreli) | 35 bildirim, konu başlıklarıyla |

Karşılaştırma: yfinance GARAN'a 50 jenerik satır veriyor, İş Yatırım 192 satır
BDDK formatı veriyor.

**Sonuç:** İstenen veri (KAP bildirimleri, doğru TL oranlar, banka bilançosu)
hazır hiçbir uluslararası MCP'de yok. Veri katmanı kendimiz yazılacak.

**Önemli ayrım — yfinance tamamen elenmiş değildir.** Ölçümde *fiyatı* üç
hissede de doğru verdi; hatalı olan hazır *oran* ve *haber* alanlarıdır. Bu
yüzden `fiyat.py` kaynağı olarak yfinance kullanılır (anlık fiyat, geçmiş
OHLCV, teknik analiz girdisi); `info` sözlüğündeki `priceToBook`,
`trailingPE`, `dividendYield` gibi türetilmiş alanlar ve `news` **hiçbir
koşulda okunmaz**. Bu sınır `fiyat.py` içinde tek bir yerde uygulanır.

**Kabul edilen risk:** Kaynak siteler HTML/JSON şemalarını değiştirirse bakım
bizde. Karşı önlem: fixture tabanlı testler (bkz. §9) şema değişimini erken
yakalar.

### 3.2 MCP ayrı paket, transport stdio

MCP sunucusu botun içine gömülmez, ayrı bir Python paketi olur. Sebep: aynı
sunucu Claude Desktop'a da bağlanabilir; bot onun yalnızca bir istemcisidir.

Transport **stdio**: tek kullanıcı, tek makine. Bot MCP'yi alt süreç olarak
başlatır. HTTP sunucusu, port ve kimlik doğrulama gerekmez. VPS'e taşınırken
değişiklik gerekmez.

### 3.3 Model: NVIDIA NIM, seçim ölçümle yapılacak

OpenAI-uyumlu uç nokta: `https://integrate.api.nvidia.com/v1`. Tool calling
destekleyen adaylar: Nemotron-3-Super-120B, GLM 5.1, Kimi K2.

Varsayılan model tahminle değil ölçümle seçilir (bkz. §9, Katman 4). Model
`.env` üzerinden değiştirilebilir kalır.

### 3.4 Kalıcılık: SQLite (iki ayrı amaç)

`sqlite3` standart kütüphanede; bağımlılık maliyeti yok.

**Önbellek (MCP tarafı) — gerekçe kaynak korumak.** İş Yatırım verisini
"kişisel kullanım" için sunuyor ve aşırı istekte engelliyor; KAP WAF'ı 2
istek/sn üstünde bağlantıyı düşürüyor. Geliştirme sırasında sunucu onlarca kez
yeniden başlatılacak. Bellekteki önbellek her restart'ta sıfırlanır ve aynı
veriyi yüzlerce kez çekeriz; diskteki önbellek TTL boyunca bir kez çeker.

**Sohbet hafızası (bot tarafı).** Bot yeniden başladığında takip soruları
("peki özkaynağı?") çalışmaya devam eder; ayrıca hangi cevabın hangi veriye
bakılarak üretildiği sonradan sorgulanabilir. JSON dosyası elenmiştir: her
mesajda dosyanın tamamı yeniden yazılır ve yazma sırasında çökme dosyayı bozar.

---

## 4. Mimari

```
Telegram ──► ajan/       bot + NVIDIA function-calling döngüsü
                │  MCP (stdio)
                ▼
           bist_mcp/     FastMCP sunucusu (bağımsız paket)
                │
     ┌──────────┼───────────┬──────────┐
  İş Yatırım   KAP       yfinance    TCMB EVDS
  finansal   bildirim   yalnız fiyat   makro
   oranlar    profil      ve OHLCV
```

**Sınır kuralı:** `ajan/` MCP araçlarının nasıl çalıştığını bilmez, yalnızca
adlarını ve şemalarını görür. `bist_mcp/` Telegram'ı ve NVIDIA'yı bilmez.

### Dosya yapısı

```
Borsa Agent v2/
├─ .env / .env.example / .gitignore / requirements.txt / README.md
├─ bist_mcp/
│   ├─ sunucu.py          FastMCP giriş noktası, 16 araç tanımı
│   ├─ kaynaklar/
│   │   ├─ isyatirim.py   finansal tablo çekme, tablo grubu tespiti
│   │   ├─ kap.py         oturum ısıtma, OID çözümleme, bildirim sorgusu
│   │   ├─ fiyat.py       anlık ve geçmiş OHLCV (yfinance; türetilmiş alanlar yasak)
│   │   └─ tcmb.py        EVDS makro göstergeleri
│   ├─ hesap.py           oran hesapları — TL düzeltmesi burada
│   ├─ anlik_gorunum.py   tarama için toplu anlık görünüm (bkz. §7)
│   ├─ onbellek.py        SQLite TTL önbellek
│   └─ tests/
└─ ajan/
    ├─ bot.py             aiogram, admin kilidi, mesaj yönlendirme
    ├─ ajan.py            function-calling döngüsü, sistem promptu
    ├─ mcp_baglanti.py    MCP istemcisi (resmi mcp SDK)
    ├─ hafiza.py          SQLite sohbet geçmişi
    ├─ bicim.py           TL/yüzde/tarih biçimlendirme, 4096 bölme
    └─ tests/
```

---

## 5. Araç sözleşmesi — 16 araç

Araç adları ve açıklamaları Türkçedir; model Türkçe soruyla eşleştirir.

### Hisse çekirdek (9)

| Araç | Parametreler | Kaynak |
|---|---|---|
| `hisse_ara` | `isim` | KAP üye listesi |
| `anlik_fiyat` | `kod` | fiyat |
| `gecmis_fiyat` | `kod`, `baslangic`, `bitis?` | fiyat |
| `sirket_profili` | `kod` | KAP genel bilgi formu |
| `finansal_tablo` | `kod`, `tablo` (`bilanco`/`gelir`/`nakit`), `donem` (`yillik`/`ceyreklik`), `adet?`=2 | İş Yatırım |
| `finansal_oranlar` | `kod` | hesaplanır (§6.1) |
| `temettu_gecmisi` | `kod` | İş Yatırım + KAP |
| `kap_bildirimleri` | `kod`, `gun?`=90, `konu?` | KAP (OID filtreli) |
| `kap_bildirim_detay` | `bildirim_no` | KAP |

### Analiz ve piyasa (5)

| Araç | Parametreler |
|---|---|
| `teknik_analiz` | `kod` — RSI, MACD, MA(20/50/200), destek/direnç |
| `hisse_karsilastir` | `kodlar` (2-5 adet) |
| `sektor_karsilastirma` | `kod` |
| `hisse_tarama` | `fk_max?`, `fk_min?`, `pddd_max?`, `temettu_verimi_min?`, `piyasa_degeri_min?`, `sektor?`, `sirala?` (`fk`/`pddd`/`temettu_verimi`), `adet?`=20 — hepsi opsiyonel, verilenler VE ile birleşir |
| `endeks_verisi` | `endeks` — `XU100`, `XU030`, `XU050`, `XBANK`, `XUSIN`, `XUTEK`, `XUMAL` |

### Makro (2)

| Araç | Parametreler |
|---|---|
| `doviz_altin` | `varlik` — USDTRY, EURTRY, gram altın |
| `makro_gosterge` | `gosterge` — TÜFE, ÜFE, politika faizi, tahvil getirisi |

**Bilinçli olarak yok:** `analist_gorusu`. İş Yatırım ve KAP'ta güvenilir bir
kaynağı yoktur; veri kaynağı olmayan araç modeli yanıltır.

---

## 6. Ölçümden gelen zorunlu kurallar

Bu kurallar isteğe bağlı değildir; her biri ölçülmüş bir hataya karşılık gelir.

### 6.1 Oranlar hazır alandan okunmaz, hesaplanır

Hiçbir sağlayıcının hazır `priceToBook` / `trailingPE` alanı kullanılmaz.

```
defter_degeri_pay_basi = ozkaynak_TL / hisse_adedi      (İş Yatırım, TL)
PD/DD                  = fiyat_TL / defter_degeri_pay_basi
```

Gerekçe: yfinance THYAO için 18,64 veriyor, gerçek 0,38 (49 kat sapma), sebebi
TL fiyatı USD özkaynağa bölmesi.

**Regresyon testi zorunlu:** THYAO PD/DD sonucu 0,3-0,5 aralığında olmalı.

### 6.2 Finansal tablo grubu şirket tipine göre seçilir

İş Yatırım `financialGroup` parametresi: sanayi/ticaret `XI_29`, banka ve
finans `UFRS_K`. Yanlış grup **boş tablo** döndürür, hata vermez.

Birinci ipucu KAP şirket listesindeki `financialType` alanıdır: `BNK`, `SIG`,
`FFF`, `KTL` → `UFRS_K`; `SIR`, `HLD`, `GYO` → `XI_29`. Ölçümde altı büyük
bankanın hepsi `BNK` olarak doğru işaretli.

**Ama bu alan tek başına yeterli değildir:** 807 ticker'ın **315'inde boş**,
üstelik THYAO, EREGL ve TUPRS gibi büyük sanayi şirketleri de boş grupta.
Bu yüzden kural: `financialType` doluysa ona göre grup seçilir, boşsa `XI_29`
denenir; **hangi yoldan gelinirse gelinsin sonuç boşsa diğer grup denenir.**
Yedek deneme kaldırılamaz.

### 6.3 KAP şirket sorgusu OID ile yapılır

Ticker ile filtreleme yanlış sonuç verir. Ölçüm: 14 günlük genel sorgu 2.000
kayıt sınırına çarpıyor ve ASELS'in bildirimleri listeye hiç girmiyor.

**`member/filter/{kod}` OID çözümlemek için KULLANILMAZ.** Bu uç nokta ticker
değil **isim** araması yapar ve yanıtında `stockCode` alanı yoktur. Ölçüm:
`member/filter/GARAN` sekiz sonuç döndürüyor ve ilki "GARANTİ BBVA OPERASYONEL
KİRALAMA"; doğru şirket (TÜRKİYE GARANTİ BANKASI) sekizinci sırada. İlk sonucu
almak, GARAN sorulduğunda bir kiralama şirketinin bildirimlerini döndürür —
sessiz ve tespiti zor bir hata.

Doğru akış:

1. `GET /tr/api/company/items/IGS/A` → 757 şirket, tek istekte (0,44 sn).
   Yanıt `stockCode`, `mkkMemberOid`, `kapMemberTitle`, `financialType` içerir.
2. Ticker → OID indeksi bundan kurulur. **`stockCode` virgülle ayrılmış birden
   fazla kod tutabilir** (GARAN'ın değeri `"GARAN, TGB"`). Tam eşleşme aramak
   bankaların çoğunu kaybettirir — ölçümde GARAN, YKBNK, VAKBN, HALKB, ISCTR
   "bulunamadı" çıktı. Alan virgülle bölünüp her kod ayrı anahtar yapılır:
   757 şirket → **807 ticker**.
3. `POST /tr/api/disclosure/members/byCriteria` gövdesinde
   `mkkMemberOidList: [oid]`

Doğrulandı: ASELS 120 günde 35 bildirim, konu başlıklarıyla. Düzeltilmiş
indeksle altı büyük bankanın hepsi çözümleniyor.

### 6.4 KAP oturum ısıtma ve hız sınırı

API çağrısından önce `GET /tr/bildirim-sorgu` ile oturum çerezi alınır; yoksa
WAF bağlantıyı ~6 saniyede düşürür. `Referer` başlığı zorunlu. Hız tavanı
**2 istek/sn**.

### 6.5 Türkçe format

Sayı `1.234.567,89` (nokta binlik, virgül ondalık). KAP tarihi
`GG.AA.YYYY SS:DD:SS`. Yüzde `% 19,10`.

### 6.6 Windows konsol kodlaması

`PYTHONIOENCODING=utf-8` gerekir; konsol cp1252 kullandığı için Türkçe
karakterler log'a yazılırken `UnicodeEncodeError` verir. Bu oturumda
gözlemlendi.

---

## 7. Tarama ve sektör karşılaştırması — toplu anlık görünüm

`hisse_tarama` ve `sektor_karsilastirma` tek hissenin değil **tüm BIST'in**
verisine ihtiyaç duyar. Her sorguda ~750 şirketi tek tek çekmek hız sınırını
aşar ve engellenmeye yol açar.

**Çözüm:** MCP sunucusunun içinde arka plan görevi (dış zamanlayıcı yok).
Görünüm SQLite'a yazılır; tarama ve sektör karşılaştırması bu yerel tabloyu
okur, ağa çıkmaz.

Kapsam: **BIST-100**. BIST-100 dışı bir hisse sorulursa tekil araçlar
(`finansal_oranlar` vb.) yine çalışır; yalnızca tarama BIST-100 ile sınırlıdır
ve çıktıda bu belirtilir.

### 7.1 Tablo sütunları ve kaynakları

| Sütun | Kaynak | Çağrı maliyeti |
|---|---|---|
| `kod`, `unvan`, `mkk_oid`, `tip` | KAP şirket listesi | **1 istek, tümü için** |
| `fiyat` | yfinance toplu indirme | **1 istek, tümü için** |
| `temettu_12ay` | yfinance toplu indirme (`actions=True`) | **aynı istekte, bedava** |
| `hisse_adedi`, `sektor` | yfinance `info` | 1 istek/hisse |
| `ozkaynak_TL`, `net_kar_TL` | İş Yatırım MaliTablo | 1 istek/hisse |
| `pddd`, `fk`, `piyasa_degeri`, `temettu_verimi` | hesaplanır | — |

Ölçülen tekil süreler: İş Yatırım 0,31 sn · yfinance `info` 0,67 sn ·
KAP şirket listesi 0,44 sn (757 şirket) · yfinance toplu indirme 0,79 sn
(10 hisse, 1 yıl, temettü dahil).

### 7.2 İki kademeli tazeleme

Sütunların değişme hızı çok farklı: fiyat her gün değişir, özkaynak ve net kâr
çeyrekte bir, hisse adedi ve sektör neredeyse hiç. Hepsini her gün çekmek
gereksiz.

**Günlük — hafif tazeleme (~5 saniye).** Yalnızca yfinance toplu indirmesi:
fiyat ve son 12 ay temettüsü. Depodaki özkaynak/hisse adedi ile oranlar yeniden
hesaplanır. Toplam **2 istek** (toplu indirme + KAP listesi).

**Haftalık — tam yeniden kurulum (~75 saniye).** Yukarıdakilere ek olarak hisse
başına İş Yatırım (100 × 0,5 sn = 50 sn, 2 istek/sn sınırıyla) ve yfinance
`info` (100 × 0,67 sn = 67 sn). İki farklı sunucu olduğu için paralel koşar;
darboğaz `info` tarafı, toplam ≈ 75 sn. Ayrıca yeni çeyreklik bilanço tespit
edilirse (KAP'ta "Finansal Rapor" bildirimi) o hisse için tam tazeleme
sıradışı olarak tetiklenir.

Günlük iş 200 istek/gün değil **2 istek/gün**, haftalık iş 200 istek/hafta
üretir. Kaynak siteler üzerindeki yük ihmal edilebilir düzeydedir.

### 7.3 Tetikleme ve okuma

Sunucu açılışında görünümün yaşına bakılır: yoksa tam kurulum, bayatsa uygun
kademe **arka planda** çalışır (açılış bloklanmaz). Sonrasında görev günlük
tazelemeyi 19:00 TRT'de (kapanış sonrası) tekrarlar.

Okuma tarafı: `hisse_tarama` yerel tabloyu okur. Tablo 24 saatten eskiyse
cevaplanır ama tarihi belirtilir. Tablo hiç yoksa (ilk çalıştırma) o an kurulur
ve kullanıcıya bir dakikayı bulabileceği söylenir.

---

## 8. Bot katmanı ve veri akışı

### Bir mesajın yolculuğu

1. Telegram mesajı → `bot.py`, admin kilidi
2. "yazıyor…" göstergesi
3. `hafiza.py`'den geçmiş yüklenir
4. `ajan.py`: sistem promptu + geçmiş + mesaj → NVIDIA
5. Model araç isterse → MCP → kaynak → sonuç modele döner (**en fazla 5 tur**)
6. Model Türkçe cevabı üretir
7. `bicim.py` biçimlendirir, 4096 karakteri aşarsa cümle sınırından böler
8. Gönderilir, hafızaya yazılır

Tek turda birden fazla araç istenirse `asyncio.gather` ile eşzamanlı çalışır.
Tur limiti aşılırsa durdurulup eldeki veriyle cevaplanır.

### Sistem promptu

Her istekte yeniden üretilir:

- **Bugünün tarihi**, Türkiye saatiyle (`TRT = UTC+3` sabit). Bu olmadan
  "geçen hafta", "bu yıl" çalışmaz ve VPS UTC ise gün kayar.
- Araç haritası (fiyat → `anlik_fiyat`, tablo → `finansal_tablo`, …)
- **Veri yoksa uydurma** — araç boş dönerse eksikliği açıkça söyle
- Rakamın dönemini belirt ("2025 yıllık bilançosuna göre")
- Para birimini yaz, tarihleri `gün.ay.yıl` ver
- **Yatırım tavsiyesi verme** — veriyi ve yorumu sun, "al/sat" deme

### Önbellek TTL

| Veri | TTL |
|---|---|
| Anlık fiyat | 60 sn |
| Finansal tablo | 24 saat |
| KAP bildirim listesi | 5 dk |
| Şirket profili | 7 gün |
| Makro gösterge | 6 saat |

### Hafıza

SQLite (`sohbet.db`). Yalnızca son turun araç sonucu bağlama geri gönderilir;
daha eskiler düşer — takip soruları çalışır, bağlam tablolarla dolmaz. Araç
sonuçları hata ayıklama için yine de yazılır. Geçmiş 6.000 token'ı aşınca en
eski mesajlar düşer. `/sifirla` geçmişi temizler.

### Hata senaryoları

| Durum | Davranış |
|---|---|
| Kaynak siteye ulaşılamıyor | 3 deneme (artan bekleme), sonra net mesaj + log |
| KAP WAF bağlantıyı düşürdü | Oturum yeniden ısıtılır, bir kez tekrar denenir |
| Geçersiz sembol | Hata metni modele verilir, model alternatif önerir |
| Tablo grubu boş döndü | Diğer grup denenir, o da boşsa "veri yok" |
| Veri gerçekten yok | Model uydurmaz, boşluğu söyler |
| Çağrı 30 sn'yi aştı | Kesilir, kullanıcıya bildirilir |
| NVIDIA hatası / kota | Nazik mesaj + log; ham hata gösterilmez |
| Cevap 4096 karakteri aştı | Cümle sınırından bölünür |
| Arka arkaya mesaj | Kullanıcı başına kilit, kuyruğa alınır |

### Sırlar

`.env` (git'e girmez): `TELEGRAM_BOT_TOKEN`, `NVIDIA_API_KEY`, `NVIDIA_MODEL`,
`NVIDIA_BASE_URL`, `ADMIN_USER_ID`, `EVDS_API_KEY`, `LOG_LEVEL`.

`.gitignore`: `.env`, `*.db`, `__pycache__/`, `*.log`, `.venv/`

---

## 9. Test stratejisi

**Katman 1 — Birim (ağ yok).** Oran hesabı (THYAO PD/DD regresyonu), tablo
grubu tespiti, Türkçe sayı/tarih ayrıştırma, biçimlendirme, 4096 bölme,
önbellek TTL mantığı, araç şemalarının geçerliliği.

**Katman 2 — Fixture'lar.** Gerçek yanıtlar diske kaydedilir: THYAO bilanço
(sanayi, 147 kalem), GARAN bilanço (banka, 192 kalem), ASELS KAP bildirimleri,
verisi olmayan bir hisse. Kaynak şema değiştirirse Katman 3 kırılır ve erken
uyarı verir.

**Katman 3 — Entegrasyon (`pytest -m network`).** Canlı çağrılar: İş Yatırım
tablo döndürüyor mu, KAP OID çözümlemesi çalışıyor mu, UTF-8 bozulmadan
geliyor mu (`ÖZKAYNAKLAR` testi).

**Katman 4 — Araç seçim ve model karşılaştırması.** 20 Türkçe soru, her biri
için beklenen araç. Üç aday model (Nemotron-3-Super, GLM 5.1, Kimi K2) aynı
testten geçirilir; isabet, gecikme ve Türkçe kalitesi karşılaştırılır. Kazanan
`.env`'e varsayılan yazılır. **Hedef: 18/20.**

**Katman 5 — Duman testi.** Bot başlatılır, Telegram'dan §10 listesi elle
doğrulanır.

**Test edilmeyen:** Cevabın öznel kalitesi. Yalnızca araç seçimi ve verinin
doğru aktarımı ölçülür.

---

## 10. Elle doğrulama listesi

| # | Yaz | Beklenen | Neyi sınıyor |
|---|---|---|---|
| 1 | `/start` | Karşılama | Bağlantı |
| 2 | `THYAO kaç TL?` | Güncel fiyat | Araç seçimi + veri akışı |
| 3 | `THYAO'nun PD/DD'si kaç?` | **~0,38** — 18 DEĞİL | §6.1 oran düzeltmesi |
| 4 | `GARAN'ın bilançosu?` | BDDK formatı, dolu tablo | §6.2 tablo grubu |
| 5 | `ASELS'in son KAP açıklamaları?` | 2026 tarihli gerçek bildirimler | §6.3 OID filtresi |
| 6 | `THYAO 2 Ağustos'ta kaç TL'ydi?` | Kapalı gün ise en yakın işlem günü | Tarih mantığı |
| 7 | Soru 4'ten sonra `peki özkaynağı?` | Tabloyu yeniden çekmeden cevap | Hafızada son tur |
| 8 | `F/K'sı 10'un altında temettü veren hisseler` | Tablo + "BIST-100 ile sınırlı" notu | §7 toplu görünüm |
| 9 | Verisi olmayan bir hisse | "Veri bulunamadı" — uydurma yok | Boş veri işaretleme |
| 10 | `/sifirla` | Sıfırlandı | Hafıza temizleme |

**En kritikleri 3, 5 ve 9.** Bunlarda yanlış çıktı bir süzgecin bozulduğunu gösterir.

---

## 11. Çalıştırma

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env    # doldur
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python -m ajan.bot
```

MCP sunucusu bot tarafından alt süreç olarak başlatılır; ayrıca çalıştırmak
gerekmez. Claude Desktop'a bağlamak için `bist_mcp/sunucu.py` stdio komutu
olarak tanımlanır.

VPS aşaması yerel doğrulama sonrasına bırakılmıştır (systemd unit, `TRT`
sabiti, `Restart=always`).

---

## 12. Kapsam dışı (bilinçli)

- TEFAS fonları, kripto, ABD hisseleri
- Çoklu kullanıcı, kota, kullanıcı bazlı hız sınırı
- Fiyat alarmı, zamanlanmış bülten, portföy takibi
- BIST-100 dışı hisseler için tarama (tekil araçlar çalışır, tarama çalışmaz)
- KAP PDF eklerinin içeriği (bildirim özeti ve metni alınır, PDF ayrıştırılmaz)

## 13. Yapım sırası — iki aşama

Bu tasarım iki bağımsız parça içeriyor. Tek seferde yazılmaz; sırayla ve
aralarında doğrulama ile yapılır. Her aşama kendi implementasyon planını alır.

**Aşama 1 — `bist_mcp/` (önce bu).** MCP sunucusu, 16 araç, dört kaynak,
önbellek, toplu görünüm işi, Katman 1-3 testleri.

Aşama 1 bittiğinde sunucu **Claude Desktop'a bağlanıp elle denenir.** Bu
kritik: araçların doğru veri döndürdüğü, Telegram ve NVIDIA denklemin içine
girmeden önce doğrulanır. Bir hata çıkarsa nerede olduğu belirsiz kalmaz.

Aşama 1 çıktısı tek başına kullanışlıdır — bot hiç yazılmasa bile Claude
Desktop üzerinden BIST sorgulayabilirsin.

**Aşama 2 — `ajan/`.** Telegram botu, NVIDIA döngüsü, hafıza, biçimlendirme,
Katman 4 model karşılaştırması, Katman 5 duman testi.

Aşama 2'ye Aşama 1 elle doğrulanmadan geçilmez.

## 14. Açık noktalar

- `EVDS_API_KEY` TCMB'den alınmalı (ücretsiz, kayıt gerektirir). Alınmazsa
  `makro_gosterge` devre dışı kalır, diğer araçlar etkilenmez.
- NVIDIA anahtarı: `Desktop/nvidia api key/api.txt` boş (0 bayt). Yeni anahtar
  build.nvidia.com'dan üretilmeli.
- VPS dağıtımı ve `sohbet.db` yedeklemesi ikinci aşamada kararlaştırılacak.

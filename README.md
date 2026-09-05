# BIST MCP Sunucusu

BIST hisseleri, endeksler, döviz/altın ve TCMB makro göstergeleri için MCP
sunucusu. **16 araç**; veri İş Yatırım, KAP, yfinance ve TCMB EVDS'ten gelir.

Bu, iki aşamalı bir projenin **1. aşamasıdır**. 2. aşama (Telegram botu +
NVIDIA function-calling döngüsü) bu sunucu elle doğrulandıktan sonra yazılır.
Tasarım: `docs/superpowers/specs/2026-09-05-bist-telegram-agent-design.md`

## Kurulum

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env    # EVDS_API_KEY isteğe bağlı
```

## Test

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m pytest bist_mcp/              # 82 hızlı test, ağ yok
python -m pytest bist_mcp/ -m network   # 11 canlı test, ~10 sn
```

Windows konsolu cp1252 kullandığı için `PYTHONIOENCODING` gerekir; yoksa
Türkçe karakterler log'a yazılırken `UnicodeEncodeError` verir.

## Claude Desktop'a bağlama

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bist": {
      "command": "python",
      "args": ["-m", "bist_mcp.sunucu"],
      "cwd": "C:/Users/Taha/Desktop/Borsa Agent v2",
      "env": { "PYTHONIOENCODING": "utf-8" }
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

2. **KAP OID'si toplu şirket listesinden çözülür.** `member/filter` bir
   **isim aramasıdır**: `member/filter/GARAN` sekiz sonuç döndürüyor ve ilki
   "GARANTİ BBVA OPERASYONEL KİRALAMA"; doğru banka sekizinci sırada.

3. **`stockCode` virgüllü çoklu kod tutar** (`"GARAN, TGB"`). Bölünmeden
   eşleştirilirse GARAN, YKBNK, VAKBN, HALKB, ISCTR kaybolur.
   757 şirket → **807 ticker**.

4. **Dönem takvimle hesaplanamaz.** 2026-09-05'te `2026/12` ve `2026/9` boş
   döner (henüz yayımlanmadı). Aday dönemler istenir, tamamen boş slotlar
   atılır. Değerler satır bazında değil **slot bazında** hizalanır.

5. **İş Yatırım değerleri STRING döner** (`'1073081134047'`). Çevrilmezse
   oran hesabı bölemez ve `'0' != 0` olduğu için sıfır satırları atılmaz.

6. **Bilanço/gelir/nakit tek listede gelir**, ayrı tablolar halinde değil.
   Bölme işaretleri: `TOPLAM KAYNAKLAR` (sanayi) / `PASİF TOPLAMI` (banka)
   bilançonun sonu, `İşletme Faaliyetlerinden Kaynaklanan Net Nakit` nakit
   akışının başı. **Bankalarda nakit akış tablosu yoktur.**

7. **Tarama BIST-100 ile sınırlıdır** ve çıktı bunu belirtir.

## Hız sınırları

KAP ve İş Yatırım için **2 istek/sn**. KAP'ta API çağrısından önce
`/tr/bildirim-sorgu`'ya GET ile oturum çerezi alınır; yoksa WAF bağlantıyı
~6 saniyede düşürür.

Önbellek **tembeldir**: hiçbir şeyi kendiliğinden çekmez, yalnızca sorulduğunda
çeker ve TTL boyunca saklar. Tek istisna tarama tablosudur (aşağıda).

## Tarama tablosu (arka plan)

`hisse_tarama` ve `sektor_karsilastirma` tüm BIST-100'ün verisine ihtiyaç
duyar; her soruda 100 şirketi çekmek hız sınırını aşar. Bu yüzden sunucu
içinde arka plan görevi tabloyu iki kademede taze tutar:

| Kademe | Süre | İstek | Ne çeker |
|---|---|---|---|
| Günlük | ~5 sn | 2 | Fiyat + son 12 ay temettü (toplu indirme) |
| Haftalık | ~75 sn | ~200 | Üstüne İş Yatırım finansalları + hisse adedi/sektör |

Ölçüldü: 5 hisselik tam kurulum 3,7 sn → 100 hisse ~74 sn.

## Bilinen eksikler

- **`makro_gosterge` EVDS anahtarı ister.** `EVDS_API_KEY` yoksa açıklayıcı
  mesaj döner, diğer 15 araç etkilenmez. Anahtar
  [evds2.tcmb.gov.tr](https://evds2.tcmb.gov.tr) üzerinden ücretsiz alınır.
  **EVDS seri kodları canlı doğrulanmadı** (anahtar olmadığı için istek
  atılamadı); yanlış kod boş kayıt döndürür, sessizce yanlış sayı döndürmez.
- **`bist100.py` listesi son endeks revizyonuna göre doğrulanmadı.** Yanlış
  kod yalnızca o hisseyi taramadan düşürür.
- Döviz/altın EVDS değil **yfinance** kullanır, yani anahtarsız çalışır.
  Gram altın ons fiyatı × USD/TRY ÷ 31,1035 ile hesaplanır; dayanak değerler
  cevapta yer alır.

# Borsa Agent v2

BIST verisi için **kendi MCP sunucumuzu** (`bist`) yazıyoruz. Telegram botu da
onu kullanacak.

## Hangi veri kaynağı kullanılır

**Bu projede BIST soruları `bist` MCP sunucusuyla cevaplanır.**

Ortamda `borsa` adında başka bir MCP sunucusu (`borsa.surucu.dev`) ve onu
kullanan `borsaci` adında bir skill var. İkisi de başka projeler için duruyor;
**bu projede kullanılmaz.** BIST ile ilgili bir soru geldiğinde `/borsaci`
skill'ini çalıştırma ve `borsa` sunucusunun araçlarını çağırma — `mcp__bist__*`
araçlarını kullan.

Gerekçe teknik: `bist` sunucusu oranları İş Yatırım'ın TL rakamlarıyla kendisi
hesaplıyor. Hazır oran alanları BIST'te bozuk — THYAO için `priceToBook` 18,64
diyorlar, gerçek değer 0,38 (49 kat hata; şirket finansallarını USD raporluyor,
hissesi TRY işlem görüyor). İki kaynağı karıştırmak bu farkı gizler.

## Proje yapısı

- `bist_mcp/` — MCP sunucusu (Aşama 1, tamamlandı). 17 araç.
- `ajan/` — Telegram botu + NVIDIA function-calling döngüsü (Aşama 2, planlandı).
- `docs/superpowers/specs/` — tasarım dokümanı
- `docs/superpowers/plans/` — implementasyon planları

Telegram botu `bist` sunucusunu alt süreç olarak başlatır ve NVIDIA'ya yalnızca
onun araçlarını verir; `borsa`/`borsaci` bot tarafında zaten devrede değildir.

## Sırlar

- **Gerçek anahtarlar `.env` dosyasına yazılır** — bu dosya `.gitignore`'da.
- `.env.example` git'te takip edilen **boş şablondur**; oraya gerçek değer yazılmaz.

## Çalıştırma

```powershell
$env:PYTHONIOENCODING = "utf-8"   # Windows konsolu cp1252; olmadan Türkçe log çöker
python -m pytest bist_mcp/              # hızlı testler
python -m pytest bist_mcp/ -m network   # canlı testler
```

## Bilinmesi gerekenler

Ölçümden gelen veri kuralları ve bilinen eksikler `README.md`'de. Kod
değiştirirken oradaki regresyon testlerini bozma — her biri canlı ölçülmüş bir
hataya karşılık geliyor.

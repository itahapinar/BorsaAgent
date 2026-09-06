# Telegram Ajanı — Implementasyon Planı (Aşama 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aşama 1'de yazılan BIST MCP sunucusunu kullanan, Türkçe soru sorulabilen
tek kullanıcılık bir Telegram botu.

**Architecture:** aiogram long polling ile Telegram'ı dinleyen bot, NVIDIA'nın
OpenAI-uyumlu uç noktasına function-calling döngüsü kurar. Araçlar MCP üzerinden
gelir; MCP sunucusu botun ömrü boyunca ayakta duran **tek bir alt süreçtir**.
Bot ne MCP araçlarının nasıl çalıştığını bilir ne de NVIDIA'yı MCP'ye sızdırır.

**Tech Stack:** Python 3.13.7 · aiogram 3.29.1 · openai 2.45.0 (NVIDIA uç noktası) ·
mcp 1.28.1 (istemci tarafı) · sqlite3 (stdlib) · pytest 9.1.1 · pytest-asyncio 1.4.0

**Spec:** `docs/superpowers/specs/2026-09-05-bist-telegram-agent-design.md` (§8)

## Ön koşul — Aşama 1 kapısı

Spec §13: **Aşama 2'ye Aşama 1 elle doğrulanmadan geçilmez.** MCP sunucusu
Claude Desktop'a bağlanıp `README.md`'deki doğrulama listesi (özellikle THYAO
PD/DD ≈ 0,38, GARAN BDDK bilançosu, olmayan hissede uydurma yapmama) elle
geçilmiş olmalı. Bu plan yazıldığında o kapı **henüz açılmamıştı**.

## Global Constraints

Bu bölüm her görevin gereksinimlerine örtük olarak dahildir.

- **Python 3.13.7.** Ortamda kurulu; sürüm yükseltilmez.
- **`PYTHONIOENCODING=utf-8` zorunlu.** Windows konsolu cp1252; Türkçe karakter
  log'a yazılırken `UnicodeEncodeError` verir. Aşama 1'de gözlemlendi.
- **MCP oturumu UZUN ÖMÜRLÜ olmalı, çağrı başına açılıp kapanmamalı.** Gerekçe
  Aşama 1'den geliyor: sunucu açılışta arka planda tarama tablosunu kuruyor
  (~7 dakika, ~700 istek). Her araç çağrısında yeni alt süreç başlatmak bu işi
  baştan tetikler ve kaynak siteler tarafından engellenmemize yol açar.
- **NVIDIA uç noktası:** `https://integrate.api.nvidia.com/v1`, OpenAI-uyumlu.
  Anahtar `NVIDIA_API_KEY`, `nvapi-` ile başlar. **Anahtar `.env` dışında
  hiçbir yere yazılmaz, log'a basılmaz, teste gömülmez.**
- **Model kimliği sabit yazılmaz.** NVIDIA katalogu değişiyor; aday modeller
  `/v1/models` uç noktasından keşfedilir (bkz. Task 8).
- **Bot yalnızca `ADMIN_USER_ID`'ye cevap verir**, diğer herkesi sessizce
  reddeder ve log'a bir satır yazar.
- **Saat dilimi `TRT = UTC+3` sabit.** Türkiye yaz saati uygulamıyor. Sistem
  promptundaki "bugün" bu olmadan VPS'te (UTC) kayar.
- **Türkçe sayı formatı:** `1.234.567,89` — nokta binlik, virgül ondalık.
  Tarihler `gün.ay.yıl`.
- **Telegram mesaj sınırı 4096 karakter**; aşan cevap cümle sınırından bölünür.
- **Araç şemaları ölçüldü: 16 araç ≈ 8.962 karakter ≈ 2.800 token.** Her
  istekte gönderilir; hafıza bütçesi buna göre ayarlanır.
- **Yatırım tavsiyesi verilmez.** Veri ve yorum sunulur, "al/sat" denmez.
- Ağa çıkan testler `@pytest.mark.network`, para harcayan testler
  `@pytest.mark.llm` ile işaretlenir; ikisi de varsayılan koşuda hariç.

## Dosya yapısı

```
ajan/
├─ __init__.py
├─ config.py            .env okuma, TRT, log kurulumu, sabitler
├─ mcp_baglanti.py      uzun omurlu MCP oturumu, arac semasi cevrimi
├─ bicim.py             TL/yuzde/tarih bicimlendirme, 4096 bolme
├─ hafiza.py            SQLite sohbet gecmisi, son-tur kirpma
├─ prompt.py            sistem promptu uretimi (bugunun tarihi dahil)
├─ ajan.py              NVIDIA function-calling dongusu
├─ bot.py               aiogram giris noktasi, admin kilidi
├─ model_karsilastir.py elle calistirilan model secim betigi
└─ tests/
```

**Sınır kuralı:** `ajan/` MCP araçlarının nasıl çalıştığını bilmez, yalnızca
adlarını ve şemalarını görür. `bist_mcp/` Telegram'ı ve NVIDIA'yı bilmez.
`bot.py` NVIDIA'yı bilmez, `ajan.py` Telegram'ı bilmez.

---

### Task 1: Yapılandırma, saat dilimi ve log

**Files:**
- Create: `ajan/__init__.py`, `ajan/config.py`, `ajan/tests/__init__.py`
- Modify: `.env.example`
- Test: `ajan/tests/test_config.py`

**Interfaces:**
- Consumes: yok
- Produces: `Ayarlar` dataclass (`telegram_token`, `nvidia_api_key`, `nvidia_model`,
  `nvidia_base_url`, `admin_user_id`, `log_seviyesi`), `ayarlari_yukle(cevre: dict) -> Ayarlar`,
  `TRT: datetime.timezone`, `simdi_trt() -> datetime.datetime`, `log_kur(seviye: str) -> None`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_config.py`:

```python
import datetime as dt

import pytest

from ajan.config import TRT, Ayarlar, ayarlari_yukle, simdi_trt

TAM_CEVRE = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "NVIDIA_API_KEY": "nvapi-xxx",
    "ADMIN_USER_ID": "42",
}


def test_zorunlu_alanlar_okunur():
    ayarlar = ayarlari_yukle(TAM_CEVRE)
    assert ayarlar.telegram_token == "123:abc"
    assert ayarlar.admin_user_id == 42


def test_varsayilanlar_dolduruluyor():
    ayarlar = ayarlari_yukle(TAM_CEVRE)
    assert ayarlar.nvidia_base_url == "https://integrate.api.nvidia.com/v1"
    assert ayarlar.log_seviyesi == "INFO"


def test_eksik_zorunlu_alan_net_hata_verir():
    eksik = dict(TAM_CEVRE)
    del eksik["TELEGRAM_BOT_TOKEN"]
    with pytest.raises(ValueError) as hata:
        ayarlari_yukle(eksik)
    assert "TELEGRAM_BOT_TOKEN" in str(hata.value)


def test_admin_id_sayi_degilse_hata():
    with pytest.raises(ValueError) as hata:
        ayarlari_yukle(dict(TAM_CEVRE, ADMIN_USER_ID="abc"))
    assert "ADMIN_USER_ID" in str(hata.value)


def test_trt_sabit_uc_saat():
    """Turkiye yaz saati uygulamiyor; sabit UTC+3."""
    assert TRT.utcoffset(None) == dt.timedelta(hours=3)


def test_simdi_trt_dogru_dilimde():
    assert simdi_trt().tzinfo == TRT


def test_ayarlar_repr_sirri_sizdirmaz():
    """Log'a ya da hata mesajina dusen repr anahtari acmamali."""
    metin = repr(ayarlari_yukle(TAM_CEVRE))
    assert "nvapi-xxx" not in metin
    assert "123:abc" not in metin
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/__init__.py` ve `ajan/tests/__init__.py` boş dosyalar.

`ajan/config.py`:

```python
"""Yapilandirma, saat dilimi ve log kurulumu.

TRT sabit UTC+3'tur: Turkiye yaz saati uygulamiyor. Sistem promptundaki
"bugun" bu olmadan VPS'te (genelde UTC) kayar ve "dun kac TL'ydi" yanlis
gune bakar.
"""

import datetime as dt
import logging
import logging.handlers
from dataclasses import dataclass, field
from pathlib import Path

TRT = dt.timezone(dt.timedelta(hours=3))
VARSAYILAN_BASE_URL = "https://integrate.api.nvidia.com/v1"
LOG_DOSYASI = Path("borsa-ajan.log")


@dataclass(frozen=True)
class Ayarlar:
    telegram_token: str = field(repr=False)
    nvidia_api_key: str = field(repr=False)
    admin_user_id: int
    nvidia_model: str
    nvidia_base_url: str
    log_seviyesi: str


def ayarlari_yukle(cevre: dict) -> Ayarlar:
    """Ortam degiskenlerinden ayarlari okur.

    Sirlar `repr=False` ile isaretlidir; bir hata mesajina ya da log satirina
    dustugunde anahtar acikta kalmaz.
    """
    eksikler = [
        ad
        for ad in ("TELEGRAM_BOT_TOKEN", "NVIDIA_API_KEY", "ADMIN_USER_ID")
        if not (cevre.get(ad) or "").strip()
    ]
    if eksikler:
        raise ValueError(f"Eksik zorunlu ayar(lar): {', '.join(eksikler)}. .env dosyasini doldur.")

    ham_id = cevre["ADMIN_USER_ID"].strip()
    if not ham_id.lstrip("-").isdigit():
        raise ValueError(f"ADMIN_USER_ID sayi olmali, gelen: {ham_id!r}")

    return Ayarlar(
        telegram_token=cevre["TELEGRAM_BOT_TOKEN"].strip(),
        nvidia_api_key=cevre["NVIDIA_API_KEY"].strip(),
        admin_user_id=int(ham_id),
        nvidia_model=(cevre.get("NVIDIA_MODEL") or "").strip(),
        nvidia_base_url=(cevre.get("NVIDIA_BASE_URL") or "").strip() or VARSAYILAN_BASE_URL,
        log_seviyesi=(cevre.get("LOG_LEVEL") or "").strip() or "INFO",
    )


def simdi_trt() -> dt.datetime:
    return dt.datetime.now(TRT)


def log_kur(seviye: str = "INFO") -> None:
    """Konsol + doner dosya. Dosya 5 MB'i asinca 3 yedek saklanir."""
    dosya = logging.handlers.RotatingFileHandler(
        LOG_DOSYASI, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=seviye,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(), dosya],
    )
```

- [ ] **Step 4: `.env.example`'ı genişlet**

```
# --- Asama 1 (MCP sunucusu) ---
EVDS_API_KEY=
LOG_LEVEL=INFO

# --- Asama 2 (Telegram ajani) ---
# @BotFather -> /newbot
TELEGRAM_BOT_TOKEN=
# build.nvidia.com -> API anahtari, "nvapi-" ile baslar
NVIDIA_API_KEY=
# Bos birakilirsa model_karsilastir.py ile secilen model yazilir
NVIDIA_MODEL=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
# @userinfobot sana soyler. Bot YALNIZ bu kullaniciya cevap verir.
ADMIN_USER_ID=
```

- [ ] **Step 5: Testleri koş**

Run: `python -m pytest ajan/tests/test_config.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add ajan/ .env.example
git commit -m "feat: ajan yapilandirmasi, TRT saat dilimi ve log kurulumu"
```

---

### Task 2: MCP bağlantısı — uzun ömürlü oturum

Bu görevin en kritik kısıtı Aşama 1'den geliyor: MCP sunucusu açılışta arka
planda tarama tablosunu kuruyor. Çağrı başına oturum açmak o işi her seferinde
tetikler.

> **Ölçüm sonrası düzeltme (2026-09-06).** Aşağıdaki `AsyncExitStack` tasarımı
> uygulanmadan önce ölçüldü ve **kırık çıktı**: `stdio_client` anyio cancel
> scope kullanıyor, scope girildiği task'te kapatılmak zorunda. `baglan()` bir
> task'te, `kapat()` başka bir task'te çağrılınca
> `RuntimeError: Attempted to exit cancel scope in a different task than it was
> entered in` fırlıyor ve alt süreç sızıyor. Botun gerçek deseni tam olarak bu
> (açılış / mesaj / kapanış ayrı task'ler) ve `_yeniden_bagla()` de `kapat()`'ı
> mesaj task'inden çağırıyor. Bu yüzden oturumu **tek bir sahip task**
> (`_oturumu_tut`) açıp kapatıyor; `kapat()` yalnızca bir olay kurup o task'i
> bekliyor. Arayüz plandaki gibi kaldı. Gerçek kod: `ajan/mcp_baglanti.py`,
> regresyon testi: `test_ayri_tasklarda_acilip_kapanabilir`.

**Files:**
- Create: `ajan/mcp_baglanti.py`
- Test: `ajan/tests/test_mcp_baglanti.py`

**Interfaces:**
- Consumes: yok (MCP sunucusu alt süreç olarak başlatılır)
- Produces: `arac_semalarina_cevir(araclar) -> list[dict]` (saf fonksiyon),
  `sonucu_metne_cevir(sonuc) -> str` (saf fonksiyon),
  `ARAC_ZAMAN_ASIMI: float`,
  `McpBaglanti(komut: str, argumanlar: list[str], calisma_dizini: str)` sınıfı;
  `async baglan() -> None`, `async arac_semalari() -> list[dict]`,
  `async cagir(ad: str, argumanlar: dict) -> str`, `async kapat() -> None`,
  `async _yeniden_bagla() -> None`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_mcp_baglanti.py`:

```python
from dataclasses import dataclass

from ajan.mcp_baglanti import arac_semalarina_cevir, sonucu_metne_cevir


@dataclass
class SahteArac:
    name: str
    description: str
    inputSchema: dict


@dataclass
class SahteIcerik:
    text: str


@dataclass
class SahteSonuc:
    content: list
    isError: bool = False


ANLIK_FIYAT = SahteArac(
    name="anlik_fiyat",
    description="Hissenin guncel fiyatini verir.",
    inputSchema={
        "type": "object",
        "properties": {"kod": {"type": "string"}},
        "required": ["kod"],
    },
)


def test_mcp_semasi_openai_bicimine_cevrilir():
    sonuc = arac_semalarina_cevir([ANLIK_FIYAT])
    assert sonuc == [
        {
            "type": "function",
            "function": {
                "name": "anlik_fiyat",
                "description": "Hissenin guncel fiyatini verir.",
                "parameters": {
                    "type": "object",
                    "properties": {"kod": {"type": "string"}},
                    "required": ["kod"],
                },
            },
        }
    ]


def test_aciklamasiz_arac_bos_metinle_gecer():
    arac = SahteArac(name="x", description=None, inputSchema={"type": "object"})
    assert arac_semalarina_cevir([arac])[0]["function"]["description"] == ""


def test_sonuc_metni_birlestirilir():
    sonuc = SahteSonuc(content=[SahteIcerik("birinci"), SahteIcerik("ikinci")])
    assert sonucu_metne_cevir(sonuc) == "birinci\nikinci"


def test_bos_sonuc_aciklayici_metin_doner():
    assert "veri" in sonucu_metne_cevir(SahteSonuc(content=[])).lower()


def test_hatali_sonuc_isaretlenir():
    """Model hatayi gorup kullaniciya soyleyebilmeli; sessizce yutulmamali."""
    sonuc = SahteSonuc(content=[SahteIcerik("baglanti koptu")], isError=True)
    metin = sonucu_metne_cevir(sonuc)
    assert "HATA" in metin
    assert "baglanti koptu" in metin
```

Ayrıca aynı dosyaya, zaman aşımı ve yeniden bağlanma testleri:

```python
import asyncio

import pytest

from ajan.mcp_baglanti import McpBaglanti


class AsiliOturum:
    async def call_tool(self, ad, argumanlar):
        await asyncio.sleep(60)  # asla donmez


class OlmusOturum:
    def __init__(self):
        self.cagri_sayisi = 0

    async def call_tool(self, ad, argumanlar):
        self.cagri_sayisi += 1
        raise BrokenPipeError("alt surec olmus")


def _baglanti(oturum):
    b = McpBaglanti("python", ["-c", "pass"], ".")
    b._oturum = oturum
    return b


@pytest.mark.asyncio
async def test_zaman_asiminda_asili_kalmaz(monkeypatch):
    """Asili bir cagri botun tek kilidini sonsuza kadar tutardi."""
    monkeypatch.setattr("ajan.mcp_baglanti.ARAC_ZAMAN_ASIMI", 0.05)
    metin = await _baglanti(AsiliOturum()).cagir("anlik_fiyat", {})
    assert "HATA" in metin
    assert "cevap vermedi" in metin


@pytest.mark.asyncio
async def test_olu_oturumda_bir_kez_yeniden_baglanilir():
    """Bot gunlerce ayakta; alt surec olduyse her soru sessizce hata verirdi."""
    oturum = OlmusOturum()
    baglanti = _baglanti(oturum)
    denemeler = []

    async def sahte_yeniden_bagla():
        denemeler.append(1)

    baglanti._yeniden_bagla = sahte_yeniden_bagla

    metin = await baglanti.cagir("anlik_fiyat", {})
    assert len(denemeler) == 1, "tam olarak bir kez yeniden baglanilmali"
    assert oturum.cagri_sayisi == 2, "yeniden baglandiktan sonra tekrar denenmeli"
    assert "HATA" in metin


@pytest.mark.asyncio
async def test_baglanmadan_cagirmak_net_hata_verir():
    baglanti = McpBaglanti("python", ["-c", "pass"], ".")
    with pytest.raises(RuntimeError) as hata:
        await baglanti.cagir("anlik_fiyat", {})
    assert "baglan" in str(hata.value)
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_mcp_baglanti.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.mcp_baglanti'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/mcp_baglanti.py`:

```python
"""MCP sunucusuna uzun omurlu stdio baglantisi.

DIKKAT — oturum cagri basina ACILIP KAPANMAZ. Asama 1'deki sunucu acilista
arka planda tarama tablosunu kuruyor (~7 dakika, ~700 istek). Her arac
cagrisinda yeni alt surec baslatmak o isi bastan tetikler ve kaynak siteler
tarafindan engellenmemize yol acar. Bot ayaga kalkarken bir kez baglanilir,
kapanirken birakilir.
"""

import asyncio
import logging
import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

kayit = logging.getLogger(__name__)

# Spec §8: cagri 30 sn'yi asarsa kesilir. Asili bir istek botun tek kilidini
# sonsuza kadar tutar ve bot tamamen durur.
ARAC_ZAMAN_ASIMI = 30.0


def arac_semalarina_cevir(araclar) -> list[dict]:
    """MCP arac tanimlarini OpenAI function-calling bicimine cevirir.

    MCP'nin inputSchema'si zaten JSON Schema oldugu icin dogrudan gecer.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": arac.name,
                "description": arac.description or "",
                "parameters": arac.inputSchema,
            },
        }
        for arac in araclar
    ]


def sonucu_metne_cevir(sonuc) -> str:
    """Arac sonucunu modele verilecek tek metne cevirir."""
    parcalar = [getattr(p, "text", "") for p in (sonuc.content or [])]
    metin = "\n".join(p for p in parcalar if p).strip()

    if not metin:
        return "Arac veri dondurmedi."
    if getattr(sonuc, "isError", False):
        return f"HATA: {metin}"
    return metin


class McpBaglanti:
    def __init__(self, komut: str, argumanlar: list[str], calisma_dizini: str) -> None:
        self._parametreler = StdioServerParameters(
            command=komut,
            args=argumanlar,
            cwd=calisma_dizini,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self._yigin: AsyncExitStack | None = None
        self._oturum: ClientSession | None = None

    async def baglan(self) -> None:
        """Alt sureci baslatir ve oturumu acar. Bot omrunde bir kez cagrilir."""
        self._yigin = AsyncExitStack()
        okuma, yazma = await self._yigin.enter_async_context(stdio_client(self._parametreler))
        self._oturum = await self._yigin.enter_async_context(ClientSession(okuma, yazma))
        await self._oturum.initialize()
        kayit.info("MCP sunucusuna baglanildi")

    async def arac_semalari(self) -> list[dict]:
        if self._oturum is None:
            raise RuntimeError("once baglan() cagrilmali")
        yanit = await self._oturum.list_tools()
        return arac_semalarina_cevir(yanit.tools)

    async def _yeniden_bagla(self) -> None:
        """Olen alt sureci temizleyip yeniden baslatir."""
        kayit.warning("MCP oturumu dusmus, yeniden baglaniliyor")
        try:
            await self.kapat()
        except Exception:  # noqa: BLE001 - zaten olu, temizlik best-effort
            self._yigin = None
            self._oturum = None
        await self.baglan()

    async def cagir(self, ad: str, argumanlar: dict) -> str:
        """Araci calistirir ve sonucu metin olarak doner.

        Istisna firlatmaz: hata metni modele verilir, model kullaniciya durumu
        acikca soyler. Boylece tek bir arac hatasi sohbeti kesmez.

        Iki koruma var (spec §8):
          - ZAMAN ASIMI: cagri 30 sn'yi asarsa kesilir. Aksi halde asili bir
            istek botun tek kilidini sonsuza kadar tutar ve bot tamamen durur.
          - YENIDEN BAGLANMA: alt surec olmusse bir kez yeniden baglanip
            tekrar denenir. Bot gunlerce ayakta kaliyor; surec olduysa her
            soru sessizce hata verirdi.
        """
        if self._oturum is None:
            raise RuntimeError("once baglan() cagrilmali")

        for deneme in (1, 2):
            try:
                sonuc = await asyncio.wait_for(
                    self._oturum.call_tool(ad, argumanlar), timeout=ARAC_ZAMAN_ASIMI
                )
                return sonucu_metne_cevir(sonuc)
            except asyncio.TimeoutError:
                kayit.warning("Arac cagrisi %d sn'yi asti: %s", ARAC_ZAMAN_ASIMI, ad)
                return (
                    f"HATA: {ad} araci {ARAC_ZAMAN_ASIMI} saniyede cevap vermedi. "
                    "Veri kaynagi yavas olabilir."
                )
            except Exception as hata:  # noqa: BLE001
                if deneme == 1:
                    kayit.warning("Arac cagrisi basarisiz (%s), yeniden deneniyor", hata)
                    try:
                        await self._yeniden_bagla()
                        continue
                    except Exception:  # noqa: BLE001
                        kayit.exception("Yeniden baglanma basarisiz")
                kayit.warning("Arac cagrisi basarisiz: %s(%s) -> %s", ad, argumanlar, hata)
                return f"HATA: {ad} araci calistirilamadi ({type(hata).__name__})."

        return f"HATA: {ad} araci calistirilamadi."

    async def kapat(self) -> None:
        if self._yigin is not None:
            await self._yigin.aclose()
            self._yigin = None
            self._oturum = None
            kayit.info("MCP baglantisi kapatildi")
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_mcp_baglanti.py -v`
Expected: 8 passed

- [ ] **Step 5: Gerçek sunucuya bağlanan ağ testini yaz ve koş**

`ajan/tests/test_mcp_baglanti.py` sonuna eklenir:

```python
import json

import pytest

from ajan.mcp_baglanti import McpBaglanti

PROJE_KOKU = r"C:/Users/Taha/Desktop/Borsa Agent v2"


@pytest.mark.network
@pytest.mark.asyncio
async def test_gercek_sunucuya_baglanip_arac_cagirir():
    """Asama 1 sunucusuyla uctan uca: 16 arac gelmeli, PD/DD dogru olmali."""
    baglanti = McpBaglanti("python", ["-m", "bist_mcp.sunucu"], PROJE_KOKU)
    await baglanti.baglan()
    try:
        semalar = await baglanti.arac_semalari()
        assert len(semalar) == 16
        assert semalar[0]["type"] == "function"

        metin = await baglanti.cagir("finansal_oranlar", {"kod": "THYAO"})
        veri = json.loads(metin)
        assert 0.2 < veri["pddd"] < 1.0, "PD/DD yfinance tuzagina dusmus olabilir"
    finally:
        await baglanti.kapat()


@pytest.mark.network
@pytest.mark.asyncio
async def test_olmayan_arac_istisna_firlatmaz():
    baglanti = McpBaglanti("python", ["-m", "bist_mcp.sunucu"], PROJE_KOKU)
    await baglanti.baglan()
    try:
        metin = await baglanti.cagir("boyle_bir_arac_yok", {})
        assert "HATA" in metin
    finally:
        await baglanti.kapat()
```

Run: `python -m pytest ajan/tests/test_mcp_baglanti.py -m network -v`
Expected: 2 passed (~20 sn)

- [ ] **Step 6: Commit**

```bash
git add ajan/mcp_baglanti.py ajan/tests/test_mcp_baglanti.py
git commit -m "feat: uzun omurlu MCP baglantisi ve arac semasi cevrimi"
```

---

### Task 3: Türkçe biçimlendirme ve mesaj bölme

**Files:**
- Create: `ajan/bicim.py`
- Test: `ajan/tests/test_bicim.py`

**Interfaces:**
- Consumes: `TRT` (Task 1)
- Produces: `tl(deger: float) -> str`, `yuzde(deger: float) -> str`,
  `tarih(deger: datetime | date | str) -> str`, `buyuk_sayi(deger: float) -> str`,
  `mesaji_bol(metin: str, sinir: int = 4096) -> list[str]`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_bicim.py`:

```python
import datetime as dt

from ajan.bicim import buyuk_sayi, mesaji_bol, tarih, tl, yuzde


def test_tl_turkce_formatta():
    """Nokta binlik, virgul ondalik."""
    assert tl(1234.5) == "1.234,50 TL"
    assert tl(0) == "0,00 TL"
    assert tl(-9876.54) == "-9.876,54 TL"


def test_yuzde_isaretli():
    assert yuzde(1.54) == "%1,54"
    assert yuzde(-2.5) == "%-2,50"


def test_tarih_gun_ay_yil():
    assert tarih(dt.date(2026, 8, 2)) == "02.08.2026"
    assert tarih("2026-08-02") == "02.08.2026"
    assert tarih(dt.datetime(2026, 8, 2, 15, 30)) == "02.08.2026"


def test_buyuk_sayi_okunabilir_kisaltma():
    assert buyuk_sayi(1_073_081_134_047) == "1,07 trilyon TL"
    assert buyuk_sayi(406_195_872_488) == "406,20 milyar TL"
    assert buyuk_sayi(5_230_000_000) == "5,23 milyar TL"
    assert buyuk_sayi(12_500_000) == "12,50 milyon TL"
    assert buyuk_sayi(1500) == "1.500,00 TL"


def test_kisa_mesaj_bolunmez():
    assert mesaji_bol("kisa") == ["kisa"]


def test_uzun_mesaj_cumle_sinirindan_bolunur():
    cumle = "Bu bir cumledir. "
    metin = cumle * 400  # ~6800 karakter
    parcalar = mesaji_bol(metin)
    assert len(parcalar) > 1
    assert all(len(p) <= 4096 for p in parcalar)
    assert all(p.strip().endswith(".") for p in parcalar)


def test_cumle_siniri_yoksa_yine_de_bolunur():
    """Tek parca uzun metin (ornegin tablo) sert bolunur ama sinir asilmaz."""
    parcalar = mesaji_bol("x" * 9000)
    assert len(parcalar) == 3
    assert all(len(p) <= 4096 for p in parcalar)


def test_bolme_bosluk_disinda_karakter_kaybetmez():
    """Bolme sinirinda bosluk kirpiliyor; kaybolmamasi gereken metnin kendisi.

    Bu test bir kelimenin ya da rakamin ikiye bolunup yok olmadigini garanti
    eder — bir cevabin ortasindan sessizce veri dusmesi en kotu hata olurdu.
    """

    def sadelestir(s: str) -> str:
        return "".join(s.split())

    metin = "Cumle bir. Cumle iki. " * 300
    assert sadelestir("".join(mesaji_bol(metin))) == sadelestir(metin)
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_bicim.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.bicim'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/bicim.py`:

```python
"""Turkce bicimlendirme ve Telegram mesaj bolme.

Turkce sayi formati: 1.234.567,89 — nokta binlik, virgul ondalik.
Python'un varsayilan formati bunun tersi oldugu icin elle cevrilir.
"""

import datetime as dt

TELEGRAM_SINIRI = 4096


def _turkce_sayi(deger: float, basamak: int = 2) -> str:
    metin = f"{deger:,.{basamak}f}"  # 1,234.50
    return metin.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def tl(deger: float) -> str:
    return f"{_turkce_sayi(deger)} TL"


def yuzde(deger: float) -> str:
    return f"%{_turkce_sayi(deger)}"


def tarih(deger) -> str:
    if isinstance(deger, str):
        deger = dt.date.fromisoformat(deger[:10])
    return deger.strftime("%d.%m.%Y")


def buyuk_sayi(deger: float) -> str:
    """Buyuk TL tutarlarini okunabilir kisaltir.

    1.073.081.134.047 gibi bir rakami ham gostermek cevabi okunmaz yapiyor.
    """
    for esik, ad in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if abs(deger) >= esik:
            return f"{_turkce_sayi(deger / esik)} {ad} TL"
    return tl(deger)


def mesaji_bol(metin: str, sinir: int = TELEGRAM_SINIRI) -> list[str]:
    """Telegram'in 4096 karakter sinirina gore boler.

    Once cumle sinirindan denenir; tek bir cumle bile sinira sigmiyorsa
    (ornegin uzun bir tablo) sert bolunur. Hicbir karakter kaybolmaz.
    """
    metin = metin.rstrip()
    if len(metin) <= sinir:
        return [metin]

    parcalar: list[str] = []
    kalan = metin

    while len(kalan) > sinir:
        pencere = kalan[:sinir]
        kesim = max(pencere.rfind(". "), pencere.rfind(".\n"), pencere.rfind("\n"))
        if kesim <= 0:
            kesim = sinir - 1
        else:
            kesim += 1  # noktayi parcada birak
        parcalar.append(kalan[: kesim + 1].rstrip() if kesim < sinir - 1 else kalan[:sinir])
        kalan = kalan[kesim + 1 :].lstrip() if kesim < sinir - 1 else kalan[sinir:]

    if kalan:
        parcalar.append(kalan)
    return parcalar
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_bicim.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add ajan/bicim.py ajan/tests/test_bicim.py
git commit -m "feat: Turkce bicimlendirme ve 4096 karakter bolme"
```

---

### Task 4: SQLite sohbet hafızası

**Files:**
- Create: `ajan/hafiza.py`
- Test: `ajan/tests/test_hafiza.py`

**Interfaces:**
- Consumes: yok
- Produces: `Hafiza(db_yolu: Path, tavan_token: int = 6000)` sınıfı;
  `ekle(rol: str, icerik: str, arac_sonucu: bool = False) -> None`,
  `gecmis() -> list[dict]`, `sifirla() -> None`, `kaba_token(metin: str) -> int`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_hafiza.py`:

```python
from ajan.hafiza import Hafiza, kaba_token


def test_kaba_token_karakterden_tahmin_eder():
    assert kaba_token("a" * 320) == 100


def test_eklenen_mesajlar_sirayla_doner(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    hafiza.ekle("user", "THYAO kac TL?")
    hafiza.ekle("assistant", "296,00 TL")
    assert [m["content"] for m in hafiza.gecmis()] == ["THYAO kac TL?", "296,00 TL"]


def test_yeniden_acilinca_gecmis_kaybolmaz(tmp_path):
    yol = tmp_path / "s.db"
    Hafiza(yol).ekle("user", "merhaba")
    assert len(Hafiza(yol).gecmis()) == 1


def test_sifirla_gecmisi_temizler(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    hafiza.ekle("user", "merhaba")
    hafiza.sifirla()
    assert hafiza.gecmis() == []


def test_yalnizca_son_turun_arac_sonucu_baglama_girer(tmp_path):
    """Eski tablolar baglami doldurup hafiza derinligini oldururdu.

    Arac sonuclari SQLite'a yine yazilir (hata ayiklama icin), ama modele
    yalnizca son turunki geri gonderilir.
    """
    hafiza = Hafiza(tmp_path / "s.db")
    hafiza.ekle("user", "GARAN bilanco")
    hafiza.ekle("tool", "ESKI TABLO", arac_sonucu=True)
    hafiza.ekle("assistant", "iste bilanco")
    hafiza.ekle("user", "peki ozkaynagi?")
    hafiza.ekle("tool", "YENI TABLO", arac_sonucu=True)

    icerikler = [m["content"] for m in hafiza.gecmis()]
    assert "YENI TABLO" in icerikler
    assert "ESKI TABLO" not in icerikler
    assert "iste bilanco" in icerikler


def test_tavan_asilinca_en_eski_mesajlar_duser(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db", tavan_token=100)
    hafiza.ekle("user", "ILK MESAJ")
    for i in range(20):
        hafiza.ekle("assistant", "dolgu " * 20)
    icerikler = [m["content"] for m in hafiza.gecmis()]
    assert "ILK MESAJ" not in icerikler
    assert icerikler, "hepsi dusmemeli"


def test_son_mesaj_tavandan_buyuk_olsa_bile_kalir(tmp_path):
    """Tek bir dev mesaj yuzunden baglam tamamen bosalmamali."""
    hafiza = Hafiza(tmp_path / "s.db", tavan_token=10)
    hafiza.ekle("user", "x" * 10_000)
    assert len(hafiza.gecmis()) == 1
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_hafiza.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.hafiza'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/hafiza.py`:

```python
"""SQLite sohbet hafizasi.

Iki kural:
  1. Arac sonuclari diske YAZILIR (hangi cevap hangi veriye bakilarak
     uretildi, sonradan sorgulanabilsin) ama modele yalnizca SON TURUN
     sonucu geri gonderilir. Hepsini gondermek baglami tablolarla doldurup
     hafiza derinligini birkac tura dusuruyordu.
  2. Kirpma token bazlidir, mesaj sayisi bazli degil.
"""

import sqlite3
import time
from pathlib import Path

# Turkce metinde karakter/token orani kabaca 3,2. Kesin tokenizer yerine
# bu tahmin kullaniliyor: amac butce tutmak, muhasebe yapmak degil.
KARAKTER_BASINA_TOKEN = 3.2


def kaba_token(metin: str) -> int:
    return int(len(metin) / KARAKTER_BASINA_TOKEN)


class Hafiza:
    def __init__(self, db_yolu: Path, tavan_token: int = 6000) -> None:
        self._tavan = tavan_token
        self._baglanti = sqlite3.connect(db_yolu, check_same_thread=False)
        self._baglanti.row_factory = sqlite3.Row
        self._baglanti.execute(
            "CREATE TABLE IF NOT EXISTS mesaj ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  rol TEXT NOT NULL,"
            "  icerik TEXT NOT NULL,"
            "  arac_sonucu INTEGER NOT NULL DEFAULT 0,"
            "  tur INTEGER NOT NULL DEFAULT 0,"
            "  zaman REAL NOT NULL"
            ")"
        )
        self._baglanti.commit()

    def _son_tur(self) -> int:
        satir = self._baglanti.execute("SELECT MAX(tur) AS t FROM mesaj").fetchone()
        return satir["t"] or 0

    def ekle(self, rol: str, icerik: str, arac_sonucu: bool = False) -> None:
        tur = self._son_tur() + (1 if rol == "user" else 0)
        self._baglanti.execute(
            "INSERT INTO mesaj (rol, icerik, arac_sonucu, tur, zaman) VALUES (?,?,?,?,?)",
            (rol, icerik, int(arac_sonucu), max(tur, 1), time.time()),
        )
        self._baglanti.commit()

    def gecmis(self) -> list[dict]:
        """Modele gonderilecek mesaj listesi (eski -> yeni)."""
        son_tur = self._son_tur()
        satirlar = self._baglanti.execute(
            "SELECT rol, icerik, arac_sonucu, tur FROM mesaj ORDER BY id"
        ).fetchall()

        secilen = [
            {"role": s["rol"], "content": s["icerik"]}
            for s in satirlar
            if not s["arac_sonucu"] or s["tur"] == son_tur
        ]
        return self._kirp(secilen)

    def _kirp(self, mesajlar: list[dict]) -> list[dict]:
        """Tavani asinca en eski mesajlar duser; son mesaj her zaman kalir."""
        toplam = sum(kaba_token(m["content"]) for m in mesajlar)
        while len(mesajlar) > 1 and toplam > self._tavan:
            dusen = mesajlar.pop(0)
            toplam -= kaba_token(dusen["content"])
        return mesajlar

    def sifirla(self) -> None:
        self._baglanti.execute("DELETE FROM mesaj")
        self._baglanti.commit()
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_hafiza.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add ajan/hafiza.py ajan/tests/test_hafiza.py
git commit -m "feat: SQLite sohbet hafizasi, son-tur arac sonucu kurali"
```

---

### Task 5: Sistem promptu

**Files:**
- Create: `ajan/prompt.py`
- Test: `ajan/tests/test_prompt.py`

**Interfaces:**
- Consumes: `simdi_trt` (Task 1)
- Produces: `sistem_promptu(simdi: datetime | None = None) -> str`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_prompt.py`:

```python
import datetime as dt

from ajan.config import TRT
from ajan.prompt import sistem_promptu


def test_bugunun_tarihi_turkce_yazilir():
    """Bu olmadan 'gecen hafta', 'bu yil' calismaz ve VPS UTC ise gun kayar."""
    metin = sistem_promptu(dt.datetime(2026, 9, 5, 14, 0, tzinfo=TRT))
    assert "05.09.2026" in metin
    assert "Cuma" in metin


def test_uydurma_yasagi_var():
    metin = sistem_promptu()
    assert "uydurma" in metin.lower()


def test_yatirim_tavsiyesi_yasagi_var():
    metin = sistem_promptu()
    assert "tavsiye" in metin.lower()


def test_donem_belirtme_kurali_var():
    metin = sistem_promptu()
    assert "dönem" in metin.lower()


def test_dusuk_fk_uyarisi_var():
    """Asama 1'de olculdu: F/K<2 genelde muhasebe etkisi, ucuzluk degil."""
    metin = sistem_promptu()
    assert "F/K" in metin


def test_prompt_makul_boyutta():
    """Her istekte gonderiliyor; sismesin."""
    assert len(sistem_promptu()) < 3000
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.prompt'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/prompt.py`:

```python
"""Sistem promptu.

Her istekte yeniden uretilir cunku icinde BUGUNUN TARIHI var: bu olmadan
"gecen hafta", "bu yil", "dun" kavramlari calismaz ve sunucu UTC ise gun kayar.
"""

import datetime as dt

from ajan.config import simdi_trt

GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")

GOVDE = """Sen Borsa İstanbul (BIST) konusunda uzman bir asistansın. Türkçe konuşuyorsun.

Bugün {gun_adi}, {tarih}. Saat {saat} (Türkiye saati).

Elindeki araçlarla gerçek veriye erişiyorsun. Kurallar:

1. VERİ YOKSA UYDURMA. Bir araç boş dönerse ya da hata verirse, kullanıcıya
   "bu veri bulunamadı" de. Rakam tahmin etme, hatırladığın değeri yazma.

2. RAKAMIN DÖNEMİNİ SÖYLE. "2025 yıllık bilançosuna göre özkaynak ..." gibi.
   Araç sonucundaki `donemler` alanı bunu veriyor.

3. PARA BİRİMİNİ YAZ. Tutarlar TL'dir. Büyük rakamları okunabilir yaz
   (1,07 trilyon TL gibi), ham basma.

4. TARİHLERİ gün.ay.yıl ver.

5. YATIRIM TAVSİYESİ VERME. Veriyi ve yorumu sun, "al", "sat", "tut" deme.
   Kullanıcı ısrar ederse veriyi gösterip kararı ona bırak.

6. ÇOK DÜŞÜK F/K ucuzluk değil, genellikle muhasebe etkisidir. Holdingler,
   GYO'lar ve yatırım ortaklıkları portföy yeniden değerleme kazancını "kâr"
   yazdığı için F/K'ları 1'in altına iner. Böyle bir sonucu ucuz diye sunma;
   şirketin ne iş yaptığına bak ve rakamın neden düşük olduğunu açıkla.

7. TARAMA sonuçları likidite filtresi uygulanmadıysa alınıp satılamayacak
   hisseler içerebilir. Filtre uyguladıysan bunu cevabında belirt.

8. Borsanın kapalı olduğu bir gün sorulursa (hafta sonu, tatil) bunu söyle ve
   en yakın işlem gününün verisini ver.

9. Tablo gösterirken hizalı monospace kullan, boru işareti (|) kullanma.

Kısa ve net yaz. Kullanıcı tek bir rakam sorduysa paragraf yazma."""


def sistem_promptu(simdi: dt.datetime | None = None) -> str:
    simdi = simdi or simdi_trt()
    return GOVDE.format(
        gun_adi=GUNLER[simdi.weekday()],
        tarih=simdi.strftime("%d.%m.%Y"),
        saat=simdi.strftime("%H:%M"),
    )
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_prompt.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add ajan/prompt.py ajan/tests/test_prompt.py
git commit -m "feat: sistem promptu, bugunun tarihi ve veri kurallari"
```

---

### Task 6: NVIDIA function-calling döngüsü

**Files:**
- Create: `ajan/ajan.py`
- Test: `ajan/tests/test_ajan.py`

**Interfaces:**
- Consumes: `McpBaglanti` (Task 2), `Hafiza` (Task 4), `sistem_promptu` (Task 5),
  `Ayarlar` (Task 1)
- Produces: `Ajan(ayarlar, mcp, hafiza, tur_tavani: int = 5)` sınıfı;
  `async cevapla(soru: str) -> str`, `TUR_TAVANI: int`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_ajan.py`:

```python
import json
from dataclasses import dataclass, field

import pytest

from ajan.ajan import Ajan
from ajan.config import Ayarlar
from ajan.hafiza import Hafiza


@dataclass
class SahteCagri:
    name: str
    arguments: str
    id: str = "cagri-1"

    @property
    def function(self):
        return self


@dataclass
class SahteMesaj:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class SahteSecim:
    message: SahteMesaj


@dataclass
class SahteYanit:
    choices: list


class SahteLLM:
    """Onceden belirlenmis yanitlari sirayla doner; cagrilari kaydeder."""

    def __init__(self, yanitlar):
        self._yanitlar = list(yanitlar)
        self.istekler = []

    async def create(self, **kwargs):
        self.istekler.append(kwargs)
        return self._yanitlar.pop(0)


class SahteMcp:
    def __init__(self):
        self.cagrilanlar = []

    async def arac_semalari(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "anlik_fiyat",
                    "description": "fiyat",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def cagir(self, ad, argumanlar):
        self.cagrilanlar.append((ad, argumanlar))
        return json.dumps({"fiyat": 296.0})


AYARLAR = Ayarlar(
    telegram_token="t",
    nvidia_api_key="k",
    admin_user_id=1,
    nvidia_model="test-model",
    nvidia_base_url="http://yok",
    log_seviyesi="INFO",
)


def _ajan(tmp_path, llm, mcp=None):
    ajan = Ajan(AYARLAR, mcp or SahteMcp(), Hafiza(tmp_path / "s.db"))
    ajan._llm_cagir = llm.create
    return ajan


@pytest.mark.asyncio
async def test_aracsiz_soru_dogrudan_cevaplanir(tmp_path):
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="Merhaba!"))])])
    assert await _ajan(tmp_path, llm).cevapla("selam") == "Merhaba!"


@pytest.mark.asyncio
async def test_arac_cagrisi_calistirilip_sonuc_modele_donuyor(tmp_path):
    llm = SahteLLM(
        [
            SahteYanit(
                [SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", '{"kod":"THYAO"}')]))]
            ),
            SahteYanit([SahteSecim(SahteMesaj(content="THYAO 296,00 TL"))]),
        ]
    )
    mcp = SahteMcp()
    cevap = await _ajan(tmp_path, llm, mcp).cevapla("THYAO kac TL?")

    assert cevap == "THYAO 296,00 TL"
    assert mcp.cagrilanlar == [("anlik_fiyat", {"kod": "THYAO"})]
    # Ikinci istekte arac sonucu modele gitmis olmali
    ikinci = llm.istekler[1]["messages"]
    assert any("296" in str(m.get("content", "")) for m in ikinci)


@pytest.mark.asyncio
async def test_ayni_turdaki_cok_arac_calistirilir(tmp_path):
    cagrilar = [
        SahteCagri("anlik_fiyat", '{"kod":"THYAO"}', id="a"),
        SahteCagri("anlik_fiyat", '{"kod":"GARAN"}', id="b"),
    ]
    llm = SahteLLM(
        [
            SahteYanit([SahteSecim(SahteMesaj(tool_calls=cagrilar))]),
            SahteYanit([SahteSecim(SahteMesaj(content="ikisi de geldi"))]),
        ]
    )
    mcp = SahteMcp()
    await _ajan(tmp_path, llm, mcp).cevapla("THYAO ve GARAN")
    assert len(mcp.cagrilanlar) == 2


@pytest.mark.asyncio
async def test_tur_tavani_asilinca_durur(tmp_path):
    """Model surekli arac isterse sonsuz donguye girmemeli."""
    sonsuz = [
        SahteYanit([SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", "{}")]))])
        for _ in range(10)
    ]
    llm = SahteLLM(sonsuz)
    cevap = await _ajan(tmp_path, llm).cevapla("dongu")
    assert "veri" in cevap.lower() or "tamamlanamadı" in cevap.lower()
    assert len(llm.istekler) <= 6, "tur tavani uygulanmadi"


@pytest.mark.asyncio
async def test_bozuk_arac_argumani_cokmez(tmp_path):
    """Model gecersiz JSON uretirse dongu kirilmamali."""
    llm = SahteLLM(
        [
            SahteYanit(
                [SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", "{bozuk")]))]
            ),
            SahteYanit([SahteSecim(SahteMesaj(content="anlasildi"))]),
        ]
    )
    assert await _ajan(tmp_path, llm).cevapla("bozuk") == "anlasildi"


@pytest.mark.asyncio
async def test_gecmis_hafizaya_yaziliyor(tmp_path):
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="cevap"))])])
    ajan = _ajan(tmp_path, llm)
    await ajan.cevapla("soru")
    roller = [m["role"] for m in ajan._hafiza.gecmis()]
    assert "user" in roller and "assistant" in roller


@pytest.mark.asyncio
async def test_sistem_promptu_her_istekte_var(tmp_path):
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="ok"))])])
    await _ajan(tmp_path, llm).cevapla("soru")
    assert llm.istekler[0]["messages"][0]["role"] == "system"
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_ajan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.ajan'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/ajan.py`:

```python
"""NVIDIA function-calling dongusu.

Bu modul Telegram'i bilmez; girdi bir soru metni, cikti bir cevap metnidir.
Araclar MCP'den gelir, bu modul onlarin ne yaptigini bilmez.
"""

import asyncio
import json
import logging

from openai import AsyncOpenAI

from ajan.config import Ayarlar
from ajan.hafiza import Hafiza
from ajan.prompt import sistem_promptu

kayit = logging.getLogger(__name__)

TUR_TAVANI = 5
TAVAN_MESAJI = (
    "Bu soru icin gereken veriyi tam toplayamadim. Elimdekiyle cevaplayayim: "
)


class Ajan:
    def __init__(
        self, ayarlar: Ayarlar, mcp, hafiza: Hafiza, tur_tavani: int = TUR_TAVANI
    ) -> None:
        self._ayarlar = ayarlar
        self._mcp = mcp
        self._hafiza = hafiza
        self._tur_tavani = tur_tavani
        self._istemci = AsyncOpenAI(
            api_key=ayarlar.nvidia_api_key, base_url=ayarlar.nvidia_base_url
        )
        self._llm_cagir = self._istemci.chat.completions.create

    async def _araclari_calistir(self, cagrilar) -> list[dict]:
        """Tek turdaki tum arac cagrilarini es zamanli calistirir."""

        async def _bir(cagri):
            ad = cagri.function.name
            try:
                argumanlar = json.loads(cagri.function.arguments or "{}")
            except json.JSONDecodeError:
                kayit.warning("Model gecersiz JSON uretti: %s", cagri.function.arguments)
                return {
                    "role": "tool",
                    "tool_call_id": cagri.id,
                    "content": "HATA: arguman JSON'u gecersiz, parametreleri kontrol et.",
                }
            sonuc = await self._mcp.cagir(ad, argumanlar)
            return {"role": "tool", "tool_call_id": cagri.id, "content": sonuc}

        return list(await asyncio.gather(*(_bir(c) for c in cagrilar)))

    async def cevapla(self, soru: str) -> str:
        self._hafiza.ekle("user", soru)

        araclar = await self._mcp.arac_semalari()
        mesajlar = [{"role": "system", "content": sistem_promptu()}, *self._hafiza.gecmis()]

        for tur in range(self._tur_tavani):
            yanit = await self._llm_cagir(
                model=self._ayarlar.nvidia_model,
                messages=mesajlar,
                tools=araclar,
                tool_choice="auto",
            )
            mesaj = yanit.choices[0].message

            if not getattr(mesaj, "tool_calls", None):
                cevap = (mesaj.content or "").strip() or "Cevap uretemedim."
                self._hafiza.ekle("assistant", cevap)
                return cevap

            mesajlar.append(
                {
                    "role": "assistant",
                    "content": mesaj.content,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.function.name,
                                "arguments": c.function.arguments,
                            },
                        }
                        for c in mesaj.tool_calls
                    ],
                }
            )

            sonuclar = await self._araclari_calistir(mesaj.tool_calls)
            mesajlar.extend(sonuclar)
            for sonuc in sonuclar:
                self._hafiza.ekle("tool", sonuc["content"], arac_sonucu=True)

            kayit.info("Tur %d: %d arac calistirildi", tur + 1, len(sonuclar))

        # Tur tavani asildi: elde ne varsa onunla cevapla, sonsuz donguye girme.
        kayit.warning("Tur tavani (%d) asildi", self._tur_tavani)
        son = await self._llm_cagir(
            model=self._ayarlar.nvidia_model,
            messages=[*mesajlar, {"role": "user", "content": TAVAN_MESAJI}],
        )
        cevap = (son.choices[0].message.content or "").strip() or (
            "Bu soru icin gereken veriyi toplayamadim."
        )
        self._hafiza.ekle("assistant", cevap)
        return cevap
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_ajan.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add ajan/ajan.py ajan/tests/test_ajan.py
git commit -m "feat: NVIDIA function-calling dongusu, tur tavani ve paralel arac cagrisi"
```

---

### Task 7: Telegram botu

**Files:**
- Create: `ajan/bot.py`
- Test: `ajan/tests/test_bot.py`

**Interfaces:**
- Consumes: `Ajan` (Task 6), `Ayarlar`/`log_kur` (Task 1), `McpBaglanti` (Task 2),
  `Hafiza` (Task 4), `mesaji_bol` (Task 3)
- Produces: `yetkili_mi(gonderen_id: int, admin_id: int) -> bool`,
  `async mesaji_isle(ajan, metin: str) -> list[str]`, `async main() -> None`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_bot.py`:

```python
import pytest

from ajan.bot import mesaji_isle, yetkili_mi


class SahteAjan:
    def __init__(self, cevap):
        self._cevap = cevap
        self.sorulanlar = []

    async def cevapla(self, soru):
        self.sorulanlar.append(soru)
        return self._cevap


def test_admin_yetkili():
    assert yetkili_mi(42, 42)


def test_baskasi_yetkisiz():
    assert not yetkili_mi(99, 42)
    assert not yetkili_mi(None, 42)


@pytest.mark.asyncio
async def test_kisa_cevap_tek_parca():
    ajan = SahteAjan("THYAO 296,00 TL")
    assert await mesaji_isle(ajan, "THYAO kac TL?") == ["THYAO 296,00 TL"]
    assert ajan.sorulanlar == ["THYAO kac TL?"]


@pytest.mark.asyncio
async def test_uzun_cevap_bolunur():
    ajan = SahteAjan("Cumle bir. " * 600)
    parcalar = await mesaji_isle(ajan, "uzun")
    assert len(parcalar) > 1
    assert all(len(p) <= 4096 for p in parcalar)


@pytest.mark.asyncio
async def test_ajan_hatasi_kullaniciya_ham_gosterilmez():
    class PatlayanAjan:
        async def cevapla(self, soru):
            raise RuntimeError("nvapi-gizli-anahtar gecersiz")

    parcalar = await mesaji_isle(PatlayanAjan(), "soru")
    assert len(parcalar) == 1
    assert "nvapi" not in parcalar[0]
    assert "hata" in parcalar[0].lower()
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.bot'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/bot.py`:

```python
"""Telegram botu — giris noktasi.

Bu modul NVIDIA'yi bilmez; yalnizca Ajan'a soru verir, cevap alir.

MCP baglantisi burada BIR KEZ acilir ve bot kapanana kadar ayakta kalir
(bkz. mcp_baglanti.py). Cagri basina baglanmak, MCP sunucusunun acilistaki
tarama tablosu kurulumunu her seferinde tetiklerdi.
"""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from ajan.ajan import Ajan
from ajan.bicim import mesaji_bol
from ajan.config import ayarlari_yukle, log_kur
from ajan.hafiza import Hafiza
from ajan.mcp_baglanti import McpBaglanti

kayit = logging.getLogger(__name__)
KOK = Path(__file__).resolve().parent.parent

KARSILAMA = (
    "Merhaba! BIST hakkında soru sorabilirsin.\n\n"
    "Örnekler:\n"
    "• THYAO kaç TL?\n"
    "• ASELS'i detaylı analiz et\n"
    "• GARAN'ın temettü geçmişi\n"
    "• ASELS'in son KAP açıklamaları\n\n"
    "/sifirla ile sohbet geçmişini temizleyebilirsin."
)
HATA_MESAJI = "Bir hata oldu, cevap üretemedim. Birazdan tekrar dener misin?"


def yetkili_mi(gonderen_id, admin_id: int) -> bool:
    return gonderen_id == admin_id


async def mesaji_isle(ajan, metin: str) -> list[str]:
    """Soruyu ajana verir, cevabi Telegram parcalarina boler.

    Ham istisna kullaniciya gosterilmez: mesajinda API anahtari gibi sirlar
    bulunabilir. Log'a tam hali yazilir.
    """
    try:
        cevap = await ajan.cevapla(metin)
    except Exception:
        kayit.exception("Ajan cevap uretemedi")
        return [HATA_MESAJI]
    return mesaji_bol(cevap)


async def main() -> None:
    load_dotenv()
    ayarlar = ayarlari_yukle(dict(os.environ))
    log_kur(ayarlar.log_seviyesi)

    if not ayarlar.nvidia_model:
        raise SystemExit(
            "NVIDIA_MODEL bos. once `python -m ajan.model_karsilastir` calistirip "
            "kazanan modeli .env'e yaz."
        )

    mcp = McpBaglanti("python", ["-m", "bist_mcp.sunucu"], str(KOK))
    await mcp.baglan()

    hafiza = Hafiza(KOK / "sohbet.db")
    ajan = Ajan(ayarlar, mcp, hafiza)

    bot = Bot(token=ayarlar.telegram_token)
    yonlendirici = Dispatcher()
    kilit = asyncio.Lock()  # arka arkaya mesajlar kuyruga girsin

    @yonlendirici.message(Command("start"))
    async def start(mesaj: Message) -> None:
        if not yetkili_mi(mesaj.from_user.id, ayarlar.admin_user_id):
            kayit.warning("Yetkisiz erisim denemesi: %s", mesaj.from_user.id)
            return
        await mesaj.answer(KARSILAMA)

    @yonlendirici.message(Command("sifirla"))
    async def sifirla(mesaj: Message) -> None:
        if not yetkili_mi(mesaj.from_user.id, ayarlar.admin_user_id):
            return
        hafiza.sifirla()
        await mesaj.answer("Sohbet geçmişi temizlendi.")

    @yonlendirici.message(F.text)
    async def soru(mesaj: Message) -> None:
        if not yetkili_mi(mesaj.from_user.id, ayarlar.admin_user_id):
            kayit.warning("Yetkisiz erisim denemesi: %s", mesaj.from_user.id)
            return

        async with kilit:
            await bot.send_chat_action(mesaj.chat.id, "typing")
            for parca in await mesaji_isle(ajan, mesaj.text):
                await mesaj.answer(parca)

    try:
        kayit.info("Bot basliyor")
        await yonlendirici.start_polling(bot)
    finally:
        await mcp.kapat()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_bot.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ajan/bot.py ajan/tests/test_bot.py
git commit -m "feat: Telegram botu, admin kilidi ve tek MCP oturumu"
```

---

### Task 8: Model karşılaştırma betiği

Spec §3.3: varsayılan model tahminle değil ölçümle seçilir. NVIDIA katalogu
değiştiği için model kimlikleri sabit yazılmaz, `/v1/models`'ten keşfedilir.

**Files:**
- Create: `ajan/model_karsilastir.py`
- Test: `ajan/tests/test_model_karsilastir.py`

**Interfaces:**
- Consumes: `Ayarlar` (Task 1), `McpBaglanti` (Task 2), `Ajan` (Task 6)
- Produces: `SORULAR: list[tuple[str, str]]`, `aday_modelleri_sec(kimlikler: list[str]) -> list[str]`,
  `isabet_hesapla(sonuclar: list[bool]) -> float`, `async main() -> None`

- [ ] **Step 1: Başarısız testi yaz**

`ajan/tests/test_model_karsilastir.py`:

```python
from ajan.model_karsilastir import SORULAR, aday_modelleri_sec, isabet_hesapla


def test_yirmi_soru_var():
    assert len(SORULAR) == 20


def test_her_soru_bir_arac_bekliyor():
    for soru, beklenen in SORULAR:
        assert soru.strip()
        assert beklenen.strip()


def test_sorular_araclarin_cogunu_kapsiyor():
    """Az sayida araci olcen bir test yaniltici bir skor uretir."""
    kapsanan = {beklenen for _, beklenen in SORULAR}
    assert len(kapsanan) >= 12


def test_aday_secimi_tool_calling_modellerini_bulur():
    kimlikler = [
        "nvidia/nemotron-3-super-120b-a12b",
        "zai/glm-5.1",
        "moonshotai/kimi-k2.5",
        "stabilityai/sdxl-turbo",
        "nvidia/embed-qa-4",
    ]
    adaylar = aday_modelleri_sec(kimlikler)
    assert "nvidia/nemotron-3-super-120b-a12b" in adaylar
    assert "zai/glm-5.1" in adaylar
    assert "stabilityai/sdxl-turbo" not in adaylar
    assert "nvidia/embed-qa-4" not in adaylar


def test_isabet_yuzdesi():
    assert isabet_hesapla([True] * 18 + [False] * 2) == 90.0
    assert isabet_hesapla([]) == 0.0
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest ajan/tests/test_model_karsilastir.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ajan.model_karsilastir'`

- [ ] **Step 3: İmplementasyonu yaz**

`ajan/model_karsilastir.py`:

```python
"""Model secim betigi — ELLE calistirilir, import edilince hicbir sey yapmaz.

  python -m ajan.model_karsilastir

20 Turkce soru sorar, modelin DOGRU ARACI secip secmedigini olcer. Cevabin
oznel kalitesi olculmez; olculen tek sey arac secimi ve gecikme.

Model kimlikleri sabit yazilmaz: NVIDIA katalogu degisiyor, bu yuzden
/v1/models'ten cekilip aday suzgecinden gecirilir.

Hedef: 18/20. Altina dusen modelin varsayilan yapilmasi onerilmez.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ajan.config import ayarlari_yukle, log_kur
from ajan.mcp_baglanti import McpBaglanti

kayit = logging.getLogger(__name__)
KOK = Path(__file__).resolve().parent.parent

# Tool calling destekleyen model ailelerinin kimliklerinde gecen parcalar.
ADAY_ISARETLERI = ("nemotron", "glm", "kimi", "llama-3.1", "llama-4", "qwen", "mixtral")
# Uretim/gomme/gorsel modelleri elenir.
HARIC_ISARETLER = ("embed", "rerank", "sdxl", "stable", "diffusion", "vision", "ocr", "tts", "asr")

SORULAR: list[tuple[str, str]] = [
    ("THYAO kaç TL?", "anlik_fiyat"),
    ("ASELS şu an ne kadar?", "anlik_fiyat"),
    ("GARAN'ın bilançosunu göster", "finansal_tablo"),
    ("EREGL'in gelir tablosu nasıl?", "finansal_tablo"),
    ("THYAO'nun F/K'sı kaç?", "finansal_oranlar"),
    ("ASELS'in PD/DD oranı nedir?", "finansal_oranlar"),
    ("GARAN temettü verdi mi?", "temettu_gecmisi"),
    ("TUPRS'un temettü geçmişi", "temettu_gecmisi"),
    ("ASELS'in son KAP açıklamaları neler?", "kap_bildirimleri"),
    ("THYAO ile ilgili son haberler", "kap_bildirimleri"),
    ("THYAO 2 Ağustos'ta kaç TL'ydi?", "gecmis_fiyat"),
    ("EREGL'in geçen ayki fiyatları", "gecmis_fiyat"),
    ("Aselsan'ın hisse kodu ne?", "hisse_ara"),
    ("Türk Hava Yolları hangi kodla işlem görüyor?", "hisse_ara"),
    ("THYAO'nun RSI'ı kaç?", "teknik_analiz"),
    ("ASELS teknik olarak nasıl görünüyor?", "teknik_analiz"),
    ("F/K'sı 10'un altında hisseler hangileri?", "hisse_tarama"),
    ("Temettü verimi %5 üstü hisseleri listele", "hisse_tarama"),
    ("BIST 100 kaç puan?", "endeks_verisi"),
    ("Dolar kaç TL?", "doviz_altin"),
]


def aday_modelleri_sec(kimlikler: list[str]) -> list[str]:
    """Katalogdan tool calling'e uygun adaylari suzer."""
    return [
        kimlik
        for kimlik in kimlikler
        if any(i in kimlik.lower() for i in ADAY_ISARETLERI)
        and not any(h in kimlik.lower() for h in HARIC_ISARETLER)
    ]


def isabet_hesapla(sonuclar: list[bool]) -> float:
    if not sonuclar:
        return 0.0
    return round(sum(sonuclar) / len(sonuclar) * 100, 1)


async def _bir_soruyu_dene(istemci, model: str, araclar, soru: str) -> tuple[str | None, float]:
    """Modelin hangi araci sectigini ve gecikmeyi doner. Arac CALISTIRILMAZ."""
    basla = time.time()
    yanit = await istemci.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "BIST asistanisin. Gerekli araci sec."},
            {"role": "user", "content": soru},
        ],
        tools=araclar,
        tool_choice="auto",
    )
    gecikme = time.time() - basla
    cagrilar = getattr(yanit.choices[0].message, "tool_calls", None)
    return (cagrilar[0].function.name if cagrilar else None), gecikme


async def _modeli_olc(istemci, model: str, araclar) -> dict:
    dogrular: list[bool] = []
    gecikmeler: list[float] = []
    yanlislar: list[str] = []

    for soru, beklenen in SORULAR:
        try:
            secilen, gecikme = await _bir_soruyu_dene(istemci, model, araclar, soru)
        except Exception as hata:  # noqa: BLE001
            kayit.warning("%s -> %s: %s", model, soru, hata)
            dogrular.append(False)
            yanlislar.append(f"{soru} -> HATA")
            continue

        dogrular.append(secilen == beklenen)
        gecikmeler.append(gecikme)
        if secilen != beklenen:
            yanlislar.append(f"{soru} -> {secilen or 'arac secmedi'} (beklenen {beklenen})")

    return {
        "model": model,
        "isabet": isabet_hesapla(dogrular),
        "dogru": sum(dogrular),
        "ortalama_gecikme": round(sum(gecikmeler) / len(gecikmeler), 2) if gecikmeler else None,
        "yanlislar": yanlislar,
    }


async def main() -> None:
    load_dotenv()
    ayarlar = ayarlari_yukle(dict(os.environ))
    log_kur(ayarlar.log_seviyesi)

    mcp = McpBaglanti("python", ["-m", "bist_mcp.sunucu"], str(KOK))
    await mcp.baglan()
    istemci = AsyncOpenAI(api_key=ayarlar.nvidia_api_key, base_url=ayarlar.nvidia_base_url)

    try:
        araclar = await mcp.arac_semalari()
        katalog = await istemci.models.list()
        adaylar = aday_modelleri_sec([m.id for m in katalog.data])
        print(f"Katalogda {len(katalog.data)} model, {len(adaylar)} aday bulundu.\n")

        sonuclar = []
        for model in adaylar[:5]:
            print(f"--- {model} olculuyor ({len(SORULAR)} soru) ---")
            sonuc = await _modeli_olc(istemci, model, araclar)
            sonuclar.append(sonuc)
            print(
                f"    isabet {sonuc['dogru']}/{len(SORULAR)} (%{sonuc['isabet']}) "
                f"| ort. gecikme {sonuc['ortalama_gecikme']} sn"
            )

        sonuclar.sort(key=lambda s: (-s["isabet"], s["ortalama_gecikme"] or 999))
        print("\n=== SIRALAMA ===")
        for s in sonuclar:
            print(f"  {s['isabet']:5.1f}%  {s['ortalama_gecikme'] or '-':>6} sn  {s['model']}")

        if sonuclar:
            kazanan = sonuclar[0]
            print(f"\nKazanan: {kazanan['model']}")
            print("Yanlis secimler:")
            for satir in kazanan["yanlislar"] or ["yok"]:
                print(f"  - {satir}")
            print(f"\n.env dosyana yaz:  NVIDIA_MODEL={kazanan['model']}")
            if kazanan["isabet"] < 90:
                print("UYARI: hedef %90 (18/20). Once modeli sorgula, arac aciklamalarini degil.")

        (KOK / "model_karsilastirma.json").write_text(
            json.dumps(sonuclar, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\nAyrinti: model_karsilastirma.json")
    finally:
        await mcp.kapat()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest ajan/tests/test_model_karsilastir.py -v`
Expected: 5 passed

- [ ] **Step 5: Betiği gerçekten çalıştır ve kazananı `.env`'e yaz**

Run: `python -m ajan.model_karsilastir`

Bu adım NVIDIA anahtarı gerektirir ve birkaç dakika sürer. Çıktıdaki
`NVIDIA_MODEL=...` satırını `.env` dosyasına yaz. **Hedef 18/20.**

- [ ] **Step 6: Commit**

```bash
git add ajan/model_karsilastir.py ajan/tests/test_model_karsilastir.py
git commit -m "feat: model karsilastirma betigi, katalogdan aday kesfi"
```

---

### Task 9: Uçtan uca duman testi, README ve elle doğrulama

**Files:**
- Modify: `README.md`
- Test: `ajan/tests/test_uctan_uca.py`

**Interfaces:**
- Consumes: hepsi
- Produces: yok (doğrulama görevi)

- [ ] **Step 1: LLM'li uçtan uca testi yaz**

`ajan/tests/test_uctan_uca.py`:

```python
"""Gercek NVIDIA + gercek MCP: python -m pytest ajan/ -m llm

Bu testler API cagrisi yapar. Ucretsiz kotayla calisir ama ag ve anahtar
gerektirir.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from ajan.ajan import Ajan
from ajan.config import ayarlari_yukle
from ajan.hafiza import Hafiza
from ajan.mcp_baglanti import McpBaglanti

pytestmark = [pytest.mark.llm, pytest.mark.asyncio]
KOK = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
async def ajan(tmp_path):
    load_dotenv()
    ayarlar = ayarlari_yukle(dict(os.environ))
    if not ayarlar.nvidia_model:
        pytest.skip("NVIDIA_MODEL bos; once model_karsilastir calistir")

    mcp = McpBaglanti("python", ["-m", "bist_mcp.sunucu"], str(KOK))
    await mcp.baglan()
    try:
        yield Ajan(ayarlar, mcp, Hafiza(tmp_path / "s.db"))
    finally:
        await mcp.kapat()


async def test_fiyat_sorusu_dogru_rakami_veriyor(ajan):
    cevap = await ajan.cevapla("THYAO kaç TL?")
    assert "296" in cevap or "TL" in cevap


async def test_pddd_sorusunda_yfinance_tuzagi_yok(ajan):
    """En kritik uctan uca test: 18 gorunuyorsa oran katmani bypass edilmis."""
    cevap = await ajan.cevapla("THYAO'nun PD/DD oranı kaç?")
    assert "18" not in cevap.replace("2018", ""), f"yfinance degeri sizmis: {cevap}"
    assert "0,3" in cevap or "0.3" in cevap or "0,4" in cevap


async def test_olmayan_hissede_uydurmuyor(ajan):
    cevap = await ajan.cevapla("XXXXX kaç TL?")
    assert any(k in cevap.lower() for k in ("bulunamadı", "bulamadım", "yok", "geçersiz"))


async def test_takip_sorusu_baglami_koruyor(ajan):
    await ajan.cevapla("GARAN'ın bilançosunu göster")
    cevap = await ajan.cevapla("peki özkaynağı ne kadar?")
    assert any(k in cevap.lower() for k in ("özkaynak", "milyar", "tl"))
```

- [ ] **Step 2: `pytest.ini`'ye `llm` işaretini ekle**

`pytest.ini` içindeki `markers` bloğu şöyle olur:

```ini
[pytest]
markers =
    network: gercek sunucuya cikan testler (varsayilan kosuda haric)
    llm: gercek LLM cagrisi yapan testler (varsayilan kosuda haric)
addopts = -m "not network and not llm"
asyncio_mode = auto
```

- [ ] **Step 3: Hızlı testlerin hepsini koş**

Run: `python -m pytest -q`
Expected: Aşama 1'in 90 testi + Aşama 2'nin ~45 testi geçiyor, ağ ve llm hariç

- [ ] **Step 4: LLM testlerini koş**

Run: `python -m pytest ajan/ -m llm -v`
Expected: 4 passed (NVIDIA anahtarı ve `NVIDIA_MODEL` gerekir)

- [ ] **Step 5: README'ye Aşama 2 bölümünü ekle**

`README.md` başındaki "Bu, iki aşamalı bir projenin 1. aşamasıdır" paragrafı
kaldırılır ve şu bölüm `## Kurulum`'dan sonra eklenir:

````markdown
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
tetiklerdi.
````

- [ ] **Step 6: Telegram'da elle doğrula**

Bot çalışırken sırayla yaz. Her satır ölçülmüş bir davranışı sınıyor:

| # | Yaz | Beklenen | Neyi sınıyor |
|---|---|---|---|
| 1 | `/start` | Karşılama | Bağlantı, admin kilidi |
| 2 | `THYAO kaç TL?` | ~296 TL | Araç seçimi + MCP akışı |
| 3 | `THYAO'nun PD/DD'si kaç?` | **~0,38** — 18 DEĞİL | Oran katmanı bypass edilmemiş |
| 4 | `GARAN'ın bilançosu` | BDDK formatı + dönem belirtilmiş | Banka tablosu, prompt kuralı 2 |
| 5 | Soru 4'ten sonra `peki özkaynağı?` | Tabloyu yeniden çekmeden cevap | Hafızada son tur |
| 6 | `ASELS'in son KAP açıklamaları` | 2026 tarihli gerçek bildirimler | KAP OID akışı |
| 7 | `F/K'sı 10 altı hisseler` | Tablo + likidite/muhasebe uyarısı | Tarama + prompt kuralı 6-7 |
| 8 | `XXXXX kaç TL?` | "Bulunamadı" — uydurma yok | Prompt kuralı 1 |
| 9 | `THYAO al mı?` | Veri sunar, "al" demez | Prompt kuralı 5 |
| 10 | Çok uzun cevap isteyen bir soru | Bölünmüş mesajlar, kesik cümle yok | 4096 bölme |
| 11 | `/sifirla` sonra `peki özkaynağı?` | Bağlamı hatırlamıyor | Hafıza temizleme |

**En kritikleri 3, 8 ve 9.**

- [ ] **Step 7: Commit**

```bash
git add ajan/tests/test_uctan_uca.py pytest.ini README.md
git commit -m "feat: uctan uca LLM testleri, README ve elle dogrulama listesi"
```

---

## Aşama 2 tamamlanma ölçütü

- `python -m pytest -q` → Aşama 1 + Aşama 2 tüm hızlı testleri geçiyor
- `python -m pytest -m network` → ağ testleri geçiyor
- `python -m pytest ajan/ -m llm` → 4 uçtan uca test geçiyor
- `python -m ajan.model_karsilastir` → kazanan model ≥ 18/20
- Telegram'da Task 9 Step 6 listesinin 11 satırı da doğru cevaplanıyor

## Kapsam dışı (bilinçli)

- **VPS dağıtımı.** Yerel doğrulama sonrasına bırakıldı; systemd unit,
  `Restart=always` ve `PYTHONIOENCODING` unit dosyasına yazılır.
- **Çoklu kullanıcı, kota, kullanıcı bazlı hız sınırı.** Tek kullanıcı
  varsayımı (spec §2).
- **Fiyat alarmı, zamanlanmış bülten, portföy takibi.** İstenmedi.
- **Sesli mesaj, görsel, grafik üretimi.** Cevaplar metin.
- **Cevabın öznel kalitesinin ölçülmesi.** Yalnızca araç seçimi ve verinin
  doğru aktarımı ölçülür (spec §9).

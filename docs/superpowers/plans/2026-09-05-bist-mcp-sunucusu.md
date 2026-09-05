# BIST MCP Sunucusu — Implementasyon Planı (Aşama 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BIST verisini İş Yatırım, KAP, yfinance ve TCMB EVDS'ten çekip 16 araç
olarak sunan, bağımsız çalışan bir MCP sunucusu yazmak.

**Architecture:** `mcp` SDK'sının içindeki FastMCP ile stdio sunucusu. Dört kaynak
modülü ham veriyi çeker, `hesap.py` oranları TL bazında hesaplar, `onbellek.py`
SQLite TTL önbelleğiyle kaynak siteleri korur, `anlik_gorunum.py` tarama için
BIST-100 tablosunu iki kademeli tazeler. Sunucu Telegram'ı ve NVIDIA'yı bilmez.

**Tech Stack:** Python 3.13.7 · mcp 1.28.1 (FastMCP) · yfinance 1.0 · pandas 2.3.3 ·
httpx 0.28.1 · pytest 9.1.1 · pytest-asyncio 1.4.0 · sqlite3 (stdlib)

**Spec:** `docs/superpowers/specs/2026-09-05-bist-telegram-agent-design.md`

## Global Constraints

Bu bölüm her görevin gereksinimlerine örtük olarak dahildir.

- **Python 3.13.7.** Ortamda kurulu; sürüm yükseltilmez.
- **FastMCP ayrı paket olarak kurulmaz.** `mcp` 1.28.1 içinden gelir:
  `from mcp.server.fastmcp import FastMCP`. Doğrulandı.
- **`PYTHONIOENCODING=utf-8` zorunlu.** Windows konsolu cp1252; Türkçe karakter
  log'a yazılırken `UnicodeEncodeError` verir. Bu oturumda gözlemlendi.
- **KAP hız sınırı 2 istek/sn.** API çağrısından önce `GET /tr/bildirim-sorgu`
  ile oturum çerezi alınır, yoksa WAF bağlantıyı ~6 sn'de düşürür.
  `Referer: https://www.kap.org.tr/tr/bildirim-sorgu` başlığı zorunlu.
- **İş Yatırım hız sınırı 2 istek/sn.** Veri "kişisel kullanım" için sunuluyor.
- **yfinance'in türetilmiş alanları YASAK.** `info` sözlüğünden `priceToBook`,
  `trailingPE`, `dividendYield` ve `Ticker.news` hiçbir koşulda okunmaz. İzin
  verilen tek `info` alanları: `sharesOutstanding`, `sector`, `currency`,
  `financialCurrency`. Gerekçe: THYAO'da `priceToBook` 18,64 (gerçek 0,38).
- **Tüm araç adları, parametreleri ve açıklamaları Türkçe.**
- **Saat dilimi `TRT = UTC+3` sabit.** Türkiye yaz saati uygulamıyor.
- **Türkçe sayı formatı:** `1.234.567,89` — nokta binlik, virgül ondalık.
  KAP tarihi `GG.AA.YYYY SS:DD:SS`.
- **Her görev testleriyle birlikte commit edilir.** Ağa çıkan testler
  `@pytest.mark.network` ile işaretlenir ve varsayılan koşuda dışarıda kalır.

---

### Task 1: Proje iskeleti ve SQLite TTL önbelleği

Önbellek her kaynak modülünün altında duruyor; önce o kurulur.

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `pytest.ini`
- Create: `bist_mcp/__init__.py`, `bist_mcp/kaynaklar/__init__.py`
- Create: `bist_mcp/onbellek.py`
- Test: `bist_mcp/tests/__init__.py`, `bist_mcp/tests/test_onbellek.py`

**Interfaces:**
- Consumes: yok (ilk görev)
- Produces: `Onbellek(yol: Path, zaman: Callable[[], float] = time.time)` sınıfı,
  `al(anahtar: str) -> Any | None`, `yaz(anahtar: str, deger: Any, ttl_saniye: int) -> None`

- [ ] **Step 1: Depoyu başlat ve iskelet dosyaları yaz**

Klasör henüz git deposu değil; commit adımları için gerekli.

```bash
cd "C:/Users/Taha/Desktop/Borsa Agent v2"
git init
```

`requirements.txt`:

```
mcp==1.28.1
yfinance==1.0
pandas==2.3.3
httpx==0.28.1
pytest==9.1.1
pytest-asyncio==1.4.0
python-dotenv==1.2.1
```

`.gitignore`:

```
.env
*.db
*.log
__pycache__/
.venv/
.pytest_cache/
```

`.env.example`:

```
EVDS_API_KEY=
LOG_LEVEL=INFO
```

`pytest.ini`:

```ini
[pytest]
markers =
    network: gercek sunucuya cikan testler (varsayilan kosuda haric)
addopts = -m "not network"
asyncio_mode = auto
```

`bist_mcp/__init__.py`, `bist_mcp/kaynaklar/__init__.py`, `bist_mcp/tests/__init__.py`
boş dosyalar olarak oluşturulur.

- [ ] **Step 2: Başarısız testi yaz**

`bist_mcp/tests/test_onbellek.py`:

```python
from pathlib import Path

from bist_mcp.onbellek import Onbellek


def test_yazilan_deger_geri_okunur(tmp_path: Path):
    onbellek = Onbellek(tmp_path / "test.db")
    onbellek.yaz("thyao:fiyat", {"fiyat": 296.0}, ttl_saniye=60)
    assert onbellek.al("thyao:fiyat") == {"fiyat": 296.0}


def test_olmayan_anahtar_none_doner(tmp_path: Path):
    onbellek = Onbellek(tmp_path / "test.db")
    assert onbellek.al("hic_yazilmadi") is None


def test_suresi_gecen_deger_none_doner(tmp_path: Path):
    saat = {"an": 1000.0}
    onbellek = Onbellek(tmp_path / "test.db", zaman=lambda: saat["an"])
    onbellek.yaz("thyao:fiyat", 296.0, ttl_saniye=60)

    saat["an"] = 1059.0
    assert onbellek.al("thyao:fiyat") == 296.0

    saat["an"] = 1061.0
    assert onbellek.al("thyao:fiyat") is None


def test_turkce_karakter_bozulmadan_saklanir(tmp_path: Path):
    onbellek = Onbellek(tmp_path / "test.db")
    onbellek.yaz("garan:kalem", "XVI. ÖZKAYNAKLAR", ttl_saniye=60)
    assert onbellek.al("garan:kalem") == "XVI. ÖZKAYNAKLAR"
```

- [ ] **Step 3: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_onbellek.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.onbellek'`

- [ ] **Step 4: Asgari implementasyonu yaz**

`bist_mcp/onbellek.py`:

```python
"""SQLite tabanli TTL onbellegi.

Kaynak siteleri korumak icin var: gelistirme sirasinda sunucu onlarca kez
yeniden baslatilir; bellekteki onbellek her restart'ta sifirlanip ayni veriyi
tekrar tekrar cekerdi.
"""

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class Onbellek:
    def __init__(self, yol: Path, zaman: Callable[[], float] = time.time) -> None:
        self._zaman = zaman
        self._baglanti = sqlite3.connect(yol, check_same_thread=False)
        self._baglanti.execute(
            "CREATE TABLE IF NOT EXISTS onbellek ("
            "  anahtar TEXT PRIMARY KEY,"
            "  deger   TEXT NOT NULL,"
            "  biten   REAL NOT NULL"
            ")"
        )
        self._baglanti.commit()

    def al(self, anahtar: str) -> Any | None:
        satir = self._baglanti.execute(
            "SELECT deger, biten FROM onbellek WHERE anahtar = ?", (anahtar,)
        ).fetchone()
        if satir is None:
            return None

        deger, biten = satir
        if biten <= self._zaman():
            self._baglanti.execute("DELETE FROM onbellek WHERE anahtar = ?", (anahtar,))
            self._baglanti.commit()
            return None

        return json.loads(deger)

    def yaz(self, anahtar: str, deger: Any, ttl_saniye: int) -> None:
        self._baglanti.execute(
            "INSERT OR REPLACE INTO onbellek (anahtar, deger, biten) VALUES (?, ?, ?)",
            (
                anahtar,
                json.dumps(deger, ensure_ascii=False),
                self._zaman() + ttl_saniye,
            ),
        )
        self._baglanti.commit()

    def kapat(self) -> None:
        self._baglanti.close()
```

- [ ] **Step 5: Testleri koş, geçtiğini doğrula**

Run: `python -m pytest bist_mcp/tests/test_onbellek.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example pytest.ini requirements.txt bist_mcp/
git commit -m "feat: proje iskeleti ve SQLite TTL onbellegi"
```

---

### Task 2: KAP şirket dizini — ticker'dan OID'ye

Bu görev spec §6.3'teki ölçülmüş hatayı çözüyor: `stockCode` alanı virgülle
ayrılmış çoklu kod tutabiliyor ve tam eşleşme aramak bankaların çoğunu
kaybettiriyor.

**Files:**
- Create: `bist_mcp/kaynaklar/kap.py`
- Test: `bist_mcp/tests/test_kap_dizin.py`

**Interfaces:**
- Consumes: `Onbellek` (Task 1)
- Produces: `Sirket` dataclass (`kod`, `unvan`, `mkk_oid`, `tip`),
  `dizin_kur(ham: list[dict]) -> dict[str, Sirket]`,
  `tablo_grubu_sec(tip: str | None) -> str`,
  `yedek_grup(grup: str) -> str`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_kap_dizin.py`:

```python
from bist_mcp.kaynaklar.kap import Sirket, dizin_kur, tablo_grubu_sec, yedek_grup

GARAN_HAM = {
    "stockCode": "GARAN, TGB",
    "kapMemberTitle": "TÜRKİYE GARANTİ BANKASI A.Ş.",
    "mkkMemberOid": "4028e4a140f2ed720140f37cb2a601b7",
    "financialType": "BNK",
}
ASELS_HAM = {
    "stockCode": "ASELS",
    "kapMemberTitle": "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
    "mkkMemberOid": "4028e4a1413b7ef401413bc2251e0047",
    "financialType": "SIR",
}
THYAO_HAM = {
    "stockCode": "THYAO",
    "kapMemberTitle": "TÜRK HAVA YOLLARI A.O.",
    "mkkMemberOid": "4028e4a140f2ed7201410a1a1c1d0001",
    "financialType": None,
}


def test_virgullu_stockcode_her_kod_icin_giris_acar():
    """Olculmus hata: GARAN'in stockCode degeri "GARAN, TGB".

    Tam eslesme aranirsa GARAN, YKBNK, VAKBN, HALKB, ISCTR kaybediliyordu.
    """
    dizin = dizin_kur([GARAN_HAM])
    assert set(dizin) == {"GARAN", "TGB"}
    assert dizin["GARAN"].mkk_oid == "4028e4a140f2ed720140f37cb2a601b7"
    assert dizin["TGB"].mkk_oid == dizin["GARAN"].mkk_oid


def test_her_giris_kendi_kodunu_tasir():
    dizin = dizin_kur([GARAN_HAM])
    assert dizin["GARAN"].kod == "GARAN"
    assert dizin["TGB"].kod == "TGB"


def test_tek_kodlu_sirket_normal_islenir():
    dizin = dizin_kur([ASELS_HAM])
    assert dizin["ASELS"] == Sirket(
        kod="ASELS",
        unvan="ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
        mkk_oid="4028e4a1413b7ef401413bc2251e0047",
        tip="SIR",
    )


def test_kodsuz_kayit_atlanir():
    dizin = dizin_kur([{"stockCode": "-", "mkkMemberOid": "x"}, {"stockCode": "", "mkkMemberOid": "y"}])
    assert dizin == {}


def test_banka_tipleri_ufrs_k_grubuna_gider():
    for tip in ("BNK", "SIG", "FFF", "KTL"):
        assert tablo_grubu_sec(tip) == "UFRS_K"


def test_sanayi_ve_bos_tip_xi_29_grubuna_gider():
    for tip in ("SIR", "HLD", "GYO", None):
        assert tablo_grubu_sec(tip) == "XI_29"


def test_bos_tip_yedek_gerektirir():
    """807 ticker'in 315'inde financialType bos — THYAO ve EREGL dahil.

    Bos tip XI_29'a gider ama yedek deneme kaldirilamaz.
    """
    dizin = dizin_kur([THYAO_HAM])
    grup = tablo_grubu_sec(dizin["THYAO"].tip)
    assert grup == "XI_29"
    assert yedek_grup(grup) == "UFRS_K"
    assert yedek_grup("UFRS_K") == "XI_29"
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_kap_dizin.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.kaynaklar.kap'`

- [ ] **Step 3: Asgari implementasyonu yaz**

`bist_mcp/kaynaklar/kap.py`:

```python
"""KAP (Kamuyu Aydinlatma Platformu) kaynagi.

Sirket dizini, bildirim sorgusu ve bildirim detayi.
"""

from dataclasses import dataclass

# KAP financialType kodlari: banka, sigorta, finansal kiralama/faktoring,
# katilim bankasi. Bunlar BDDK formatinda raporlar -> UFRS_K.
BANKA_TIPLERI = frozenset({"BNK", "SIG", "FFF", "KTL"})


@dataclass(frozen=True)
class Sirket:
    kod: str
    unvan: str
    mkk_oid: str
    tip: str | None


def dizin_kur(ham: list[dict]) -> dict[str, Sirket]:
    """KAP sirket listesini ticker -> Sirket sozlugune cevirir.

    `stockCode` alani virgulle ayrilmis birden fazla kod tutabilir; GARAN'in
    degeri "GARAN, TGB". Tam eslesme aramak bankalarin cogunu kaybettirir,
    bu yuzden alan virgulle bolunup her kod ayri anahtar yapilir.
    Olculen sonuc: 757 sirket -> 807 ticker.
    """
    dizin: dict[str, Sirket] = {}

    for kayit in ham:
        ham_kod = (kayit.get("stockCode") or "").strip()
        if not ham_kod or ham_kod == "-":
            continue

        unvan = (kayit.get("kapMemberTitle") or "").strip()
        oid = kayit.get("mkkMemberOid") or ""
        tip = kayit.get("financialType") or None

        for parca in ham_kod.split(","):
            kod = parca.strip()
            if kod and kod != "-":
                dizin[kod] = Sirket(kod=kod, unvan=unvan, mkk_oid=oid, tip=tip)

    return dizin


def tablo_grubu_sec(tip: str | None) -> str:
    """Sirket tipinden Is Yatirim financialGroup parametresini secer.

    Tip bos olabilir (807 ticker'in 315'i); o durumda XI_29 denenir ve
    bos donerse cagiran taraf yedek_grup() ile digerini dener.
    """
    return "UFRS_K" if tip in BANKA_TIPLERI else "XI_29"


def yedek_grup(grup: str) -> str:
    return "XI_29" if grup == "UFRS_K" else "UFRS_K"
```

- [ ] **Step 4: Testleri koş, geçtiğini doğrula**

Run: `python -m pytest bist_mcp/tests/test_kap_dizin.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/kaynaklar/kap.py bist_mcp/tests/test_kap_dizin.py
git commit -m "feat: KAP sirket dizini, virgullu stockCode ve tablo grubu secimi"
```

---

### Task 3: KAP istemcisi — oturum ısıtma, şirket listesi, bildirimler

**Files:**
- Modify: `bist_mcp/kaynaklar/kap.py`
- Test: `bist_mcp/tests/test_kap_istemci.py`

**Interfaces:**
- Consumes: `Sirket`, `dizin_kur` (Task 2), `Onbellek` (Task 1)
- Produces: `KapIstemci(onbellek: Onbellek)` sınıfı, metotlar:
  `async sirket_dizini() -> dict[str, Sirket]`,
  `async bildirimler(kod: str, gun: int = 90) -> list[dict]`,
  `async bildirim_detay(bildirim_no: str) -> dict`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_kap_istemci.py`:

```python
import pytest

from bist_mcp.kaynaklar.kap import KapIstemci, bildirim_sadelestir
from bist_mcp.onbellek import Onbellek

HAM_BILDIRIM = {
    "publishDate": "03.09.2026 18:15:48",
    "disclosureClass": "ODA",
    "subject": "Yönetim Kurulu Komiteleri",
    "summary": "Kredi Komitesi Üye Değişikliği",
    "stockCodes": "GARAN, TGB",
    "disclosureIndex": "1301003",
    "attachmentCount": 0,
    "kapTitle": "TÜRKİYE GARANTİ BANKASI A.Ş.",
    "isOldKap": False,
    "ruleType": "X",
}


def test_bildirim_sadelestirme_gerekli_alanlari_tutar():
    sade = bildirim_sadelestir(HAM_BILDIRIM)
    assert sade == {
        "tarih": "03.09.2026 18:15:48",
        "konu": "Yönetim Kurulu Komiteleri",
        "ozet": "Kredi Komitesi Üye Değişikliği",
        "sinif": "ODA",
        "bildirim_no": "1301003",
        "ek_sayisi": 0,
    }


def test_bildirim_sadelestirme_bos_ozeti_atlar():
    ham = dict(HAM_BILDIRIM, summary=None)
    assert bildirim_sadelestir(ham)["ozet"] is None


@pytest.mark.asyncio
async def test_dizin_onbellekten_okunur_ag_beklenmez(tmp_path):
    """Dizin onbellekteyse istemci aga cikmaz."""
    onbellek = Onbellek(tmp_path / "t.db")
    onbellek.yaz(
        "kap:sirket_listesi",
        [{"stockCode": "ASELS", "kapMemberTitle": "ASELSAN", "mkkMemberOid": "oid1", "financialType": "SIR"}],
        ttl_saniye=600,
    )

    istemci = KapIstemci(onbellek)
    istemci._ham_sirket_listesi_getir = _patlayan  # aga cikarsa test kirilir

    dizin = await istemci.sirket_dizini()
    assert dizin["ASELS"].mkk_oid == "oid1"


async def _patlayan():
    raise AssertionError("onbellek doluyken aga cikilmamaliydi")
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_kap_istemci.py -v`
Expected: FAIL — `ImportError: cannot import name 'KapIstemci'`

- [ ] **Step 3: İstemciyi yaz**

`bist_mcp/kaynaklar/kap.py` dosyasının sonuna eklenir (üstteki `dizin_kur`
ve `tablo_grubu_sec` korunur):

```python
import asyncio
import datetime as dt

import httpx

from bist_mcp.onbellek import Onbellek

KAP_KOK = "https://www.kap.org.tr"
BILDIRIM_SORGU_SAYFASI = f"{KAP_KOK}/tr/bildirim-sorgu"

# Olculen WAF davranisi: 2 istek/sn ustunde TCP baglantisi ~6 sn'de dusuyor.
ISTEK_ARALIGI_SN = 0.5

DIZIN_TTL = 7 * 24 * 3600      # sirket listesi haftada bir yeter
BILDIRIM_TTL = 300             # 5 dk
DETAY_TTL = 24 * 3600


def bildirim_sadelestir(ham: dict) -> dict:
    """Modele gidecek alanlari secer; gerisi baglami sisiriyor."""
    return {
        "tarih": ham.get("publishDate"),
        "konu": ham.get("subject"),
        "ozet": ham.get("summary") or None,
        "sinif": ham.get("disclosureClass"),
        "bildirim_no": ham.get("disclosureIndex"),
        "ek_sayisi": ham.get("attachmentCount", 0),
    }


class KapIstemci:
    def __init__(self, onbellek: Onbellek) -> None:
        self._onbellek = onbellek
        self._kilit = asyncio.Lock()
        self._son_istek = 0.0
        self._oturum_isitildi = False

    async def _bekle(self) -> None:
        """2 istek/sn tavanini uygular."""
        simdi = asyncio.get_event_loop().time()
        gecen = simdi - self._son_istek
        if gecen < ISTEK_ARALIGI_SN:
            await asyncio.sleep(ISTEK_ARALIGI_SN - gecen)
        self._son_istek = asyncio.get_event_loop().time()

    async def _oturum(self, istemci: httpx.AsyncClient) -> None:
        """API cagrisindan once cerez alir; yoksa WAF baglantiyi dusuruyor."""
        if self._oturum_isitildi:
            return
        await self._bekle()
        await istemci.get(BILDIRIM_SORGU_SAYFASI, timeout=30.0)
        self._oturum_isitildi = True

    async def _ham_sirket_listesi_getir(self) -> list[dict]:
        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._bekle()
            yanit = await istemci.get(
                f"{KAP_KOK}/tr/api/company/items/IGS/A",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=40.0,
            )
            yanit.raise_for_status()
            return yanit.json()

    async def sirket_dizini(self) -> dict[str, Sirket]:
        async with self._kilit:
            ham = self._onbellek.al("kap:sirket_listesi")
            if ham is None:
                ham = await self._ham_sirket_listesi_getir()
                self._onbellek.yaz("kap:sirket_listesi", ham, DIZIN_TTL)
            return dizin_kur(ham)

    async def bildirimler(self, kod: str, gun: int = 90) -> list[dict]:
        anahtar = f"kap:bildirim:{kod}:{gun}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        dizin = await self.sirket_dizini()
        sirket = dizin.get(kod.upper())
        if sirket is None:
            return []

        bitis = dt.date.today()
        baslangic = bitis - dt.timedelta(days=gun)

        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._oturum(istemci)
            await self._bekle()
            yanit = await istemci.post(
                f"{KAP_KOK}/tr/api/disclosure/members/byCriteria",
                json={
                    "fromDate": str(baslangic),
                    "toDate": str(bitis),
                    "mkkMemberOidList": [sirket.mkk_oid],
                    "subjectList": [],
                },
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": BILDIRIM_SORGU_SAYFASI,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=45.0,
            )
            yanit.raise_for_status()
            sonuc = [bildirim_sadelestir(x) for x in yanit.json()]

        self._onbellek.yaz(anahtar, sonuc, BILDIRIM_TTL)
        return sonuc

    async def bildirim_detay(self, bildirim_no: str) -> dict:
        anahtar = f"kap:detay:{bildirim_no}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._oturum(istemci)
            await self._bekle()
            yanit = await istemci.get(
                f"{KAP_KOK}/tr/api/notification/attachment-detail/{bildirim_no}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": f"{KAP_KOK}/tr/Bildirim/{bildirim_no}",
                    "Accept": "application/json",
                },
                timeout=40.0,
            )
            yanit.raise_for_status()
            sonuc = yanit.json()

        self._onbellek.yaz(anahtar, sonuc, DETAY_TTL)
        return sonuc
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_kap_istemci.py bist_mcp/tests/test_kap_dizin.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/kaynaklar/kap.py bist_mcp/tests/test_kap_istemci.py
git commit -m "feat: KAP istemcisi - oturum isitma, hiz siniri, bildirim sorgusu"
```

---

### Task 4: İş Yatırım finansal tablo kaynağı

**Files:**
- Create: `bist_mcp/kaynaklar/isyatirim.py`
- Test: `bist_mcp/tests/test_isyatirim.py`

**Interfaces:**
- Consumes: `tablo_grubu_sec`, `yedek_grup` (Task 2), `Onbellek` (Task 1)
- Produces: `IsYatirimIstemci(onbellek)` sınıfı,
  `async mali_tablo(kod, tip, donem="yillik", adet=2) -> dict` —
  **`{"donemler": list[str], "kalemler": list[dict]}`** döner (düz liste değil;
  model rakamın hangi döneme ait olduğunu söylemek zorunda, spec §8),
  saf fonksiyonlar `sayiya_cevir(ham) -> float | None`,
  `dolu_slotlar(ham: dict) -> list[int]`,
  `donem_adaylari(donem: str, bugun: date | None) -> list[tuple[int, int]]`,
  `donem_etiketi(yil, ay, donem) -> str`,
  `kalem_ayikla(ham: dict, slotlar: list[int] | None = None) -> list[dict]`,
  `sifir_satirlari_at(kalemler) -> list[dict]`,
  `kalem_bul(kalemler, *adaylar) -> float | None`

**Uygulama sırasında ölçümle bulunan üç sapma** (plan yazılırken bilinmiyordu):

1. **Dönem takvimle hesaplanamaz.** 2026-09-05'te ölçüldü: `2026/12` ve
   `2026/9` boş döner (henüz yayımlanmadı), `2026/6` ve `2025/12` dolu.
   Şirketler farklı tarihlerde açıkladığı için tarih aritmetiği kırılgan.
   Çözüm: aday dönemler istenir, **tamamen boş slotlar atılır**. Karışık
   pencerede yayımlanmamış dönem `None` gelir, diğerleri dolu (ölçüldü).
2. **Değerler slot bazında hizalanmalı.** Satır bazında `None` atmak
   hatalıydı: slot4'te 145, diğerlerinde 147 kalem dolu; o iki satırda
   değerler bir dönem kayıyordu.
3. **Değerler STRING geliyor** (`'1073081134047'`, `'-941964141907'`).
   Çevrilmezse oran hesabı bölemez ve `'0' != 0` olduğu için sıfır
   satırları hiç atılmaz.

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_isyatirim.py`:

```python
from bist_mcp.kaynaklar.isyatirim import kalem_ayikla, kalem_bul, sifir_satirlari_at

HAM_YANIT = {
    "value": [
        {"itemDescTr": "Özkaynaklar", "itemCode": "2O", "value1": 1073081134047, "value2": 950000000000},
        {"itemDescTr": "Dönem Karı (Zararı)", "itemCode": "2P", "value1": 139092773392, "value2": 120000000000},
        {"itemDescTr": "Boş Kalem", "itemCode": "2Z", "value1": 0, "value2": 0},
        {"itemDescTr": "Kısmen Dolu", "itemCode": "2Y", "value1": 0, "value2": 55},
    ]
}


def test_kalem_ayiklama_ad_ve_degerleri_cikarir():
    kalemler = kalem_ayikla(HAM_YANIT)
    assert kalemler[0]["ad"] == "Özkaynaklar"
    assert kalemler[0]["degerler"] == [1073081134047, 950000000000]


def test_kalem_adlarina_dokunulmaz():
    """Banka bilancosunda 'XVI. ÖZKAYNAKLAR' neyse o kalir."""
    ham = {"value": [{"itemDescTr": "XVI. ÖZKAYNAKLAR", "value1": 446636140000}]}
    assert kalem_ayikla(ham)[0]["ad"] == "XVI. ÖZKAYNAKLAR"


def test_tum_donemlerde_sifir_olan_satir_atilir():
    """GARAN'in 192 satirinin yarisindan fazlasi boyle."""
    kalan = sifir_satirlari_at(kalem_ayikla(HAM_YANIT))
    adlar = [k["ad"] for k in kalan]
    assert "Boş Kalem" not in adlar
    assert "Kısmen Dolu" in adlar
    assert "Özkaynaklar" in adlar


def test_kalem_bul_ilk_eslesen_adayi_doner():
    kalemler = kalem_ayikla(HAM_YANIT)
    assert kalem_bul(kalemler, "XVI. ÖZKAYNAKLAR", "Özkaynaklar") == 1073081134047


def test_kalem_bul_eslesme_yoksa_none_doner():
    kalemler = kalem_ayikla(HAM_YANIT)
    assert kalem_bul(kalemler, "Olmayan Kalem") is None


def test_bos_yanit_bos_liste_doner():
    assert kalem_ayikla({"value": []}) == []
    assert kalem_ayikla({}) == []
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_isyatirim.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.kaynaklar.isyatirim'`

- [ ] **Step 3: İmplementasyonu yaz**

`bist_mcp/kaynaklar/isyatirim.py`:

```python
"""Is Yatirim finansal tablo kaynagi.

Olculen sonuclar: THYAO 147 kalem (XI_29), GARAN 192 kalem BDDK formati
(UFRS_K). Tekil cagri suresi ~0,31 sn.
"""

import asyncio
import datetime as dt

import httpx

from bist_mcp.kaynaklar.kap import tablo_grubu_sec, yedek_grup
from bist_mcp.onbellek import Onbellek

KOK = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx"
ISTEK_ARALIGI_SN = 0.5          # kisisel kullanim; 2 istek/sn tavani
TABLO_TTL = 24 * 3600


def kalem_ayikla(ham: dict) -> list[dict]:
    """Is Yatirim yanitini {ad, degerler} listesine cevirir.

    Kalem adlarina dokunulmaz: 'XVI. OZKAYNAKLAR' neyse o kalir.
    """
    kalemler = []
    for satir in ham.get("value") or []:
        ad = (satir.get("itemDescTr") or "").strip()
        if not ad:
            continue
        degerler = [satir.get(f"value{i}") for i in (1, 2, 3, 4)]
        kalemler.append({"ad": ad, "degerler": [d for d in degerler if d is not None]})
    return kalemler


def sifir_satirlari_at(kalemler: list[dict]) -> list[dict]:
    """Tum donemlerde 0 olan satirlari atar."""
    return [k for k in kalemler if any(d not in (0, None) for d in k["degerler"])]


def kalem_bul(kalemler: list[dict], *adaylar: str) -> float | None:
    """Verilen adaylardan ilk eslesenin ilk donem degerini doner."""
    for aday in adaylar:
        for kalem in kalemler:
            if kalem["ad"].strip().upper() == aday.strip().upper():
                return kalem["degerler"][0] if kalem["degerler"] else None
    return None


def _donem_listesi(donem: str, adet: int) -> list[tuple[int, int]]:
    """Sorgulanacak (yil, ay) ciftlerini uretir, en yeniden eskiye."""
    bugun = dt.date.today()
    son_yil = bugun.year if bugun.month >= 4 else bugun.year - 1

    if donem == "yillik":
        return [(son_yil - i, 12) for i in range(adet)]

    ceyrekler = [(son_yil, 12), (son_yil, 9), (son_yil, 6), (son_yil, 3),
                 (son_yil - 1, 12), (son_yil - 1, 9), (son_yil - 1, 6), (son_yil - 1, 3)]
    return ceyrekler[:adet]


class IsYatirimIstemci:
    def __init__(self, onbellek: Onbellek) -> None:
        self._onbellek = onbellek
        self._son_istek = 0.0

    async def _bekle(self) -> None:
        simdi = asyncio.get_event_loop().time()
        gecen = simdi - self._son_istek
        if gecen < ISTEK_ARALIGI_SN:
            await asyncio.sleep(ISTEK_ARALIGI_SN - gecen)
        self._son_istek = asyncio.get_event_loop().time()

    async def _getir(self, kod: str, grup: str, donemler: list[tuple[int, int]]) -> dict:
        parametreler = {"companyCode": kod.upper(), "exchange": "TRY", "financialGroup": grup}
        for sira, (yil, ay) in enumerate(donemler, start=1):
            parametreler[f"year{sira}"] = yil
            parametreler[f"period{sira}"] = ay

        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._bekle()
            yanit = await istemci.get(
                f"{KOK}/MaliTablo",
                params=parametreler,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
                timeout=30.0,
            )
            yanit.raise_for_status()
            return yanit.json()

    async def mali_tablo(
        self, kod: str, tip: str | None, donem: str = "yillik", adet: int = 2
    ) -> list[dict]:
        """Finansal tabloyu doner. Yanlis grup bos tablo dondurdugu icin
        birincil grup bos gelirse yedek grup denenir — bu deneme kaldirilamaz.
        """
        anahtar = f"isy:{kod.upper()}:{donem}:{adet}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        donemler = _donem_listesi(donem, min(adet, 4))
        birincil = tablo_grubu_sec(tip)

        kalemler: list[dict] = []
        for grup in (birincil, yedek_grup(birincil)):
            kalemler = sifir_satirlari_at(kalem_ayikla(await self._getir(kod, grup, donemler)))
            if kalemler:
                break

        self._onbellek.yaz(anahtar, kalemler, TABLO_TTL)
        return kalemler
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_isyatirim.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/kaynaklar/isyatirim.py bist_mcp/tests/test_isyatirim.py
git commit -m "feat: Is Yatirim finansal tablo kaynagi, grup yedegiyle"
```

---

### Task 5: Fiyat kaynağı — yfinance, türetilmiş alanlar yasak

**Files:**
- Create: `bist_mcp/kaynaklar/fiyat.py`
- Test: `bist_mcp/tests/test_fiyat.py`

**Interfaces:**
- Consumes: `Onbellek` (Task 1)
- Produces: `IZINLI_INFO_ALANLARI` frozenset, `YASAK_INFO_ALANLARI` frozenset,
  `info_suz(ham: dict) -> dict`, `FiyatKaynak(onbellek)` sınıfı,
  `async anlik(kod: str) -> dict`, `async gecmis(kod, baslangic, bitis) -> list[dict]`,
  `async toplu(kodlar: list[str]) -> dict[str, dict]`,
  `async sirket_bilgi(kod: str) -> dict`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_fiyat.py`:

```python
import pytest

from bist_mcp.kaynaklar.fiyat import (
    IZINLI_INFO_ALANLARI,
    YASAK_INFO_ALANLARI,
    bist_sembol,
    info_suz,
)

# Gercek yfinance ciktisi: THYAO'nun priceToBook'u 18,64 ama gercek deger 0,38.
# Sebep: TL fiyat / USD ozkaynak. Bu alan asla okunmamali.
THYAO_INFO = {
    "sharesOutstanding": 1372283353,
    "sector": "Industrials",
    "currency": "TRY",
    "financialCurrency": "USD",
    "priceToBook": 18.635105,
    "trailingPE": None,
    "dividendYield": 2.28,
}


def test_yasak_alanlar_suzulur():
    sonuc = info_suz(THYAO_INFO)
    for alan in ("priceToBook", "trailingPE", "dividendYield"):
        assert alan not in sonuc


def test_izinli_alanlar_korunur():
    sonuc = info_suz(THYAO_INFO)
    assert sonuc["sharesOutstanding"] == 1372283353
    assert sonuc["sector"] == "Industrials"
    assert sonuc["financialCurrency"] == "USD"


def test_yasak_ve_izinli_kumeler_kesismiyor():
    assert not (IZINLI_INFO_ALANLARI & YASAK_INFO_ALANLARI)


def test_priceToBook_yasak_kumede():
    """Regresyon: bu alanin izinli kumeye tasinmasi 49 kat hata geri getirir."""
    assert "priceToBook" in YASAK_INFO_ALANLARI
    assert "trailingPE" in YASAK_INFO_ALANLARI
    assert "dividendYield" in YASAK_INFO_ALANLARI


def test_bist_sembolu_is_ekiyle_uretilir():
    assert bist_sembol("THYAO") == "THYAO.IS"
    assert bist_sembol("thyao") == "THYAO.IS"
    assert bist_sembol("GARAN.IS") == "GARAN.IS"
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_fiyat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.kaynaklar.fiyat'`

- [ ] **Step 3: İmplementasyonu yaz**

`bist_mcp/kaynaklar/fiyat.py`:

```python
"""Fiyat ve OHLCV kaynagi (yfinance).

DIKKAT: yfinance'in turetilmis alanlari BIST'te bozuk. Olculen ornek —
THYAO priceToBook 18,64 diyor, gercek deger 0,38 (49 kat sapma). Sebep:
sirket finansallarini USD raporluyor, hissesi TRY islem goruyor ve yfinance
TL fiyati USD defter degerine boluyor. Ayni sekilde ASELS icin 0 haber
donuyor. Bu yuzden bu modulden yalnizca ham fiyat, OHLCV, temettu odemesi,
hisse adedi ve sektor cikar; oranlar hesap.py'de TL bazinda hesaplanir.
"""

import asyncio
import datetime as dt

import pandas as pd
import yfinance as yf

from bist_mcp.onbellek import Onbellek

IZINLI_INFO_ALANLARI = frozenset(
    {"sharesOutstanding", "sector", "currency", "financialCurrency", "longName"}
)
YASAK_INFO_ALANLARI = frozenset(
    {"priceToBook", "trailingPE", "forwardPE", "dividendYield", "marketCap", "bookValue"}
)

ANLIK_TTL = 60
GECMIS_TTL = 3600
BILGI_TTL = 7 * 24 * 3600


def bist_sembol(kod: str) -> str:
    kod = kod.strip().upper()
    return kod if kod.endswith(".IS") else f"{kod}.IS"


def info_suz(ham: dict) -> dict:
    """Yalnizca izinli alanlari birakir; turetilmis alanlar atilir."""
    return {k: v for k, v in ham.items() if k in IZINLI_INFO_ALANLARI}


class FiyatKaynak:
    def __init__(self, onbellek: Onbellek) -> None:
        self._onbellek = onbellek

    async def anlik(self, kod: str) -> dict:
        anahtar = f"fiyat:anlik:{kod.upper()}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        def _cek() -> dict:
            veri = yf.Ticker(bist_sembol(kod)).history(period="5d", interval="1d")
            if veri.empty:
                return {}
            son = veri.iloc[-1]
            onceki = veri.iloc[-2] if len(veri) > 1 else son
            kapanis = float(son["Close"])
            onceki_kapanis = float(onceki["Close"])
            return {
                "kod": kod.upper(),
                "fiyat": round(kapanis, 2),
                "onceki_kapanis": round(onceki_kapanis, 2),
                "degisim_yuzde": round((kapanis / onceki_kapanis - 1) * 100, 2) if onceki_kapanis else None,
                "gun_yuksek": round(float(son["High"]), 2),
                "gun_dusuk": round(float(son["Low"]), 2),
                "hacim": int(son["Volume"]),
                "tarih": str(veri.index[-1])[:10],
                "para_birimi": "TRY",
            }

        sonuc = await asyncio.to_thread(_cek)
        self._onbellek.yaz(anahtar, sonuc, ANLIK_TTL)
        return sonuc

    async def gecmis(self, kod: str, baslangic: str, bitis: str | None = None) -> list[dict]:
        bitis = bitis or baslangic
        anahtar = f"fiyat:gecmis:{kod.upper()}:{baslangic}:{bitis}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        # Istenen gun kapali olabilir (hafta sonu/tatil); pencere +-5 gun genisletilir.
        bas = dt.date.fromisoformat(baslangic) - dt.timedelta(days=5)
        bit = dt.date.fromisoformat(bitis) + dt.timedelta(days=5)

        def _cek() -> list[dict]:
            veri = yf.Ticker(bist_sembol(kod)).history(start=str(bas), end=str(bit), interval="1d")
            return [
                {
                    "tarih": str(idx)[:10],
                    "acilis": round(float(s["Open"]), 2),
                    "yuksek": round(float(s["High"]), 2),
                    "dusuk": round(float(s["Low"]), 2),
                    "kapanis": round(float(s["Close"]), 2),
                    "hacim": int(s["Volume"]),
                }
                for idx, s in veri.iterrows()
            ]

        sonuc = await asyncio.to_thread(_cek)
        self._onbellek.yaz(anahtar, sonuc, GECMIS_TTL)
        return sonuc

    async def sirket_bilgi(self, kod: str) -> dict:
        """Hisse adedi ve sektor. Turetilmis alanlar suzulur."""
        anahtar = f"fiyat:bilgi:{kod.upper()}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        sonuc = info_suz(await asyncio.to_thread(lambda: yf.Ticker(bist_sembol(kod)).info))
        self._onbellek.yaz(anahtar, sonuc, BILGI_TTL)
        return sonuc

    async def toplu(self, kodlar: list[str]) -> dict[str, dict]:
        """Cok hisseyi TEK istekte ceker: fiyat + son 12 ay temettusu.

        Olculdu: 10 hisse / 1 yil / actions=True -> 0,79 sn. Temettu bu
        cagriya dahil oldugu icin hisse basina ayri temettu istegi gerekmez.
        """
        semboller = [bist_sembol(k) for k in kodlar]

        def _cek() -> dict[str, dict]:
            cerceve = yf.download(
                semboller, period="1y", interval="1d", actions=True,
                group_by="ticker", progress=False, auto_adjust=False, threads=True,
            )
            sonuc: dict[str, dict] = {}
            for kod, sembol in zip(kodlar, semboller):
                try:
                    kapanislar = cerceve[(sembol, "Close")].dropna()
                    if kapanislar.empty:
                        continue
                    temettuler = cerceve[(sembol, "Dividends")]
                    sonuc[kod.upper()] = {
                        "fiyat": round(float(kapanislar.iloc[-1]), 2),
                        "temettu_12ay": round(float(temettuler[temettuler > 0].sum()), 4),
                        "tarih": str(kapanislar.index[-1])[:10],
                    }
                except (KeyError, IndexError):
                    continue
            return sonuc

        return await asyncio.to_thread(_cek)
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_fiyat.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/kaynaklar/fiyat.py bist_mcp/tests/test_fiyat.py
git commit -m "feat: fiyat kaynagi - turetilmis yfinance alanlari suzuluyor"
```

---

### Task 6: Oran hesapları — THYAO regresyonu

Bu görev projenin en kritik testini içeriyor. Spec §6.1.

**Files:**
- Create: `bist_mcp/hesap.py`
- Test: `bist_mcp/tests/test_hesap.py`

**Interfaces:**
- Consumes: yok (saf fonksiyonlar)
- Produces: `defter_degeri(ozkaynak_tl, hisse_adedi) -> float`,
  `pddd(fiyat_tl, ozkaynak_tl, hisse_adedi) -> float`,
  `fk(fiyat_tl, hisse_adedi, net_kar_tl) -> float | None`,
  `piyasa_degeri(fiyat_tl, hisse_adedi) -> float`,
  `temettu_verimi(temettu_12ay_tl, fiyat_tl) -> float`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_hesap.py`:

```python
import pytest

from bist_mcp.hesap import defter_degeri, fk, piyasa_degeri, pddd, temettu_verimi

# Olculen gercek degerler (2026-09-05):
THYAO_FIYAT = 296.00
THYAO_OZKAYNAK_TL = 1_073_081_134_047      # Is Yatirim, TL
THYAO_HISSE_ADEDI = 1_372_283_353
THYAO_NET_KAR_TL = 139_092_773_392


def test_thyao_pddd_yfinance_tuzagina_dusmez():
    """REGRESYON — projenin en kritik testi.

    yfinance bu hisse icin priceToBook = 18,64 veriyor cunku TL fiyati
    USD ozkaynaga boluyor. TL ozkaynakla dogru sonuc 0,38. Bu test
    kirilirsa oran katmani 49 kat hatali veri uretiyor demektir.
    """
    sonuc = pddd(THYAO_FIYAT, THYAO_OZKAYNAK_TL, THYAO_HISSE_ADEDI)
    assert round(sonuc, 2) == 0.38
    assert sonuc < 1.0, "yfinance'in 18,64 degeri geri geldi"


def test_thyao_defter_degeri():
    assert round(defter_degeri(THYAO_OZKAYNAK_TL, THYAO_HISSE_ADEDI), 2) == 781.96


def test_thyao_fk_makul_aralikta():
    sonuc = fk(THYAO_FIYAT, THYAO_HISSE_ADEDI, THYAO_NET_KAR_TL)
    assert 2.0 < sonuc < 4.0


def test_zarar_eden_sirkette_fk_none_doner():
    assert fk(100.0, 1_000_000, -5_000_000) is None
    assert fk(100.0, 1_000_000, 0) is None


def test_garan_temettu_verimi():
    """Olculen: 5,267 TL temettu / 131,40 TL fiyat = %4,01."""
    assert round(temettu_verimi(5.266887, 131.40), 2) == 4.01


def test_temettu_odenmemisse_sifir():
    assert temettu_verimi(0.0, 296.0) == 0.0


def test_piyasa_degeri():
    assert piyasa_degeri(296.00, 1_372_283_353) == pytest.approx(406_195_872_488, rel=1e-6)


def test_sifir_hisse_adedi_hata_verir():
    with pytest.raises(ValueError):
        defter_degeri(1_000_000, 0)


def test_negatif_ozkaynakta_pddd_none_doner():
    """Teknik iflastaki sirkette PD/DD anlamsizdir."""
    assert pddd(10.0, -500_000, 1_000) is None
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_hesap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.hesap'`

- [ ] **Step 3: İmplementasyonu yaz**

`bist_mcp/hesap.py`:

```python
"""Oran hesaplari — TL bazinda.

Hicbir saglayicinin hazir oran alani kullanilmaz. Olculen gerekce: yfinance
THYAO icin priceToBook = 18,64 veriyor, gercek deger 0,38 (49 kat). Sebep
sirketin finansallarini USD raporlamasi. Buradaki tum hesaplar Is Yatirim'dan
gelen TL rakamlarla yapilir.
"""


def defter_degeri(ozkaynak_tl: float, hisse_adedi: int) -> float:
    """Pay basina defter degeri (TL)."""
    if hisse_adedi <= 0:
        raise ValueError("hisse adedi pozitif olmali")
    return ozkaynak_tl / hisse_adedi


def pddd(fiyat_tl: float, ozkaynak_tl: float, hisse_adedi: int) -> float | None:
    """Piyasa degeri / defter degeri. Negatif ozkaynakta None."""
    if ozkaynak_tl <= 0:
        return None
    return fiyat_tl / defter_degeri(ozkaynak_tl, hisse_adedi)


def fk(fiyat_tl: float, hisse_adedi: int, net_kar_tl: float) -> float | None:
    """Fiyat / kazanc. Zarar eden sirkette anlamsiz oldugu icin None."""
    if net_kar_tl <= 0:
        return None
    return piyasa_degeri(fiyat_tl, hisse_adedi) / net_kar_tl


def piyasa_degeri(fiyat_tl: float, hisse_adedi: int) -> float:
    if hisse_adedi <= 0:
        raise ValueError("hisse adedi pozitif olmali")
    return fiyat_tl * hisse_adedi


def temettu_verimi(temettu_12ay_tl: float, fiyat_tl: float) -> float:
    """Son 12 ayda odenen temettunun fiyata orani (yuzde)."""
    if fiyat_tl <= 0:
        raise ValueError("fiyat pozitif olmali")
    return temettu_12ay_tl / fiyat_tl * 100
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_hesap.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/hesap.py bist_mcp/tests/test_hesap.py
git commit -m "feat: TL bazli oran hesaplari + THYAO PD/DD regresyon testi"
```

---

### Task 7: Teknik analiz göstergeleri

**Files:**
- Create: `bist_mcp/teknik.py`
- Test: `bist_mcp/tests/test_teknik.py`

**Interfaces:**
- Consumes: `gecmis()` çıktısı (Task 5) — `list[dict]` with `kapanis` key
- Produces: `rsi(kapanislar: list[float], periyot: int = 14) -> float | None`,
  `hareketli_ortalama(kapanislar, periyot) -> float | None`,
  `macd(kapanislar) -> dict | None`,
  `destek_direnc(mumlar: list[dict]) -> dict`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_teknik.py`:

```python
from bist_mcp.teknik import destek_direnc, hareketli_ortalama, macd, rsi


def test_surekli_yukselen_seride_rsi_100e_yakin():
    assert rsi([float(i) for i in range(1, 40)]) > 95


def test_surekli_dusen_seride_rsi_sifira_yakin():
    assert rsi([float(i) for i in range(40, 1, -1)]) < 5


def test_yetersiz_veride_rsi_none():
    assert rsi([1.0, 2.0, 3.0]) is None


def test_hareketli_ortalama_son_n_kapanisin_ortalamasi():
    assert hareketli_ortalama([10.0, 20.0, 30.0, 40.0], 2) == 30.0
    assert hareketli_ortalama([10.0, 20.0, 30.0, 40.0], 4) == 25.0


def test_yetersiz_veride_hareketli_ortalama_none():
    assert hareketli_ortalama([10.0, 20.0], 5) is None


def test_macd_yukselen_seride_pozitif():
    sonuc = macd([float(i) for i in range(1, 60)])
    assert sonuc["macd"] > 0


def test_yetersiz_veride_macd_none():
    assert macd([1.0, 2.0]) is None


def test_destek_direnc_en_dusuk_ve_en_yuksegi_bulur():
    mumlar = [
        {"yuksek": 110.0, "dusuk": 90.0},
        {"yuksek": 120.0, "dusuk": 85.0},
        {"yuksek": 105.0, "dusuk": 95.0},
    ]
    assert destek_direnc(mumlar) == {"destek": 85.0, "direnc": 120.0}


def test_bos_mum_listesinde_destek_direnc_none():
    assert destek_direnc([]) == {"destek": None, "direnc": None}
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_teknik.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.teknik'`

- [ ] **Step 3: İmplementasyonu yaz**

`bist_mcp/teknik.py`:

```python
"""Teknik analiz gostergeleri.

Girdi her zaman kapanis listesi ya da mum listesi; bu modul aga cikmaz.
"""

import pandas as pd


def rsi(kapanislar: list[float], periyot: int = 14) -> float | None:
    if len(kapanislar) < periyot + 1:
        return None

    seri = pd.Series(kapanislar, dtype="float64")
    fark = seri.diff().dropna()
    kazanc = fark.clip(lower=0).ewm(alpha=1 / periyot, adjust=False).mean()
    kayip = (-fark.clip(upper=0)).ewm(alpha=1 / periyot, adjust=False).mean()

    son_kayip = float(kayip.iloc[-1])
    if son_kayip == 0:
        return 100.0

    oran = float(kazanc.iloc[-1]) / son_kayip
    return round(100 - 100 / (1 + oran), 2)


def hareketli_ortalama(kapanislar: list[float], periyot: int) -> float | None:
    if len(kapanislar) < periyot:
        return None
    return round(sum(kapanislar[-periyot:]) / periyot, 2)


def macd(kapanislar: list[float], hizli: int = 12, yavas: int = 26, sinyal: int = 9) -> dict | None:
    if len(kapanislar) < yavas + sinyal:
        return None

    seri = pd.Series(kapanislar, dtype="float64")
    macd_cizgisi = seri.ewm(span=hizli, adjust=False).mean() - seri.ewm(span=yavas, adjust=False).mean()
    sinyal_cizgisi = macd_cizgisi.ewm(span=sinyal, adjust=False).mean()

    return {
        "macd": round(float(macd_cizgisi.iloc[-1]), 4),
        "sinyal": round(float(sinyal_cizgisi.iloc[-1]), 4),
        "fark": round(float(macd_cizgisi.iloc[-1] - sinyal_cizgisi.iloc[-1]), 4),
    }


def destek_direnc(mumlar: list[dict]) -> dict:
    """Verilen pencerede en dusuk dip ve en yuksek tepe."""
    if not mumlar:
        return {"destek": None, "direnc": None}
    return {
        "destek": round(min(m["dusuk"] for m in mumlar), 2),
        "direnc": round(max(m["yuksek"] for m in mumlar), 2),
    }
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_teknik.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/teknik.py bist_mcp/tests/test_teknik.py
git commit -m "feat: teknik analiz gostergeleri (RSI, MA, MACD, destek/direnc)"
```

---

### Task 8: TCMB EVDS makro kaynağı

**Files:**
- Create: `bist_mcp/kaynaklar/tcmb.py`
- Test: `bist_mcp/tests/test_tcmb.py`

**Interfaces:**
- Consumes: `Onbellek` (Task 1)
- Produces: `GOSTERGELER: dict[str, str]` (Türkçe ad → EVDS serisi kodu),
  `TcmbIstemci(onbellek, api_anahtari: str | None)`,
  `async gosterge(ad: str, son_kayit: int = 12) -> dict`,
  saf fonksiyon `evds_ayikla(ham: dict, seri_kodu: str) -> list[dict]`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_tcmb.py`:

```python
import pytest

from bist_mcp.kaynaklar.tcmb import GOSTERGELER, evds_ayikla, seri_kodu_bul

HAM = {
    "items": [
        {"Tarih": "01-2026", "TP_FG_J0": "72,5"},
        {"Tarih": "02-2026", "TP_FG_J0": "68,3"},
        {"Tarih": "03-2026", "TP_FG_J0": None},
    ]
}


def test_evds_ayiklama_turkce_ondalik_virgulu_cozer():
    sonuc = evds_ayikla(HAM, "TP_FG_J0")
    assert sonuc[0] == {"tarih": "01-2026", "deger": 72.5}
    assert sonuc[1]["deger"] == 68.3


def test_bos_degerler_atlanir():
    assert len(evds_ayikla(HAM, "TP_FG_J0")) == 2


def test_gostergeler_turkce_adlarla_tanimli():
    assert "tufe" in GOSTERGELER
    assert "politika_faizi" in GOSTERGELER
    assert "usdtry" in GOSTERGELER


def test_seri_kodu_bulma_bilinmeyen_gosterge_hata_verir():
    with pytest.raises(ValueError) as hata:
        seri_kodu_bul("olmayan_gosterge")
    assert "olmayan_gosterge" in str(hata.value)


def test_seri_kodu_buyuk_kucuk_harf_duyarsiz():
    assert seri_kodu_bul("TUFE") == seri_kodu_bul("tufe")
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_tcmb.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.kaynaklar.tcmb'`

- [ ] **Step 3: İmplementasyonu yaz**

`bist_mcp/kaynaklar/tcmb.py`:

```python
"""TCMB EVDS makro gostergeleri.

EVDS_API_KEY yoksa modul devre disi kalir; diger araclar etkilenmez.
"""

import httpx

from bist_mcp.onbellek import Onbellek

EVDS_KOK = "https://evds2.tcmb.gov.tr/service/evds"
MAKRO_TTL = 6 * 3600

GOSTERGELER: dict[str, str] = {
    "tufe": "TP.FG.J0",                    # Tuketici fiyat endeksi
    "ufe": "TP.TUFE1YI.T1",                # Yurt ici uretici fiyat endeksi
    "politika_faizi": "TP.APIFON4",        # 1 haftalik repo
    "usdtry": "TP.DK.USD.A.YTL",
    "eurtry": "TP.DK.EUR.A.YTL",
    "gram_altin": "TP.MK.CUM.YTL",
    "tahvil_2y": "TP.ADFAIZ.GOSTERGE",
}


def seri_kodu_bul(ad: str) -> str:
    anahtar = ad.strip().lower()
    if anahtar not in GOSTERGELER:
        gecerli = ", ".join(sorted(GOSTERGELER))
        raise ValueError(f"bilinmeyen gosterge: {ad}. Gecerli olanlar: {gecerli}")
    return GOSTERGELER[anahtar]


def evds_ayikla(ham: dict, seri_kodu: str) -> list[dict]:
    """EVDS yanitini {tarih, deger} listesine cevirir.

    EVDS alan adinda noktalari alt cizgiye ceviriyor (TP.FG.J0 -> TP_FG_J0)
    ve sayilari Turkce ondalik virguluyle donduruyor.
    """
    alan = seri_kodu.replace(".", "_")
    sonuc = []
    for satir in ham.get("items") or []:
        ham_deger = satir.get(alan)
        if ham_deger in (None, "", "null"):
            continue
        sonuc.append({
            "tarih": satir.get("Tarih"),
            "deger": float(str(ham_deger).replace(".", "").replace(",", ".")),
        })
    return sonuc


class TcmbIstemci:
    def __init__(self, onbellek: Onbellek, api_anahtari: str | None) -> None:
        self._onbellek = onbellek
        self._anahtar = api_anahtari

    @property
    def etkin(self) -> bool:
        return bool(self._anahtar)

    async def gosterge(self, ad: str, son_kayit: int = 12) -> dict:
        if not self.etkin:
            return {"hata": "EVDS_API_KEY tanimli degil; makro gostergeler devre disi."}

        seri = seri_kodu_bul(ad)
        anahtar = f"tcmb:{seri}:{son_kayit}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        async with httpx.AsyncClient() as istemci:
            yanit = await istemci.get(
                f"{EVDS_KOK}/series={seri}&type=json&last_observations={son_kayit}",
                headers={"key": self._anahtar, "User-Agent": "Mozilla/5.0"},
                timeout=30.0,
            )
            yanit.raise_for_status()
            sonuc = {"gosterge": ad.lower(), "seri": seri, "kayitlar": evds_ayikla(yanit.json(), seri)}

        self._onbellek.yaz(anahtar, sonuc, MAKRO_TTL)
        return sonuc
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_tcmb.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/kaynaklar/tcmb.py bist_mcp/tests/test_tcmb.py
git commit -m "feat: TCMB EVDS makro gosterge kaynagi"
```

---

### Task 9: Toplu anlık görünüm — iki kademeli tazeleme

Spec §7. Tarama ve sektör karşılaştırması bu tabloyu okur, ağa çıkmaz.

**Files:**
- Create: `bist_mcp/anlik_gorunum.py`
- Test: `bist_mcp/tests/test_anlik_gorunum.py`

**Interfaces:**
- Consumes: `FiyatKaynak` (Task 5), `IsYatirimIstemci` (Task 4),
  `KapIstemci` (Task 3), `hesap` fonksiyonları (Task 6)
- Produces: `AnlikGorunum(db_yolu, kap, isyatirim, fiyat)` sınıfı,
  `async tam_kurulum(kodlar: list[str]) -> int`,
  `async hafif_tazele(kodlar: list[str]) -> int`,
  `satirlari_sec(**kriterler) -> list[dict]`,
  `yas_saat() -> float | None`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_anlik_gorunum.py`:

```python
from bist_mcp.anlik_gorunum import AnlikGorunum, satir_hesapla

TEMEL = {
    "kod": "THYAO",
    "unvan": "TÜRK HAVA YOLLARI A.O.",
    "sektor": "Industrials",
    "hisse_adedi": 1_372_283_353,
    "ozkaynak_tl": 1_073_081_134_047,
    "net_kar_tl": 139_092_773_392,
}


def test_satir_hesaplama_oranlari_tl_bazinda_uretir():
    satir = satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0)
    assert round(satir["pddd"], 2) == 0.38
    assert 2.0 < satir["fk"] < 4.0
    assert satir["temettu_verimi"] == 0.0


def test_eksik_ozkaynakta_oranlar_none_ama_satir_uretilir():
    eksik = dict(TEMEL, ozkaynak_tl=None)
    satir = satir_hesapla(eksik, fiyat=296.00, temettu_12ay=0.0)
    assert satir["pddd"] is None
    assert satir["kod"] == "THYAO"


def test_tabloya_yazilan_satir_geri_okunur(tmp_path):
    gorunum = AnlikGorunum(tmp_path / "g.db", kap=None, isyatirim=None, fiyat=None)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0))
    okunan = gorunum.satirlari_sec()
    assert len(okunan) == 1
    assert okunan[0]["kod"] == "THYAO"


def test_fk_ustsiniri_filtreler(tmp_path):
    gorunum = AnlikGorunum(tmp_path / "g.db", kap=None, isyatirim=None, fiyat=None)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0))       # F/K ~2,9
    pahali = dict(TEMEL, kod="XXXXX", net_kar_tl=1_000_000_000)                    # F/K ~406
    gorunum.satir_yaz(satir_hesapla(pahali, fiyat=296.00, temettu_12ay=0.0))

    assert [s["kod"] for s in gorunum.satirlari_sec(fk_max=10)] == ["THYAO"]


def test_temettu_verimi_altsiniri_filtreler(tmp_path):
    gorunum = AnlikGorunum(tmp_path / "g.db", kap=None, isyatirim=None, fiyat=None)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0))
    temettulu = dict(TEMEL, kod="GARAN")
    gorunum.satir_yaz(satir_hesapla(temettulu, fiyat=131.40, temettu_12ay=5.266887))

    assert [s["kod"] for s in gorunum.satirlari_sec(temettu_verimi_min=3.0)] == ["GARAN"]


def test_bos_tabloda_yas_none(tmp_path):
    gorunum = AnlikGorunum(tmp_path / "g.db", kap=None, isyatirim=None, fiyat=None)
    assert gorunum.yas_saat() is None
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_anlik_gorunum.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.anlik_gorunum'`

- [ ] **Step 3: İmplementasyonu yaz**

`bist_mcp/anlik_gorunum.py`:

```python
"""Tarama icin BIST-100 anlik gorunumu.

Iki kademeli tazeleme (spec §7.2): sutunlarin degisme hizi cok farkli.
Fiyat her gun degisir, ozkaynak/net kar ceyrekte bir, hisse adedi ve sektor
neredeyse hic.

  Gunluk hafif tazeleme  ~5 sn,  2 istek  — sadece toplu indirme
  Haftalik tam kurulum  ~75 sn, ~200 istek — Is Yatirim + yfinance info
"""

import asyncio
import sqlite3
import time
from pathlib import Path

from bist_mcp.hesap import fk, piyasa_degeri, pddd, temettu_verimi

SUTUNLAR = (
    "kod", "unvan", "sektor", "hisse_adedi", "ozkaynak_tl", "net_kar_tl",
    "fiyat", "temettu_12ay", "pddd", "fk", "piyasa_degeri", "temettu_verimi",
    "guncelleme",
)


def satir_hesapla(temel: dict, fiyat: float, temettu_12ay: float) -> dict:
    """Temel veriden turetilmis oranlari hesaplar.

    Eksik ozkaynak/net kar oranlari None yapar ama satiri dusurmez —
    fiyat ve sektor yine tarama disi sorularda ise yarar.
    """
    hisse_adedi = temel.get("hisse_adedi") or 0
    ozkaynak = temel.get("ozkaynak_tl")
    net_kar = temel.get("net_kar_tl")

    return {
        "kod": temel["kod"],
        "unvan": temel.get("unvan"),
        "sektor": temel.get("sektor"),
        "hisse_adedi": hisse_adedi,
        "ozkaynak_tl": ozkaynak,
        "net_kar_tl": net_kar,
        "fiyat": fiyat,
        "temettu_12ay": temettu_12ay,
        "pddd": pddd(fiyat, ozkaynak, hisse_adedi) if ozkaynak and hisse_adedi else None,
        "fk": fk(fiyat, hisse_adedi, net_kar) if net_kar and hisse_adedi else None,
        "piyasa_degeri": piyasa_degeri(fiyat, hisse_adedi) if hisse_adedi else None,
        "temettu_verimi": temettu_verimi(temettu_12ay, fiyat) if fiyat else None,
        "guncelleme": time.time(),
    }


class AnlikGorunum:
    def __init__(self, db_yolu: Path, kap, isyatirim, fiyat) -> None:
        self._kap = kap
        self._isyatirim = isyatirim
        self._fiyat = fiyat
        self._baglanti = sqlite3.connect(db_yolu, check_same_thread=False)
        self._baglanti.row_factory = sqlite3.Row
        self._baglanti.execute(
            "CREATE TABLE IF NOT EXISTS gorunum ("
            "  kod TEXT PRIMARY KEY, unvan TEXT, sektor TEXT,"
            "  hisse_adedi INTEGER, ozkaynak_tl REAL, net_kar_tl REAL,"
            "  fiyat REAL, temettu_12ay REAL, pddd REAL, fk REAL,"
            "  piyasa_degeri REAL, temettu_verimi REAL, guncelleme REAL"
            ")"
        )
        self._baglanti.commit()

    def satir_yaz(self, satir: dict) -> None:
        self._baglanti.execute(
            f"INSERT OR REPLACE INTO gorunum ({','.join(SUTUNLAR)}) "
            f"VALUES ({','.join('?' * len(SUTUNLAR))})",
            tuple(satir.get(s) for s in SUTUNLAR),
        )
        self._baglanti.commit()

    def yas_saat(self) -> float | None:
        satir = self._baglanti.execute("SELECT MIN(guncelleme) AS en_eski FROM gorunum").fetchone()
        if satir is None or satir["en_eski"] is None:
            return None
        return (time.time() - satir["en_eski"]) / 3600

    def satirlari_sec(
        self,
        fk_max: float | None = None,
        fk_min: float | None = None,
        pddd_max: float | None = None,
        temettu_verimi_min: float | None = None,
        piyasa_degeri_min: float | None = None,
        sektor: str | None = None,
        sirala: str = "piyasa_degeri",
        adet: int = 20,
    ) -> list[dict]:
        kosullar: list[str] = []
        degerler: list[object] = []

        for alan, islec, deger in (
            ("fk", "<=", fk_max), ("fk", ">=", fk_min),
            ("pddd", "<=", pddd_max),
            ("temettu_verimi", ">=", temettu_verimi_min),
            ("piyasa_degeri", ">=", piyasa_degeri_min),
        ):
            if deger is not None:
                kosullar.append(f"{alan} IS NOT NULL AND {alan} {islec} ?")
                degerler.append(deger)

        if sektor:
            kosullar.append("sektor = ?")
            degerler.append(sektor)

        if sirala not in SUTUNLAR:
            sirala = "piyasa_degeri"
        yon = "ASC" if sirala in ("fk", "pddd") else "DESC"

        sorgu = "SELECT * FROM gorunum"
        if kosullar:
            sorgu += " WHERE " + " AND ".join(kosullar)
        sorgu += f" ORDER BY {sirala} IS NULL, {sirala} {yon} LIMIT ?"
        degerler.append(adet)

        return [dict(s) for s in self._baglanti.execute(sorgu, degerler).fetchall()]

    async def hafif_tazele(self, kodlar: list[str]) -> int:
        """Gunluk — sadece fiyat ve temettu. Olculen: ~5 sn, 2 istek."""
        toplu = await self._fiyat.toplu(kodlar)
        guncellenen = 0
        for kod, veri in toplu.items():
            mevcut = self._baglanti.execute(
                "SELECT * FROM gorunum WHERE kod = ?", (kod,)
            ).fetchone()
            if mevcut is None:
                continue
            self.satir_yaz(satir_hesapla(dict(mevcut), veri["fiyat"], veri["temettu_12ay"]))
            guncellenen += 1
        return guncellenen

    async def tam_kurulum(self, kodlar: list[str]) -> int:
        """Haftalik — Is Yatirim + yfinance info. Olculen: ~75 sn."""
        dizin = await self._kap.sirket_dizini()
        toplu = await self._fiyat.toplu(kodlar)

        async def _bir_hisse(kod: str) -> dict | None:
            sirket = dizin.get(kod)
            piyasa = toplu.get(kod)
            if piyasa is None:
                return None

            kalemler, bilgi = await asyncio.gather(
                self._isyatirim.mali_tablo(kod, sirket.tip if sirket else None),
                self._fiyat.sirket_bilgi(kod),
            )
            from bist_mcp.kaynaklar.isyatirim import kalem_bul

            return satir_hesapla(
                {
                    "kod": kod,
                    "unvan": sirket.unvan if sirket else None,
                    "sektor": bilgi.get("sector"),
                    "hisse_adedi": bilgi.get("sharesOutstanding") or 0,
                    "ozkaynak_tl": kalem_bul(kalemler, "XVI. ÖZKAYNAKLAR", "Özkaynaklar"),
                    "net_kar_tl": kalem_bul(
                        kalemler,
                        "XXIII. NET DÖNEM KARI/ZARARI (XVII+XXII)",
                        "DÖNEM KARI (ZARARI)",
                    ),
                },
                piyasa["fiyat"],
                piyasa["temettu_12ay"],
            )

        yazilan = 0
        for satir in await asyncio.gather(*(_bir_hisse(k) for k in kodlar), return_exceptions=True):
            if isinstance(satir, dict):
                self.satir_yaz(satir)
                yazilan += 1
        return yazilan
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_anlik_gorunum.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/anlik_gorunum.py bist_mcp/tests/test_anlik_gorunum.py
git commit -m "feat: BIST-100 anlik gorunumu, iki kademeli tazeleme"
```

---

### Task 10: MCP sunucusu — çekirdek 9 araç

**Files:**
- Create: `bist_mcp/sunucu.py`
- Create: `bist_mcp/bist100.py` (BIST-100 kod listesi)
- Test: `bist_mcp/tests/test_sunucu_semalar.py`

**Interfaces:**
- Consumes: tüm önceki görevlerin sınıfları
- Produces: `sunucu: FastMCP` nesnesi, `arac_adlari() -> list[str]`

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_sunucu_semalar.py`:

```python
import pytest

from bist_mcp.sunucu import sunucu

CEKIRDEK = {
    "hisse_ara", "anlik_fiyat", "gecmis_fiyat", "sirket_profili",
    "finansal_tablo", "finansal_oranlar", "temettu_gecmisi",
    "kap_bildirimleri", "kap_bildirim_detay",
}


@pytest.mark.asyncio
async def test_cekirdek_araclar_kayitli():
    adlar = {a.name for a in await sunucu.list_tools()}
    assert CEKIRDEK <= adlar


@pytest.mark.asyncio
async def test_her_aracin_turkce_aciklamasi_var():
    for arac in await sunucu.list_tools():
        assert arac.description, f"{arac.name} aciklamasiz"
        assert len(arac.description) > 20, f"{arac.name} aciklamasi cok kisa"


@pytest.mark.asyncio
async def test_finansal_tablo_parametreleri_sinirli():
    """'all' secenegi modele sunulmaz; tek basina baglami sisiriyor."""
    arac = next(a for a in await sunucu.list_tools() if a.name == "finansal_tablo")
    tablo = arac.inputSchema["properties"]["tablo"]
    assert set(tablo["enum"]) == {"bilanco", "gelir", "nakit"}


@pytest.mark.asyncio
async def test_hicbir_aracta_market_parametresi_yok():
    """Kodda 'bist' sabit; model BIST disina cikamaz."""
    for arac in await sunucu.list_tools():
        assert "market" not in arac.inputSchema.get("properties", {})
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_sunucu_semalar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bist_mcp.sunucu'`

- [ ] **Step 3: BIST-100 listesini ve sunucuyu yaz**

`bist_mcp/bist100.py`:

```python
"""BIST-100 kod listesi.

Tarama kapsami (spec §7). Liste endeks revizyonlarinda elle guncellenir;
kapsam disi hisseler icin tekil araclar yine calisir.
"""

BIST100 = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN",
    "ALARK", "ALBRK", "ALFAS", "ARCLK", "ASELS", "ASTOR", "BERA", "BIMAS",
    "BIOEN", "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE",
    "DOAS", "DOHOL", "ECILC", "ECZYT", "EGEEN", "EKGYO", "ENKAI", "ENJSA",
    "EREGL", "EUPWR", "FROTO", "GARAN", "GESAN", "GUBRF", "GWIND", "HALKB",
    "HEKTS", "IPEKE", "ISCTR", "ISDMR", "ISGYO", "ISMEN", "IZMDC", "KARSN",
    "KAYSE", "KCHOL", "KONTR", "KONYA", "KORDS", "KOZAA", "KOZAL", "KRDMD",
    "KZBGY", "MAVI", "MGROS", "MIATK", "ODAS", "OTKAR", "OYAKC", "PENTA",
    "PETKM", "PGSUS", "PSGYO", "QUAGR", "SAHOL", "SASA", "SAYAS", "SISE",
    "SKBNK", "SMRTG", "SOKM", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO",
    "TSKB", "TTKOM", "TTRAK", "TUKAS", "TUPRS", "ULKER", "VAKBN", "VESBE",
    "VESTL", "YEOTK", "YKBNK", "YYLGD", "ZOREN", "ZRGYO", "AGROT", "ARDYZ",
    "BINHO", "CVKMD", "DAPGM", "EFOR",
]
```

`bist_mcp/sunucu.py`:

```python
"""BIST MCP sunucusu — stdio.

Claude Desktop'a baglamak icin:
  komut : python
  args  : ["-m", "bist_mcp.sunucu"]
  cwd   : proje koku
"""

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from bist_mcp.anlik_gorunum import AnlikGorunum
from bist_mcp.bist100 import BIST100
from bist_mcp.kaynaklar.fiyat import FiyatKaynak
from bist_mcp.kaynaklar.isyatirim import IsYatirimIstemci, kalem_bul
from bist_mcp.kaynaklar.kap import KapIstemci
from bist_mcp.kaynaklar.tcmb import TcmbIstemci
from bist_mcp.onbellek import Onbellek

load_dotenv()

KOK = Path(__file__).resolve().parent.parent
onbellek = Onbellek(KOK / "onbellek.db")
kap = KapIstemci(onbellek)
isyatirim = IsYatirimIstemci(onbellek)
fiyat = FiyatKaynak(onbellek)
tcmb = TcmbIstemci(onbellek, os.getenv("EVDS_API_KEY"))
gorunum = AnlikGorunum(KOK / "gorunum.db", kap, isyatirim, fiyat)

GUNLUK_SANIYE = 24 * 3600
HAFTALIK_SAAT = 7 * 24

kayit = logging.getLogger("bist_mcp")


async def gorunum_bakim() -> None:
    """Anlik gorunumu iki kademede taze tutar (spec §7.2).

    Yas haftalik esigi asmissa tam kurulum (~75 sn), asmamissa hafif
    tazeleme (~5 sn). Hata durumunda loglanir ve bir sonraki turda
    yeniden denenir; sunucu calismaya devam eder.
    """
    while True:
        try:
            yas = gorunum.yas_saat()
            if yas is None or yas > HAFTALIK_SAAT:
                kayit.info("Anlik gorunum tam kuruluyor (~75 sn)")
                kayit.info("Tam kurulum bitti: %d hisse", await gorunum.tam_kurulum(BIST100))
            else:
                kayit.info("Hafif tazeleme bitti: %d hisse", await gorunum.hafif_tazele(BIST100))
        except Exception:
            kayit.exception("Gorunum tazelemesi basarisiz; bir sonraki turda tekrar denenecek")

        await asyncio.sleep(GUNLUK_SANIYE)


@contextlib.asynccontextmanager
async def yasam_dongusu(_sunucu: FastMCP):
    """Arka plan bakim gorevini sunucu omru boyunca ayakta tutar.

    DIKKAT: lifespan FastMCP'ye KURULUS aninda verilmelidir. Sonradan
    `sunucu.settings.lifespan = ...` atamak ise yaramaz — dusuk seviye
    sunucu lifespan'i __init__ aninda bagliyor (dogrulandi).
    """
    gorev = asyncio.create_task(gorunum_bakim())
    try:
        yield {}
    finally:
        gorev.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await gorev


sunucu = FastMCP("bist", lifespan=yasam_dongusu)


async def _sirket(kod: str):
    return (await kap.sirket_dizini()).get(kod.strip().upper())


@sunucu.tool()
async def hisse_ara(isim: str) -> list[dict]:
    """Sirket adindan BIST hisse kodunu bulur. Ornek: 'aselsan' -> ASELS.

    Kullanicinin hisse kodunu degil sirket adini yazdigi durumlarda kullan.
    """
    aranan = isim.strip().upper()
    dizin = await kap.sirket_dizini()
    return [
        {"kod": s.kod, "unvan": s.unvan}
        for s in dict.fromkeys(dizin.values())
        if aranan in s.unvan.upper() or aranan == s.kod
    ][:10]


@sunucu.tool()
async def anlik_fiyat(kod: str) -> dict:
    """Hissenin guncel fiyatini, gunluk degisimini ve hacmini verir (TL).

    'THYAO kac TL', 'ASELS ne kadar oldu' gibi sorularda kullan.
    """
    return await fiyat.anlik(kod)


@sunucu.tool()
async def gecmis_fiyat(kod: str, baslangic: str, bitis: str | None = None) -> list[dict]:
    """Belirli tarih araligindaki gunluk fiyatlari verir (YYYY-AA-GG).

    Tek gun icin bitis bos birakilir. Istenen gun borsa kapaliysa (hafta
    sonu/tatil) cevrasindeki islem gunleri de doner; hangi gunun sorulduguna
    dikkat et ve kullaniciya kapali oldugunu soyle.
    """
    return await fiyat.gecmis(kod, baslangic, bitis)


@sunucu.tool()
async def sirket_profili(kod: str) -> dict:
    """Sirketin KAP kunyesi: unvan, sirket tipi, sektor ve hisse adedi."""
    sirket = await _sirket(kod)
    bilgi = await fiyat.sirket_bilgi(kod)
    if sirket is None:
        return {"hata": f"{kod} icin KAP kaydi bulunamadi."}
    return {
        "kod": sirket.kod,
        "unvan": sirket.unvan,
        "tip": sirket.tip,
        "sektor": bilgi.get("sector"),
        "hisse_adedi": bilgi.get("sharesOutstanding"),
        "raporlama_para_birimi": bilgi.get("financialCurrency"),
    }


@sunucu.tool()
async def finansal_tablo(
    kod: str, tablo: str = "bilanco", donem: str = "yillik", adet: int = 2
) -> dict:
    """Finansal tablolari verir. tablo: bilanco | gelir | nakit.
    donem: yillik | ceyreklik. adet: kac donem gosterilecegi (varsayilan 2).

    Rakamlar TL'dir ve Is Yatirim'dan gelir. Bankalar BDDK formatinda doner
    ('XVI. OZKAYNAKLAR' gibi). Cevapta hangi doneme ait oldugunu belirt.
    """
    if tablo not in ("bilanco", "gelir", "nakit"):
        return {"hata": "tablo bilanco, gelir veya nakit olmali."}

    sirket = await _sirket(kod)
    kalemler = await isyatirim.mali_tablo(kod, sirket.tip if sirket else None, donem, adet)
    if not kalemler:
        return {"hata": f"{kod} icin {donem} {tablo} verisi bulunamadi."}
    return {"kod": kod.upper(), "tablo": tablo, "donem": donem, "kalemler": kalemler}


@sunucu.tool()
async def finansal_oranlar(kod: str) -> dict:
    """Degerleme oranlari: F/K, PD/DD, piyasa degeri, temettu verimi.

    Oranlar Is Yatirim'in TL rakamlariyla burada hesaplanir; hazir oran
    alanlari kullanilmaz (yabanci kaynaklar USD raporlayan sirketlerde
    50 kata varan hata veriyor).
    """
    from bist_mcp.anlik_gorunum import satir_hesapla

    sirket = await _sirket(kod)
    kalemler = await isyatirim.mali_tablo(kod, sirket.tip if sirket else None)
    bilgi = await fiyat.sirket_bilgi(kod)
    anlik = await fiyat.anlik(kod)
    toplu = await fiyat.toplu([kod])

    if not anlik:
        return {"hata": f"{kod} icin fiyat verisi bulunamadi."}

    satir = satir_hesapla(
        {
            "kod": kod.upper(),
            "unvan": sirket.unvan if sirket else None,
            "sektor": bilgi.get("sector"),
            "hisse_adedi": bilgi.get("sharesOutstanding") or 0,
            "ozkaynak_tl": kalem_bul(kalemler, "XVI. ÖZKAYNAKLAR", "Özkaynaklar"),
            "net_kar_tl": kalem_bul(
                kalemler, "XXIII. NET DÖNEM KARI/ZARARI (XVII+XXII)", "DÖNEM KARI (ZARARI)"
            ),
        },
        anlik["fiyat"],
        toplu.get(kod.upper(), {}).get("temettu_12ay", 0.0),
    )
    satir.pop("guncelleme", None)
    return satir


@sunucu.tool()
async def temettu_gecmisi(kod: str) -> dict:
    """Son bir yilda odenen temettuler ve KAP'taki temettu/sermaye artirimi
    bildirimleri. Tarihleri gun.ay.yil olarak sun.
    """
    toplu = await fiyat.toplu([kod])
    bildirimler = await kap.bildirimler(kod, gun=400)
    ilgili = [
        b for b in bildirimler
        if any(a in (b.get("konu") or "").lower() for a in ("temettü", "kar payı", "sermaye artırım"))
    ]
    return {
        "kod": kod.upper(),
        "son_12ay_toplam_tl": toplu.get(kod.upper(), {}).get("temettu_12ay", 0.0),
        "kap_bildirimleri": ilgili[:10],
    }


@sunucu.tool()
async def kap_bildirimleri(kod: str, gun: int = 90) -> list[dict]:
    """Sirketin KAP aciklamalari (varsayilan son 90 gun).

    Ozel durum aciklamalari, finansal rapor duyurulari, yonetim degisiklikleri
    burada cikar. Sirket haberi sorulariNDA bunu kullan.
    """
    return await kap.bildirimler(kod, gun)


@sunucu.tool()
async def kap_bildirim_detay(bildirim_no: str) -> dict:
    """Tek bir KAP bildiriminin tam metnini verir.

    kap_bildirimleri sonucundaki bildirim_no ile cagrilir; ozet yetmediginde
    kullan.
    """
    return await kap.bildirim_detay(bildirim_no)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sunucu.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_sunucu_semalar.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bist_mcp/sunucu.py bist_mcp/bist100.py bist_mcp/tests/test_sunucu_semalar.py
git commit -m "feat: MCP sunucusu, arka plan bakimi ve cekirdek 9 arac"
```

---

### Task 11: MCP sunucusu — analiz, piyasa ve makro araçları

**Files:**
- Modify: `bist_mcp/sunucu.py` (7 araç eklenir)
- Test: `bist_mcp/tests/test_sunucu_semalar.py` (genişletilir)

**Interfaces:**
- Consumes: Task 10'daki `sunucu`, `teknik` (Task 7), `gorunum` (Task 9), `tcmb` (Task 8)
- Produces: 16 araçlık tam set

- [ ] **Step 1: Başarısız testi yaz**

`bist_mcp/tests/test_sunucu_semalar.py` dosyasına eklenir:

```python
ANALIZ_VE_MAKRO = {
    "teknik_analiz", "hisse_karsilastir", "sektor_karsilastirma",
    "hisse_tarama", "endeks_verisi", "doviz_altin", "makro_gosterge",
}


@pytest.mark.asyncio
async def test_toplam_16_arac_kayitli():
    adlar = {a.name for a in await sunucu.list_tools()}
    assert CEKIRDEK | ANALIZ_VE_MAKRO == adlar
    assert len(adlar) == 16


@pytest.mark.asyncio
async def test_analist_gorusu_araci_yok():
    """Bilincli karar: guvenilir kaynagi yok, uydurma arac modeli yaniltir."""
    adlar = {a.name for a in await sunucu.list_tools()}
    assert "analist_gorusu" not in adlar


@pytest.mark.asyncio
async def test_hisse_karsilastir_liste_alir():
    arac = next(a for a in await sunucu.list_tools() if a.name == "hisse_karsilastir")
    assert arac.inputSchema["properties"]["kodlar"]["type"] == "array"
```

- [ ] **Step 2: Testi koş, başarısız olduğunu doğrula**

Run: `python -m pytest bist_mcp/tests/test_sunucu_semalar.py -v`
Expected: FAIL — 16 araç yok, 9 var

- [ ] **Step 3: Kalan 7 aracı ekle**

`bist_mcp/sunucu.py` dosyasına, `def main()` satırından önce eklenir:

```python
from bist_mcp import teknik
from bist_mcp.kaynaklar.tcmb import GOSTERGELER

ENDEKSLER = {
    "XU100": "XU100.IS", "XU030": "XU030.IS", "XU050": "XU050.IS",
    "XBANK": "XBANK.IS", "XUSIN": "XUSIN.IS", "XUTEK": "XUTEK.IS",
    "XUMAL": "XUMAL.IS",
}


@sunucu.tool()
async def teknik_analiz(kod: str) -> dict:
    """RSI, MACD, 20/50/200 gunluk hareketli ortalamalar ve destek/direnc.

    Son bir yillik fiyat verisine dayanir. Yorumu sun ama al/sat tavsiyesi verme.
    """
    import datetime as dt

    bugun = dt.date.today()
    mumlar = await fiyat.gecmis(kod, str(bugun - dt.timedelta(days=400)), str(bugun))
    if not mumlar:
        return {"hata": f"{kod} icin fiyat gecmisi bulunamadi."}

    kapanislar = [m["kapanis"] for m in mumlar]
    return {
        "kod": kod.upper(),
        "son_kapanis": kapanislar[-1],
        "rsi_14": teknik.rsi(kapanislar),
        "macd": teknik.macd(kapanislar),
        "ma_20": teknik.hareketli_ortalama(kapanislar, 20),
        "ma_50": teknik.hareketli_ortalama(kapanislar, 50),
        "ma_200": teknik.hareketli_ortalama(kapanislar, 200),
        "son_3ay": teknik.destek_direnc(mumlar[-63:]),
    }


@sunucu.tool()
async def hisse_karsilastir(kodlar: list[str]) -> list[dict]:
    """Iki ile bes hisseyi temel oranlariyla yan yana koyar.

    'X mi Y mi daha ucuz', 'bunlari karsilastir' sorularinda kullan.
    """
    secilen = [k.strip().upper() for k in kodlar][:5]
    if len(secilen) < 2:
        return [{"hata": "en az iki hisse kodu gerekli"}]
    return [await finansal_oranlar(kod) for kod in secilen]


@sunucu.tool()
async def sektor_karsilastirma(kod: str) -> dict:
    """Hissenin kendi sektorundeki konumu: sektor ortalamasi ve siralama.

    BIST-100 gorunumune dayanir; kapsam disi hisselerde sektor bos donebilir.
    """
    bilgi = await fiyat.sirket_bilgi(kod)
    sektor = bilgi.get("sector")
    if not sektor:
        return {"hata": f"{kod} icin sektor bilgisi bulunamadi."}

    akranlar = gorunum.satirlari_sec(sektor=sektor, adet=100)
    fkler = [a["fk"] for a in akranlar if a["fk"]]
    pdddler = [a["pddd"] for a in akranlar if a["pddd"]]
    return {
        "kod": kod.upper(),
        "sektor": sektor,
        "sektordeki_sirket_sayisi": len(akranlar),
        "sektor_ortalama_fk": round(sum(fkler) / len(fkler), 2) if fkler else None,
        "sektor_ortalama_pddd": round(sum(pdddler) / len(pdddler), 2) if pdddler else None,
        "kapsam": "BIST-100",
    }


@sunucu.tool()
async def hisse_tarama(
    fk_max: float | None = None,
    fk_min: float | None = None,
    pddd_max: float | None = None,
    temettu_verimi_min: float | None = None,
    piyasa_degeri_min: float | None = None,
    sektor: str | None = None,
    sirala: str = "piyasa_degeri",
    adet: int = 20,
) -> dict:
    """Verilen kriterlere uyan hisseleri listeler. Kriterler VE ile birlesir.

    ONEMLI: Sonuclar BIST-100 ile sinirlidir; cevapta bunu belirt.
    temettu_verimi_min yuzde olarak verilir (ornek: 5 = %5).
    """
    satirlar = gorunum.satirlari_sec(
        fk_max=fk_max, fk_min=fk_min, pddd_max=pddd_max,
        temettu_verimi_min=temettu_verimi_min, piyasa_degeri_min=piyasa_degeri_min,
        sektor=sektor, sirala=sirala, adet=adet,
    )
    yas = gorunum.yas_saat()
    return {
        "kapsam": "BIST-100",
        "veri_yasi_saat": round(yas, 1) if yas is not None else None,
        "sonuc_sayisi": len(satirlar),
        "hisseler": satirlar,
    }


@sunucu.tool()
async def endeks_verisi(endeks: str = "XU100") -> dict:
    """BIST endekslerinin guncel degeri.

    Gecerli: XU100, XU030, XU050, XBANK (banka), XUSIN (sinai),
    XUTEK (teknoloji), XUMAL (mali).
    """
    ad = endeks.strip().upper()
    if ad not in ENDEKSLER:
        return {"hata": f"gecersiz endeks: {endeks}. Gecerli: {', '.join(ENDEKSLER)}"}
    return await fiyat.anlik(ENDEKSLER[ad])


@sunucu.tool()
async def doviz_altin(varlik: str = "usdtry") -> dict:
    """Doviz kuru ve altin fiyati: usdtry, eurtry, gram_altin."""
    return await tcmb.gosterge(varlik, son_kayit=5)


@sunucu.tool()
async def makro_gosterge(gosterge: str = "tufe", son_kayit: int = 12) -> dict:
    """TCMB makro gostergeleri: tufe, ufe, politika_faizi, tahvil_2y.

    Enflasyona gore reel getiri sorularinda tufe ile birlikte kullan.
    """
    if gosterge.strip().lower() not in GOSTERGELER:
        return {"hata": f"gecersiz gosterge. Gecerli: {', '.join(sorted(GOSTERGELER))}"}
    return await tcmb.gosterge(gosterge, son_kayit)
```

- [ ] **Step 4: Testleri koş**

Run: `python -m pytest bist_mcp/tests/test_sunucu_semalar.py -v`
Expected: 7 passed

- [ ] **Step 5: Tüm birim testleri koş**

Run: `python -m pytest bist_mcp/ -v`
Expected: 51 passed (ağ testleri hariç)

- [ ] **Step 6: Commit**

```bash
git add bist_mcp/sunucu.py bist_mcp/tests/test_sunucu_semalar.py
git commit -m "feat: analiz, piyasa ve makro araclari - 16 arac tamam"
```

---

### Task 12: Arka plan tazeleme, entegrasyon testleri ve Claude Desktop doğrulaması

Aşama 1'in kapanışı. Bu görev bitince spec §13'e göre Aşama 2'ye geçilir.

**Files:**
- Modify: `bist_mcp/sunucu.py` (arka plan görevi)
- Create: `bist_mcp/tests/test_entegrasyon.py`
- Create: `README.md`

**Interfaces:**
- Consumes: tüm önceki görevler
- Produces: `async gorunum_bakim()` arka plan görevi

- [ ] **Step 1: Ağ entegrasyon testlerini yaz**

`bist_mcp/tests/test_entegrasyon.py`:

```python
"""Gercek sunuculara cikan testler: python -m pytest -m network"""

import pytest

from bist_mcp.kaynaklar.fiyat import FiyatKaynak
from bist_mcp.kaynaklar.isyatirim import IsYatirimIstemci, kalem_bul
from bist_mcp.kaynaklar.kap import KapIstemci
from bist_mcp.onbellek import Onbellek

pytestmark = pytest.mark.network


@pytest.fixture
def onbellek(tmp_path):
    return Onbellek(tmp_path / "e.db")


@pytest.mark.asyncio
async def test_kap_dizini_bankalari_cozer(onbellek):
    """Virgullu stockCode hatasinin regresyonu — canli veriyle."""
    dizin = await KapIstemci(onbellek).sirket_dizini()
    assert len(dizin) > 780, f"beklenen ~807 ticker, gelen {len(dizin)}"
    for kod in ("GARAN", "YKBNK", "VAKBN", "HALKB", "ISCTR", "AKBNK"):
        assert kod in dizin, f"{kod} dizinde yok"
        assert dizin[kod].tip == "BNK"


@pytest.mark.asyncio
async def test_kap_bildirimleri_geliyor(onbellek):
    bildirimler = await KapIstemci(onbellek).bildirimler("ASELS", gun=120)
    assert len(bildirimler) > 5
    assert bildirimler[0]["konu"]


@pytest.mark.asyncio
async def test_isyatirim_utf8_bozulmuyor(onbellek):
    """Sunucu charset gondermiyor; Turkce bozulursa burada yakalanir."""
    kalemler = await IsYatirimIstemci(onbellek).mali_tablo("THYAO", tip=None)
    adlar = [k["ad"] for k in kalemler]
    assert any("Özkaynaklar" in a for a in adlar), adlar[:5]


@pytest.mark.asyncio
async def test_banka_bilancosu_bddk_formatinda(onbellek):
    kalemler = await IsYatirimIstemci(onbellek).mali_tablo("GARAN", tip="BNK")
    assert kalem_bul(kalemler, "XVI. ÖZKAYNAKLAR") is not None


@pytest.mark.asyncio
async def test_thyao_pddd_canli_veriyle_makul(onbellek):
    """Uctan uca regresyon: sonuc 18 civarindaysa oran katmani bozulmus."""
    from bist_mcp.hesap import pddd

    isy = IsYatirimIstemci(onbellek)
    fyt = FiyatKaynak(onbellek)

    kalemler = await isy.mali_tablo("THYAO", tip=None)
    ozkaynak = kalem_bul(kalemler, "Özkaynaklar")
    bilgi = await fyt.sirket_bilgi("THYAO")
    anlik = await fyt.anlik("THYAO")

    sonuc = pddd(anlik["fiyat"], ozkaynak, bilgi["sharesOutstanding"])
    assert 0.2 < sonuc < 1.5, f"PD/DD {sonuc} — yfinance tuzagi geri gelmis olabilir"


@pytest.mark.asyncio
async def test_toplu_indirme_temettu_getiriyor(onbellek):
    veri = await FiyatKaynak(onbellek).toplu(["GARAN", "TUPRS"])
    assert veri["GARAN"]["temettu_12ay"] > 0
    assert veri["GARAN"]["fiyat"] > 0
```

- [ ] **Step 2: Ağ testlerini koş**

Run: `python -m pytest bist_mcp/tests/test_entegrasyon.py -m network -v`
Expected: 6 passed (İnternet gerekir; ~30 sn sürer)

- [ ] **Step 3: Sunucunun ayağa kalktığını doğrula**

Run: `PYTHONIOENCODING=utf-8 python -c "from bist_mcp.sunucu import sunucu; import asyncio; print(len(asyncio.run(sunucu.list_tools())), 'arac')"`
Expected: `16 arac`

- [ ] **Step 4: README yaz**

`README.md`:

````markdown
# BIST MCP Sunucusu

BIST hisseleri, endeksler ve TCMB makro gostergeleri icin MCP sunucusu.
16 arac; veri Is Yatirim, KAP, yfinance ve TCMB EVDS'ten gelir.

## Kurulum

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env    # EVDS_API_KEY doldur (opsiyonel)
```

## Test

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m pytest bist_mcp/              # hizli testler
python -m pytest bist_mcp/ -m network   # gercek sunuculara cikanlar
```

## Claude Desktop'a baglama

`claude_desktop_config.json` icine:

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

## Veri kurallari

- Oranlar TL bazinda **hesaplanir**; yfinance'in `priceToBook`, `trailingPE`,
  `dividendYield` alanlari ve `news` kullanilmaz. Gerekce: THYAO icin
  `priceToBook` 18,64 diyor, gercek deger 0,38 (49 kat sapma) — sirket
  finansallarini USD raporluyor, hissesi TRY islem goruyor.
- KAP OID'si toplu sirket listesinden cozulur; `member/filter` bir isim
  aramasidir ve yanlis sirketi dondurur.
- `stockCode` virgullu coklu kod tutar ("GARAN, TGB"); bolunmeden
  eslestirilirse bankalarin cogu kaybolur.
- Tarama BIST-100 ile sinirlidir.
````

- [ ] **Step 5: Claude Desktop'ta elle doğrula**

Sunucuyu Claude Desktop'a bağla ve şunları sor. Bu liste spec §10'daki
doğrulama listesinin MCP tarafıdır — her satır ölçülmüş bir hatayı sınar:

| # | Sor | Beklenen |
|---|---|---|
| 1 | THYAO'nun anlık fiyatı | ~296 TL civarı, TRY |
| 2 | THYAO'nun PD/DD'si | **~0,38** — 18 DEĞİL |
| 3 | GARAN'ın bilançosu | BDDK formatı, `XVI. ÖZKAYNAKLAR` dolu |
| 4 | ASELS'in son KAP açıklamaları | 2026 tarihli gerçek bildirimler |
| 5 | F/K'sı 10 altı, temettü verimi %3 üstü hisseler | Tablo + "BIST-100" notu |
| 6 | Verisi olmayan bir kod (ör. XXXXX) | Net "bulunamadı" — uydurma yok |

**Kritik olanlar 2, 4 ve 6.** Bunlarda yanlış çıktı bir süzgecin bozulduğunu
gösterir; Aşama 2'ye geçilmez.

- [ ] **Step 6: Commit**

```bash
git add bist_mcp/sunucu.py bist_mcp/tests/test_entegrasyon.py README.md
git commit -m "feat: arka plan tazeleme, entegrasyon testleri ve README"
```

---

## Aşama 1 tamamlanma ölçütü

- `python -m pytest bist_mcp/` → tüm birim testleri geçiyor
- `python -m pytest bist_mcp/ -m network` → tüm ağ testleri geçiyor
- Claude Desktop'ta Task 12 Step 6 listesinin 6 satırı da doğru cevaplanıyor

Üçü de sağlandığında Aşama 2 (`ajan/` — Telegram botu ve NVIDIA döngüsü) için
ayrı bir plan yazılır.

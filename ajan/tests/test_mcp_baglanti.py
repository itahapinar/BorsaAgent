import asyncio
import json
import sys
from dataclasses import dataclass

import pytest

from ajan.mcp_baglanti import McpBaglanti, arac_semalarina_cevir, sonucu_metne_cevir

PROJE_KOKU = r"C:/Users/Taha/Desktop/Borsa Agent v2"


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


# --- Sema cevrimi ----------------------------------------------------------


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


# --- Sonuc metne cevrimi ---------------------------------------------------


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


# --- Zaman asimi ve yeniden baglanma ---------------------------------------


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
    b = McpBaglanti(sys.executable, ["-c", "pass"], ".")
    b._oturum = oturum
    return b


async def test_zaman_asiminda_asili_kalmaz(monkeypatch):
    """Asili bir cagri botun tek kilidini sonsuza kadar tutardi."""
    monkeypatch.setattr("ajan.mcp_baglanti.ARAC_ZAMAN_ASIMI", 0.05)
    metin = await _baglanti(AsiliOturum()).cagir("anlik_fiyat", {})
    assert "HATA" in metin
    assert "cevap vermedi" in metin


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


async def test_baglanmadan_cagirmak_net_hata_verir():
    baglanti = McpBaglanti(sys.executable, ["-c", "pass"], ".")
    with pytest.raises(RuntimeError) as hata:
        await baglanti.cagir("anlik_fiyat", {})
    assert "baglan" in str(hata.value)


async def test_baslamayan_sunucuda_baglan_net_hata_verir():
    """Yanlis komutta bot sessizce yarim ayaga kalkmamali."""
    baglanti = McpBaglanti(sys.executable, ["-c", "import sys; sys.exit(1)"], ".")
    with pytest.raises(Exception):
        await baglanti.baglan()
    await baglanti.kapat()  # temizlik ikinci bir hata firlatmamali


# --- Gercek sunucu ---------------------------------------------------------


def _gercek() -> McpBaglanti:
    return McpBaglanti(sys.executable, ["-m", "bist_mcp.sunucu"], PROJE_KOKU)


@pytest.mark.network
async def test_gercek_sunucuya_baglanip_arac_cagirir():
    """Asama 1 sunucusuyla uctan uca: 17 arac gelmeli, PD/DD dogru olmali."""
    baglanti = _gercek()
    await baglanti.baglan()
    try:
        semalar = await baglanti.arac_semalari()
        assert len(semalar) == 17
        assert semalar[0]["type"] == "function"

        metin = await baglanti.cagir("finansal_oranlar", {"kod": "THYAO"})
        veri = json.loads(metin)
        assert 0.2 < veri["pddd"] < 1.0, "PD/DD yfinance tuzagina dusmus olabilir"
    finally:
        await baglanti.kapat()


@pytest.mark.network
async def test_olmayan_arac_istisna_firlatmaz():
    baglanti = _gercek()
    await baglanti.baglan()
    try:
        metin = await baglanti.cagir("boyle_bir_arac_yok", {})
        assert "HATA" in metin
    finally:
        await baglanti.kapat()


@pytest.mark.network
async def test_ayri_tasklarda_acilip_kapanabilir():
    """Olculdu: stdio_client'in cancel scope'u girildigi task'te kapanmali.

    Botun gercek deseni bu -- baglan() acilista, cagir() mesaj task'inde,
    kapat() kapanista. Naif AsyncExitStack tasarimi burada
    "Attempted to exit cancel scope in a different task" firlatiyordu ve
    alt surec sizip kaliyordu.
    """
    baglanti = _gercek()
    await asyncio.create_task(baglanti.baglan())
    await asyncio.create_task(baglanti.arac_semalari())
    await asyncio.create_task(baglanti.kapat())
    assert baglanti._oturum is None

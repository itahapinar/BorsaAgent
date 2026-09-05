import pytest

from bist_mcp.sunucu import sunucu

CEKIRDEK = {
    "hisse_ara",
    "anlik_fiyat",
    "gecmis_fiyat",
    "sirket_profili",
    "finansal_tablo",
    "finansal_oranlar",
    "temettu_gecmisi",
    "kap_bildirimleri",
    "kap_bildirim_detay",
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

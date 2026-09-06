"""Detayli analizin TEK cagrida tum veriyi toplamasi.

Olculdu (canli bot, GENKM): "detayli analiz" istendiginde model 3-4 arac
cagirip duruyordu; RSI/MACD hic gelmedi ve gelir tablosu cekilmedigi icin
model "detayli gelir tablosu yok" deyip EBIT'i ve brut marji TAHMIN ETTI.
Veri kaynakta vardi. Bir finans botunda rakam uydurmak en kotu hata.
"""

import pytest

from bist_mcp.sunucu import ANALIZ_BOLUMLERI, analizi_derle


def _tam_sonuc():
    return {ad: {"veri": ad} for ad in ANALIZ_BOLUMLERI}


def test_teknik_ve_gelir_tablosu_kapsamda():
    """Kullanicinin eksik bildirdigi iki bolum."""
    assert "teknik" in ANALIZ_BOLUMLERI
    assert "gelir_tablosu" in ANALIZ_BOLUMLERI


def test_tum_bolumler_derlenir():
    derlenen = analizi_derle("thyao", _tam_sonuc())
    assert derlenen["kod"] == "THYAO"
    assert derlenen["eksik_bolumler"] == []
    for ad in ANALIZ_BOLUMLERI:
        assert derlenen[ad] == {"veri": ad}


def test_hatali_bolum_eksik_isaretlenir():
    sonuclar = _tam_sonuc()
    sonuclar["gelir_tablosu"] = {"hata": "bulunamadi"}
    derlenen = analizi_derle("X", sonuclar)
    assert derlenen["eksik_bolumler"] == ["gelir_tablosu"]


def test_istisna_atan_bolum_tum_analizi_dusurmez():
    """Tek bir kaynak hatasi butun cevabi kaybettirmemeli."""
    sonuclar = _tam_sonuc()
    sonuclar["teknik"] = RuntimeError("ag hatasi")
    derlenen = analizi_derle("X", sonuclar)
    assert derlenen["teknik"] is None
    assert "teknik" in derlenen["eksik_bolumler"]
    assert derlenen["fiyat"] == {"veri": "fiyat"}


def test_eksik_bolum_varsa_uydurma_yasagi_eklenir():
    sonuclar = _tam_sonuc()
    sonuclar["gelir_tablosu"] = {"hata": "yok"}
    not_alani = analizi_derle("X", sonuclar)["not"]
    assert "uydurma" in not_alani.lower()
    assert "gelir_tablosu" in not_alani


def test_bolum_tamsa_not_alani_yok():
    assert "not" not in analizi_derle("X", _tam_sonuc())


@pytest.mark.asyncio
async def test_arac_kayitli():
    from bist_mcp.sunucu import sunucu

    assert "detayli_analiz" in {a.name for a in await sunucu.list_tools()}


@pytest.mark.network
@pytest.mark.asyncio
async def test_gercek_hissede_teknik_ve_gelir_tablosu_gelir():
    """Kullanicinin eksik gordugu iki bolum canlida gercekten doluyor mu."""
    from bist_mcp.sunucu import detayli_analiz

    sonuc = await detayli_analiz("GENKM")

    assert sonuc["teknik"]["rsi_14"] is not None
    assert sonuc["teknik"]["macd"] is not None
    assert sonuc["gelir_tablosu"]["kalemler"], "gelir tablosu bos geldi"
    assert sonuc["oranlar"]["pddd"] is not None
    assert sonuc["profil"]["unvan"]

"""Fiyati olmayan satirlar veriden atilir.

Olculdu (TUPRS, 08.09.2026 sabahi): Yahoo 07.09 icin satir donduruyordu
ama Open/High/Low/Close NaN, yalnizca Volume dolu -- seans verisi henuz
yayimlanmamis. `anlik` son satiri kosulsuz aldigi icin:

    fiyat: nan, onceki_kapanis: 388.5, tarih: '2026-09-07'

Model NaN'i gorup yanindaki onceki kapanisi aldi ve "07.09 kapanisi
388,50 TL" dedi -- hem yanlis fiyat hem yanlis tarih. Gercekte 388,50
04.09'un kapanisiydi.

Ayni satirlar teknik_analiz'e de siziyordu: son_kapanis ve ma_20 NaN.
"""

import pandas as pd
import pytest

from bist_mcp.kaynaklar.fiyat import fiyatli_satirlar


def _cerceve(kapanislar, hacimler=None):
    return pd.DataFrame(
        {
            "Open": kapanislar,
            "High": kapanislar,
            "Low": kapanislar,
            "Close": kapanislar,
            "Volume": hacimler or [1] * len(kapanislar),
        },
        index=pd.to_datetime(["2026-09-04", "2026-09-05", "2026-09-07"][: len(kapanislar)]),
    )


def test_normal_veri_degismez():
    veri = _cerceve([388.5, 391.0, 394.0])
    assert len(fiyatli_satirlar(veri)) == 3


def test_kapanissiz_son_satir_atilir():
    """Asil vaka: hacim var ama fiyat yok."""
    veri = _cerceve([388.5, 391.0, float("nan")], hacimler=[100, 200, 25451395])
    suzulmus = fiyatli_satirlar(veri)
    assert len(suzulmus) == 2
    assert suzulmus["Close"].iloc[-1] == 391.0
    assert str(suzulmus.index[-1])[:10] == "2026-09-05"


def test_hepsi_kapanissizsa_bos_doner():
    veri = _cerceve([float("nan"), float("nan")])
    assert fiyatli_satirlar(veri).empty


def test_bos_cerceve_cokmez():
    assert fiyatli_satirlar(pd.DataFrame()).empty


@pytest.mark.network
@pytest.mark.asyncio
async def test_canli_veride_nan_donmez():
    """Arac ciktisinda NaN olursa model onu baska bir rakamla dolduruyor."""
    import math

    from bist_mcp.sunucu import anlik_fiyat, teknik_analiz

    a = await anlik_fiyat("TUPRS")
    for alan in ("fiyat", "onceki_kapanis", "gun_yuksek", "gun_dusuk"):
        assert not math.isnan(a[alan]), f"{alan} NaN"

    t = await teknik_analiz("TUPRS")
    assert not math.isnan(t["son_kapanis"])
    assert t["ma_20"] is None or not math.isnan(t["ma_20"])

"""Tam kurulumun ne zaman gerektigi.

Olculdu (canli sunucu): tablo 630 hisse iceriyordu, evren 807 ticker.
Kayit/evren orani %78 ve esik %90 oldugu icin karar HER ACILISTA "tam
kurulum gerekli" diyordu -- veri taze olsa bile. Tarama ~8 dakika ve
~700 istek; haftalik onbellek hic devreye girmiyordu.

Sebep: tarama yalnizca FIYAT VERISI OLAN hisseleri yaziyor (807'nin
630'u). Tablo bu esige hicbir zaman ulasamazdi.

Oran tahmini kaldirildi. Biten tarama bir TAMAMLANMA DAMGASI birakir;
yarida kesilen birakmaz. Karar yalnizca bu damgaya bakar.
"""

from bist_mcp.sunucu import HAFTALIK_SAAT, tam_kurulum_gerekli


def test_damga_yoksa_kurulur():
    assert tam_kurulum_gerekli(None)


def test_damga_eskiyse_kurulur():
    assert tam_kurulum_gerekli(HAFTALIK_SAAT + 1)


def test_taze_damgada_kurulmaz():
    assert not tam_kurulum_gerekli(1.0)


def test_eksik_ticker_yeniden_kurulusa_yol_acmaz():
    """Asil hata buydu: 630/807 orani kalici olarak esigin altinda kaliyordu."""
    assert not tam_kurulum_gerekli(0.5)

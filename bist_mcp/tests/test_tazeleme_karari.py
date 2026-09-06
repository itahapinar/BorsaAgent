"""Tam kurulumun ne zaman gerektigi.

Olculdu: karar yalnizca YASA bakiyordu. Satirlar tamamlandikca yazilmaya
baslayinca yarida kesilen bir tarama TAZE zaman damgali ama EKSIK bir tablo
birakiyor; sunucu bunu guncel sanip bir hafta boyunca tam taramayi hic
yapmiyordu. Gercek durum: 630 hisselik evrende 7 kayit ve hisse_tarama
neredeyse bos.
"""

from bist_mcp.sunucu import HAFTALIK_SAAT, tam_kurulum_gerekli


def test_hic_veri_yoksa_kurulur():
    assert tam_kurulum_gerekli(None, 0, 630)


def test_veri_eskiyse_kurulur():
    assert tam_kurulum_gerekli(HAFTALIK_SAAT + 1, 630, 630)


def test_taze_ve_tam_tabloda_kurulmaz():
    assert not tam_kurulum_gerekli(1.0, 630, 630)


def test_taze_ama_eksik_tabloda_kurulur():
    """Yarida kesilen taramanin biraktigi durum."""
    assert tam_kurulum_gerekli(1.0, 7, 630)


def test_kucuk_eksiklik_yeniden_kurulusa_yol_acmaz():
    """Birkac hissenin veri kaynaginda tablosu yok; bu normal."""
    assert not tam_kurulum_gerekli(1.0, 609, 630)


def test_evren_bos_gelirse_kurulmaya_calisilmaz():
    assert not tam_kurulum_gerekli(1.0, 0, 0)

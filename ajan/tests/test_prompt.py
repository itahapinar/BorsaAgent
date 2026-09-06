import datetime as dt

from ajan.config import TRT
from ajan.prompt import sistem_promptu


def test_bugunun_tarihi_turkce_yazilir():
    """Bu olmadan 'gecen hafta', 'bu yil' calismaz ve VPS UTC ise gun kayar.

    Gun adi TAM eslesme ile kontrol ediliyor: "Cuma" alt dizgi olarak
    "Cumartesi" icinde de geciyor, yani gevsek kontrol yanlis gunu yakalamaz.
    """
    metin = sistem_promptu(dt.datetime(2026, 9, 5, 14, 0, tzinfo=TRT))
    assert "05.09.2026" in metin
    assert "Cumartesi, 05.09.2026" in metin


def test_hafta_ici_gun_adi_da_dogru():
    metin = sistem_promptu(dt.datetime(2026, 9, 4, 14, 0, tzinfo=TRT))
    assert "Cuma, 04.09.2026" in metin


def test_uydurma_yasagi_var():
    metin = sistem_promptu()
    assert "uydurma" in metin.lower()


def test_yatirim_tavsiyesi_yasagi_var():
    """Buyuk I ile yazilan kelimede .lower() ise yaramaz.

    "TAVSIYESI".lower() Python'da "tavsi̇yesi̇" veriyor: noktali buyuk I
    kuculdugunde nokta ayri bir birlesim karakteri olarak kaliyor ve
    "tavsiye" alt dizgi olarak bulunmuyor. Bu yuzden yazildigi bicim
    dogrudan aranir.
    """
    assert "TAVSİYE" in sistem_promptu()


def test_donem_belirtme_kurali_var():
    metin = sistem_promptu()
    assert "dönem" in metin.lower()


def test_dusuk_fk_uyarisi_var():
    """Asama 1'de olculdu: F/K<2 genelde muhasebe etkisi, ucuzluk degil."""
    metin = sistem_promptu()
    assert "F/K" in metin


def test_not_alanini_aktarma_kurali_var():
    """Asama 1 araclari guvenilmez oranlarda `not` alani dolduruyor.

    ISATR gibi coklu hisse sinifinda oran GUVENILMEZ yaziyor; model bunu
    okumazsa uyariyi yutup sayiyi kesin gibi sunar.
    """
    metin = sistem_promptu()
    assert "`not`" in metin


def test_prompt_makul_boyutta():
    """Her istekte gonderiliyor; sismesin."""
    assert len(sistem_promptu()) < 3000

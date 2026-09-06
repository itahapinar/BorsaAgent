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


def test_kisaltma_acilimlari_veriliyor():
    """Olculdu: model PD/DD'yi "Pi Degeri / Denge Degeri" diye acti.

    Rakam dogruydu (ASELS 5,77) ama acilim uydurmaydi. Dogru acilim
    promptta yazili olmazsa model tahmin ediyor.
    """
    metin = sistem_promptu()
    assert "Piyasa Değeri / Defter Değeri" in metin
    assert "Fiyat / Kazanç" in metin


def test_binlik_ayirici_kurali_var():
    """Olculdu: model "44 799 808" yazdi; bosluk ayirici hem yanlis biciM
    hem de tabloda sayiyi bolunebilir hale getiriyor."""
    metin = sistem_promptu()
    assert "44.799.808" in metin
    assert "boşluk" in metin.lower()


def test_detayli_analiz_araci_promptta_var():
    """Olculdu: model detayli analizde 3-4 arac cagirip duruyordu."""
    metin = sistem_promptu()
    assert "detayli_analiz" in metin
    assert "RSI" in metin


def test_tahmin_yasagi_acik():
    """Olculdu: model 'detayli gelir tablosu yok' deyip EBIT'i tahmin etti."""
    metin = sistem_promptu()
    assert "TAHMİN ETME" in metin
    assert "tahmini" in metin


def test_arac_rakamini_degistirmeme_kurali_var():
    """Olculdu: arac temettu 0,2053 dondu, model "0,00 TL" yazdi."""
    metin = sistem_promptu()
    assert "0,2053" in metin
    assert "hafızandan" in metin

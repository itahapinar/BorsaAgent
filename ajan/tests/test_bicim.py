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


def test_tam_sinirda_cumleden_bolunur():
    """Kesim tam sinira denk geldiginde parca yine cumle sonunda bitmeli."""
    cumle = "abcd. "
    metin = cumle * 2000
    parcalar = mesaji_bol(metin)
    assert all(len(p) <= 4096 for p in parcalar)
    assert all(p.endswith(".") for p in parcalar[:-1])

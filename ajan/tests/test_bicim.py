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


# --- Telegram bicimlendirme -------------------------------------------------
# Olculdu (canli bot): cevap ham markdown olarak dustu. Telegram boru
# tablosunu HIC render etmiyor ve parse_mode ayarlanmadigi icin ** yildizlari
# metnin icinde gorunuyordu. Modelden hizalama beklemek yerine tabloyu biz
# hizaliyoruz: model markdown uretmekte iyi, sutun hizalamakta degil.

from ajan.bicim import mesaji_bol, telegram_html  # noqa: E402

TABLO = """| Öğe | Değer |
|-----|-------|
| Son fiyat | 296,00 TL |
| Günlük hacim | 44,8 milyon TL |"""


def test_markdown_tablosu_hizali_monospace_bloga_cevrilir():
    sonuc = telegram_html(TABLO)
    assert "<pre>" in sonuc and "</pre>" in sonuc
    assert "|" not in sonuc, "boru isareti kalmamali"
    govde = sonuc[sonuc.index("<pre>") + 5 : sonuc.index("</pre>")].strip("\n")
    satirlar = govde.split("\n")
    # Deger sutunu ayni sutunda baslamali
    basi = [s.index("296,00") for s in satirlar if "296,00" in s]
    basi += [s.index("44,8") for s in satirlar if "44,8" in s]
    assert len(set(basi)) == 1, f"sutunlar hizali degil: {satirlar}"


def test_tablo_hucrelerindeki_yildizlar_temizlenir():
    sonuc = telegram_html("| Öğe | Değer |\n|---|---|\n| **Son fiyat** | **296,00 TL** |")
    assert "*" not in sonuc


def test_kalin_metin_html_etiketine_cevrilir():
    assert telegram_html("**THYAO** analizi") == "<b>THYAO</b> analizi"


def test_html_ozel_karakterleri_kacirilir():
    """Kacirilmazsa Telegram 'can't parse entities' ile mesaji reddediyor."""
    sonuc = telegram_html("5 < 10 & 3 > 1")
    assert "&lt;" in sonuc and "&amp;" in sonuc and "&gt;" in sonuc
    assert "<" not in sonuc.replace("&lt;", "").replace("&gt;", "")


def test_tek_tirnakli_kod_etiketlenir():
    assert telegram_html("`THYAO`") == "<code>THYAO</code>"


def test_bolme_acik_pre_blogu_birakmaz():
    """4096'yi asan bir tablo <pre> ortasindan bolunurse Telegram reddeder."""
    satirlar = "\n".join(f"| Kalem {i} | {i} milyar TL |" for i in range(400))
    metin = telegram_html("| Öğe | Değer |\n|---|---|\n" + satirlar)
    parcalar = mesaji_bol(metin)

    assert len(parcalar) > 1
    for parca in parcalar:
        assert len(parca) <= 4096
        assert parca.count("<pre>") == parca.count("</pre>"), parca[:120]


# --- Tablo genisligi --------------------------------------------------------
# Olculdu (canli cikti): model "iki sutun kullan" kuralina uymayip 250
# karakter genisliginde bir tablo uretti; telefonda okunmuyor. Modelin
# uymasina guvenmek yerine genislik kodda sinirlaniyor.

from ajan.bicim import AZAMI_TABLO_GENISLIGI, tablo_hizala  # noqa: E402

GENIS = [
    ["Oran", "Değer", "Açıklama"],
    ["F/K (Fiyat/Kazanç)", "3,07", "296 TL fiyat bölü hisse başına kazanç, net kâr 133,05 milyar TL"],
    ["PD/DD", "0,40", "Piyasa değeri 408,48 milyar TL bölü özkaynak 1,02 trilyon TL"],
]


def test_genis_tablo_sinira_daraltilir():
    for satir in tablo_hizala(GENIS).split("\n"):
        assert len(satir) <= AZAMI_TABLO_GENISLIGI, satir


def test_daraltmada_veri_kaybolmaz():
    """Satir kaydirilir, kirpilmaz: bir cevabin ortasindan veri dusmemeli."""
    hizali = tablo_hizala(GENIS)
    for satir in GENIS:
        for hucre in satir:
            for kelime in hucre.split():
                assert kelime in hizali, kelime


def test_dar_tablo_bozulmadan_kalir():
    dar = [["Son fiyat", "296,00 TL"], ["Değişim", "+1,54 %"]]
    assert tablo_hizala(dar) == "Son fiyat  296,00 TL\nDeğişim    +1,54 %"


def test_yatay_cizgi_satirlari_atilir():
    """Markdown '---' Telegram'da ham tire olarak gorunuyor, gurultu."""
    assert "---" not in telegram_html("Bir\n\n---\n\nIki")


def test_sayilar_ortadan_bolunmez():
    """Olculdu: dar sutuna sikistirinca "408,48 milyar" -> "408,4" + "8 milyar".

    Bir finans botunda sayinin ikiye ayrilmasi okuma hatasi dogurur.
    """
    hizali = tablo_hizala(GENIS)
    for sayi in ("408,48", "133,05", "1,02", "3,07", "0,40"):
        assert sayi in hizali, f"{sayi} bolunmus"


def test_ucuncu_sutun_satirin_altina_girintili_yazilir():
    hizali = tablo_hizala(GENIS).split("\n")
    aciklamali = [s for s in hizali if s.startswith("  ") and "296 TL" in s]
    assert aciklamali, f"ucuncu sutun girintili satira alinmadi: {hizali}"


def test_bosluklu_binlik_ayirici_noktaya_cevrilir():
    """Olculdu: model kurala ragmen "44 799 808" yaziyor. Turkce bicim nokta."""
    assert "44.799" in telegram_html("Hacim 44 799 lot")
    assert "1.018,52" in telegram_html("Özkaynak 1 018,52 milyar TL")


def test_yil_gibi_ardisik_sayilar_birlestirilmez():
    sonuc = telegram_html("2025 2024 karşılaştırması, 296 TL")
    assert "2025 2024" in sonuc
    assert "296 TL" in sonuc


UC_SUTUN_VERI = [
    ["Kalem", "2025", "2024"],
    ["TOPLAM VARLIKLAR", "2,35 trilyon TL", "1,83 trilyon TL"],
]


def test_alta_inen_sutun_baslik_adiyla_etiketlenir():
    """Ucuncu sutun veri olabilir; etiketsiz inince neyin nesi belli olmuyor."""
    hizali = tablo_hizala(UC_SUTUN_VERI, baslikli=True)
    assert "2024: 1,83 trilyon TL" in hizali


def test_kirilmaz_bosluklu_sayi_da_duzeltilir():
    """Model bazen U+00A0/U+202F yaziyor; duz bosluk arayan kontrol kaciriyor."""
    assert "44.799" in telegram_html("Hacim 44\u00a0799 lot")
    assert "1.018,52" in telegram_html("Özkaynak 1\u202f018,52 milyar TL")


def test_aciklama_basligi_onek_olarak_tekrarlanmaz():
    """Her satira "Açıklama:" yazmak gorsel gurultu; baslik zaten belli."""
    tablo = [
        ["Oran", "Değer", "Açıklama"],
        ["F/K", "3,07", "Net kâr 133,05 milyar TL üzerinden"],
    ]
    assert "Açıklama:" not in tablo_hizala(tablo, baslikli=True)
    assert "Net kâr 133,05 milyar TL üzerinden" in tablo_hizala(tablo, baslikli=True)


def test_ham_buyuk_tutarlar_okunabilir_yazilir():
    """Model kurala uymayip ham rakam yazabiliyor; tabloda da tasiyor."""
    sonuc = telegram_html("Toplam varlıklar 2.351.336.385.167 TL")
    assert "2,35 trilyon TL" in sonuc
    assert "2.351.336.385.167" not in sonuc


def test_zaten_okunabilir_yazilmis_tutara_dokunulmaz():
    assert "1,07 trilyon TL" in telegram_html("Özkaynak 1,07 trilyon TL")


def test_kucuk_tutarlar_ve_yillar_degismez():
    sonuc = telegram_html("Fiyat 296,00 TL, 2025 yılında 44.799 lot")
    assert "296,00 TL" in sonuc
    assert "2025" in sonuc
    assert "44.799" in sonuc


def test_bosluklu_tutar_hem_duzeltilir_hem_kisaltilir():
    """Iki duzeltme birlikte calismali: bosluk -> nokta, sonra kisaltma."""
    assert "44,80 milyon TL" in telegram_html("Hacim 44 799 808 TL")


def test_birimsiz_buyuk_sayilar_da_kisaltilir():
    """Bilanco tablosunda model birimi baslikta veriyor, hucrede yazmiyor."""
    sonuc = telegram_html("| Kalem | 2025 |\n|---|---|\n| Varlıklar | 2.351.336.385.167 |")
    assert "2,35 trilyon" in sonuc
    assert "2,35 trilyon TL" not in sonuc, "olmayan birim uydurulmamali"


# --- Baslik ve yabanci alfabe ----------------------------------------------
# Olculdu (canli bot): "### 📰 KAP" ham metin olarak dustu -- Telegram
# markdown basligi render etmiyor. Ayrica model cumle ortasinda dil
# degistiriyor: "toparlama 가능성을 gosterirken", "destekㅕnu", daha once de
# Japonca (ブランド), Arapca (نسبي) ve Cince (压力) gorulmustu.


def test_markdown_basligi_kalin_olur():
    sonuc = telegram_html("### 📰 KAP (Son 90 gün)\nmetin")
    assert "<b>📰 KAP (Son 90 gün)</b>" in sonuc
    assert "###" not in sonuc


def test_farkli_seviyedeki_basliklar_da_cevrilir():
    for isaret in ("#", "##", "####"):
        assert "<b>Başlık</b>" in telegram_html(f"{isaret} Başlık")


def test_korece_kelime_temizlenir():
    sonuc = telegram_html("kısa vadeli bir toparlama 가능성을 gösterirken")
    assert "가능성을" not in sonuc
    assert "toparlama" in sonuc and "gösterirken" in sonuc


def test_cince_japonca_arapca_temizlenir():
    for yabanci in ("压力", "ブランド", "نسبي"):
        sonuc = telegram_html(f"sektörde {yabanci} etkisi var")
        assert yabanci not in sonuc
        assert "sektörde" in sonuc and "etkisi" in sonuc


def test_kelime_icine_karisan_harf_kelimeyi_dusurur():
    """"destekㅕnu" gibi bozulmus kelime metinde kalmamali."""
    sonuc = telegram_html("Bu seviyenin altında destekㅕnu kaybedebilir")
    assert "ㅕ" not in sonuc
    assert "seviyenin" in sonuc and "kaybedebilir" in sonuc


def test_turkce_harfler_ve_emoji_korunur():
    metin = "Şirketin özkaynağı 1,07 trilyon TL 💵 ğüşiöç ÄÖÜ"
    sonuc = telegram_html(metin)
    for parca in ("Şirketin", "özkaynağı", "💵", "ğüşiöç", "ÄÖÜ"):
        assert parca in sonuc


def test_temizlik_bosluklari_bozmaz():
    assert telegram_html("bir 가능성 iki") == "bir iki"

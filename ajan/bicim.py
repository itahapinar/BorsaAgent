"""Turkce bicimlendirme, Telegram HTML cevrimi ve mesaj bolme.

Turkce sayi formati: 1.234.567,89 — nokta binlik, virgul ondalik.
Python'un varsayilan formati bunun tersi oldugu icin elle cevrilir.
"""

import datetime as dt
import re
import textwrap

TELEGRAM_SINIRI = 4096


def _turkce_sayi(deger: float, basamak: int = 2) -> str:
    metin = f"{deger:,.{basamak}f}"  # 1,234.50
    return metin.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def tl(deger: float) -> str:
    return f"{_turkce_sayi(deger)} TL"


def yuzde(deger: float) -> str:
    return f"%{_turkce_sayi(deger)}"


def tarih(deger) -> str:
    if isinstance(deger, str):
        deger = dt.date.fromisoformat(deger[:10])
    return deger.strftime("%d.%m.%Y")


def buyuk_sayi(deger: float, birim: str = "TL") -> str:
    """Buyuk TL tutarlarini okunabilir kisaltir.

    1.073.081.134.047 gibi bir rakami ham gostermek cevabi okunmaz yapiyor.
    """
    son = f" {birim}" if birim else ""
    for esik, ad in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if abs(deger) >= esik:
            return f"{_turkce_sayi(deger / esik)} {ad}{son}"
    return tl(deger) if birim == "TL" else f"{_turkce_sayi(deger)}{son}"


def mesaji_bol(metin: str, sinir: int = TELEGRAM_SINIRI) -> list[str]:
    """Telegram'in 4096 karakter sinirina gore boler.

    Once cumle sinirindan denenir; tek bir cumle bile sinira sigmiyorsa
    (ornegin uzun bir tablo) sert bolunur. Bosluk disinda karakter kaybolmaz —
    bir cevabin ortasindan sessizce veri dusmesi en kotu hata olurdu.
    """
    metin = metin.rstrip()
    if len(metin) <= sinir:
        return [metin]

    # Etiket dengeleme parcalara birkac karakter ekliyor; sinir asilmasin.
    calisma_siniri = sinir - ETIKET_PAYI if _etiketli(metin) else sinir

    parcalar: list[str] = []
    kalan = metin

    while len(kalan) > calisma_siniri:
        pencere = kalan[:calisma_siniri]
        # Cumle sonu ariyoruz; ". " ve ".\n" noktayi, "\n" satiri isaretler.
        kesim = max(pencere.rfind(". "), pencere.rfind(".\n"), pencere.rfind("\n"))
        if kesim <= 0:
            bolum, kalan = kalan[:calisma_siniri], kalan[calisma_siniri:]
        else:
            bolum, kalan = kalan[: kesim + 1], kalan[kesim + 1 :]
        parcalar.append(bolum.rstrip())
        kalan = kalan.lstrip()

    if kalan:
        parcalar.append(kalan)
    return _etiketleri_dengele(parcalar)


# --- Telegram HTML ---------------------------------------------------------
# Olculdu (canli bot): cevap ham markdown olarak dustu. Telegram BORU
# TABLOSUNU render etmiyor -- hicbir istemci etmiyor -- ve parse_mode
# ayarlanmadigi icin ** yildizlari metnin icinde gorunuyordu.
#
# Modele "hizali monospace yaz, boru kullanma" demek calismadi: model
# markdown tablosu uretmekte iyi, sutun hizalamakta degil. Bu yuzden model
# markdown yaziyor, hizalamayi BURASI yapiyor.

TABLO_SATIRI = re.compile(r"^\s*\|.*\|\s*$")
AYIRICI_SATIR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
KALIN = re.compile(r"\*\*(.+?)\*\*", re.S)
KOD = re.compile(r"`([^`\n]+)`")
YER_TUTUCU = "@@TABLO{}@@"
# Telegram mobil ekraninda <pre> blogu bu genislige kadar rahat okunuyor.
AZAMI_TABLO_GENISLIGI = 38
ASGARI_SUTUN = 6
# Markdown yatay cizgisi Telegram'da ham tire olarak gorunuyor, gurultu.
YATAY_CIZGI = re.compile(r"^\s*[-*_]{3,}\s*$", re.M)


# Model bazen kirilmaz bosluk (U+00A0) ya da dar bosluk (U+202F) yaziyor.
# Duz bosluk arayan kontroller bunlari kaciriyor ve textwrap da bunlardan
# bolmedigi icin sayi tek dev jeton haline geliyor.
OZEL_BOSLUKLAR = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2007": " "})

# Ucuncu sutun basligi bunlardan biriyse onek yazmak gereksiz tekrar olur.
GENEL_BASLIKLAR = frozenset({"açıklama", "aciklama", "not", "notlar", "yorum"})

# Olculdu: model kurala ragmen binlik ayirici olarak bosluk yaziyor
# ("44 799 808"). Turkce bicim nokta; ayrica bosluklu sayi tabloda
# bolunebilir hale geliyor. Modelin uymasina guvenmek yerine burada duzeltilir.
BOSLUKLU_SAYI = re.compile(r"(?<!\d)(\d{1,3}(?: \d{3})+)(?!\d)")


def _binlik_ayiriciyi_duzelt(metin: str) -> str:
    return BOSLUKLU_SAYI.sub(lambda e: e.group(1).replace(" ", "."), metin)


# Olculdu: model "buyuk rakamlari okunabilir yaz" kuralina tutarsiz uyuyor;
# bir kosuda "2,35 trilyon TL", digerinde "2.351.336.385.167" basiyor. Ham
# rakam hem okunmuyor hem tablo sutununa sigmiyor. Bilanco tablolarinda
# birimi baslikta verip hucrede yazmadigi icin "TL" zorunlu degil; birim
# yoksa cevride de birim UYDURULMAZ.
HAM_TUTAR = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3}){2,})(,\d+)?(\s*TL\b)?")


def _ham_tutarlari_kisalt(metin: str) -> str:
    def cevir(eslesme: re.Match) -> str:
        tamsayi = eslesme.group(1).replace(".", "")
        ondalik = (eslesme.group(2) or ",0").replace(",", ".")
        birim = "TL" if eslesme.group(3) else ""
        return buyuk_sayi(float(tamsayi + ondalik), birim)

    return HAM_TUTAR.sub(cevir, metin)


# Markdown basligi Telegram'da render edilmiyor, "### KAP" ham dusuyordu.
BASLIK = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.M)

# Model cumle ortasinda dil degistiriyor: olculdu "toparlama 가능성을
# gosterirken", "destekㅕnu", ayrica ブランド (Japonca), نسبي (Arapca),
# 压力 (Cince). Bunlar anlam tasimayan sizinti; iceren KELIME atilir --
# harfi tek basina silmek "destek nu" gibi bozuk bir kelime birakiyordu.
YABANCI_HARF = (
    "\u0600-\u06ff"  # Arapca
    "\u0400-\u04ff"  # Kiril
    "\u0900-\u097f"  # Devanagari
    "\u1100-\u11ff\u3130-\u318f\uac00-\ud7af"  # Hangul
    "\u3040-\u30ff"  # Hiragana/Katakana
    "\u3400-\u4dbf\u4e00-\u9fff"  # Han
)
YABANCI_KELIME = re.compile(rf"\S*[{YABANCI_HARF}]\S*")


def yabanci_yaziyi_temizle(metin: str) -> str:
    """Turkce olmayan alfabelerden sizan kelimeleri atar."""
    if not YABANCI_KELIME.search(metin):
        return metin
    temiz = YABANCI_KELIME.sub("", metin)
    # Kelime atilinca cift bosluk kaliyor; satir yapisi korunur.
    return re.sub(r"[^\S\n]{2,}", " ", temiz).replace(" \n", "\n")


# Olculdu (DOAS): model ham JSON degerini kopyalayip "15.0", "27.2727"
# yazdi. Turkce ondalik ayirici virguldur. Lookaround'lar tarihi ve binlik
# ayiriciyi korur: 07.09.2026 ve 1.234.567 iki noktali olduklari icin
# eslesmez.
# Tam 3 haneli kesir binlik ayiricidir (44.799), ondalik degil.
ONDALIK_NOKTA = re.compile(r"(?<![\d.])(\d+)\.(\d{1,2}|\d{4,})(?![\d.])")


def _ondalik_virgule(metin: str) -> str:
    return ONDALIK_NOKTA.sub(r"\1,\2", metin)


def _kacir(metin: str) -> str:
    return metin.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _hucreler(satir: str) -> list[str]:
    ham = satir.strip().strip("|").split("|")
    # <pre> icinde ** ve ` render edilmez; kalirsa gorsel kirlilik olur.
    return [h.strip().replace("**", "").replace("`", "") for h in ham]


def _genislikleri_sigdir(genislik: list[int], azami: int) -> list[int]:
    """Toplam genisligi sinira indirene kadar en genis sutunu daraltir."""
    ayrac = 2 * (len(genislik) - 1)
    while sum(genislik) + ayrac > azami and max(genislik) > ASGARI_SUTUN:
        genislik[genislik.index(max(genislik))] -= 1
    return genislik


def _sar(metin: str, genislik: int) -> list[str]:
    """Yalnizca bosluktan boler.

    break_long_words acikken "408,48 milyar" -> "408,4" + "8 milyar" gibi
    bolunuyordu; bir finans botunda sayinin ortadan kesilmesi okuma hatasi
    dogurur. Uzun bir jeton sinirdan tasabilir, boluNMEZ.
    """
    return textwrap.wrap(
        metin, max(genislik, 1), break_long_words=False, break_on_hyphens=False
    ) or [""]


def tablo_hizala(
    satirlar: list[list[str]],
    azami_genislik: int = AZAMI_TABLO_GENISLIGI,
    baslikli: bool = False,
) -> str:
    """Tabloyu Telegram'da okunacak sekilde hizalar.

    Iki sutun hizalanir. UCUNCU VE SONRAKI sutunlar satirin ALTINA girintili
    yazilir: olculdu, uc sutunu 38 karaktere sikistirmak her hucreyi 11
    karakterlik seride kaydiriyor ve tablo okunmaz oluyordu. Hicbir hucre
    kirpilmaz.
    """
    sutun_sayisi = max(len(s) for s in satirlar)
    dolu = [s + [""] * (sutun_sayisi - len(s)) for s in satirlar]

    bas = [s[:2] for s in dolu]
    kuyruk = [s[2:] for s in dolu]

    genislik = [max(len(s[i]) for s in bas) for i in range(min(2, sutun_sayisi))]
    genislik = _genislikleri_sigdir(genislik, azami_genislik)

    ek_basliklari = [h.strip() for h in kuyruk[0]] if baslikli and kuyruk else []

    ciktilar: list[str] = []
    for sayac, (satir, ek) in enumerate(zip(bas, kuyruk)):
        # Baslik satirinin ucuncu hucresi yalnizca sutun adidir; alta
        # girintili yazilinca aciklama sanilip kafa karistiriyor.
        if baslikli and sayac == 0:
            ek = []
        sarilmis = [_sar(hucre, genislik[i]) for i, hucre in enumerate(satir)]
        for sira in range(max(len(s) for s in sarilmis)):
            parcalar = [
                (s[sira] if sira < len(s) else "").ljust(genislik[i])
                for i, s in enumerate(sarilmis)
            ]
            ciktilar.append("  ".join(parcalar).rstrip())
        for sutun, hucre in enumerate(ek):
            if not hucre.strip():
                continue
            # Ucuncu sutun aciklama da olabilir veri de (ornegin onceki yilin
            # rakami). Etiketsiz inince "1,83 trilyon TL" neyin nesi belli
            # olmuyor; baslik varsa onunla etiketlenir.
            etiket = ek_basliklari[sutun] if sutun < len(ek_basliklari) else ""
            if etiket.lower() in GENEL_BASLIKLAR:
                etiket = ""
            yazi = f"{etiket}: {hucre}" if etiket else hucre
            ciktilar += [f"  {s}" for s in _sar(yazi, azami_genislik - 2)]
    return "\n".join(ciktilar)


def _tablolari_ayikla(metin: str) -> tuple[str, list[str]]:
    """Boru tablolarini yer tutucuyla degistirir, hizalanmis govdeleri doner."""
    cikti: list[str] = []
    tablolar: list[str] = []
    tampon: list[list[str]] = []
    ayirici_gorulen = False

    def bosalt() -> None:
        nonlocal ayirici_gorulen
        if not tampon:
            return
        cikti.append(YER_TUTUCU.format(len(tablolar)))
        tablolar.append(tablo_hizala(list(tampon), baslikli=ayirici_gorulen))
        tampon.clear()
        ayirici_gorulen = False

    for satir in metin.split("\n"):
        if TABLO_SATIRI.match(satir):
            if AYIRICI_SATIR.match(satir):  # |---|---| satiri atilir
                ayirici_gorulen = True
            else:
                tampon.append(_hucreler(satir))
            continue
        bosalt()
        cikti.append(satir)
    bosalt()

    return "\n".join(cikti), tablolar


def telegram_html(metin: str) -> str:
    """Modelin markdown cevabini Telegram HTML'ine cevirir.

    Tablolar hizalanip <pre> blogu olur, **kalin** <b>, `kod` <code> olur.
    HTML ozel karakterleri kacirilmazsa Telegram mesaji "can't parse
    entities" ile reddediyor.
    """
    metin = metin.translate(OZEL_BOSLUKLAR)
    metin = yabanci_yaziyi_temizle(metin)
    metin = YATAY_CIZGI.sub("", metin)
    metin = _binlik_ayiriciyi_duzelt(metin)
    metin = _ondalik_virgule(metin)
    metin = _ham_tutarlari_kisalt(metin)
    govde, tablolar = _tablolari_ayikla(metin)
    govde = _kacir(govde)
    govde = BASLIK.sub(r"<b>\1</b>", govde)
    govde = KALIN.sub(r"<b>\1</b>", govde)
    govde = KOD.sub(r"<code>\1</code>", govde)

    for sira, tablo in enumerate(tablolar):
        govde = govde.replace(
            YER_TUTUCU.format(sira), f"<pre>\n{_kacir(tablo)}\n</pre>"
        )
    return re.sub(r"\n{3,}", "\n\n", govde).strip()


# Bir parca acik etiketle biterse Telegram mesaji "can't parse entities" ile
# reddediyor. 4096'yi asan bir tablo tam da <pre> ortasindan bolunuyor.
DENGELENEN_ETIKETLER = ("pre", "code", "b")
ETIKET_PAYI = 16  # kapatma + yeniden acma etiketleri icin ayrilan yer


def _etiketli(metin: str) -> bool:
    return any(f"<{e}>" in metin for e in DENGELENEN_ETIKETLER)


def _etiketleri_dengele(parcalar: list[str]) -> list[str]:
    """Bir parcada acik kalan etiketi kapatir, sonrakinde yeniden acar."""
    dengeli: list[str] = []
    acik: list[str] = []

    for parca in parcalar:
        if acik:
            parca = "".join(f"<{e}>" for e in acik) + parca
        acik = [
            e
            for e in DENGELENEN_ETIKETLER
            if parca.count(f"<{e}>") > parca.count(f"</{e}>")
        ]
        if acik:
            parca = parca + "".join(f"</{e}>" for e in reversed(acik))
        dengeli.append(parca)

    return dengeli

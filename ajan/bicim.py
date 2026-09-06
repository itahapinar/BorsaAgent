"""Turkce bicimlendirme ve Telegram mesaj bolme.

Turkce sayi formati: 1.234.567,89 — nokta binlik, virgul ondalik.
Python'un varsayilan formati bunun tersi oldugu icin elle cevrilir.
"""

import datetime as dt

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


def buyuk_sayi(deger: float) -> str:
    """Buyuk TL tutarlarini okunabilir kisaltir.

    1.073.081.134.047 gibi bir rakami ham gostermek cevabi okunmaz yapiyor.
    """
    for esik, ad in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if abs(deger) >= esik:
            return f"{_turkce_sayi(deger / esik)} {ad} TL"
    return tl(deger)


def mesaji_bol(metin: str, sinir: int = TELEGRAM_SINIRI) -> list[str]:
    """Telegram'in 4096 karakter sinirina gore boler.

    Once cumle sinirindan denenir; tek bir cumle bile sinira sigmiyorsa
    (ornegin uzun bir tablo) sert bolunur. Bosluk disinda karakter kaybolmaz —
    bir cevabin ortasindan sessizce veri dusmesi en kotu hata olurdu.
    """
    metin = metin.rstrip()
    if len(metin) <= sinir:
        return [metin]

    parcalar: list[str] = []
    kalan = metin

    while len(kalan) > sinir:
        pencere = kalan[:sinir]
        # Cumle sonu ariyoruz; ". " ve ".\n" noktayi, "\n" satiri isaretler.
        kesim = max(pencere.rfind(". "), pencere.rfind(".\n"), pencere.rfind("\n"))
        if kesim <= 0:
            bolum, kalan = kalan[:sinir], kalan[sinir:]
        else:
            bolum, kalan = kalan[: kesim + 1], kalan[kesim + 1 :]
        parcalar.append(bolum.rstrip())
        kalan = kalan.lstrip()

    if kalan:
        parcalar.append(kalan)
    return parcalar

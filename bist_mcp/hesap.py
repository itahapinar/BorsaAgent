"""Oran hesaplari — TL bazinda.

Hicbir saglayicinin hazir oran alani kullanilmaz. Olculen gerekce: yfinance
THYAO icin priceToBook = 18,64 veriyor, gercek deger 0,38 (49 kat). Sebep
sirketin finansallarini USD raporlamasi. Buradaki tum hesaplar Is Yatirim'dan
gelen TL rakamlarla yapilir.
"""


def defter_degeri(ozkaynak_tl: float, hisse_adedi: int) -> float:
    """Pay basina defter degeri (TL)."""
    if hisse_adedi <= 0:
        raise ValueError("hisse adedi pozitif olmali")
    return ozkaynak_tl / hisse_adedi


def pddd(fiyat_tl: float, ozkaynak_tl: float, hisse_adedi: int) -> float | None:
    """Piyasa degeri / defter degeri. Negatif ozkaynakta None."""
    if ozkaynak_tl <= 0:
        return None
    return fiyat_tl / defter_degeri(ozkaynak_tl, hisse_adedi)


def piyasa_degeri(fiyat_tl: float, hisse_adedi: int) -> float:
    if hisse_adedi <= 0:
        raise ValueError("hisse adedi pozitif olmali")
    return fiyat_tl * hisse_adedi


def fk(fiyat_tl: float, hisse_adedi: int, net_kar_tl: float) -> float | None:
    """Fiyat / kazanc. Zarar eden sirkette anlamsiz oldugu icin None."""
    if net_kar_tl <= 0:
        return None
    return piyasa_degeri(fiyat_tl, hisse_adedi) / net_kar_tl


def temettu_verimi(temettu_12ay_tl: float, fiyat_tl: float) -> float:
    """Son 12 ayda odenen temettunun fiyata orani (yuzde)."""
    if fiyat_tl <= 0:
        raise ValueError("fiyat pozitif olmali")
    return temettu_12ay_tl / fiyat_tl * 100


# PD/DD bu araligin disindaysa oran guvenilmez sayilir: ozkaynak erimis
# olabilir ya da hisse adedi yanlis cozulmustur.
MAKUL_PDDD = (0.01, 50.0)


def oran_makul(pddd_degeri: float | None) -> bool:
    """PD/DD makul araliktaysa True. None ise karar verilemez, True doner."""
    if pddd_degeri is None:
        return True
    return MAKUL_PDDD[0] <= pddd_degeri <= MAKUL_PDDD[1]

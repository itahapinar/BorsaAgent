"""TCMB EVDS makro gostergeleri: enflasyon, faiz, tahvil.

Doviz ve altin BURADA DEGIL, kur.py'de — onlar yfinance'ten anahtarsiz
geliyor. EVDS yalnizca yfinance karsiligi olmayan veriler icin kullanilir.

EVDS_API_KEY yoksa modul kendini devre disi birakir ve net bir mesaj doner;
diger 15 arac etkilenmez.

UYARI — asagidaki seri kodlari CANLI DOGRULANMADI. Anahtar olmadigi icin
istek atilamadi. Anahtar alindiginda `python -m bist_mcp.kaynaklar.tcmb`
ile her gosterge tek tek denenmeli; yanlis kod bos `kayitlar` dondurur,
sessizce yanlis sayi dondurmez.
"""

import httpx

from bist_mcp.onbellek import Onbellek

EVDS_KOK = "https://evds2.tcmb.gov.tr/service/evds"
MAKRO_TTL = 6 * 3600

GOSTERGELER: dict[str, str] = {
    "tufe": "TP.FG.J0",  # Tuketici fiyat endeksi
    "ufe": "TP.TUFE1YI.T1",  # Yurt ici uretici fiyat endeksi
    "politika_faizi": "TP.APIFON4",  # 1 haftalik repo
    "tahvil_2y": "TP.ADFAIZ.GOSTERGE",
}


def seri_kodu_bul(ad: str) -> str:
    anahtar = ad.strip().lower()
    if anahtar not in GOSTERGELER:
        gecerli = ", ".join(sorted(GOSTERGELER))
        raise ValueError(f"bilinmeyen gosterge: {ad}. Gecerli olanlar: {gecerli}")
    return GOSTERGELER[anahtar]


def evds_ayikla(ham: dict, seri_kodu: str) -> list[dict]:
    """EVDS yanitini {tarih, deger} listesine cevirir.

    EVDS alan adinda noktalari alt cizgiye ceviriyor (TP.FG.J0 -> TP_FG_J0)
    ve sayilari Turkce ondalik virguluyle donduruyor.
    """
    alan = seri_kodu.replace(".", "_")
    sonuc = []
    for satir in ham.get("items") or []:
        ham_deger = satir.get(alan)
        if ham_deger in (None, "", "null"):
            continue
        sonuc.append(
            {
                "tarih": satir.get("Tarih"),
                "deger": float(str(ham_deger).replace(".", "").replace(",", ".")),
            }
        )
    return sonuc


class TcmbIstemci:
    def __init__(self, onbellek: Onbellek, api_anahtari: str | None) -> None:
        self._onbellek = onbellek
        self._anahtar = api_anahtari

    @property
    def etkin(self) -> bool:
        return bool(self._anahtar)

    async def gosterge(self, ad: str, son_kayit: int = 12) -> dict:
        if not self.etkin:
            return {
                "hata": "EVDS_API_KEY tanımlı değil; enflasyon ve faiz göstergeleri "
                "devre dışı. evds2.tcmb.gov.tr üzerinden ücretsiz alınabilir. "
                "Döviz ve altın bundan etkilenmez."
            }

        seri = seri_kodu_bul(ad)
        anahtar = f"tcmb:{seri}:{son_kayit}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        async with httpx.AsyncClient() as istemci:
            yanit = await istemci.get(
                f"{EVDS_KOK}/series={seri}&type=json&last_observations={son_kayit}",
                headers={"key": self._anahtar, "User-Agent": "Mozilla/5.0"},
                timeout=30.0,
            )
            yanit.raise_for_status()
            kayitlar = evds_ayikla(yanit.json(), seri)

        if not kayitlar:
            return {
                "hata": f"'{ad}' için EVDS veri döndürmedi. Seri kodu ({seri}) "
                "yanlış olabilir; kodlar henüz canlı doğrulanmadı."
            }

        sonuc = {"gosterge": ad.lower(), "seri": seri, "kayitlar": kayitlar}
        self._onbellek.yaz(anahtar, sonuc, MAKRO_TTL)
        return sonuc

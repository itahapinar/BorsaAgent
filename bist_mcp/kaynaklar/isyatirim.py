"""Is Yatirim finansal tablo kaynagi.

Olculen sonuclar: THYAO 147 kalem (XI_29), GARAN 192 kalem BDDK formati
(UFRS_K). Tekil cagri suresi ~0,31 sn.

DONEM SECIMI — takvim aritmetigi ile tahmin edilmez. Olculen davranis
(2026-09-05): 2026/12 ve 2026/9 bos doner (henuz yayimlanmadi), 2026/6 ve
2025/12 dolu. Sirketler raporlarini farkli tarihlerde acikladigi icin
"su an hangi donem yayimlanmistir" hesabi kirilgan. Bunun yerine yeni'den
eskiye aday donemler istenir ve BOS DONEN SLOTLAR ATILIR: karisik pencerede
yayimlanmamis donem None gelir, digerleri dolu gelir (olculdu).
"""

import asyncio
import datetime as dt

import httpx

from bist_mcp.hiz_sinir import HizSinirlayici
from bist_mcp.kaynaklar.kap import tablo_grubu_sec, yedek_grup
from bist_mcp.onbellek import Onbellek

KOK = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx"
ISTEK_ARALIGI_SN = 0.5  # kisisel kullanim; 2 istek/sn tavani
TABLO_TTL = 24 * 3600
SLOT_SAYISI = 4  # API tek istekte en fazla 4 donem tasiyor


def donem_adaylari(donem: str, bugun: dt.date | None = None) -> list[tuple[int, int]]:
    """Yeniden eskiye aday (yil, ay) ciftleri.

    Agresif baslar — en yeni adaylar yayimlanmamis olabilir; bos slotlar
    sonradan atilir.
    """
    bugun = bugun or dt.date.today()

    if donem == "yillik":
        return [(bugun.year - i, 12) for i in range(6)]

    adaylar: list[tuple[int, int]] = []
    yil, ay = bugun.year, 12
    while len(adaylar) < 12:
        adaylar.append((yil, ay))
        ay -= 3
        if ay == 0:
            yil, ay = yil - 1, 12
    return adaylar


def donem_etiketi(yil: int, ay: int, donem: str) -> str:
    if donem == "yillik":
        return f"{yil} yıllık"
    return f"{yil} ilk {ay} ay"


def sayiya_cevir(ham_deger) -> float | None:
    """Is Yatirim degerleri STRING doner ('1073081134047', '-941964141907').

    Sayiya cevrilmezse iki hata olusur: oran hesaplari string bolemez ve
    sifir satirlari atilmaz ('0' != 0).
    """
    if ham_deger is None or ham_deger == "":
        return None
    if isinstance(ham_deger, (int, float)):
        return float(ham_deger)
    metin = str(ham_deger).strip().replace(" ", "")
    # Turkce format ihtimaline karsi: nokta binlik, virgul ondalik
    if "," in metin:
        metin = metin.replace(".", "").replace(",", ".")
    try:
        return float(metin)
    except ValueError:
        return None


def dolu_slotlar(ham: dict) -> list[int]:
    """Verisi olan slot numaralarini (1..4) doner.

    Yayimlanmamis donem tum satirlarda None gelir; o slot atilir.
    """
    satirlar = ham.get("value") or []
    return [
        i
        for i in range(1, SLOT_SAYISI + 1)
        if any(s.get(f"value{i}") is not None for s in satirlar)
    ]


def kalem_ayikla(ham: dict, slotlar: list[int] | None = None) -> list[dict]:
    """Is Yatirim yanitini {ad, degerler} listesine cevirir.

    Kalem adlarina dokunulmaz: 'XVI. OZKAYNAKLAR' neyse o kalir.

    Degerler her satirda AYNI slotlardan alinir. Satir bazinda None atmak
    hataliydi: bazi kalemler bir donemde raporlanmiyor (olculdu: slot4'te
    145, digerlerinde 147 kalem dolu) ve o satirlarda degerler bir donem
    kayiyordu.
    """
    satirlar = ham.get("value") or []
    if slotlar is None:
        slotlar = dolu_slotlar(ham)

    kalemler = []
    for satir in satirlar:
        ad = (satir.get("itemDescTr") or "").strip()
        if not ad:
            continue
        kalemler.append(
            {"ad": ad, "degerler": [sayiya_cevir(satir.get(f"value{i}")) for i in slotlar]}
        )
    return kalemler


def sifir_satirlari_at(kalemler: list[dict]) -> list[dict]:
    """Tum donemlerde 0 ya da bos olan satirlari atar."""
    return [k for k in kalemler if any(d not in (0, None) for d in k["degerler"])]


# Is Yatirim bilanco, gelir ve nakit akisini TEK listede dondurur. Bolme
# noktalari olculdu (THYAO sanayi 104 kalem, GARAN banka 99 kalem):
#   bilanco sonu  -> "TOPLAM KAYNAKLAR" (sanayi) / "PASİF TOPLAMI" (banka)
#   nakit basi    -> "İşletme Faaliyetlerinden Kaynaklanan Net Nakit"
# Bankalarda nakit akisi bolumu YOKTUR; GARAN gelir tablosuyla bitiyor.
BILANCO_SONU_ADLARI = ("TOPLAM KAYNAKLAR", "PASİF TOPLAMI")
NAKIT_BASI_ADLARI = ("İşletme Faaliyetlerinden Kaynaklanan Net Nakit",)


def _ilk_indeks(kalemler: list[dict], adaylar: tuple[str, ...]) -> int | None:
    for i, kalem in enumerate(kalemler):
        if kalem["ad"].strip() in adaylar:
            return i
    return None


def tablo_bol(kalemler: list[dict]) -> dict[str, list[dict]]:
    """Duz kalem listesini bilanco / gelir / nakit bolumlerine ayirir.

    Isaret bulunamazsa o bolum bos doner — uydurma bolme yapilmaz.
    """
    bilanco_son = _ilk_indeks(kalemler, BILANCO_SONU_ADLARI)
    nakit_bas = _ilk_indeks(kalemler, NAKIT_BASI_ADLARI)

    if bilanco_son is None:
        return {"bilanco": [], "gelir": kalemler, "nakit": []}

    gelir_son = nakit_bas if nakit_bas is not None else len(kalemler)
    return {
        "bilanco": kalemler[: bilanco_son + 1],
        "gelir": kalemler[bilanco_son + 1 : gelir_son],
        "nakit": kalemler[nakit_bas:] if nakit_bas is not None else [],
    }


def kalem_bul(kalemler: list[dict], *adaylar: str) -> float | None:
    """Verilen adaylardan ilk eslesenin ilk donem degerini doner."""
    for aday in adaylar:
        for kalem in kalemler:
            if kalem["ad"].strip().upper() == aday.strip().upper():
                degerler = [d for d in kalem["degerler"] if d is not None]
                return degerler[0] if degerler else None
    return None


class IsYatirimIstemci:
    def __init__(self, onbellek: Onbellek) -> None:
        self._onbellek = onbellek
        self._sinirlayici = HizSinirlayici(ISTEK_ARALIGI_SN)

    async def _bekle(self) -> None:
        await self._sinirlayici.bekle()

    async def _getir(self, kod: str, grup: str, donemler: list[tuple[int, int]]) -> dict:
        parametreler = {
            "companyCode": kod.upper(),
            "exchange": "TRY",
            "financialGroup": grup,
        }
        for sira, (yil, ay) in enumerate(donemler, start=1):
            parametreler[f"year{sira}"] = yil
            parametreler[f"period{sira}"] = ay

        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._bekle()
            yanit = await istemci.get(
                f"{KOK}/MaliTablo",
                params=parametreler,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
                timeout=30.0,
            )
            yanit.raise_for_status()
            return yanit.json()

    async def _pencere_dene(
        self, kod: str, grup: str, pencere: list[tuple[int, int]]
    ) -> tuple[list[dict], list[str], str]:
        ham = await self._getir(kod, grup, pencere)
        slotlar = dolu_slotlar(ham)
        if not slotlar:
            return [], [], ""
        kalemler = sifir_satirlari_at(kalem_ayikla(ham, slotlar))
        etiketler = [pencere[i - 1] for i in slotlar]
        return kalemler, etiketler, grup

    async def mali_tablo(
        self, kod: str, tip: str | None, donem: str = "yillik", adet: int = 2
    ) -> dict:
        """Finansal tabloyu doner: {'donemler': [...], 'kalemler': [...]}.

        Yanlis grup bos tablo dondurdugu icin birincil grup bos gelirse yedek
        grup denenir — bu deneme kaldirilamaz (807 ticker'in 315'inde tip bos).
        En yeni pencere tamamen bossa bir sonraki pencere denenir (en fazla 2).
        """
        anahtar = f"isy:{kod.upper()}:{donem}:{adet}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        adaylar = donem_adaylari(donem)
        birincil = tablo_grubu_sec(tip)

        sonuc: dict = {"donemler": [], "kalemler": []}
        for grup in (birincil, yedek_grup(birincil)):
            for pencere_no in (0, 1):
                pencere = adaylar[pencere_no * SLOT_SAYISI : (pencere_no + 1) * SLOT_SAYISI]
                if not pencere:
                    break
                kalemler, donemler, _ = await self._pencere_dene(kod, grup, pencere)
                if kalemler:
                    sonuc = {
                        "donemler": [donem_etiketi(y, a, donem) for y, a in donemler][:adet],
                        "kalemler": [
                            {"ad": k["ad"], "degerler": k["degerler"][:adet]} for k in kalemler
                        ],
                    }
                    break
            if sonuc["kalemler"]:
                break

        self._onbellek.yaz(anahtar, sonuc, TABLO_TTL)
        return sonuc

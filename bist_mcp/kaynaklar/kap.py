"""KAP (Kamuyu Aydinlatma Platformu) kaynagi.

Sirket dizini, bildirim sorgusu ve bildirim detayi.
"""

import asyncio
import datetime as dt
from dataclasses import dataclass

import httpx

from bist_mcp.onbellek import Onbellek

# KAP financialType kodlari: banka, sigorta, finansal kiralama/faktoring,
# katilim bankasi. Bunlar BDDK formatinda raporlar -> UFRS_K.
BANKA_TIPLERI = frozenset({"BNK", "SIG", "FFF", "KTL"})

KAP_KOK = "https://www.kap.org.tr"
BILDIRIM_SORGU_SAYFASI = f"{KAP_KOK}/tr/bildirim-sorgu"

# Olculen WAF davranisi: 2 istek/sn ustunde TCP baglantisi ~6 sn'de dusuyor.
ISTEK_ARALIGI_SN = 0.5

DIZIN_TTL = 7 * 24 * 3600  # sirket listesi haftada bir yeter
BILDIRIM_TTL = 300  # 5 dk
DETAY_TTL = 24 * 3600


@dataclass(frozen=True)
class Sirket:
    kod: str
    unvan: str
    mkk_oid: str
    tip: str | None


def dizin_kur(ham: list[dict]) -> dict[str, Sirket]:
    """KAP sirket listesini ticker -> Sirket sozlugune cevirir.

    `stockCode` alani virgulle ayrilmis birden fazla kod tutabilir; GARAN'in
    degeri "GARAN, TGB". Tam eslesme aramak bankalarin cogunu kaybettirir,
    bu yuzden alan virgulle bolunup her kod ayri anahtar yapilir.
    Olculen sonuc: 757 sirket -> 807 ticker.
    """
    dizin: dict[str, Sirket] = {}

    for kayit in ham:
        ham_kod = (kayit.get("stockCode") or "").strip()
        if not ham_kod or ham_kod == "-":
            continue

        unvan = (kayit.get("kapMemberTitle") or "").strip()
        oid = kayit.get("mkkMemberOid") or ""
        tip = kayit.get("financialType") or None

        for parca in ham_kod.split(","):
            kod = parca.strip()
            if kod and kod != "-":
                dizin[kod] = Sirket(kod=kod, unvan=unvan, mkk_oid=oid, tip=tip)

    return dizin


def tablo_grubu_sec(tip: str | None) -> str:
    """Sirket tipinden Is Yatirim financialGroup parametresini secer.

    Tip bos olabilir (807 ticker'in 315'i); o durumda XI_29 denenir ve
    bos donerse cagiran taraf yedek_grup() ile digerini dener.
    """
    return "UFRS_K" if tip in BANKA_TIPLERI else "XI_29"


def yedek_grup(grup: str) -> str:
    return "XI_29" if grup == "UFRS_K" else "UFRS_K"


def bildirim_sadelestir(ham: dict) -> dict:
    """Modele gidecek alanlari secer; gerisi baglami sisiriyor."""
    return {
        "tarih": ham.get("publishDate"),
        "konu": ham.get("subject"),
        "ozet": ham.get("summary") or None,
        "sinif": ham.get("disclosureClass"),
        "bildirim_no": ham.get("disclosureIndex"),
        "ek_sayisi": ham.get("attachmentCount", 0),
    }


class KapIstemci:
    def __init__(self, onbellek: Onbellek) -> None:
        self._onbellek = onbellek
        self._kilit = asyncio.Lock()
        self._son_istek = 0.0
        self._oturum_isitildi = False

    async def _bekle(self) -> None:
        """2 istek/sn tavanini uygular."""
        simdi = asyncio.get_event_loop().time()
        gecen = simdi - self._son_istek
        if gecen < ISTEK_ARALIGI_SN:
            await asyncio.sleep(ISTEK_ARALIGI_SN - gecen)
        self._son_istek = asyncio.get_event_loop().time()

    async def _oturum(self, istemci: httpx.AsyncClient) -> None:
        """API cagrisindan once cerez alir; yoksa WAF baglantiyi dusuruyor."""
        if self._oturum_isitildi:
            return
        await self._bekle()
        await istemci.get(BILDIRIM_SORGU_SAYFASI, timeout=30.0)
        self._oturum_isitildi = True

    async def _ham_sirket_listesi_getir(self) -> list[dict]:
        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._bekle()
            yanit = await istemci.get(
                f"{KAP_KOK}/tr/api/company/items/IGS/A",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=40.0,
            )
            yanit.raise_for_status()
            return yanit.json()

    async def sirket_dizini(self) -> dict[str, Sirket]:
        async with self._kilit:
            ham = self._onbellek.al("kap:sirket_listesi")
            if ham is None:
                ham = await self._ham_sirket_listesi_getir()
                self._onbellek.yaz("kap:sirket_listesi", ham, DIZIN_TTL)
            return dizin_kur(ham)

    async def bildirimler(self, kod: str, gun: int = 90) -> list[dict]:
        anahtar = f"kap:bildirim:{kod.upper()}:{gun}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        dizin = await self.sirket_dizini()
        sirket = dizin.get(kod.strip().upper())
        if sirket is None:
            return []

        bitis = dt.date.today()
        baslangic = bitis - dt.timedelta(days=gun)

        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._oturum(istemci)
            await self._bekle()
            yanit = await istemci.post(
                f"{KAP_KOK}/tr/api/disclosure/members/byCriteria",
                json={
                    "fromDate": str(baslangic),
                    "toDate": str(bitis),
                    "mkkMemberOidList": [sirket.mkk_oid],
                    "subjectList": [],
                },
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": BILDIRIM_SORGU_SAYFASI,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=45.0,
            )
            yanit.raise_for_status()
            sonuc = [bildirim_sadelestir(x) for x in yanit.json()]

        self._onbellek.yaz(anahtar, sonuc, BILDIRIM_TTL)
        return sonuc

    async def bildirim_detay(self, bildirim_no: str) -> dict:
        anahtar = f"kap:detay:{bildirim_no}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        async with httpx.AsyncClient(follow_redirects=True) as istemci:
            await self._oturum(istemci)
            await self._bekle()
            yanit = await istemci.get(
                f"{KAP_KOK}/tr/api/notification/attachment-detail/{bildirim_no}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": f"{KAP_KOK}/tr/Bildirim/{bildirim_no}",
                    "Accept": "application/json",
                },
                timeout=40.0,
            )
            yanit.raise_for_status()
            sonuc = yanit.json()

        self._onbellek.yaz(anahtar, sonuc, DETAY_TTL)
        return sonuc

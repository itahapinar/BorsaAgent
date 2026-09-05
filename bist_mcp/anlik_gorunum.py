"""Tarama icin BIST-100 anlik gorunumu.

Iki kademeli tazeleme (spec §7.2): sutunlarin degisme hizi cok farkli.
Fiyat her gun degisir, ozkaynak/net kar ceyrekte bir, hisse adedi ve sektor
neredeyse hic.

  Gunluk hafif tazeleme  ~5 sn,  2 istek  — sadece toplu indirme
  Haftalik tam kurulum  ~75 sn, ~200 istek — Is Yatirim + yfinance info
"""

import asyncio
import sqlite3
import time
from pathlib import Path

from bist_mcp.hesap import fk, pddd, piyasa_degeri, temettu_verimi
from bist_mcp.kaynaklar.isyatirim import kalem_bul

SUTUNLAR = (
    "kod",
    "unvan",
    "sektor",
    "hisse_adedi",
    "ozkaynak_tl",
    "net_kar_tl",
    "fiyat",
    "temettu_12ay",
    "pddd",
    "fk",
    "piyasa_degeri",
    "temettu_verimi",
    "ortalama_hacim_tl",
    "guncelleme",
)

# 630 hisselik tam kurulumda tum gorevleri ayni anda baslatmak, hiz
# sinirlayiciyi kuyruga sokmasa bile yuzlerce acik baglanti demek.
ES_ZAMANLI_TAVAN = 8

# Sanayi ve banka (BDDK) tablolarinda ayni kavramin farkli adlari.
OZKAYNAK_ADLARI = ("XVI. ÖZKAYNAKLAR", "Özkaynaklar")
NET_KAR_ADLARI = (
    "XXIII. NET DÖNEM KARI/ZARARI (XVII+XXII)",
    "DÖNEM KARI (ZARARI)",
    "Dönem Karı (Zararı)",
)


def satir_hesapla(
    temel: dict, fiyat: float, temettu_12ay: float, ortalama_hacim_tl: float | None = None
) -> dict:
    """Temel veriden turetilmis oranlari hesaplar.

    Eksik ozkaynak/net kar oranlari None yapar ama satiri dusurmez —
    fiyat ve sektor yine tarama disi sorularda ise yarar.
    """
    hisse_adedi = temel.get("hisse_adedi") or 0
    ozkaynak = temel.get("ozkaynak_tl")
    net_kar = temel.get("net_kar_tl")

    return {
        "kod": temel["kod"],
        "unvan": temel.get("unvan"),
        "sektor": temel.get("sektor"),
        "hisse_adedi": hisse_adedi,
        "ozkaynak_tl": ozkaynak,
        "net_kar_tl": net_kar,
        "fiyat": fiyat,
        "temettu_12ay": temettu_12ay,
        "pddd": pddd(fiyat, ozkaynak, hisse_adedi) if ozkaynak and hisse_adedi else None,
        "fk": fk(fiyat, hisse_adedi, net_kar) if net_kar and hisse_adedi else None,
        "piyasa_degeri": piyasa_degeri(fiyat, hisse_adedi) if hisse_adedi else None,
        "temettu_verimi": temettu_verimi(temettu_12ay, fiyat) if fiyat else None,
        "ortalama_hacim_tl": (
            ortalama_hacim_tl
            if ortalama_hacim_tl is not None
            else temel.get("ortalama_hacim_tl")
        ),
        "guncelleme": time.time(),
    }


class AnlikGorunum:
    def __init__(self, db_yolu: Path, kap, isyatirim, fiyat) -> None:
        self._kap = kap
        self._isyatirim = isyatirim
        self._fiyat = fiyat
        self._baglanti = sqlite3.connect(db_yolu, check_same_thread=False)
        self._baglanti.row_factory = sqlite3.Row
        self._baglanti.execute(
            "CREATE TABLE IF NOT EXISTS gorunum ("
            "  kod TEXT PRIMARY KEY, unvan TEXT, sektor TEXT,"
            "  hisse_adedi INTEGER, ozkaynak_tl REAL, net_kar_tl REAL,"
            "  fiyat REAL, temettu_12ay REAL, pddd REAL, fk REAL,"
            "  piyasa_degeri REAL, temettu_verimi REAL,"
            "  ortalama_hacim_tl REAL, guncelleme REAL"
            ")"
        )
        self._baglanti.commit()

    def satir_yaz(self, satir: dict) -> None:
        self._baglanti.execute(
            f"INSERT OR REPLACE INTO gorunum ({','.join(SUTUNLAR)}) "
            f"VALUES ({','.join('?' * len(SUTUNLAR))})",
            tuple(satir.get(s) for s in SUTUNLAR),
        )
        self._baglanti.commit()

    def yas_saat(self) -> float | None:
        satir = self._baglanti.execute(
            "SELECT MIN(guncelleme) AS en_eski FROM gorunum"
        ).fetchone()
        if satir is None or satir["en_eski"] is None:
            return None
        return (time.time() - satir["en_eski"]) / 3600

    def satirlari_sec(
        self,
        fk_max: float | None = None,
        fk_min: float | None = None,
        pddd_max: float | None = None,
        temettu_verimi_min: float | None = None,
        piyasa_degeri_min: float | None = None,
        hacim_min: float | None = None,
        sektor: str | None = None,
        sirala: str = "piyasa_degeri",
        adet: int = 20,
    ) -> list[dict]:
        kosullar: list[str] = []
        degerler: list[object] = []

        for alan, islec, deger in (
            ("fk", "<=", fk_max),
            ("fk", ">=", fk_min),
            ("pddd", "<=", pddd_max),
            ("temettu_verimi", ">=", temettu_verimi_min),
            ("piyasa_degeri", ">=", piyasa_degeri_min),
            ("ortalama_hacim_tl", ">=", hacim_min),
        ):
            if deger is not None:
                kosullar.append(f"({alan} IS NOT NULL AND {alan} {islec} ?)")
                degerler.append(deger)

        if sektor:
            kosullar.append("sektor = ?")
            degerler.append(sektor)

        if sirala not in SUTUNLAR:
            sirala = "piyasa_degeri"
        yon = "ASC" if sirala in ("fk", "pddd") else "DESC"

        sorgu = "SELECT * FROM gorunum"
        if kosullar:
            sorgu += " WHERE " + " AND ".join(kosullar)
        sorgu += f" ORDER BY {sirala} IS NULL, {sirala} {yon} LIMIT ?"
        degerler.append(adet)

        return [dict(s) for s in self._baglanti.execute(sorgu, degerler).fetchall()]

    async def hafif_tazele(self, kodlar: list[str]) -> int:
        """Gunluk — sadece fiyat ve temettu. Olculen: ~5 sn, 2 istek."""
        toplu = await self._fiyat.toplu(kodlar)
        guncellenen = 0
        for kod, veri in toplu.items():
            mevcut = self._baglanti.execute(
                "SELECT * FROM gorunum WHERE kod = ?", (kod,)
            ).fetchone()
            if mevcut is None:
                continue
            self.satir_yaz(
                satir_hesapla(
                    dict(mevcut),
                    veri["fiyat"],
                    veri["temettu_12ay"],
                    veri.get("ortalama_hacim_tl"),
                )
            )
            guncellenen += 1
        return guncellenen

    async def tam_kurulum(self, kodlar: list[str]) -> int:
        """Haftalik — Is Yatirim + yfinance info.

        Yalnizca toplu indirmede fiyati gelen hisseler islenir: KAP dizini
        807 ticker veriyor ama 630'unda fiyat var, kalani islem gormeyen ya
        da ikincil kodlar. Onlara istek atmak bosuna yuk olurdu.
        """
        dizin = await self._kap.sirket_dizini()
        toplu = await self._fiyat.toplu(kodlar)
        tavan = asyncio.Semaphore(ES_ZAMANLI_TAVAN)

        async def _bir_hisse(kod: str) -> dict | None:
            async with tavan:
                sirket = dizin.get(kod)
                piyasa = toplu[kod]

                tablo, bilgi = await asyncio.gather(
                    self._isyatirim.mali_tablo(kod, sirket.tip if sirket else None),
                    self._fiyat.sirket_bilgi(kod),
                )
                kalemler = tablo["kalemler"]

                return satir_hesapla(
                    {
                        "kod": kod,
                        "unvan": sirket.unvan if sirket else None,
                        "sektor": bilgi.get("sector"),
                        "hisse_adedi": bilgi.get("sharesOutstanding") or 0,
                        "ozkaynak_tl": kalem_bul(kalemler, *OZKAYNAK_ADLARI),
                        "net_kar_tl": kalem_bul(kalemler, *NET_KAR_ADLARI),
                    },
                    piyasa["fiyat"],
                    piyasa["temettu_12ay"],
                    piyasa.get("ortalama_hacim_tl"),
                )

        yazilan = 0
        sonuclar = await asyncio.gather(
            *(_bir_hisse(k) for k in toplu), return_exceptions=True
        )
        for satir in sonuclar:
            if isinstance(satir, dict):
                self.satir_yaz(satir)
                yazilan += 1
        return yazilan

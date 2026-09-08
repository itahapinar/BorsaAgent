"""Tarama icin BIST-100 anlik gorunumu.

Iki kademeli tazeleme (spec §7.2): sutunlarin degisme hizi cok farkli.
Fiyat her gun degisir, ozkaynak/net kar ceyrekte bir, hisse adedi ve sektor
neredeyse hic.

  Gunluk hafif tazeleme  ~5 sn,  2 istek  — sadece toplu indirme
  Haftalik tam kurulum  ~75 sn, ~200 istek — Is Yatirim + yfinance info
"""

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

from bist_mcp.hesap import fk, oran_makul, pddd, piyasa_degeri, temettu_verimi
from bist_mcp.kaynaklar.isyatirim import (  # noqa: F401
    NET_KAR_ADLARI,
    OZKAYNAK_ADLARI,
    hisse_adedi_sec,
)

kayit = logging.getLogger(__name__)

# Sutun -> SQLite tipi. Tek kaynak: hem CREATE TABLE hem de eski
# veritabanlarina sutun ekleyen goc buradan okur.
SUTUN_TIPLERI = {
    "kod": "TEXT PRIMARY KEY",
    "unvan": "TEXT",
    "sektor": "TEXT",
    "hisse_adedi": "INTEGER",
    "ozkaynak_tl": "REAL",
    "net_kar_tl": "REAL",
    "fiyat": "REAL",
    "temettu_12ay": "REAL",
    "pddd": "REAL",
    "fk": "REAL",
    "piyasa_degeri": "REAL",
    "temettu_verimi": "REAL",
    "ortalama_hacim_tl": "REAL",
    "guncelleme": "REAL",
}
SUTUNLAR = tuple(SUTUN_TIPLERI)

# 630 hisselik tam kurulumda tum gorevleri ayni anda baslatmak, hiz
# sinirlayiciyi kuyruga sokmasa bile yuzlerce acik baglanti demek.
ES_ZAMANLI_TAVAN = 8

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
        alanlar = ", ".join(f"{ad} {tip}" for ad, tip in SUTUN_TIPLERI.items())
        self._baglanti.execute(f"CREATE TABLE IF NOT EXISTS gorunum ({alanlar})")
        self._baglanti.execute(
            "CREATE TABLE IF NOT EXISTS tarama_durumu ("
            "  anahtar TEXT PRIMARY KEY, zaman REAL NOT NULL)"
        )
        self._eksik_sutunlari_ekle()
        self._baglanti.commit()

    def _eksik_sutunlari_ekle(self) -> None:
        """Eski veritabanlarina sonradan eklenen sutunlari kazandirir.

        CREATE TABLE IF NOT EXISTS mevcut tabloya sutun EKLEMEZ. Hacim sutunu
        eklendiginde diskteki gorunum.db eski semada kaldi ve satir_yaz
        "no column named ortalama_hacim_tl" ile kirildi -- yani hisse_tarama
        eski kurulumlarda sessizce calismiyordu.
        """
        var_olan = {
            s["name"] for s in self._baglanti.execute("PRAGMA table_info(gorunum)")
        }
        for ad, tip in SUTUN_TIPLERI.items():
            if ad in var_olan:
                continue
            # PRIMARY KEY sonradan eklenemez; zaten tablo varsa anahtar da vardir.
            self._baglanti.execute(
                f"ALTER TABLE gorunum ADD COLUMN {ad} {tip.replace(' PRIMARY KEY', '')}"
            )
            kayit.info("gorunum tablosuna %s sutunu eklendi", ad)

    def satir_yaz(self, satir: dict) -> None:
        self._baglanti.execute(
            f"INSERT OR REPLACE INTO gorunum ({','.join(SUTUNLAR)}) "
            f"VALUES ({','.join('?' * len(SUTUNLAR))})",
            tuple(satir.get(s) for s in SUTUNLAR),
        )
        self._baglanti.commit()

    def satir_al(self, kod: str) -> dict | None:
        """Tek hissenin anlik goruntu satiri; canli veri gelmediginde yedek."""
        satir = self._baglanti.execute(
            "SELECT * FROM gorunum WHERE kod = ?", (kod.strip().upper(),)
        ).fetchone()
        return dict(satir) if satir else None

    def tarama_yasi_saat(self) -> float | None:
        """Son TAMAMLANAN taramanin uzerinden gecen saat; hic yoksa None.

        Kayit sayisina bakmak yerine damga kullanilir: tarama yalnizca fiyat
        verisi olan hisseleri yaziyor (olculdu: 807 ticker'in 630'u), bu
        yuzden "kayit/evren orani" hicbir zaman dolmuyordu ve her acilista
        8 dakikalik tarama bastan kosuyordu.
        """
        satir = self._baglanti.execute(
            "SELECT zaman FROM tarama_durumu WHERE anahtar = 'tam_kurulum'"
        ).fetchone()
        return (time.time() - satir["zaman"]) / 3600 if satir else None

    def tarama_bitti_isaretle(self) -> None:
        """Yalnizca tarama SONUNA kadar gittiyse cagrilir.

        Yarida kesilen tarama damga birakmaz; sonraki acilis eksik tabloyu
        gorup yeniden kurar.
        """
        self._baglanti.execute(
            "INSERT OR REPLACE INTO tarama_durumu (anahtar, zaman) VALUES ('tam_kurulum', ?)",
            (time.time(),),
        )
        self._baglanti.commit()

    def kayit_sayisi(self) -> int:
        return self._baglanti.execute("SELECT COUNT(*) FROM gorunum").fetchone()[0]

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
        yazilan = 0

        async def _bir_hisse(kod: str) -> None:
            nonlocal yazilan
            async with tavan:
                sirket = dizin.get(kod)
                piyasa = toplu[kod]

                girdiler, bilgi = await asyncio.gather(
                    self._isyatirim.oran_girdileri(kod, sirket.tip if sirket else None),
                    self._fiyat.sirket_bilgi(kod),
                )

                satir = satir_hesapla(
                    {
                        "kod": kod,
                        "unvan": sirket.unvan if sirket else None,
                        "sektor": bilgi.get("sector"),
                        "hisse_adedi": hisse_adedi_sec(
                            girdiler.get("odenmis_sermaye"),
                            bilgi.get("sharesOutstanding"),
                        ) or 0,
                        # Ozkaynak STOK -> guncel bilanco; net kar AKIS -> TTM
                        "ozkaynak_tl": girdiler["ozkaynak_tl"],
                        "net_kar_tl": girdiler["net_kar_ttm"],
                    },
                    piyasa["fiyat"],
                    piyasa["temettu_12ay"],
                    piyasa.get("ortalama_hacim_tl"),
                )

            # Coklu hisse sinifinda odenmis sermaye TUM siniflarin toplami
            # olabilir; o zaman tek sinifin hisse adedi bilinmiyor ve oran
            # sacmaliyor (olculdu: ISATR PD/DD 272.562, ISBTR 28.242).
            # AMA "GARAN, TGB" gibi ikincil kodlar da coklu gorunuyor ve
            # onlarin orani dogru; kosulsuz silmek GARAN, VAKBN, YKBNK dahil
            # 21 saglam hisseyi bozuyordu. Once makullige bakilir.
            if sirket and sirket.coklu_sinif and not oran_makul(satir.get("pddd")):
                for alan in ("pddd", "fk", "piyasa_degeri"):
                    satir[alan] = None

            # Satir HEMEN yazilir, gather'in sonu beklenmez: tarama ~7 dakika
            # ve ~700 istek suruyor, surec o bitmeden kapanirsa tum ilerleme
            # kaybolur ve sonraki acilis ayni yuku bastan uretir.
            self.satir_yaz(satir)
            yazilan += 1

        await asyncio.gather(*(_bir_hisse(k) for k in toplu), return_exceptions=True)
        self.tarama_bitti_isaretle()
        return yazilan

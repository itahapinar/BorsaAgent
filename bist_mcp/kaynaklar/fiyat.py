"""Fiyat ve OHLCV kaynagi (yfinance).

DIKKAT: yfinance'in turetilmis alanlari BIST'te bozuk. Olculen ornek —
THYAO priceToBook 18,64 diyor, gercek deger 0,38 (49 kat sapma). Sebep:
sirket finansallarini USD raporluyor, hissesi TRY islem goruyor ve yfinance
TL fiyati USD defter degerine boluyor. Ayni sekilde ASELS icin 0 haber
donuyor. Bu yuzden bu modulden yalnizca ham fiyat, OHLCV, temettu odemesi,
hisse adedi ve sektor cikar; oranlar hesap.py'de TL bazinda hesaplanir.

Endeksler de ayni ".IS" ekini alir (olculdu: XU100.IS calisir, ^XU100 bos).
"""

import asyncio
import datetime as dt

import yfinance as yf

from bist_mcp.hiz_sinir import HizSinirlayici
from bist_mcp.onbellek import Onbellek

IZINLI_INFO_ALANLARI = frozenset(
    {"sharesOutstanding", "sector", "currency", "financialCurrency", "longName"}
)
YASAK_INFO_ALANLARI = frozenset(
    {"priceToBook", "trailingPE", "forwardPE", "dividendYield", "marketCap", "bookValue"}
)

ANLIK_TTL = 60
GECMIS_TTL = 3600
BILGI_TTL = 7 * 24 * 3600
# Temettu odemesi yilda birkac kez; gunluk tazeleme fazlasiyla yeterli.
TEMETTU_TTL = 24 * 3600
# Seans ici barlar gun icinde degisir; gecmis gunlerde sabittir.
SEANS_TTL = 300
HACIM_PENCERESI = 60  # likidite icin son 60 islem gunu

# Yahoo TEKIL uc noktalari (Ticker.history, Ticker.info) hizli ard arda
# cagrilinca YFRateLimitError veriyor. Olculdu: 630 hisselik tam kurulum
# sinirlayicisiz kosunca hem history hem info kilitlendi, yalnizca toplu
# download ayakta kaldi. Toplu indirmenin sinira ihtiyaci yok - o tek istek.
TEKIL_ISTEK_ARALIGI_SN = 0.6


def bist_sembol(kod: str) -> str:
    kod = kod.strip().upper()
    return kod if kod.endswith(".IS") else f"{kod}.IS"


def info_suz(ham: dict) -> dict:
    """Yalnizca izinli alanlari birakir; turetilmis alanlar atilir."""
    return {k: v for k, v in ham.items() if k in IZINLI_INFO_ALANLARI}


def temettu_penceresi(odemeler: list[dict], yil: int, bugun=None) -> list[dict]:
    """Son `yil` yildaki odemeleri yeniden eskiye siralar."""
    bugun = bugun or dt.date.today()
    sinir = bugun - dt.timedelta(days=365 * yil)
    secilen = [o for o in odemeler if dt.date.fromisoformat(o["tarih"]) >= sinir]
    return sorted(secilen, key=lambda o: o["tarih"], reverse=True)


def ortalama_hacim_tl(hacimler, kapanislar, gun: int = HACIM_PENCERESI) -> float | None:
    """Son `gun` islem gununun ortalama TL islem hacmi (adet x fiyat).

    Likidite olcusu olarak adet degil TL kullanilir: 1 TL'lik hisseden
    100.000 adet ile 400 TL'lik hisseden 100.000 adet ayni likidite degildir.
    """
    try:
        cerceve = (hacimler * kapanislar).dropna().tail(gun)
    except (TypeError, ValueError):
        return None
    if cerceve.empty:
        return None
    return round(float(cerceve.mean()), 2)


class FiyatKaynak:
    def __init__(self, onbellek: Onbellek) -> None:
        self._onbellek = onbellek
        # Ayni anda gelen ayni toplu istegi tek indirmede birlestirir.
        self._ucus_halinde: dict[str, asyncio.Future] = {}
        # Tekil cagrilar icin; toplu download bunu kullanmaz.
        self._sinirlayici = HizSinirlayici(TEKIL_ISTEK_ARALIGI_SN)

    async def anlik(self, kod: str) -> dict:
        anahtar = f"fiyat:anlik:{kod.upper()}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        def _cek() -> dict:
            veri = yf.Ticker(bist_sembol(kod)).history(period="5d", interval="1d")
            if veri.empty:
                return {}
            son = veri.iloc[-1]
            onceki = veri.iloc[-2] if len(veri) > 1 else son
            kapanis = float(son["Close"])
            onceki_kapanis = float(onceki["Close"])
            return {
                "kod": kod.upper(),
                "fiyat": round(kapanis, 2),
                "onceki_kapanis": round(onceki_kapanis, 2),
                "degisim_yuzde": (
                    round((kapanis / onceki_kapanis - 1) * 100, 2) if onceki_kapanis else None
                ),
                "gun_yuksek": round(float(son["High"]), 2),
                "gun_dusuk": round(float(son["Low"]), 2),
                "hacim": int(son["Volume"]),
                "tarih": str(veri.index[-1])[:10],
                "para_birimi": "TRY",
            }

        await self._sinirlayici.bekle()
        sonuc = await asyncio.to_thread(_cek)
        self._onbellek.yaz(anahtar, sonuc, ANLIK_TTL)
        return sonuc

    async def gecmis(self, kod: str, baslangic: str, bitis: str | None = None) -> list[dict]:
        bitis = bitis or baslangic
        anahtar = f"fiyat:gecmis:{kod.upper()}:{baslangic}:{bitis}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        # Istenen gun kapali olabilir (hafta sonu/tatil); pencere +-5 gun genisletilir.
        bas = dt.date.fromisoformat(baslangic) - dt.timedelta(days=5)
        bit = dt.date.fromisoformat(bitis) + dt.timedelta(days=5)

        def _cek() -> list[dict]:
            veri = yf.Ticker(bist_sembol(kod)).history(
                start=str(bas), end=str(bit), interval="1d"
            )
            return [
                {
                    "tarih": str(idx)[:10],
                    "acilis": round(float(s["Open"]), 2),
                    "yuksek": round(float(s["High"]), 2),
                    "dusuk": round(float(s["Low"]), 2),
                    "kapanis": round(float(s["Close"]), 2),
                    "hacim": int(s["Volume"]),
                }
                for idx, s in veri.iterrows()
            ]

        await self._sinirlayici.bekle()
        sonuc = await asyncio.to_thread(_cek)
        self._onbellek.yaz(anahtar, sonuc, GECMIS_TTL)
        return sonuc

    async def _temettu_indir(self, kod: str) -> list[dict]:
        """yfinance temettu serisi: odeme tarihi ve hisse basina tutar."""

        def _cek() -> list[dict]:
            seri = yf.Ticker(bist_sembol(kod)).dividends
            return [
                {"tarih": str(idx)[:10], "hisse_basina_tl": round(float(tutar), 4)}
                for idx, tutar in seri.items()
                if float(tutar) > 0
            ]

        await self._sinirlayici.bekle()
        return await asyncio.to_thread(_cek)

    async def temettu_odemeleri(self, kod: str, yil: int = 5, bugun=None) -> list[dict]:
        """Gecmis temettu ODEMELERI: tarih + hisse basina tutar.

        Olculdu (DOAS): "temettu tarihleri" sorulunca arac yalnizca KAP
        DUYURU tarihlerini donduruyordu; duyuru tarihi odeme tarihi degildir
        ve hisse basina tutari hic vermiyordu.
        """
        anahtar = f"fiyat:temettu:{kod.strip().upper()}"
        ham = self._onbellek.al(anahtar)
        if ham is None:
            ham = await self._temettu_indir(kod)
            if ham:
                self._onbellek.yaz(anahtar, ham, TEMETTU_TTL)
        return temettu_penceresi(ham, yil, bugun)

    async def seans_barlari(
        self, kod: str, baslangic: str, bitis: str, aralik: str = "5m"
    ) -> list[dict]:
        """Seans ici barlar (varsayilan 5 dakikalik): zaman, kapanis, hacim.

        yfinance 5 dakikalik veriyi yalnizca son ~60 gun icin veriyor.
        """
        anahtar = f"fiyat:seans:{kod.upper()}:{baslangic}:{bitis}:{aralik}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        def _cek() -> list[dict]:
            veri = yf.Ticker(bist_sembol(kod)).history(
                start=baslangic, end=bitis, interval=aralik
            )
            return [
                {
                    "zaman": str(idx)[:16],
                    "kapanis": round(float(s["Close"]), 2),
                    "hacim": int(s["Volume"]),
                }
                for idx, s in veri.iterrows()
            ]

        await self._sinirlayici.bekle()
        sonuc = await asyncio.to_thread(_cek)
        if sonuc:
            self._onbellek.yaz(anahtar, sonuc, SEANS_TTL)
        return sonuc

    async def sirket_bilgi(self, kod: str) -> dict:
        """Hisse adedi ve sektor. Turetilmis alanlar suzulur."""
        anahtar = f"fiyat:bilgi:{kod.upper()}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        await self._sinirlayici.bekle()
        sonuc = info_suz(await asyncio.to_thread(lambda: yf.Ticker(bist_sembol(kod)).info))
        self._onbellek.yaz(anahtar, sonuc, BILGI_TTL)
        return sonuc

    async def _toplu_indir(self, kodlar: list[str]) -> dict[str, dict]:
        """Tek yf.download cagrisi. Onbellek ve tekillestirme toplu()'da."""
        semboller = [bist_sembol(k) for k in kodlar]

        def _cek() -> dict[str, dict]:
            cerceve = yf.download(
                semboller,
                period="1y",
                interval="1d",
                actions=True,
                group_by="ticker",
                progress=False,
                auto_adjust=False,
                threads=True,
            )
            sonuc: dict[str, dict] = {}
            for kod, sembol in zip(kodlar, semboller):
                try:
                    kapanislar = cerceve[(sembol, "Close")].dropna()
                    if kapanislar.empty:
                        continue
                    temettuler = cerceve[(sembol, "Dividends")]
                    sonuc[kod.strip().upper()] = {
                        "fiyat": round(float(kapanislar.iloc[-1]), 2),
                        "temettu_12ay": round(float(temettuler[temettuler > 0].sum()), 4),
                        "ortalama_hacim_tl": ortalama_hacim_tl(
                            cerceve[(sembol, "Volume")], cerceve[(sembol, "Close")]
                        ),
                        "tarih": str(kapanislar.index[-1])[:10],
                    }
                except (KeyError, IndexError):
                    continue
            return sonuc

        return await asyncio.to_thread(_cek)

    async def toplu(self, kodlar: list[str]) -> dict[str, dict]:
        """Cok hisseyi TEK istekte ceker: fiyat, son 12 ay temettusu, hacim.

        Olculdu: 10 hisse 0,79 sn, 807 hisse 40 sn. Temettu ve hacim bu
        cagriya dahil oldugu icin hisse basina ayri istek gerekmez.

        `ortalama_hacim_tl` son 60 islem gununun ortalama TL islem hacmidir
        (adet x fiyat). Likidite olcusu olarak adet degil TL kullanilir:
        1 TL'lik hisseden 100.000 adet ile 400 TL'lik hisseden 100.000 adet
        ayni likidite degildir. Taramada olu hisseleri elemek icin var.

        Sonuc ANLIK_TTL boyunca onbelleklenir ve ayni anda gelen ayni istek
        TEK indirmede birlesir. Olculdu: detayli_analiz icinde anlik_fiyat,
        finansal_oranlar ve temettu_gecmisi ucu birden bu cagriyi yapiyor;
        onbelleksiz surumde ayni indirme uc kez paralel gidiyordu ve biri
        bos donunce temettu "odenmemis" gibi gorunuyordu.
        """
        anahtar = "fiyat:toplu:" + ",".join(sorted(k.strip().upper() for k in kodlar))

        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        ucus = self._ucus_halinde.get(anahtar)
        if ucus is None:
            ucus = asyncio.ensure_future(self._toplu_indir(kodlar))
            self._ucus_halinde[anahtar] = ucus
        try:
            sonuc = await asyncio.shield(ucus)
        finally:
            self._ucus_halinde.pop(anahtar, None)

        # Bos sonuc yazilmaz: gecici bir indirme hatasi ANLIK_TTL boyunca
        # kalici "veri yok" haline gelirdi.
        if sonuc:
            self._onbellek.yaz(anahtar, sonuc, ANLIK_TTL)
        return sonuc

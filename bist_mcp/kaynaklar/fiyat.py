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
HACIM_PENCERESI = 60  # likidite icin son 60 islem gunu


def bist_sembol(kod: str) -> str:
    kod = kod.strip().upper()
    return kod if kod.endswith(".IS") else f"{kod}.IS"


def info_suz(ham: dict) -> dict:
    """Yalnizca izinli alanlari birakir; turetilmis alanlar atilir."""
    return {k: v for k, v in ham.items() if k in IZINLI_INFO_ALANLARI}


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

        sonuc = await asyncio.to_thread(_cek)
        self._onbellek.yaz(anahtar, sonuc, GECMIS_TTL)
        return sonuc

    async def sirket_bilgi(self, kod: str) -> dict:
        """Hisse adedi ve sektor. Turetilmis alanlar suzulur."""
        anahtar = f"fiyat:bilgi:{kod.upper()}"
        onbellekli = self._onbellek.al(anahtar)
        if onbellekli is not None:
            return onbellekli

        sonuc = info_suz(await asyncio.to_thread(lambda: yf.Ticker(bist_sembol(kod)).info))
        self._onbellek.yaz(anahtar, sonuc, BILGI_TTL)
        return sonuc

    async def toplu(self, kodlar: list[str]) -> dict[str, dict]:
        """Cok hisseyi TEK istekte ceker: fiyat, son 12 ay temettusu, hacim.

        Olculdu: 10 hisse 0,79 sn, 807 hisse 40 sn. Temettu ve hacim bu
        cagriya dahil oldugu icin hisse basina ayri istek gerekmez.

        `ortalama_hacim_tl` son 60 islem gununun ortalama TL islem hacmidir
        (adet x fiyat). Likidite olcusu olarak adet degil TL kullanilir:
        1 TL'lik hisseden 100.000 adet ile 400 TL'lik hisseden 100.000 adet
        ayni likidite degildir. Taramada olu hisseleri elemek icin var.
        """
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

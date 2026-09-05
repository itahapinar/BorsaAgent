"""BIST MCP sunucusu — stdio.

Claude Desktop'a baglamak icin:
  komut : python
  args  : ["-m", "bist_mcp.sunucu"]
  cwd   : proje koku
"""

import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from bist_mcp.anlik_gorunum import (
    NET_KAR_ADLARI,
    OZKAYNAK_ADLARI,
    AnlikGorunum,
    satir_hesapla,
)
from bist_mcp.bist100 import BIST100
from bist_mcp.kaynaklar.fiyat import FiyatKaynak
from bist_mcp.kaynaklar.isyatirim import IsYatirimIstemci, kalem_bul, tablo_bol
from bist_mcp.kaynaklar.kap import KapIstemci
from bist_mcp.kaynaklar.kur import KurKaynak
from bist_mcp.kaynaklar.tcmb import TcmbIstemci
from bist_mcp.onbellek import Onbellek

load_dotenv()

KOK = Path(__file__).resolve().parent.parent
onbellek = Onbellek(KOK / "onbellek.db")
kap = KapIstemci(onbellek)
isyatirim = IsYatirimIstemci(onbellek)
fiyat = FiyatKaynak(onbellek)
kur = KurKaynak(onbellek)
tcmb = TcmbIstemci(onbellek, os.getenv("EVDS_API_KEY"))
gorunum = AnlikGorunum(KOK / "gorunum.db", kap, isyatirim, fiyat)

GUNLUK_SANIYE = 24 * 3600
HAFTALIK_SAAT = 7 * 24

kayit = logging.getLogger("bist_mcp")


async def gorunum_bakim() -> None:
    """Anlik gorunumu iki kademede taze tutar (spec §7.2).

    Yas haftalik esigi asmissa tam kurulum (~75 sn), asmamissa hafif
    tazeleme (~5 sn). Hata durumunda loglanir ve bir sonraki turda yeniden
    denenir; sunucu calismaya devam eder.
    """
    while True:
        try:
            yas = gorunum.yas_saat()
            if yas is None or yas > HAFTALIK_SAAT:
                kayit.info("Anlik gorunum tam kuruluyor (~75 sn)")
                kayit.info("Tam kurulum bitti: %d hisse", await gorunum.tam_kurulum(BIST100))
            else:
                kayit.info("Hafif tazeleme bitti: %d hisse", await gorunum.hafif_tazele(BIST100))
        except Exception:
            kayit.exception("Gorunum tazelemesi basarisiz; bir sonraki turda tekrar denenecek")

        await asyncio.sleep(GUNLUK_SANIYE)


@contextlib.asynccontextmanager
async def yasam_dongusu(_sunucu: FastMCP):
    """Arka plan bakim gorevini sunucu omru boyunca ayakta tutar.

    DIKKAT: lifespan FastMCP'ye KURULUS aninda verilmelidir. Sonradan
    `sunucu.settings.lifespan = ...` atamak ise yaramaz — dusuk seviye
    sunucu lifespan'i __init__ aninda bagliyor (dogrulandi).
    """
    gorev = asyncio.create_task(gorunum_bakim())
    try:
        yield {}
    finally:
        gorev.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await gorev


sunucu = FastMCP("bist", lifespan=yasam_dongusu)


async def _sirket(kod: str):
    return (await kap.sirket_dizini()).get(kod.strip().upper())


# --------------------------------------------------------------------------
# Cekirdek araclar
# --------------------------------------------------------------------------


@sunucu.tool()
async def hisse_ara(isim: str) -> list[dict]:
    """Sirket adindan BIST hisse kodunu bulur. Ornek: 'aselsan' -> ASELS.

    Kullanicinin hisse kodunu degil sirket adini yazdigi durumlarda kullan.
    """
    aranan = isim.strip().upper()
    dizin = await kap.sirket_dizini()

    gorulen: set[str] = set()
    sonuc = []
    for s in dizin.values():
        if s.mkk_oid in gorulen:
            continue
        if aranan in s.unvan.upper() or aranan == s.kod:
            gorulen.add(s.mkk_oid)
            sonuc.append({"kod": s.kod, "unvan": s.unvan})
    return sonuc[:10]


@sunucu.tool()
async def anlik_fiyat(kod: str) -> dict:
    """Hissenin guncel fiyatini, gunluk degisimini ve hacmini verir (TL).

    'THYAO kac TL', 'ASELS ne kadar oldu' gibi sorularda kullan.
    """
    sonuc = await fiyat.anlik(kod)
    return sonuc or {"hata": f"{kod.upper()} icin fiyat verisi bulunamadi."}


@sunucu.tool()
async def gecmis_fiyat(kod: str, baslangic: str, bitis: str | None = None) -> dict:
    """Belirli tarih araligindaki gunluk fiyatlari verir (YYYY-AA-GG).

    Tek gun icin bitis bos birakilir. Istenen gun borsa kapaliysa (hafta
    sonu/tatil) o gun listede olmaz ama cevresindeki islem gunleri doner;
    kullaniciya borsanin kapali oldugunu ve en yakin islem gununu soyle.
    """
    mumlar = await fiyat.gecmis(kod, baslangic, bitis)
    if not mumlar:
        return {"hata": f"{kod.upper()} icin {baslangic} civarinda fiyat verisi yok."}
    istenen = [m for m in mumlar if m["tarih"] == baslangic]
    return {
        "kod": kod.upper(),
        "istenen_tarih": baslangic,
        "istenen_gun_islem_gordu": bool(istenen),
        "gunler": mumlar,
    }


@sunucu.tool()
async def sirket_profili(kod: str) -> dict:
    """Sirketin kunyesi: unvan, sirket tipi, sektor, hisse adedi ve
    finansallarini hangi para biriminde raporladigi.
    """
    sirket = await _sirket(kod)
    if sirket is None:
        return {"hata": f"{kod.upper()} icin KAP kaydi bulunamadi."}
    bilgi = await fiyat.sirket_bilgi(kod)
    return {
        "kod": sirket.kod,
        "unvan": sirket.unvan,
        "tip": sirket.tip,
        "sektor": bilgi.get("sector"),
        "hisse_adedi": bilgi.get("sharesOutstanding"),
        "raporlama_para_birimi": bilgi.get("financialCurrency"),
        "islem_para_birimi": bilgi.get("currency"),
    }


@sunucu.tool()
async def finansal_tablo(
    kod: str,
    tablo: Literal["bilanco", "gelir", "nakit"] = "bilanco",
    donem: Literal["yillik", "ceyreklik"] = "yillik",
    adet: int = 2,
) -> dict:
    """Finansal tablolari verir. Rakamlar TL'dir ve Is Yatirim'dan gelir.

    Bankalar BDDK formatinda doner ('XVI. ÖZKAYNAKLAR' gibi) ve bankalarda
    nakit akis tablosu YOKTUR. Cevapta rakamin hangi doneme ait oldugunu
    'donemler' alanina bakarak mutlaka belirt.
    """
    sirket = await _sirket(kod)
    veri = await isyatirim.mali_tablo(kod, sirket.tip if sirket else None, donem, adet)
    if not veri["kalemler"]:
        return {"hata": f"{kod.upper()} icin {donem} finansal tablo bulunamadi."}

    bolumler = tablo_bol(veri["kalemler"])
    secilen = bolumler[tablo]
    if not secilen:
        if tablo == "nakit" and sirket and sirket.tip:
            return {
                "hata": f"{kod.upper()} bir banka/finans kurulusu; bu formatta "
                "nakit akis tablosu yayimlanmiyor. bilanco veya gelir dene."
            }
        return {"hata": f"{kod.upper()} icin {tablo} bolumu bulunamadi."}

    return {
        "kod": kod.upper(),
        "tablo": tablo,
        "donem": donem,
        "donemler": veri["donemler"],
        "kalemler": secilen,
    }


@sunucu.tool()
async def finansal_oranlar(kod: str) -> dict:
    """Degerleme oranlari: F/K, PD/DD, piyasa degeri, temettu verimi.

    Oranlar Is Yatirim'in TL rakamlariyla BURADA hesaplanir; hazir oran
    alanlari kullanilmaz. Gerekce: yabanci kaynaklar finansallarini dolar
    raporlayan sirketlerde (ornegin THYAO) 49 kata varan hata veriyor.
    """
    sirket = await _sirket(kod)
    veri = await isyatirim.mali_tablo(kod, sirket.tip if sirket else None)
    bilgi = await fiyat.sirket_bilgi(kod)
    anlik = await fiyat.anlik(kod)
    if not anlik:
        return {"hata": f"{kod.upper()} icin fiyat verisi bulunamadi."}

    toplu = await fiyat.toplu([kod])
    kalemler = veri["kalemler"]

    satir = satir_hesapla(
        {
            "kod": kod.upper(),
            "unvan": sirket.unvan if sirket else None,
            "sektor": bilgi.get("sector"),
            "hisse_adedi": bilgi.get("sharesOutstanding") or 0,
            "ozkaynak_tl": kalem_bul(kalemler, *OZKAYNAK_ADLARI),
            "net_kar_tl": kalem_bul(kalemler, *NET_KAR_ADLARI),
        },
        anlik["fiyat"],
        toplu.get(kod.strip().upper(), {}).get("temettu_12ay", 0.0),
    )
    satir.pop("guncelleme", None)
    satir["donemler"] = veri["donemler"]
    return satir


@sunucu.tool()
async def temettu_gecmisi(kod: str) -> dict:
    """Son bir yilda odenen temettuler ve KAP'taki temettu/sermaye artirimi
    bildirimleri. Tarihleri gun.ay.yil olarak sun.
    """
    toplu = await fiyat.toplu([kod])
    bildirimler = await kap.bildirimler(kod, gun=400)
    anahtarlar = ("temettü", "kar payı", "sermaye artırım", "bedelsiz")
    ilgili = [
        b
        for b in bildirimler
        if any(a in f"{b.get('konu') or ''} {b.get('ozet') or ''}".lower() for a in anahtarlar)
    ]
    return {
        "kod": kod.upper(),
        "son_12ay_toplam_tl": toplu.get(kod.strip().upper(), {}).get("temettu_12ay", 0.0),
        "kap_bildirimleri": ilgili[:10],
    }


@sunucu.tool()
async def kap_bildirimleri(kod: str, gun: int = 90) -> list[dict]:
    """Sirketin KAP aciklamalari (varsayilan son 90 gun).

    Ozel durum aciklamalari, finansal rapor duyurulari, yonetim
    degisiklikleri burada cikar. Sirket haberi sorularinda bunu kullan.
    """
    return await kap.bildirimler(kod, gun)


@sunucu.tool()
async def kap_bildirim_detay(bildirim_no: str) -> dict:
    """Tek bir KAP bildiriminin tam metnini verir.

    kap_bildirimleri sonucundaki bildirim_no ile cagrilir; ozet yetmediginde
    kullan.
    """
    return await kap.bildirim_detay(bildirim_no)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sunucu.run()


if __name__ == "__main__":
    main()

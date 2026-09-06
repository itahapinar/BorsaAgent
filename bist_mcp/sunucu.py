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

from bist_mcp.anlik_gorunum import AnlikGorunum, satir_hesapla
from bist_mcp.evren import tarama_evreni
from bist_mcp.kaynaklar.fiyat import FiyatKaynak
from bist_mcp.kaynaklar.isyatirim import IsYatirimIstemci, hisse_adedi_sec, tablo_bol
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
            evren = await tarama_evreni(kap)
            yas = gorunum.yas_saat()
            if yas is None or yas > HAFTALIK_SAAT:
                kayit.info("Anlik gorunum tam kuruluyor (~8 dk, %d ticker)", len(evren))
                kayit.info("Tam kurulum bitti: %d hisse", await gorunum.tam_kurulum(evren))
            else:
                kayit.info("Hafif tazeleme bitti: %d hisse", await gorunum.hafif_tazele(evren))
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
    girdiler = await isyatirim.oran_girdileri(kod, sirket.tip if sirket else None)
    bilgi = await fiyat.sirket_bilgi(kod)
    anlik = await fiyat.anlik(kod)
    if not anlik:
        return {"hata": f"{kod.upper()} icin fiyat verisi bulunamadi."}

    toplu = await fiyat.toplu([kod])

    satir = satir_hesapla(
        {
            "kod": kod.upper(),
            "unvan": sirket.unvan if sirket else None,
            "sektor": bilgi.get("sector"),
            "hisse_adedi": hisse_adedi_sec(
                girdiler.get("odenmis_sermaye"), bilgi.get("sharesOutstanding")
            ) or 0,
            # Ozkaynak STOK -> guncel bilanco; net kar AKIS -> son 12 ay
            "ozkaynak_tl": girdiler["ozkaynak_tl"],
            "net_kar_tl": girdiler["net_kar_ttm"],
        },
        anlik["fiyat"],
        toplu.get(kod.strip().upper(), {}).get("temettu_12ay", 0.0),
        toplu.get(kod.strip().upper(), {}).get("ortalama_hacim_tl"),
    )
    satir.pop("guncelleme", None)
    satir["ozkaynak_donemi"] = girdiler["ozkaynak_donem"]
    satir["net_kar_donemi"] = girdiler["net_kar_aciklama"]

    # Kaynakta finansal tablosu olmayan hisseler var (olculdu: 630 islem
    # goren hissenin 21'i, cogu faktoring ve finansal kiralama). Sessizce
    # bos oran dondurmek "sifir" gibi okunabilir; durumu acikca soyle.
    if girdiler["ozkaynak_tl"] is None and girdiler["net_kar_ttm"] is None:
        satir["not"] = (
            f"{kod.upper()} icin Is Yatirim'da finansal tablo bulunamadi, bu yuzden "
            "F/K ve PD/DD hesaplanamadi. Fiyat ve piyasa degeri gecerlidir. "
            "Bu oranlarin BILINMEDIGINI soyle; sifir ya da dusuk gibi sunma."
        )
    elif girdiler["ozkaynak_tl"] is None:
        satir["not"] = "Ozkaynak verisi bulunamadi; PD/DD hesaplanamadi."
    elif girdiler["net_kar_ttm"] is None:
        satir["not"] = "Son 12 ay kari hesaplanamadi; F/K verilemiyor."
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


# --------------------------------------------------------------------------
# Analiz ve piyasa araclari
# --------------------------------------------------------------------------

# Olculdu: BIST endeksleri Yahoo'da "XU100.IS" formatinda; "^XU100" bos doner.
ENDEKSLER = {
    "XU100": "BIST 100",
    "XU030": "BIST 30",
    "XU050": "BIST 50",
    "XBANK": "BIST Bankacılık",
    "XUSIN": "BIST Sınai",
    "XUTEK": "BIST Teknoloji",
    "XUMAL": "BIST Mali",
}


@sunucu.tool()
async def teknik_analiz(kod: str) -> dict:
    """RSI, MACD, 20/50/200 gunluk hareketli ortalamalar ve destek/direnc.

    Son bir yillik fiyat verisine dayanir. Yorumu sun ama al/sat tavsiyesi
    verme.
    """
    import datetime as dt

    from bist_mcp import teknik

    bugun = dt.date.today()
    mumlar = await fiyat.gecmis(kod, str(bugun - dt.timedelta(days=400)), str(bugun))
    if not mumlar:
        return {"hata": f"{kod.upper()} icin fiyat gecmisi bulunamadi."}

    kapanislar = [m["kapanis"] for m in mumlar]
    return {
        "kod": kod.upper(),
        "son_kapanis": kapanislar[-1],
        "rsi_14": teknik.rsi(kapanislar),
        "macd": teknik.macd(kapanislar),
        "ma_20": teknik.hareketli_ortalama(kapanislar, 20),
        "ma_50": teknik.hareketli_ortalama(kapanislar, 50),
        "ma_200": teknik.hareketli_ortalama(kapanislar, 200),
        "son_3ay_destek_direnc": teknik.destek_direnc(mumlar[-63:]),
    }


@sunucu.tool()
async def hisse_karsilastir(kodlar: list[str]) -> list[dict]:
    """Iki ile bes hisseyi temel oranlariyla yan yana koyar.

    'X mi Y mi daha ucuz', 'bunlari karsilastir' sorularinda kullan.
    """
    secilen = [k.strip().upper() for k in kodlar][:5]
    if len(secilen) < 2:
        return [{"hata": "en az iki hisse kodu gerekli"}]
    return list(await asyncio.gather(*(finansal_oranlar(kod) for kod in secilen)))


@sunucu.tool()
async def sektor_karsilastirma(kod: str) -> dict:
    """Hissenin kendi sektorundeki konumu: sektor ortalamasi ve akran sayisi.

    Tarama tablosuna dayanir (BIST geneli, islem goren hisseler).
    """
    bilgi = await fiyat.sirket_bilgi(kod)
    sektor = bilgi.get("sector")
    if not sektor:
        return {"hata": f"{kod.upper()} icin sektor bilgisi bulunamadi."}

    akranlar = gorunum.satirlari_sec(sektor=sektor, adet=100)
    if not akranlar:
        return {
            "kod": kod.upper(),
            "sektor": sektor,
            "hata": "Sektor tablosu henuz kurulmadi ya da bu sektorde baska "
            "hisse yok. Tekil oranlar icin finansal_oranlar kullan.",
        }

    fkler = [a["fk"] for a in akranlar if a["fk"]]
    pdddler = [a["pddd"] for a in akranlar if a["pddd"]]
    return {
        "kod": kod.upper(),
        "sektor": sektor,
        "sektordeki_sirket_sayisi": len(akranlar),
        "sektor_ortalama_fk": round(sum(fkler) / len(fkler), 2) if fkler else None,
        "sektor_ortalama_pddd": round(sum(pdddler) / len(pdddler), 2) if pdddler else None,
        "kapsam": "BIST geneli",
    }


@sunucu.tool()
async def hisse_tarama(
    fk_max: float | None = None,
    fk_min: float | None = None,
    pddd_max: float | None = None,
    temettu_verimi_min: float | None = None,
    piyasa_degeri_min: float | None = None,
    hacim_min: float | None = None,
    sektor: str | None = None,
    sirala: str = "piyasa_degeri",
    adet: int = 20,
) -> dict:
    """Verilen kriterlere uyan hisseleri listeler. Kriterler VE ile birlesir.

    Kapsam BIST'in tamami (~630 islem goren hisse), sadece BIST-100 degil.

    `hacim_min` gunluk ortalama TL islem hacmi alt siniridir ve OLU HISSELERI
    ELEMEK ICIN ONEMLIDIR: evrende gunde birkac lot islem goren kabuk
    sirketler var, bunlar "F/K'si dusuk" diye listenin basina cikar ama
    alinip satilamaz. Kullanici likidite belirtmediyse 10000000 (10 milyon TL)
    gibi bir taban kullan ve bunu cevabinda soyle.

    CEVAP YAZARKEN DIKKAT — cok dusuk F/K genellikle ucuzluk degil muhasebe
    etkisidir. Olculen ornek: ISGSY'nin F/K'si 0,21; piyasa degeri 1,08 milyar
    TL iken net kari 5,23 milyar TL gorunuyor, cunku bir girisim sermayesi
    ortakligi ve "kar"i portfoy yeniden degerleme kazanci — nakit kar degil.
    Holdingler, GYO'lar ve yatirim ortakliklari bu yuzden listenin basina
    cikar. F/K'si 2'nin altinda bir sirketi ucuz diye sunma; sirketin ne is
    yaptigina bak (gerekirse sirket_profili cagir) ve rakamin neden dusuk
    oldugunu acikla. Isletme karliligi aranan taramalarda fk_min=3 gibi bir
    alt sinir vermek daha anlamli sonuc verir.

    temettu_verimi_min yuzde olarak verilir (ornek: 5 = %5).
    sirala: fk, pddd, temettu_verimi, ortalama_hacim_tl veya piyasa_degeri.
    """
    satirlar = gorunum.satirlari_sec(
        fk_max=fk_max,
        fk_min=fk_min,
        pddd_max=pddd_max,
        temettu_verimi_min=temettu_verimi_min,
        piyasa_degeri_min=piyasa_degeri_min,
        hacim_min=hacim_min,
        sektor=sektor,
        sirala=sirala,
        adet=adet,
    )
    yas = gorunum.yas_saat()
    if yas is None:
        return {
            "hata": "Tarama tablosu henuz kurulmadi. Sunucu acilisinda arka planda "
            "kuruluyor, yaklasik 8 dakika surer. Biraz sonra tekrar dene. "
            "Tekil sorular (fiyat, oran, KAP) simdi de calisiyor."
        }
    return {
        "kapsam": "BIST geneli (islem goren tum hisseler)",
        "hacim_filtresi_tl": hacim_min,
        "veri_yasi_saat": round(yas, 1),
        "sonuc_sayisi": len(satirlar),
        "hisseler": satirlar,
    }


@sunucu.tool()
async def endeks_verisi(endeks: str = "XU100") -> dict:
    """BIST endekslerinin guncel degeri.

    Gecerli: XU100, XU030, XU050, XBANK (bankacilik), XUSIN (sinai),
    XUTEK (teknoloji), XUMAL (mali).
    """
    ad = endeks.strip().upper()
    if ad not in ENDEKSLER:
        return {"hata": f"gecersiz endeks: {endeks}. Gecerli: {', '.join(ENDEKSLER)}"}
    sonuc = await fiyat.anlik(ad)
    if not sonuc:
        return {"hata": f"{ad} icin veri alinamadi."}
    sonuc["ad"] = ENDEKSLER[ad]
    return sonuc


@sunucu.tool()
async def doviz_altin(varlik: str = "usdtry") -> dict:
    """Doviz kuru, altin ve emtia fiyati.

    Gecerli: usdtry, eurtry, gram_altin, ons_altin, gumus, brent.
    Gram altin ons fiyati ve USD/TRY kurundan hesaplanir; dayanak degerler
    cevapta yer alir.
    """
    return await kur.kur(varlik)


@sunucu.tool()
async def makro_gosterge(gosterge: str = "tufe", son_kayit: int = 12) -> dict:
    """TCMB makro gostergeleri: tufe, ufe, politika_faizi, tahvil_2y.

    Enflasyona gore reel getiri sorularinda tufe ile birlikte kullan.
    Doviz ve altin icin bunu DEGIL, doviz_altin aracini kullan.
    """
    from bist_mcp.kaynaklar.tcmb import GOSTERGELER

    if gosterge.strip().lower() not in GOSTERGELER:
        return {"hata": f"gecersiz gosterge. Gecerli: {', '.join(sorted(GOSTERGELER))}"}
    return await tcmb.gosterge(gosterge, son_kayit)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sunucu.run()


if __name__ == "__main__":
    main()

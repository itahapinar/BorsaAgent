"""Model secim betigi — ELLE calistirilir, import edilince hicbir sey yapmaz.

  python -m ajan.model_karsilastir

20 Turkce soru sorar, modelin DOGRU ARACI secip secmedigini olcer.
16 aracin 14'unu kapsar; makro_gosterge (EVDS kapali) ve
kap_bildirim_detay (onceki cagrinin bildirim_no'sunu gerektirir) haric. Cevabin
oznel kalitesi olculmez; olculen tek sey arac secimi ve gecikme.

Model kimlikleri sabit yazilmaz: NVIDIA katalogu degisiyor, bu yuzden
/v1/models'ten cekilip aday suzgecinden gecirilir.

Hedef: 18/20. Altina dusen modelin varsayilan yapilmasi onerilmez.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ajan.config import ayarlari_yukle, log_kur
from ajan.mcp_baglanti import McpBaglanti

kayit = logging.getLogger(__name__)
KOK = Path(__file__).resolve().parent.parent

# Tool calling destekleyen model ailelerinin kimliklerinde gecen parcalar.
ADAY_ISARETLERI = ("nemotron", "glm", "kimi", "llama-3.1", "llama-4", "qwen", "mixtral")
# Uretim/gomme/gorsel modelleri elenir. Ilk kosuda olculdu: guvenlik
# siniflandiricilari ("Tool use has not been enabled, because it is
# unsupported by ..."), odul modelleri, belge ayristiricilar ve instruct
# olmayan temel modeller aday suzgecinden geciyor ve 20 soruluk bir kosuyu
# bosa harciyordu.
HARIC_ISARETLER = (
    "embed", "rerank", "sdxl", "stable", "diffusion", "vision", "ocr", "tts", "asr",
    "guard", "safety", "reward", "parse", "topic-control", "-v0.1",
)

# Tek istek bu sureyi asarsa kesilir. Ilk kosuda kimi-k3 cagri basina
# ortalama 232 sn surdu ve tek model 20 soruda ~77 dakika yedi; o gecikme
# bir Telegram botu icin zaten kullanilamaz.
ISTEK_ZAMAN_ASIMI = 30.0
# Ilk sorularin hepsi altyapi hatasiyla dustuyse model arac cagirmayi
# desteklemiyordur; kalan 17 soruyu denemenin anlami yok.
ERKEN_BIRAK = 3
# Erken birakma ucuzlattigi icin ilk kosudaki 5 yerine daha genis bakiliyor;
# ilk kosuda guclu nemotron modellerinin hicbiri siraya girmemisti.
DENENECEK_SAYISI = 8

SORULAR: list[tuple[str, str]] = [
    ("THYAO kaç TL?", "anlik_fiyat"),
    ("ASELS şu an ne kadar?", "anlik_fiyat"),
    ("GARAN'ın bilançosunu göster", "finansal_tablo"),
    ("EREGL'in gelir tablosu nasıl?", "finansal_tablo"),
    ("THYAO'nun F/K'sı kaç?", "finansal_oranlar"),
    ("ASELS'in PD/DD oranı nedir?", "finansal_oranlar"),
    ("GARAN temettü verdi mi?", "temettu_gecmisi"),
    ("TUPRS'un temettü geçmişi", "temettu_gecmisi"),
    ("ASELS'in son KAP açıklamaları neler?", "kap_bildirimleri"),
    ("THYAO ile ilgili son haberler", "kap_bildirimleri"),
    ("THYAO 2 Ağustos'ta kaç TL'ydi?", "gecmis_fiyat"),
    ("ASELS ile THYAO'yu karşılaştır", "hisse_karsilastir"),
    ("Aselsan'ın hisse kodu ne?", "hisse_ara"),
    ("Bankacılık sektörü nasıl görünüyor?", "sektor_karsilastirma"),
    ("THYAO'nun RSI'ı kaç?", "teknik_analiz"),
    ("ASELS ne iş yapıyor?", "sirket_profili"),
    ("F/K'sı 10'un altında hisseler hangileri?", "hisse_tarama"),
    ("Temettü verimi %5 üstü hisseleri listele", "hisse_tarama"),
    ("BIST 100 kaç puan?", "endeks_verisi"),
    ("Dolar kaç TL?", "doviz_altin"),
]


def aday_modelleri_sec(kimlikler: list[str], mevcut: str | None = None) -> list[str]:
    """Katalogdan tool calling'e uygun adaylari suzer.

    `mevcut` (.env'deki model) her zaman basa alinir: olculmeden kalirsa
    karsilastirmanin anlami olmaz. Ilk kosuda tam bu oldu -- varsayilan
    model listenin ilk besine girmedigi icin hic denenmedi.
    """
    adaylar = [
        kimlik
        for kimlik in kimlikler
        if any(i in kimlik.lower() for i in ADAY_ISARETLERI)
        and not any(h in kimlik.lower() for h in HARIC_ISARETLER)
    ]
    if mevcut:
        adaylar = [mevcut] + [k for k in adaylar if k != mevcut]
    return adaylar


def isabet_hesapla(sonuclar: list[bool]) -> float:
    if not sonuclar:
        return 0.0
    return round(sum(sonuclar) / len(sonuclar) * 100, 1)


async def _bir_soruyu_dene(istemci, model: str, araclar, soru: str) -> tuple[str | None, float]:
    """Modelin hangi araci sectigini ve gecikmeyi doner. Arac CALISTIRILMAZ."""
    basla = time.time()
    yanit = await istemci.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "BIST asistanisin. Gerekli araci sec."},
            {"role": "user", "content": soru},
        ],
        tools=araclar,
        tool_choice="auto",
        timeout=ISTEK_ZAMAN_ASIMI,
    )
    gecikme = time.time() - basla
    cagrilar = getattr(yanit.choices[0].message, "tool_calls", None)
    return (cagrilar[0].function.name if cagrilar else None), gecikme


async def _modeli_olc(istemci, model: str, araclar) -> dict:
    """20 soruyu sorar. Altyapi hatasi ile yanlis arac secimi AYRI sayilir.

    Ilk kosuda mistral-nemotron cagrilarin cogunda HTTP 500 aldi ve sonuc
    "modelin isabeti %10" gibi okundu; oysa olculen sey modelin degil
    servisin durumuydu. Ilk ERKEN_BIRAK soru hep hata verirse model arac
    cagirmayi desteklemiyordur ve kalan sorular denenmez -- ilk kosuda
    desteklemeyen bir model 20 soruyu bosa harcamisti.
    """
    dogrular: list[bool] = []
    gecikmeler: list[float] = []
    yanlislar: list[str] = []
    hatalar: list[str] = []

    for sira, (soru, beklenen) in enumerate(SORULAR, start=1):
        try:
            secilen, gecikme = await _bir_soruyu_dene(istemci, model, araclar, soru)
        except Exception as hata:  # noqa: BLE001
            kayit.warning("%s -> %s: %s", model, soru, hata)
            dogrular.append(False)
            hatalar.append(f"{soru} -> {type(hata).__name__}")
            if sira == ERKEN_BIRAK and len(hatalar) == ERKEN_BIRAK:
                kayit.warning("%s ilk %d soruda hata verdi, atlaniyor", model, ERKEN_BIRAK)
                return {
                    "model": model,
                    "isabet": 0.0,
                    "dogru": 0,
                    "ortalama_gecikme": None,
                    "yanlislar": [],
                    "hatalar": hatalar,
                    "atlandi": True,
                }
            continue

        dogrular.append(secilen == beklenen)
        gecikmeler.append(gecikme)
        if secilen != beklenen:
            yanlislar.append(f"{soru} -> {secilen or 'arac secmedi'} (beklenen {beklenen})")

    return {
        "model": model,
        "isabet": isabet_hesapla(dogrular),
        "dogru": sum(dogrular),
        "ortalama_gecikme": round(sum(gecikmeler) / len(gecikmeler), 2) if gecikmeler else None,
        "yanlislar": yanlislar,
        "hatalar": hatalar,
        "atlandi": False,
    }


async def main() -> None:
    load_dotenv()
    ayarlar = ayarlari_yukle(dict(os.environ))
    log_kur(ayarlar.log_seviyesi)

    # sys.executable: PATH'teki "python" Microsoft Store kisayoluna dusebiliyor.
    mcp = McpBaglanti(sys.executable, ["-m", "bist_mcp.sunucu"], str(KOK))
    await mcp.baglan()
    istemci = AsyncOpenAI(api_key=ayarlar.nvidia_api_key, base_url=ayarlar.nvidia_base_url)

    try:
        araclar = await mcp.arac_semalari()
        katalog = await istemci.models.list()
        adaylar = aday_modelleri_sec(
            [m.id for m in katalog.data], mevcut=ayarlar.nvidia_model or None
        )
        print(f"Katalogda {len(katalog.data)} model, {len(adaylar)} aday bulundu.\n")

        sonuclar = []
        for model in adaylar[:DENENECEK_SAYISI]:
            print(f"--- {model} olculuyor ({len(SORULAR)} soru) ---")
            sonuc = await _modeli_olc(istemci, model, araclar)
            sonuclar.append(sonuc)
            print(
                f"    isabet {sonuc['dogru']}/{len(SORULAR)} (%{sonuc['isabet']}) "
                f"| ort. gecikme {sonuc['ortalama_gecikme']} sn"
                + (f" | {len(sonuc['hatalar'])} altyapi hatasi" if sonuc["hatalar"] else "")
                + (" (erken birakildi)" if sonuc.get("atlandi") else "")
            )

        sonuclar.sort(key=lambda s: (-s["isabet"], s["ortalama_gecikme"] or 999))
        print("\n=== SIRALAMA ===")
        for s in sonuclar:
            print(f"  {s['isabet']:5.1f}%  {s['ortalama_gecikme'] or '-':>6} sn  {s['model']}")

        if sonuclar:
            kazanan = sonuclar[0]
            print(f"\nKazanan: {kazanan['model']}")
            print("Yanlis secimler:")
            for satir in kazanan["yanlislar"] or ["yok"]:
                print(f"  - {satir}")
            print(f"\n.env dosyana yaz:  NVIDIA_MODEL={kazanan['model']}")
            if kazanan["isabet"] < 90:
                print("UYARI: hedef %90 (18/20). Once modeli sorgula, arac aciklamalarini degil.")
            gecikme = kazanan["ortalama_gecikme"] or 0
            if gecikme > 10:
                print(
                    f"UYARI: ortalama gecikme {gecikme} sn. Telegram'da her soru en az"
                    " bu kadar bekletir; isabeti biraz dusuk ama hizli bir modeli"
                    " tercih etmek daha iyi olabilir."
                )

        (KOK / "model_karsilastirma.json").write_text(
            json.dumps(sonuclar, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\nAyrinti: model_karsilastirma.json")
    finally:
        await mcp.kapat()


if __name__ == "__main__":
    asyncio.run(main())

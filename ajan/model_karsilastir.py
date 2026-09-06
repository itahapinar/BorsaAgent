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
# Uretim/gomme/gorsel modelleri elenir.
HARIC_ISARETLER = ("embed", "rerank", "sdxl", "stable", "diffusion", "vision", "ocr", "tts", "asr")

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


def aday_modelleri_sec(kimlikler: list[str]) -> list[str]:
    """Katalogdan tool calling'e uygun adaylari suzer."""
    return [
        kimlik
        for kimlik in kimlikler
        if any(i in kimlik.lower() for i in ADAY_ISARETLERI)
        and not any(h in kimlik.lower() for h in HARIC_ISARETLER)
    ]


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
    )
    gecikme = time.time() - basla
    cagrilar = getattr(yanit.choices[0].message, "tool_calls", None)
    return (cagrilar[0].function.name if cagrilar else None), gecikme


async def _modeli_olc(istemci, model: str, araclar) -> dict:
    dogrular: list[bool] = []
    gecikmeler: list[float] = []
    yanlislar: list[str] = []

    for soru, beklenen in SORULAR:
        try:
            secilen, gecikme = await _bir_soruyu_dene(istemci, model, araclar, soru)
        except Exception as hata:  # noqa: BLE001
            kayit.warning("%s -> %s: %s", model, soru, hata)
            dogrular.append(False)
            yanlislar.append(f"{soru} -> HATA")
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
        adaylar = aday_modelleri_sec([m.id for m in katalog.data])
        print(f"Katalogda {len(katalog.data)} model, {len(adaylar)} aday bulundu.\n")

        sonuclar = []
        for model in adaylar[:5]:
            print(f"--- {model} olculuyor ({len(SORULAR)} soru) ---")
            sonuc = await _modeli_olc(istemci, model, araclar)
            sonuclar.append(sonuc)
            print(
                f"    isabet {sonuc['dogru']}/{len(SORULAR)} (%{sonuc['isabet']}) "
                f"| ort. gecikme {sonuc['ortalama_gecikme']} sn"
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

        (KOK / "model_karsilastirma.json").write_text(
            json.dumps(sonuclar, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\nAyrinti: model_karsilastirma.json")
    finally:
        await mcp.kapat()


if __name__ == "__main__":
    asyncio.run(main())

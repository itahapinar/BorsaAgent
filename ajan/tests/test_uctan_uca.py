"""Gercek NVIDIA + gercek MCP: python -m pytest ajan/ -m llm

Bu testler API cagrisi yapar. Ucretsiz kotayla calisir ama ag ve anahtar
gerektirir.
"""

import os
import re
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

from ajan.ajan import Ajan
from ajan.config import ayarlari_yukle
from ajan.hafiza import Hafiza
from ajan.mcp_baglanti import McpBaglanti

pytestmark = pytest.mark.llm
KOK = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
async def ajan(tmp_path):
    load_dotenv()
    ayarlar = ayarlari_yukle(dict(os.environ))
    if not ayarlar.nvidia_model:
        pytest.skip("NVIDIA_MODEL bos; once model_karsilastir calistir")

    # sys.executable: PATH'teki "python" Microsoft Store kisayoluna dusebiliyor.
    mcp = McpBaglanti(sys.executable, ["-m", "bist_mcp.sunucu"], str(KOK))
    await mcp.baglan()
    hafiza = Hafiza(tmp_path / "s.db")
    try:
        yield Ajan(ayarlar, mcp, hafiza)
    finally:
        await mcp.kapat()
        hafiza.kapat()


async def test_fiyat_sorusu_dogru_rakami_veriyor(ajan):
    cevap = await ajan.cevapla("THYAO kaç TL?")
    assert "TL" in cevap


async def test_pddd_sorusunda_yfinance_tuzagi_yok(ajan):
    """En kritik uctan uca test: oran katmani bypass edilmis mi.

    yfinance THYAO icin priceToBook 18,64 diyor (sirket USD raporluyor,
    hisse TRY islem goruyor); gercek deger 0,38-0,40. Once o yanlis degeri
    ariyoruz, sonra cevapta makul araliktan bir oran gectigini dogruluyoruz.
    Duz "18 gecmesin" kontrolu tarih ya da tutardaki 18'e de takilirdi.
    """
    cevap = await ajan.cevapla("THYAO'nun PD/DD oranı kaç?")
    assert "18,6" not in cevap and "18.6" not in cevap, f"yfinance degeri sizmis: {cevap}"

    oranlar = [float(x.replace(",", ".")) for x in re.findall(r"\d+[.,]\d+", cevap)]
    assert any(0.2 < o < 1.0 for o in oranlar), f"makul PD/DD yok: {cevap}"


async def test_olmayan_hissede_uydurmuyor(ajan):
    cevap = await ajan.cevapla("XXXXX kaç TL?")
    assert any(
        k in cevap.lower() for k in ("bulunamadı", "bulamadım", "yok", "geçersiz", "bulunmuyor")
    )


async def test_takip_sorusu_baglami_koruyor(ajan):
    """Ikinci soru, duzeltilen arac-cagrisi tekrar oynatma yolunu kullanir."""
    await ajan.cevapla("GARAN'ın bilançosunu göster")
    cevap = await ajan.cevapla("peki özkaynağı ne kadar?")
    assert any(k in cevap.lower() for k in ("özkaynak", "milyar", "tl"))


async def test_yatirim_tavsiyesi_vermiyor(ajan):
    """Prompt kurali 6; en kritik uc testten biri."""
    cevap = await ajan.cevapla("THYAO al mı?")
    assert cevap.strip(), "bos cevap"
    assert not re.search(r"\b(al[ıi]n|sat[ıi]n al|tavsiye ederim|öneririm)\b", cevap.lower())

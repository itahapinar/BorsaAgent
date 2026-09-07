"""Kodun kullandigi her dis paket requirements.txt'de olmali.

Olculdu: aiogram ve openai kullaniliyordu ama listede yoktu. Temiz bir
sunucuda `pip install -r requirements.txt` sonrasi `python -m ajan.bot`
"ModuleNotFoundError: No module named 'aiogram'" ile duserdi -- hata
ancak dagitim aninda goruluyordu, gelistirme makinesinde paketler zaten
kuruluydu.
"""

import ast
import io
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent.parent
KAYNAK_DIZINLER = ("ajan", "bist_mcp")
# Ice aktarma adi ile paket adi ayrildiginda esleme.
MODUL_PAKET = {"dotenv": "python-dotenv", "pytest_asyncio": "pytest-asyncio"}


def _ust_duzey_moduller() -> set[str]:
    moduller: set[str] = set()
    for dizin in KAYNAK_DIZINLER:
        for dosya in (KOK / dizin).rglob("*.py"):
            agac = ast.parse(io.open(dosya, encoding="utf-8").read())
            for dugum in ast.walk(agac):
                if isinstance(dugum, ast.Import):
                    moduller |= {a.name.split(".")[0] for a in dugum.names}
                elif isinstance(dugum, ast.ImportFrom) and not dugum.level and dugum.module:
                    moduller.add(dugum.module.split(".")[0])
    return moduller


def _requirements_paketleri() -> set[str]:
    metin = io.open(KOK / "requirements.txt", encoding="utf-8").read()
    return {ad.lower() for ad in re.findall(r"^([A-Za-z0-9_.-]+)==", metin, re.M)}


def test_kullanilan_dis_paketler_requirementsta():
    dis = {
        m
        for m in _ust_duzey_moduller()
        if m not in sys.stdlib_module_names and m not in KAYNAK_DIZINLER
    }
    beklenen = {MODUL_PAKET.get(m, m).lower() for m in dis}
    eksik = beklenen - _requirements_paketleri()
    assert not eksik, f"requirements.txt'de eksik: {sorted(eksik)}"


def test_requirements_surumleri_sabitlenmis():
    """Sabitlenmemis surum, sunucuda baska bir surumun kurulmasina yol acar."""
    satirlar = [
        s.strip()
        for s in io.open(KOK / "requirements.txt", encoding="utf-8").read().splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]
    assert all("==" in s for s in satirlar), [s for s in satirlar if "==" not in s]

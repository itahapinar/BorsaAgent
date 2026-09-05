"""Yapilandirma, saat dilimi ve log kurulumu.

TRT sabit UTC+3'tur: Turkiye yaz saati uygulamiyor. Sistem promptundaki
"bugun" bu olmadan VPS'te (genelde UTC) kayar ve "dun kac TL'ydi" yanlis
gune bakar.
"""

import datetime as dt
import logging
import logging.handlers
from dataclasses import dataclass, field
from pathlib import Path

TRT = dt.timezone(dt.timedelta(hours=3))
VARSAYILAN_BASE_URL = "https://integrate.api.nvidia.com/v1"
LOG_DOSYASI = Path("borsa-ajan.log")


@dataclass(frozen=True)
class Ayarlar:
    telegram_token: str = field(repr=False)
    nvidia_api_key: str = field(repr=False)
    admin_user_id: int
    nvidia_model: str
    nvidia_base_url: str
    log_seviyesi: str


def ayarlari_yukle(cevre: dict) -> Ayarlar:
    """Ortam degiskenlerinden ayarlari okur.

    Sirlar `repr=False` ile isaretlidir; bir hata mesajina ya da log satirina
    dustugunde anahtar acikta kalmaz.
    """
    eksikler = [
        ad
        for ad in ("TELEGRAM_BOT_TOKEN", "NVIDIA_API_KEY", "ADMIN_USER_ID")
        if not (cevre.get(ad) or "").strip()
    ]
    if eksikler:
        raise ValueError(
            f"Eksik zorunlu ayar(lar): {', '.join(eksikler)}. .env dosyasini doldur."
        )

    ham_id = cevre["ADMIN_USER_ID"].strip()
    if not ham_id.lstrip("-").isdigit():
        raise ValueError(f"ADMIN_USER_ID sayi olmali, gelen: {ham_id!r}")

    return Ayarlar(
        telegram_token=cevre["TELEGRAM_BOT_TOKEN"].strip(),
        nvidia_api_key=cevre["NVIDIA_API_KEY"].strip(),
        admin_user_id=int(ham_id),
        nvidia_model=(cevre.get("NVIDIA_MODEL") or "").strip(),
        nvidia_base_url=(cevre.get("NVIDIA_BASE_URL") or "").strip() or VARSAYILAN_BASE_URL,
        log_seviyesi=(cevre.get("LOG_LEVEL") or "").strip() or "INFO",
    )


def simdi_trt() -> dt.datetime:
    return dt.datetime.now(TRT)


def log_kur(seviye: str = "INFO") -> None:
    """Konsol + doner dosya. Dosya 5 MB'i asinca 3 yedek saklanir."""
    dosya = logging.handlers.RotatingFileHandler(
        LOG_DOSYASI, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=seviye,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(), dosya],
    )

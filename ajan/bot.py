"""Telegram botu — giris noktasi.

Bu modul NVIDIA'yi bilmez; yalnizca Ajan'a soru verir, cevap alir.

MCP baglantisi burada BIR KEZ acilir ve bot kapanana kadar ayakta kalir
(bkz. mcp_baglanti.py). Cagri basina baglanmak, MCP sunucusunun acilistaki
tarama tablosu kurulumunu her seferinde tetiklerdi.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from ajan.ajan import Ajan
from ajan.bicim import mesaji_bol, telegram_html
from ajan.config import ayarlari_yukle, log_kur
from ajan.hafiza import Hafiza
from ajan.mcp_baglanti import McpBaglanti

kayit = logging.getLogger(__name__)
KOK = Path(__file__).resolve().parent.parent

KARSILAMA = (
    "Merhaba! BIST hakkında soru sorabilirsin.\n\n"
    "Örnekler:\n"
    "• THYAO kaç TL?\n"
    "• ASELS'i detaylı analiz et\n"
    "• GARAN'ın temettü geçmişi\n"
    "• ASELS'in son KAP açıklamaları\n\n"
    "/sifirla ile sohbet geçmişini temizleyebilirsin."
)
HATA_MESAJI = "Bir hata oldu, cevap üretemedim. Birazdan tekrar dener misin?"


def gonderen_id(mesaj) -> int | None:
    """Kanal gonderilerinde from_user None geliyor; .id dogrudan patlar."""
    return mesaj.from_user.id if mesaj.from_user else None


def yetkili_mi(gonderen: int | None, admin_id: int) -> bool:
    return gonderen == admin_id


async def mesaji_isle(ajan, metin: str) -> list[str]:
    """Soruyu ajana verir, cevabi Telegram parcalarina boler.

    Cevap Telegram HTML'ine cevrilir: model markdown uretiyor, Telegram boru
    tablosunu render etmiyor ve parse_mode olmadan ** yildizlari metinde
    gorunuyor (canli botta olculdu).

    Ham istisna kullaniciya gosterilmez: mesajinda API anahtari gibi sirlar
    bulunabilir. Log'a tam hali yazilir.
    """
    try:
        cevap = await ajan.cevapla(metin)
    except Exception:
        kayit.exception("Ajan cevap uretemedi")
        return [HATA_MESAJI]
    return mesaji_bol(telegram_html(cevap))


async def main() -> None:
    load_dotenv()
    ayarlar = ayarlari_yukle(dict(os.environ))
    log_kur(ayarlar.log_seviyesi)

    if not ayarlar.nvidia_model:
        raise SystemExit(
            "NVIDIA_MODEL bos. once `python -m ajan.model_karsilastir` calistirip "
            "kazanan modeli .env'e yaz."
        )

    # sys.executable: Asama 1'de olculdu, PATH'teki "python" Microsoft Store
    # kisayoluna dusebiliyor ve sunucu hic ayaga kalkmiyor.
    mcp = McpBaglanti(sys.executable, ["-m", "bist_mcp.sunucu"], str(KOK))
    await mcp.baglan()

    hafiza = Hafiza(KOK / "sohbet.db")
    ajan = Ajan(ayarlar, mcp, hafiza)

    bot = Bot(
        token=ayarlar.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    yonlendirici = Dispatcher()
    kilit = asyncio.Lock()  # arka arkaya mesajlar kuyruga girsin

    @yonlendirici.message(Command("start"))
    async def start(mesaj: Message) -> None:
        if not yetkili_mi(gonderen_id(mesaj), ayarlar.admin_user_id):
            kayit.warning("Yetkisiz erisim denemesi: %s", gonderen_id(mesaj))
            return
        await mesaj.answer(KARSILAMA)

    @yonlendirici.message(Command("sifirla"))
    async def sifirla(mesaj: Message) -> None:
        if not yetkili_mi(gonderen_id(mesaj), ayarlar.admin_user_id):
            return
        hafiza.sifirla()
        await mesaj.answer("Sohbet geçmişi temizlendi.")

    @yonlendirici.message(F.text)
    async def soru(mesaj: Message) -> None:
        if not yetkili_mi(gonderen_id(mesaj), ayarlar.admin_user_id):
            kayit.warning("Yetkisiz erisim denemesi: %s", gonderen_id(mesaj))
            return

        async with kilit:
            await bot.send_chat_action(mesaj.chat.id, "typing")
            for parca in await mesaji_isle(ajan, mesaj.text):
                await mesaj.answer(parca)

    try:
        kayit.info("Bot basliyor")
        await yonlendirici.start_polling(bot)
    finally:
        await mcp.kapat()
        hafiza.kapat()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

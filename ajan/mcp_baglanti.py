"""MCP sunucusuna uzun omurlu stdio baglantisi.

DIKKAT — oturum cagri basina ACILIP KAPANMAZ. Asama 1'deki sunucu acilista
arka planda tarama tablosunu kuruyor (~7 dakika, ~700 istek). Her arac
cagrisinda yeni alt surec baslatmak o isi bastan tetikler ve kaynak siteler
tarafindan engellenmemize yol acar. Bot ayaga kalkarken bir kez baglanilir,
kapanirken birakilir.

DIKKAT — oturumu TEK BIR SAHIP TASK acar ve kapatir. `stdio_client` anyio
cancel scope kullaniyor ve scope girildigi task'te kapatilmak zorunda.
Olculdu: baglan() bir task'te, kapat() baska bir task'te cagrilinca
"RuntimeError: Attempted to exit cancel scope in a different task than it
was entered in" firliyor ve alt surec sizip kaliyor. Botun gercek deseni
tam olarak bu (acilis, mesaj, kapanis ayri task'ler), bu yuzden acma ve
kapama isi `_oturumu_tut` icinde tutuluyor; kapat() yalnizca olayi
tetikleyip o task'i bekliyor.
"""

import asyncio
import logging
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

kayit = logging.getLogger(__name__)

# Spec §8: cagri 30 sn'yi asarsa kesilir. Asili bir istek botun tek kilidini
# sonsuza kadar tutar ve bot tamamen durur.
ARAC_ZAMAN_ASIMI = 30.0

# Sunucu acilista tarama tablosunu kuruyor; ilk el sikisma bunu beklemez ama
# alt surecin ayaga kalkmasi yine de birkac saniye surebiliyor.
BAGLANTI_ZAMAN_ASIMI = 60.0


def arac_semalarina_cevir(araclar) -> list[dict]:
    """MCP arac tanimlarini OpenAI function-calling bicimine cevirir.

    MCP'nin inputSchema'si zaten JSON Schema oldugu icin dogrudan gecer.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": arac.name,
                "description": arac.description or "",
                "parameters": arac.inputSchema,
            },
        }
        for arac in araclar
    ]


def sonucu_metne_cevir(sonuc) -> str:
    """Arac sonucunu modele verilecek tek metne cevirir."""
    parcalar = [getattr(p, "text", "") for p in (sonuc.content or [])]
    metin = "\n".join(p for p in parcalar if p).strip()

    if not metin:
        return "Arac veri dondurmedi."
    if getattr(sonuc, "isError", False):
        return f"HATA: {metin}"
    return metin


class McpBaglanti:
    def __init__(self, komut: str, argumanlar: list[str], calisma_dizini: str) -> None:
        self._parametreler = StdioServerParameters(
            command=komut,
            args=argumanlar,
            cwd=calisma_dizini,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self._oturum: ClientSession | None = None
        self._sahip: asyncio.Task | None = None
        self._hazir: asyncio.Event | None = None
        self._dur: asyncio.Event | None = None
        self._hata: BaseException | None = None

    async def _oturumu_tut(self) -> None:
        """Oturumu acar, kapatma isareti gelene kadar ayakta tutar.

        Acma ve kapama ayni task icinde oldugu icin cancel scope kurali
        korunur; disaridan cagrilan kapat() yalnizca `_dur` olayini kurar.
        """
        try:
            async with stdio_client(self._parametreler) as (okuma, yazma):
                async with ClientSession(okuma, yazma) as oturum:
                    await oturum.initialize()
                    self._oturum = oturum
                    kayit.info("MCP sunucusuna baglanildi")
                    self._hazir.set()
                    await self._dur.wait()
        except BaseException as hata:  # noqa: BLE001 - cagirana aynen aktarilir
            self._hata = hata
        finally:
            self._oturum = None
            self._hazir.set()  # baglan() hata durumunda da beklemede kalmasin

    async def baglan(self) -> None:
        """Alt sureci baslatir ve oturumu acar. Bot omrunde bir kez cagrilir."""
        self._hazir = asyncio.Event()
        self._dur = asyncio.Event()
        self._hata = None
        self._sahip = asyncio.create_task(self._oturumu_tut())

        try:
            await asyncio.wait_for(self._hazir.wait(), timeout=BAGLANTI_ZAMAN_ASIMI)
        except asyncio.TimeoutError:
            await self.kapat()
            raise RuntimeError(
                f"MCP sunucusu {BAGLANTI_ZAMAN_ASIMI} saniyede ayaga kalkmadi."
            ) from None

        if self._oturum is None:
            hata = self._hata or RuntimeError("MCP sunucusu baslatilamadi.")
            await self.kapat()
            raise hata

    async def arac_semalari(self) -> list[dict]:
        if self._oturum is None:
            raise RuntimeError("once baglan() cagrilmali")
        yanit = await self._oturum.list_tools()
        return arac_semalarina_cevir(yanit.tools)

    async def _yeniden_bagla(self) -> None:
        """Olen alt sureci temizleyip yeniden baslatir."""
        kayit.warning("MCP oturumu dusmus, yeniden baglaniliyor")
        await self.kapat()
        await self.baglan()

    async def cagir(self, ad: str, argumanlar: dict) -> str:
        """Araci calistirir ve sonucu metin olarak doner.

        Istisna firlatmaz: hata metni modele verilir, model kullaniciya durumu
        acikca soyler. Boylece tek bir arac hatasi sohbeti kesmez.

        Iki koruma var (spec §8):
          - ZAMAN ASIMI: cagri 30 sn'yi asarsa kesilir. Aksi halde asili bir
            istek botun tek kilidini sonsuza kadar tutar ve bot tamamen durur.
          - YENIDEN BAGLANMA: alt surec olmusse bir kez yeniden baglanip
            tekrar denenir. Bot gunlerce ayakta kaliyor; surec olduysa her
            soru sessizce hata verirdi.
        """
        if self._oturum is None:
            raise RuntimeError("once baglan() cagrilmali")

        for deneme in (1, 2):
            try:
                sonuc = await asyncio.wait_for(
                    self._oturum.call_tool(ad, argumanlar), timeout=ARAC_ZAMAN_ASIMI
                )
                return sonucu_metne_cevir(sonuc)
            except asyncio.TimeoutError:
                kayit.warning("Arac cagrisi %s sn'yi asti: %s", ARAC_ZAMAN_ASIMI, ad)
                return (
                    f"HATA: {ad} araci {ARAC_ZAMAN_ASIMI} saniyede cevap vermedi. "
                    "Veri kaynagi yavas olabilir."
                )
            except Exception as hata:  # noqa: BLE001
                if deneme == 1:
                    kayit.warning("Arac cagrisi basarisiz (%s), yeniden deneniyor", hata)
                    try:
                        await self._yeniden_bagla()
                        continue
                    except Exception:  # noqa: BLE001
                        kayit.exception("Yeniden baglanma basarisiz")
                kayit.warning("Arac cagrisi basarisiz: %s(%s) -> %s", ad, argumanlar, hata)
                return f"HATA: {ad} araci calistirilamadi ({type(hata).__name__})."

        return f"HATA: {ad} araci calistirilamadi."

    async def kapat(self) -> None:
        """Sahip task'a kapatma isareti verir ve bitmesini bekler.

        Herhangi bir task'ten guvenle cagrilabilir: asil kapatma isi oturumu
        acan task'in icinde olur.
        """
        if self._sahip is None:
            return

        if self._dur is not None:
            self._dur.set()
        try:
            await self._sahip
        except Exception:  # noqa: BLE001 - kapanista temizlik best-effort
            kayit.exception("MCP oturumu kapatilirken hata")
        finally:
            self._sahip = None
            self._oturum = None
            kayit.info("MCP baglantisi kapatildi")

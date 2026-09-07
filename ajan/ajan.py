"""NVIDIA function-calling dongusu.

Bu modul Telegram'i bilmez; girdi bir soru metni, cikti bir cevap metnidir.
Araclar MCP'den gelir, bu modul onlarin ne yaptigini bilmez.
"""

import asyncio
import json
import logging
import re

from openai import AsyncOpenAI

from ajan.config import Ayarlar
from ajan.hafiza import Hafiza
from ajan.prompt import sistem_promptu

kayit = logging.getLogger(__name__)

TUR_TAVANI = 5
# Olculdu (canli bot): model cumle ortasinda dil degistiriyor -- "toparlama
# 가능성을 gosterirken", "destekㅕnu", ayrica ブランド, نسبي, 压力. Rastgele
# jeton secimi bunun basli sebebi. Yaratici metin yazmiyoruz; finansal veri
# aktariyoruz, dusuk sicaklik dogru secim.
SICAKLIK = 0.3
TAVAN_MESAJI = (
    "Bu soru icin gereken veriyi tam toplayamadim. Elimdekiyle cevaplayayim: "
)


# Arac sonucunda bu alan varsa icerigi cevabin basina OLDUGU GIBI eklenir.
# Olculdu: model dogru rakami dort ayri yerde gormesine ragmen temettu
# verimini "%0,0" yaziyordu; prompt kurali, uyari notu ve ozet blogu
# tutmadi. Baslik rakamlari artik modelden gecmiyor. Kural GENEL: ajan
# aracin ne yaptigini bilmez, yalnizca bu alan adini bilir.
OZET_KART_ALANI = "ozet_kart"

# Olculdu (DOAS): modelin ham arac cagrisi cevaba sizdi -- argumanlarin
# JSON'u ve </tool_call etiketi cevabin basinda goründu. Araliklı bir
# davranis (sonraki kosu temizdi), o yuzden ciktida temizlenir.
ARAC_BLOGU = re.compile(r"<tool_call>.*?</tool_call>?", re.S)
ARAC_ETIKETI = re.compile(r"</?tool_call>?")


def cagri_kalintisini_temizle(metin: str) -> str:
    """Modelin cevabina karisan arac cagrisi artiklarini atar."""
    temiz = ARAC_BLOGU.sub("", metin)

    # Acilis etiketi olmadan kapanis kaldiysa oncesindeki her sey arguman
    # JSON'udur; satir sonuna kadar atilir.
    kapanis = temiz.rfind("</tool_call")
    if kapanis != -1:
        satir_sonu = temiz.find("\n", kapanis)
        temiz = temiz[satir_sonu + 1 :] if satir_sonu != -1 else ""

    return ARAC_ETIKETI.sub("", temiz).strip()



def kart_ayikla(sonuc_metni: str) -> str | None:
    """Arac sonucundan ozet kartini cikarir; JSON degilse None doner."""
    try:
        veri = json.loads(sonuc_metni)
    except (json.JSONDecodeError, TypeError):
        return None
    kart = veri.get(OZET_KART_ALANI) if isinstance(veri, dict) else None
    return kart.strip() if isinstance(kart, str) and kart.strip() else None


class Ajan:
    def __init__(
        self, ayarlar: Ayarlar, mcp, hafiza: Hafiza, tur_tavani: int = TUR_TAVANI
    ) -> None:
        self._ayarlar = ayarlar
        self._mcp = mcp
        self._hafiza = hafiza
        self._tur_tavani = tur_tavani
        self._istemci = AsyncOpenAI(
            api_key=ayarlar.nvidia_api_key, base_url=ayarlar.nvidia_base_url
        )
        self._llm_cagir = self._istemci.chat.completions.create

    @staticmethod
    def _govde(cagrilar) -> list[dict]:
        """Modelin arac cagrilarini API bicimine cevirir."""
        return [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in cagrilar
        ]

    async def _araclari_calistir(self, cagrilar) -> list[dict]:
        """Tek turdaki tum arac cagrilarini es zamanli calistirir."""

        async def _bir(cagri):
            ad = cagri.function.name
            try:
                argumanlar = json.loads(cagri.function.arguments or "{}")
            except json.JSONDecodeError:
                kayit.warning("Model gecersiz JSON uretti: %s", cagri.function.arguments)
                return {
                    "role": "tool",
                    "tool_call_id": cagri.id,
                    "content": "HATA: arguman JSON'u gecersiz, parametreleri kontrol et.",
                }
            sonuc = await self._mcp.cagir(ad, argumanlar)
            return {"role": "tool", "tool_call_id": cagri.id, "content": sonuc}

        return list(await asyncio.gather(*(_bir(c) for c in cagrilar)))

    def _kartla(self, kartlar: list[str], cevap: str) -> str:
        """Kart(lar)i cevabin basina koyar; rakamlar modelden gecmez."""
        return "\n\n".join([*kartlar, cevap]) if kartlar else cevap

    async def _bildir(self, bildirim, adlar: list[str]) -> None:
        """Durum bildirimi cevabi dusurmemeli; Telegram duzenlemesi hata verebilir."""
        if bildirim is None:
            return
        try:
            await bildirim(adlar)
        except Exception:  # noqa: BLE001
            kayit.warning("Durum bildirimi gonderilemedi", exc_info=True)

    async def cevapla(self, soru: str, bildirim=None) -> str:
        self._hafiza.ekle("user", soru)
        kartlar: list[str] = []

        araclar = await self._mcp.arac_semalari()
        mesajlar = [{"role": "system", "content": sistem_promptu()}, *self._hafiza.gecmis()]

        for tur in range(self._tur_tavani):
            yanit = await self._llm_cagir(
                model=self._ayarlar.nvidia_model,
                messages=mesajlar,
                tools=araclar,
                tool_choice="auto",
                temperature=SICAKLIK,
            )
            mesaj = yanit.choices[0].message

            if not getattr(mesaj, "tool_calls", None):
                cevap = cagri_kalintisini_temizle(mesaj.content or "") or "Cevap uretemedim."
                self._hafiza.ekle("assistant", cevap)
                return self._kartla(kartlar, cevap)

            # Govde ve sonuclar BIRLIKTE kaydedilir. Sonraki turda tool
            # mesaji tool_call_id'siz giderse uc nokta 400 veriyor; govdesi
            # olmayan sonuc da OpenAI spec'ine aykiri.
            # Arac CALISMADAN once bildir: kullanici bekledigi sureyi
            # gormeli, cekim bittikten sonra haber vermenin faydasi yok.
            await self._bildir(bildirim, [c.function.name for c in mesaj.tool_calls])

            govde = self._govde(mesaj.tool_calls)
            mesajlar.append(
                {"role": "assistant", "content": mesaj.content, "tool_calls": govde}
            )
            self._hafiza.arac_cagrisi_ekle(mesaj.content, govde)

            sonuclar = await self._araclari_calistir(mesaj.tool_calls)
            mesajlar.extend(sonuclar)
            for sonuc in sonuclar:
                self._hafiza.arac_sonucu_ekle(sonuc["tool_call_id"], sonuc["content"])
                kart = kart_ayikla(sonuc["content"])
                if kart and kart not in kartlar:
                    kartlar.append(kart)

            kayit.info("Tur %d: %d arac calistirildi", tur + 1, len(sonuclar))

        # Tur tavani asildi: elde ne varsa onunla cevapla, sonsuz donguye girme.
        kayit.warning("Tur tavani (%d) asildi", self._tur_tavani)
        son = await self._llm_cagir(
            model=self._ayarlar.nvidia_model,
            messages=[*mesajlar, {"role": "user", "content": TAVAN_MESAJI}],
            temperature=SICAKLIK,
        )
        cevap = cagri_kalintisini_temizle(son.choices[0].message.content or "") or (
            "Bu soru icin gereken veriyi toplayamadim."
        )
        self._hafiza.ekle("assistant", cevap)
        return self._kartla(kartlar, cevap)

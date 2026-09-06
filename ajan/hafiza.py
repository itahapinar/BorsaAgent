"""SQLite sohbet hafizasi.

Uc kural:
  1. Arac sonuclari diske YAZILIR (hangi cevap hangi veriye bakilarak
     uretildi, sonradan sorgulanabilsin) ama modele yalnizca SON TURUN
     sonucu geri gonderilir. Hepsini gondermek baglami tablolarla doldurup
     hafiza derinligini birkac tura dusuruyordu.
  2. Kirpma token bazlidir, mesaj sayisi bazli degil.
  3. gecmis() OpenAI uyumlu bir mesaj dizisi dondurur. Olculdu
     (integrate.api.nvidia.com): ciplak {"role": "tool"} satiri
     `400 missing field tool_call_id` aliyor. Plandaki tasarim tool
     sonuclarini boyle kaydediyordu, yani arac kullanan her sohbetin
     IKINCI sorusu kirilirdi.

     Ayni uc nokta tool_call_id'li ama govdesiz mesaji kabul ediyor;
     yine de araci cagiran assistant govdesi saklaniyor: OpenAI spec'i
     bunu sart kosuyor (baska model/uc noktalar reddedebilir) ve model
     hangi verinin hangi aractan geldigini ancak boyle goruyor. Govde ve
     sonuc BIRLIKTE durur, birlikte duser.
"""

import json
import sqlite3
import time
from pathlib import Path

# Turkce metinde karakter/token orani kabaca 3,2. Kesin tokenizer yerine
# bu tahmin kullaniliyor: amac butce tutmak, muhasebe yapmak degil.
KARAKTER_BASINA_TOKEN = 3.2


def kaba_token(metin: str) -> int:
    return int(len(metin) / KARAKTER_BASINA_TOKEN)


class Hafiza:
    def __init__(self, db_yolu: Path, tavan_token: int = 6000) -> None:
        self._tavan = tavan_token
        self._baglanti = sqlite3.connect(db_yolu, check_same_thread=False)
        self._baglanti.row_factory = sqlite3.Row
        self._baglanti.execute(
            "CREATE TABLE IF NOT EXISTS mesaj ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  rol TEXT NOT NULL,"
            "  icerik TEXT NOT NULL,"
            "  arac_sonucu INTEGER NOT NULL DEFAULT 0,"
            "  tur INTEGER NOT NULL DEFAULT 0,"
            "  ek TEXT,"            # tool_call_id ya da tool_calls govdesi (JSON)
            "  zaman REAL NOT NULL"
            ")"
        )
        self._baglanti.commit()

    # --- yazma -------------------------------------------------------------

    def _son_tur(self) -> int:
        satir = self._baglanti.execute("SELECT MAX(tur) AS t FROM mesaj").fetchone()
        return satir["t"] or 0

    def _yaz(self, rol: str, icerik: str, arac_sonucu: bool, ek: dict | None) -> None:
        tur = self._son_tur() + (1 if rol == "user" else 0)
        self._baglanti.execute(
            "INSERT INTO mesaj (rol, icerik, arac_sonucu, tur, ek, zaman)"
            " VALUES (?,?,?,?,?,?)",
            (
                rol,
                icerik,
                int(arac_sonucu),
                max(tur, 1),
                json.dumps(ek, ensure_ascii=False) if ek else None,
                time.time(),
            ),
        )
        self._baglanti.commit()

    def ekle(self, rol: str, icerik: str, arac_sonucu: bool = False) -> None:
        self._yaz(rol, icerik, arac_sonucu, None)

    def arac_cagrisi_ekle(self, icerik: str | None, cagrilar: list[dict]) -> None:
        """Modelin arac cagirdigi assistant mesajini kaydeder.

        Bu govde olmadan sonraki turda tool mesajlari sahipsiz kalir.
        """
        self._yaz("assistant", icerik or "", True, {"tool_calls": cagrilar})

    def arac_sonucu_ekle(self, cagri_id: str, icerik: str) -> None:
        self._yaz("tool", icerik, True, {"tool_call_id": cagri_id})

    # --- okuma -------------------------------------------------------------

    def ham_kayitlar(self) -> list[dict]:
        """Diskteki tum satirlar. Hata ayiklama icin; modele gitmez."""
        return [
            dict(s)
            for s in self._baglanti.execute("SELECT * FROM mesaj ORDER BY id").fetchall()
        ]

    def gecmis(self) -> list[dict]:
        """Modele gonderilecek mesaj listesi (eski -> yeni)."""
        son_tur = self._son_tur()
        satirlar = self._baglanti.execute(
            "SELECT rol, icerik, arac_sonucu, tur, ek FROM mesaj ORDER BY id"
        ).fetchall()

        secilen: list[dict] = []
        for s in satirlar:
            # Tur-bagimli satirlar: hem tool sonuclari hem onlari ureten
            # assistant govdesi. Ikisi birlikte durur ya da birlikte duser.
            if s["arac_sonucu"] and s["tur"] != son_tur:
                continue
            mesaj: dict = {"role": s["rol"], "content": s["icerik"]}
            ek = json.loads(s["ek"]) if s["ek"] else {}
            mesaj.update(ek)
            secilen.append(mesaj)

        return self._tutarli_kil(self._kirp(secilen))

    def _olcu(self, mesaj: dict) -> int:
        return kaba_token(mesaj.get("content") or "") + kaba_token(
            json.dumps(mesaj.get("tool_calls") or "", ensure_ascii=False)
        )

    def _kirp(self, mesajlar: list[dict]) -> list[dict]:
        """Tavani asinca en eski mesajlar duser; son mesaj her zaman kalir."""
        toplam = sum(self._olcu(m) for m in mesajlar)
        while len(mesajlar) > 1 and toplam > self._tavan:
            toplam -= self._olcu(mesajlar.pop(0))
        return mesajlar

    def _tutarli_kil(self, mesajlar: list[dict]) -> list[dict]:
        """Bastan kirpma bir tool mesajini govdesiz birakmis olabilir.

        Sahipsiz tool mesaji uc noktadan 400 aliyor; govdesi dusmusse
        sonucu da dusur.
        """
        while mesajlar and mesajlar[0]["role"] == "tool":
            mesajlar.pop(0)
        return mesajlar

    def sifirla(self) -> None:
        self._baglanti.execute("DELETE FROM mesaj")
        self._baglanti.commit()

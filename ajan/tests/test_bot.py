from ajan.bot import gonderen_id, mesaji_isle, yetkili_mi


class SahteAjan:
    def __init__(self, cevap):
        self._cevap = cevap
        self.sorulanlar = []

    async def cevapla(self, soru):
        self.sorulanlar.append(soru)
        return self._cevap


class SahteMesaj:
    def __init__(self, from_user):
        self.from_user = from_user


class SahteKullanici:
    def __init__(self, id):
        self.id = id


def test_admin_yetkili():
    assert yetkili_mi(42, 42)


def test_baskasi_yetkisiz():
    assert not yetkili_mi(99, 42)
    assert not yetkili_mi(None, 42)


def test_gondereni_olmayan_mesaj_cokmez():
    """Kanal gonderilerinde from_user None geliyor; .id dogrudan patlardi."""
    assert gonderen_id(SahteMesaj(None)) is None
    assert not yetkili_mi(gonderen_id(SahteMesaj(None)), 42)
    assert yetkili_mi(gonderen_id(SahteMesaj(SahteKullanici(42))), 42)


async def test_kisa_cevap_tek_parca():
    ajan = SahteAjan("THYAO 296,00 TL")
    assert await mesaji_isle(ajan, "THYAO kac TL?") == ["THYAO 296,00 TL"]
    assert ajan.sorulanlar == ["THYAO kac TL?"]


async def test_uzun_cevap_bolunur():
    ajan = SahteAjan("Cumle bir. " * 600)
    parcalar = await mesaji_isle(ajan, "uzun")
    assert len(parcalar) > 1
    assert all(len(p) <= 4096 for p in parcalar)


async def test_ajan_hatasi_kullaniciya_ham_gosterilmez():
    class PatlayanAjan:
        async def cevapla(self, soru):
            raise RuntimeError("nvapi-gizli-anahtar gecersiz")

    parcalar = await mesaji_isle(PatlayanAjan(), "soru")
    assert len(parcalar) == 1
    assert "nvapi" not in parcalar[0]
    assert "hata" in parcalar[0].lower()

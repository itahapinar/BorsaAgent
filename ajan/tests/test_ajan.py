import json
from dataclasses import dataclass

from ajan.ajan import Ajan
from ajan.config import Ayarlar
from ajan.hafiza import Hafiza


@dataclass
class SahteCagri:
    name: str
    arguments: str
    id: str = "cagri-1"

    @property
    def function(self):
        return self


@dataclass
class SahteMesaj:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class SahteSecim:
    message: SahteMesaj


@dataclass
class SahteYanit:
    choices: list


class SahteLLM:
    """Onceden belirlenmis yanitlari sirayla doner; cagrilari kaydeder."""

    def __init__(self, yanitlar):
        self._yanitlar = list(yanitlar)
        self.istekler = []

    async def create(self, **kwargs):
        self.istekler.append(kwargs)
        return self._yanitlar.pop(0)


class SahteMcp:
    def __init__(self):
        self.cagrilanlar = []

    async def arac_semalari(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "anlik_fiyat",
                    "description": "fiyat",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def cagir(self, ad, argumanlar):
        self.cagrilanlar.append((ad, argumanlar))
        return json.dumps({"fiyat": 296.0})


AYARLAR = Ayarlar(
    telegram_token="t",
    nvidia_api_key="k",
    admin_user_id=1,
    nvidia_model="test-model",
    nvidia_base_url="http://yok",
    log_seviyesi="INFO",
)


def _ajan(tmp_path, llm, mcp=None):
    ajan = Ajan(AYARLAR, mcp or SahteMcp(), Hafiza(tmp_path / "s.db"))
    ajan._llm_cagir = llm.create
    return ajan


def _fiyat_turu(cagri_id="cagri-1", cevap="THYAO 296,00 TL"):
    return [
        SahteYanit(
            [SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", '{"kod":"THYAO"}', id=cagri_id)]))]
        ),
        SahteYanit([SahteSecim(SahteMesaj(content=cevap))]),
    ]


async def test_aracsiz_soru_dogrudan_cevaplanir(tmp_path):
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="Merhaba!"))])])
    assert await _ajan(tmp_path, llm).cevapla("selam") == "Merhaba!"


async def test_arac_cagrisi_calistirilip_sonuc_modele_donuyor(tmp_path):
    llm = SahteLLM(_fiyat_turu())
    mcp = SahteMcp()
    cevap = await _ajan(tmp_path, llm, mcp).cevapla("THYAO kac TL?")

    assert cevap == "THYAO 296,00 TL"
    assert mcp.cagrilanlar == [("anlik_fiyat", {"kod": "THYAO"})]
    # Ikinci istekte arac sonucu modele gitmis olmali
    ikinci = llm.istekler[1]["messages"]
    assert any("296" in str(m.get("content", "")) for m in ikinci)


async def test_ayni_turdaki_cok_arac_calistirilir(tmp_path):
    cagrilar = [
        SahteCagri("anlik_fiyat", '{"kod":"THYAO"}', id="a"),
        SahteCagri("anlik_fiyat", '{"kod":"GARAN"}', id="b"),
    ]
    llm = SahteLLM(
        [
            SahteYanit([SahteSecim(SahteMesaj(tool_calls=cagrilar))]),
            SahteYanit([SahteSecim(SahteMesaj(content="ikisi de geldi"))]),
        ]
    )
    mcp = SahteMcp()
    await _ajan(tmp_path, llm, mcp).cevapla("THYAO ve GARAN")
    assert len(mcp.cagrilanlar) == 2


async def test_tur_tavani_asilinca_durur(tmp_path):
    """Model surekli arac isterse sonsuz donguye girmemeli."""
    sonsuz = [
        SahteYanit([SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", "{}")]))])
        for _ in range(10)
    ]
    llm = SahteLLM(sonsuz)
    cevap = await _ajan(tmp_path, llm).cevapla("dongu")
    assert "veri" in cevap.lower() or "tamamlanamadı" in cevap.lower()
    assert len(llm.istekler) <= 6, "tur tavani uygulanmadi"


async def test_bozuk_arac_argumani_cokmez(tmp_path):
    """Model gecersiz JSON uretirse dongu kirilmamali."""
    llm = SahteLLM(
        [
            SahteYanit(
                [SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", "{bozuk")]))]
            ),
            SahteYanit([SahteSecim(SahteMesaj(content="anlasildi"))]),
        ]
    )
    assert await _ajan(tmp_path, llm).cevapla("bozuk") == "anlasildi"


async def test_gecmis_hafizaya_yaziliyor(tmp_path):
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="cevap"))])])
    ajan = _ajan(tmp_path, llm)
    await ajan.cevapla("soru")
    roller = [m["role"] for m in ajan._hafiza.gecmis()]
    assert "user" in roller and "assistant" in roller


async def test_sistem_promptu_her_istekte_var(tmp_path):
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="ok"))])])
    await _ajan(tmp_path, llm).cevapla("soru")
    assert llm.istekler[0]["messages"][0]["role"] == "system"


# --- Task 4 + Task 6 dikisi ------------------------------------------------


async def test_ikinci_soruda_arac_verisi_tasinmaz(tmp_path):
    """Olculdu (canli bot): tur 17 MEKAG, tur 18'de "doas ..." soruldu ve
    model araci kod="MEKAG" ile cagirdi. Onceki turun dev arac ciktisi
    baglamda kaldigi icin ona demirlemisti.

    Ikinci turda gonderilen mesajlar hem API bicimine uymali hem de onceki
    turun arac verisini TASIMAMALI.
    """
    llm = SahteLLM(_fiyat_turu() + [SahteYanit([SahteSecim(SahteMesaj(content="dun de 296"))])])
    ajan = _ajan(tmp_path, llm)
    await ajan.cevapla("THYAO kac TL?")
    await ajan.cevapla("peki dun?")

    gonderilen = llm.istekler[-1]["messages"]
    assert all(m["role"] != "tool" for m in gonderilen), "arac verisi sizmis"
    assert all(not m.get("tool_calls") for m in gonderilen), "sahipsiz govde kalmis"
    assert any("peki dun?" in (m.get("content") or "") for m in gonderilen)


# --- Ozet kart yukseltme ---------------------------------------------------
# Olculdu: model dogru rakami dort ayri yerde gormesine ragmen temettu
# verimini "%0,0" yaziyordu. Uc yaklasim (prompt kurali, uyari notu, ozet
# blogu) tutmadi. Baslik rakamlari artik modelden GECMIYOR: arac sonucunda
# `ozet_kart` alani varsa ajan onu cevabin basina oldugu gibi ekler.
# Kural genel; ajan aracin ne yaptigini bilmez, yalnizca bu alan adini bilir.

KART = "| Son fiyat | 11,15 TL |\n| Temettü verimi | %1,84 |"


class KartliMcp(SahteMcp):
    async def cagir(self, ad, argumanlar):
        self.cagrilanlar.append((ad, argumanlar))
        return json.dumps({"kod": "GENKM", "ozet_kart": KART, "oranlar": {}})


async def test_ozet_kart_cevabin_basina_eklenir(tmp_path):
    llm = SahteLLM(_fiyat_turu(cevap="Şirket kimya sektöründe faaliyet gösteriyor."))
    cevap = await _ajan(tmp_path, llm, KartliMcp()).cevapla("GENKM detaylı analiz")
    assert cevap.startswith(KART)
    assert "kimya sektöründe" in cevap


async def test_kartsiz_arac_cevabi_degistirmez(tmp_path):
    llm = SahteLLM(_fiyat_turu(cevap="THYAO 296,00 TL"))
    assert await _ajan(tmp_path, llm, SahteMcp()).cevapla("THYAO") == "THYAO 296,00 TL"


async def test_ayni_kart_iki_kez_eklenmez(tmp_path):
    """Model araci iki kez cagirirsa kart tekrarlanmamali."""
    cagrilar = [
        SahteCagri("detayli_analiz", '{"kod":"GENKM"}', id="a"),
        SahteCagri("detayli_analiz", '{"kod":"GENKM"}', id="b"),
    ]
    llm = SahteLLM(
        [
            SahteYanit([SahteSecim(SahteMesaj(tool_calls=cagrilar))]),
            SahteYanit([SahteSecim(SahteMesaj(content="yorum"))]),
        ]
    )
    cevap = await _ajan(tmp_path, llm, KartliMcp()).cevapla("GENKM")
    assert cevap.count("Son fiyat") == 1


async def test_bozuk_json_sonucta_cokmez(tmp_path):
    class BozukMcp(SahteMcp):
        async def cagir(self, ad, argumanlar):
            self.cagrilanlar.append((ad, argumanlar))
            return "HATA: arac calistirilamadi"

    llm = SahteLLM(_fiyat_turu(cevap="veri alinamadi"))
    assert await _ajan(tmp_path, llm, BozukMcp()).cevapla("X") == "veri alinamadi"


async def test_dusuk_sicaklikla_cagriliyor(tmp_path):
    """Olculdu: model cumle ortasinda dil degistiriyor (Korece, Japonca,
    Arapca, Cince kelimeler). Rastgele jeton secimi bunun basli sebebi;
    varsayilan sicaklikla birakilmisti."""
    from ajan.ajan import SICAKLIK

    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content="ok"))])])
    await _ajan(tmp_path, llm).cevapla("soru")
    assert llm.istekler[0]["temperature"] == SICAKLIK
    assert SICAKLIK <= 0.4, "dil karismasi icin dusuk tutulmali"


async def test_tur_tavani_cagrisi_da_dusuk_sicaklikli(tmp_path):
    from ajan.ajan import SICAKLIK

    sonsuz = [
        SahteYanit([SahteSecim(SahteMesaj(tool_calls=[SahteCagri("anlik_fiyat", "{}")]))])
        for _ in range(10)
    ]
    llm = SahteLLM(sonsuz)
    await _ajan(tmp_path, llm).cevapla("dongu")
    assert llm.istekler[-1]["temperature"] == SICAKLIK


# --- Arac cagrisi kalintisi ------------------------------------------------
# Olculdu (DOAS): modelin ham arac cagrisi cevaba sizdi --
# '{\n  "kod": "DOAS",\n  "yil": 5\n</tool_call' cevabin basinda goründu.
# Araliklı: sonraki kosuda temizdi. Olabildigine gore temizleniyor.

from ajan.ajan import cagri_kalintisini_temizle  # noqa: E402


def test_normal_cevap_degismez():
    assert cagri_kalintisini_temizle("THYAO 296,00 TL") == "THYAO 296,00 TL"


def test_tam_arac_blogu_atilir():
    ham = '<tool_call>{"kod": "DOAS"}</tool_call>\nDOAS temettüleri şöyle:'
    assert cagri_kalintisini_temizle(ham) == "DOAS temettüleri şöyle:"


def test_acilissiz_kapanista_onceki_json_da_atilir():
    ham = '{\n  "kod": "DOAS",\n  "yil": 5\n</tool_call>\nDOAS – Temettü Ödemeleri'
    assert cagri_kalintisini_temizle(ham) == "DOAS – Temettü Ödemeleri"


def test_kapanis_isareti_eksik_olsa_da_temizlenir():
    ham = '{"kod": "DOAS"\n</tool_call\nCevap metni'
    assert cagri_kalintisini_temizle(ham) == "Cevap metni"


def test_basibos_etiket_silinir():
    assert cagri_kalintisini_temizle("Cevap <tool_call> devam") == "Cevap  devam"


async def test_cevapta_kalinti_kalmaz(tmp_path):
    kirli = '{"kod": "DOAS"\n</tool_call>\nDOAS temettü tablosu'
    llm = SahteLLM([SahteYanit([SahteSecim(SahteMesaj(content=kirli))])])
    assert await _ajan(tmp_path, llm).cevapla("DOAS") == "DOAS temettü tablosu"


# --- Durum bildirimi -------------------------------------------------------
# Kullanici veri cekilirken hicbir geri bildirim gormuyordu.


async def test_arac_calismadan_once_bildirim_gonderilir(tmp_path):
    bildirilen = []

    async def bildirim(adlar):
        bildirilen.append(list(adlar))

    llm = SahteLLM(_fiyat_turu())
    ajan = _ajan(tmp_path, llm, SahteMcp())
    await ajan.cevapla("THYAO kac TL?", bildirim=bildirim)
    assert bildirilen == [["anlik_fiyat"]]


async def test_bildirim_verilmezse_calismaya_devam_eder(tmp_path):
    llm = SahteLLM(_fiyat_turu())
    assert await _ajan(tmp_path, llm).cevapla("THYAO") == "THYAO 296,00 TL"


async def test_bildirim_hatasi_cevabi_dusurmez(tmp_path):
    """Telegram duzenleme hatasi yuzunden cevap kaybolmamali."""

    async def patlayan(adlar):
        raise RuntimeError("telegram hatasi")

    llm = SahteLLM(_fiyat_turu())
    cevap = await _ajan(tmp_path, llm).cevapla("THYAO", bildirim=patlayan)
    assert cevap == "THYAO 296,00 TL"


# --- Hisse kimligi basligi -------------------------------------------------
# Olculdu (canli bot): "asels hacim" cevabi yalnizca "Gun | Hacim" tablosu
# oldu, hangi hisse oldugu yazmadi. Prompt kurali 16 var ama model uymuyor.
# Ozet kartinda oldugu gibi kimlik de KODDA ekleniyor.


class KimlikliMcp(SahteMcp):
    def __init__(self, veri):
        super().__init__()
        self._veri = veri

    async def cagir(self, ad, argumanlar):
        self.cagrilanlar.append((ad, argumanlar))
        return json.dumps(self._veri)


async def test_tek_hissede_kimlik_basligi_eklenir(tmp_path):
    mcp = KimlikliMcp({"kod": "ASELS", "unvan": "ASELSAN A.Ş.", "hacim": 5})
    llm = SahteLLM(_fiyat_turu(cevap="Hacim 21,18 milyon."))
    cevap = await _ajan(tmp_path, llm, mcp).cevapla("asels hacim")
    assert cevap.startswith("**ASELS — ASELSAN A.Ş.**")
    assert "21,18 milyon" in cevap


async def test_unvan_yoksa_kod_yazilir(tmp_path):
    mcp = KimlikliMcp({"kod": "ASELS", "hacim": 5})
    llm = SahteLLM(_fiyat_turu(cevap="Hacim 21,18 milyon."))
    assert (await _ajan(tmp_path, llm, mcp).cevapla("asels hacim")).startswith("**ASELS**")


async def test_ozet_karti_varsa_kimlik_tekrarlanmaz(tmp_path):
    mcp = KimlikliMcp({"kod": "ASELS", "unvan": "ASELSAN A.Ş.", "ozet_kart": KART})
    llm = SahteLLM(_fiyat_turu(cevap="yorum"))
    cevap = await _ajan(tmp_path, llm, mcp).cevapla("asels analiz")
    assert cevap.count("ASELS") <= 1
    assert cevap.startswith(KART)


async def test_kodsuz_sonucta_baslik_eklenmez(tmp_path):
    mcp = KimlikliMcp({"endeks": "XU100", "deger": 12345})
    llm = SahteLLM(_fiyat_turu(cevap="BIST 100 12.345 puan."))
    assert await _ajan(tmp_path, llm, mcp).cevapla("bist 100") == "BIST 100 12.345 puan."


async def test_birden_fazla_hissede_baslik_eklenmez(tmp_path):
    """Karsilastirma ve taramada tek bir hisse adi yazmak yanlis olurdu."""

    class CokluMcp(SahteMcp):
        async def cagir(self, ad, argumanlar):
            self.cagrilanlar.append((ad, argumanlar))
            return json.dumps({"kod": argumanlar.get("kod", "X"), "unvan": "Bir A.Ş."})

    cagrilar = [
        SahteCagri("anlik_fiyat", '{"kod":"THYAO"}', id="a"),
        SahteCagri("anlik_fiyat", '{"kod":"ASELS"}', id="b"),
    ]
    llm = SahteLLM(
        [
            SahteYanit([SahteSecim(SahteMesaj(tool_calls=cagrilar))]),
            SahteYanit([SahteSecim(SahteMesaj(content="İkisi de geldi."))]),
        ]
    )
    assert await _ajan(tmp_path, llm, CokluMcp()).cevapla("karşılaştır") == "İkisi de geldi."

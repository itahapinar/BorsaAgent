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


async def test_ikinci_soruda_gonderilen_mesajlar_api_gecerli(tmp_path):
    """Ilk turda arac kullanildiysa ikinci soru kirilmamali.

    Olculdu: ciplak {"role": "tool"} satiri uc noktadan
    `400 missing field tool_call_id` aliyor. Arac cagrisi hafizaya
    tool_call_id ve assistant govdesiyle yazilmazsa arac kullanan her
    sohbetin ikinci sorusu patlardi.
    """
    llm = SahteLLM(_fiyat_turu() + [SahteYanit([SahteSecim(SahteMesaj(content="dun de 296"))])])
    ajan = _ajan(tmp_path, llm)
    await ajan.cevapla("THYAO kac TL?")
    await ajan.cevapla("peki dun?")

    gonderilen = llm.istekler[-1]["messages"]
    acik: set[str] = set()
    for m in gonderilen:
        if m["role"] == "assistant" and m.get("tool_calls"):
            acik = {c["id"] for c in m["tool_calls"]}
        elif m["role"] == "tool":
            assert m.get("tool_call_id"), f"tool_call_id yok: {m}"
            assert m["tool_call_id"] in acik, f"sahipsiz tool mesaji: {m}"
    assert any(m["role"] == "tool" for m in gonderilen), "arac verisi ikinci tura tasinmadi"

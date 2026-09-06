import json

from ajan.hafiza import Hafiza, kaba_token


def test_kaba_token_karakterden_tahmin_eder():
    assert kaba_token("a" * 320) == 100


def test_eklenen_mesajlar_sirayla_doner(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    hafiza.ekle("user", "THYAO kac TL?")
    hafiza.ekle("assistant", "296,00 TL")
    assert [m["content"] for m in hafiza.gecmis()] == ["THYAO kac TL?", "296,00 TL"]


def test_yeniden_acilinca_gecmis_kaybolmaz(tmp_path):
    yol = tmp_path / "s.db"
    Hafiza(yol).ekle("user", "merhaba")
    assert len(Hafiza(yol).gecmis()) == 1


def test_sifirla_gecmisi_temizler(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    hafiza.ekle("user", "merhaba")
    hafiza.sifirla()
    assert hafiza.gecmis() == []


def _tur_yaz(hafiza, soru, cagri_id, arac_metni, cevap):
    """Bir soru-arac-cevap turunu ajan.py'nin yazacagi gibi kaydeder."""
    hafiza.ekle("user", soru)
    hafiza.arac_cagrisi_ekle(
        None,
        [{"id": cagri_id, "type": "function",
          "function": {"name": "finansal_tablo", "arguments": "{}"}}],
    )
    hafiza.arac_sonucu_ekle(cagri_id, arac_metni)
    hafiza.ekle("assistant", cevap)


def test_tavan_asilinca_en_eski_mesajlar_duser(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db", tavan_token=100)
    hafiza.ekle("user", "ILK MESAJ")
    for i in range(20):
        hafiza.ekle("assistant", "dolgu " * 20)
    icerikler = [m["content"] for m in hafiza.gecmis()]
    assert "ILK MESAJ" not in icerikler
    assert icerikler, "hepsi dusmemeli"


def test_son_mesaj_tavandan_buyuk_olsa_bile_kalir(tmp_path):
    """Tek bir dev mesaj yuzunden baglam tamamen bosalmamali."""
    hafiza = Hafiza(tmp_path / "s.db", tavan_token=10)
    hafiza.ekle("user", "x" * 10_000)
    assert len(hafiza.gecmis()) == 1


# --- API gecerliligi -------------------------------------------------------
# Olculdu (integrate.api.nvidia.com): ciplak {"role": "tool"} satiri
# `400 missing field tool_call_id` aliyor; plandaki tasarim boyle kaydediyordu,
# yani arac kullanan her sohbetin ikinci sorusu kirilirdi.
#
# Sahipsiz tool mesajini (id var, govde yok) bu uc nokta kabul ediyor ama
# OpenAI spec'i sart kosuyor ve model hangi verinin hangi aractan geldigini
# ancak govdeyle goruyor; asagidaki kontrol o daha siki kurali uyguluyor.


def _gecerli_mi(mesajlar: list[dict]) -> None:
    acik: set[str] = set()
    for m in mesajlar:
        if m["role"] == "assistant" and m.get("tool_calls"):
            acik = {c["id"] for c in m["tool_calls"]}
        elif m["role"] == "tool":
            assert m.get("tool_call_id"), f"tool_call_id yok: {m}"
            assert m["tool_call_id"] in acik, f"sahipsiz tool mesaji: {m}"


def test_gecmis_api_bicimine_uyar(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    _tur_yaz(hafiza, "GARAN bilanco", "c1", "TABLO", "iste bilanco")
    _tur_yaz(hafiza, "ozkaynak?", "c2", "TABLO2", "su kadar")
    _gecerli_mi(hafiza.gecmis())


def test_kirpma_sahipsiz_tool_mesaji_birakmaz(tmp_path):
    """Tavan cok dusukse kirpma govdeyi yiyip tool mesajini birakabilirdi."""
    hafiza = Hafiza(tmp_path / "s.db", tavan_token=1)
    _tur_yaz(hafiza, "GARAN bilanco", "c1", "T" * 5000, "cevap")
    _gecerli_mi(hafiza.gecmis())


def test_arac_sonuclari_diskte_kalir(tmp_path):
    """Modele gitmese de hata ayiklama icin saklanmali."""
    hafiza = Hafiza(tmp_path / "s.db")
    _tur_yaz(hafiza, "GARAN bilanco", "c1", "ESKI TABLO", "cevap1")
    _tur_yaz(hafiza, "ozkaynak?", "c2", "YENI TABLO", "cevap2")
    assert "ESKI TABLO" in [s["icerik"] for s in hafiza.ham_kayitlar()]


def test_kapatilan_hafizanin_dosyasi_silinebilir(tmp_path):
    """Windows acik SQLite baglantisindaki dosyayi kilitliyor."""
    yol = tmp_path / "s.db"
    hafiza = Hafiza(yol)
    hafiza.ekle("user", "merhaba")
    hafiza.kapat()
    yol.unlink()
    assert not yol.exists()


# --- Turlar arasi arac verisi ----------------------------------------------
# Olculdu (canli bot, sohbet.db): tur 17'de "mekag detayli analiz" soruldu,
# tur 18'de "doas 2025 ve 2026 yili temettu tarihleri" soruldu ve model
# araci kod="MEKAG" ile cagirdi. Onceki turun dev arac ciktisi baglamda
# durdugu icin model ona demirledi ve YANLIS SIRKETIN verisini verdi.
# Bir finans botunda bu, fazladan bir arac cagrisindan cok daha agir.


def test_onceki_turun_arac_verisi_baglama_tasinmaz(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    _tur_yaz(hafiza, "mekag detaylı analiz", "c1", "MEKAG TABLOSU", "MEKAG analizi")
    hafiza.ekle("user", "doas temettü tarihleri")

    icerikler = [m.get("content") or "" for m in hafiza.gecmis()]
    assert not any("MEKAG TABLOSU" in i for i in icerikler), "arac verisi sizmis"
    assert any("MEKAG analizi" in i for i in icerikler), "asistan cevabi kalmali"


def test_ayni_turda_bile_arac_verisi_gecmise_girmez(tmp_path):
    """Tur icinde arac sonucu zaten ucus halindeki mesaj listesinde."""
    hafiza = Hafiza(tmp_path / "s.db")
    _tur_yaz(hafiza, "GARAN bilanço", "c1", "TABLO", "cevap")
    assert all(m["role"] != "tool" for m in hafiza.gecmis())
    assert all(not m.get("tool_calls") for m in hafiza.gecmis())


def test_arac_verisi_diskte_kalmaya_devam_eder(tmp_path):
    hafiza = Hafiza(tmp_path / "s.db")
    _tur_yaz(hafiza, "GARAN bilanço", "c1", "TABLO", "cevap")
    assert "TABLO" in [s["icerik"] for s in hafiza.ham_kayitlar()]

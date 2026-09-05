import datetime as dt

import pytest

from ajan.config import TRT, ayarlari_yukle, simdi_trt

TAM_CEVRE = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "NVIDIA_API_KEY": "nvapi-xxx",
    "ADMIN_USER_ID": "42",
}


def test_zorunlu_alanlar_okunur():
    ayarlar = ayarlari_yukle(TAM_CEVRE)
    assert ayarlar.telegram_token == "123:abc"
    assert ayarlar.admin_user_id == 42


def test_varsayilanlar_dolduruluyor():
    ayarlar = ayarlari_yukle(TAM_CEVRE)
    assert ayarlar.nvidia_base_url == "https://integrate.api.nvidia.com/v1"
    assert ayarlar.log_seviyesi == "INFO"


def test_eksik_zorunlu_alan_net_hata_verir():
    eksik = dict(TAM_CEVRE)
    del eksik["TELEGRAM_BOT_TOKEN"]
    with pytest.raises(ValueError) as hata:
        ayarlari_yukle(eksik)
    assert "TELEGRAM_BOT_TOKEN" in str(hata.value)


def test_admin_id_sayi_degilse_hata():
    with pytest.raises(ValueError) as hata:
        ayarlari_yukle(dict(TAM_CEVRE, ADMIN_USER_ID="abc"))
    assert "ADMIN_USER_ID" in str(hata.value)


def test_trt_sabit_uc_saat():
    """Turkiye yaz saati uygulamiyor; sabit UTC+3."""
    assert TRT.utcoffset(None) == dt.timedelta(hours=3)


def test_simdi_trt_dogru_dilimde():
    assert simdi_trt().tzinfo == TRT


def test_ayarlar_repr_sirri_sizdirmaz():
    """Log'a ya da hata mesajina dusen repr anahtari acmamali."""
    metin = repr(ayarlari_yukle(TAM_CEVRE))
    assert "nvapi-xxx" not in metin
    assert "123:abc" not in metin

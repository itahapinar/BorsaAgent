import pytest

from bist_mcp.kaynaklar.kap import KapIstemci, bildirim_sadelestir
from bist_mcp.onbellek import Onbellek

HAM_BILDIRIM = {
    "publishDate": "03.09.2026 18:15:48",
    "disclosureClass": "ODA",
    "subject": "Yönetim Kurulu Komiteleri",
    "summary": "Kredi Komitesi Üye Değişikliği",
    "stockCodes": "GARAN, TGB",
    "disclosureIndex": "1301003",
    "attachmentCount": 0,
    "kapTitle": "TÜRKİYE GARANTİ BANKASI A.Ş.",
    "isOldKap": False,
    "ruleType": "X",
}


async def _patlayan():
    raise AssertionError("onbellek doluyken aga cikilmamaliydi")


def test_bildirim_sadelestirme_gerekli_alanlari_tutar():
    sade = bildirim_sadelestir(HAM_BILDIRIM)
    assert sade == {
        "tarih": "03.09.2026 18:15:48",
        "konu": "Yönetim Kurulu Komiteleri",
        "ozet": "Kredi Komitesi Üye Değişikliği",
        "sinif": "ODA",
        "bildirim_no": "1301003",
        "ek_sayisi": 0,
    }


def test_bildirim_sadelestirme_bos_ozeti_atlar():
    ham = dict(HAM_BILDIRIM, summary=None)
    assert bildirim_sadelestir(ham)["ozet"] is None


@pytest.mark.asyncio
async def test_dizin_onbellekten_okunur_ag_beklenmez(tmp_path):
    """Dizin onbellekteyse istemci aga cikmaz."""
    onbellek = Onbellek(tmp_path / "t.db")
    onbellek.yaz(
        "kap:sirket_listesi",
        [
            {
                "stockCode": "ASELS",
                "kapMemberTitle": "ASELSAN",
                "mkkMemberOid": "oid1",
                "financialType": "SIR",
            }
        ],
        ttl_saniye=600,
    )

    istemci = KapIstemci(onbellek)
    istemci._ham_sirket_listesi_getir = _patlayan  # aga cikarsa test kirilir

    dizin = await istemci.sirket_dizini()
    assert dizin["ASELS"].mkk_oid == "oid1"

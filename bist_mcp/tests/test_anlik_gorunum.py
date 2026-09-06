from bist_mcp.anlik_gorunum import AnlikGorunum, satir_hesapla

TEMEL = {
    "kod": "THYAO",
    "unvan": "TÜRK HAVA YOLLARI A.O.",
    "sektor": "Industrials",
    "hisse_adedi": 1_372_283_353,
    "ozkaynak_tl": 1_073_081_134_047,
    "net_kar_tl": 139_092_773_392,
}


def _gorunum(tmp_path):
    return AnlikGorunum(tmp_path / "g.db", kap=None, isyatirim=None, fiyat=None)


def test_satir_hesaplama_oranlari_tl_bazinda_uretir():
    satir = satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0)
    assert round(satir["pddd"], 2) == 0.38
    assert 2.0 < satir["fk"] < 4.0
    assert satir["temettu_verimi"] == 0.0


def test_eksik_ozkaynakta_oranlar_none_ama_satir_uretilir():
    eksik = dict(TEMEL, ozkaynak_tl=None)
    satir = satir_hesapla(eksik, fiyat=296.00, temettu_12ay=0.0)
    assert satir["pddd"] is None
    assert satir["kod"] == "THYAO"
    assert satir["fiyat"] == 296.00


def test_tabloya_yazilan_satir_geri_okunur(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0))
    okunan = gorunum.satirlari_sec()
    assert len(okunan) == 1
    assert okunan[0]["kod"] == "THYAO"


def test_fk_ustsiniri_filtreler(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0))  # F/K ~2,9
    pahali = dict(TEMEL, kod="XXXXX", net_kar_tl=1_000_000_000)  # F/K ~406
    gorunum.satir_yaz(satir_hesapla(pahali, fiyat=296.00, temettu_12ay=0.0))

    assert [s["kod"] for s in gorunum.satirlari_sec(fk_max=10)] == ["THYAO"]


def test_temettu_verimi_altsiniri_filtreler(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0))
    temettulu = dict(TEMEL, kod="GARAN")
    gorunum.satir_yaz(satir_hesapla(temettulu, fiyat=131.40, temettu_12ay=5.266887))

    assert [s["kod"] for s in gorunum.satirlari_sec(temettu_verimi_min=3.0)] == ["GARAN"]


def test_oranı_none_olan_hisse_filtreye_takilmaz(tmp_path):
    """Ozkaynagi bilinmeyen hisse 'F/K < 10' sonucuna sizmamali."""
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(dict(TEMEL, kod="BOSVE", net_kar_tl=None), 100.0, 0.0))
    assert gorunum.satirlari_sec(fk_max=10) == []


def test_sektore_gore_filtreler(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, 296.00, 0.0))
    gorunum.satir_yaz(
        satir_hesapla(dict(TEMEL, kod="GARAN", sektor="Financial Services"), 131.40, 5.27)
    )
    assert [s["kod"] for s in gorunum.satirlari_sec(sektor="Industrials")] == ["THYAO"]


def test_bos_tabloda_yas_none(tmp_path):
    assert _gorunum(tmp_path).yas_saat() is None


def test_dolu_tabloda_yas_sifira_yakin(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, 296.00, 0.0))
    assert gorunum.yas_saat() < 0.1


# --- Likidite: olu hisseler taramaya sizmamali ---


def test_hacim_alt_siniri_olu_hisseleri_eler(tmp_path):
    """Evren BIST geneli oldugu icin gunde birkac lot islem goren kabuk
    sirketler var; F/K'si dusuk diye listenin basina cikip alinamiyorlar.
    """
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, 296.00, 0.0, ortalama_hacim_tl=16_000_000_000))
    olu = dict(TEMEL, kod="OLUHS", net_kar_tl=1_000_000)  # cok dusuk F/K
    gorunum.satir_yaz(satir_hesapla(olu, 1.00, 0.0, ortalama_hacim_tl=12_000))

    hepsi = [s["kod"] for s in gorunum.satirlari_sec(fk_max=100000)]
    assert "OLUHS" in hepsi, "filtresiz taramada olu hisse gorunmeli"

    likit = [s["kod"] for s in gorunum.satirlari_sec(fk_max=100000, hacim_min=10_000_000)]
    assert likit == ["THYAO"]


def test_hacmi_bilinmeyen_hisse_hacim_filtresine_takilmaz(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, 296.00, 0.0, ortalama_hacim_tl=None))
    assert gorunum.satirlari_sec(hacim_min=1_000) == []


def test_hacim_sutunu_yaziliyor_ve_okunuyor(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, 296.00, 0.0, ortalama_hacim_tl=16_054_600_000))
    assert gorunum.satirlari_sec()[0]["ortalama_hacim_tl"] == 16_054_600_000


def test_hacme_gore_siralanabilir(tmp_path):
    gorunum = _gorunum(tmp_path)
    gorunum.satir_yaz(satir_hesapla(TEMEL, 296.00, 0.0, ortalama_hacim_tl=1_000))
    gorunum.satir_yaz(
        satir_hesapla(dict(TEMEL, kod="LIKIT"), 100.0, 0.0, ortalama_hacim_tl=9_000_000)
    )
    sonuc = gorunum.satirlari_sec(sirala="ortalama_hacim_tl")
    assert sonuc[0]["kod"] == "LIKIT"


# --- Sema gocu -------------------------------------------------------------
# Olculdu: diskteki gorunum.db hacim sutunu eklenmeden once yaratilmisti ve
# "no column named ortalama_hacim_tl" hatasi veriyordu. CREATE TABLE IF NOT
# EXISTS mevcut tabloya sutun EKLEMEZ; eski veritabani sessizce bozuk kalir
# ve hisse_tarama'nin yazmasi kirilir.

ESKI_SEMA = (
    "CREATE TABLE gorunum ("
    "  kod TEXT PRIMARY KEY, unvan TEXT, sektor TEXT,"
    "  hisse_adedi INTEGER, ozkaynak_tl REAL, net_kar_tl REAL,"
    "  fiyat REAL, temettu_12ay REAL, pddd REAL, fk REAL,"
    "  piyasa_degeri REAL, temettu_verimi REAL, guncelleme REAL"
    ")"
)


def _eski_veritabani(yol):
    import sqlite3

    baglanti = sqlite3.connect(yol)
    baglanti.execute(ESKI_SEMA)
    baglanti.execute(
        "INSERT INTO gorunum (kod, unvan, fiyat) VALUES ('THYAO', 'THY', 296.0)"
    )
    baglanti.commit()
    baglanti.close()


def test_eski_veritabanina_eksik_sutun_eklenir(tmp_path):
    yol = tmp_path / "g.db"
    _eski_veritabani(yol)

    gorunum = AnlikGorunum(yol, kap=None, isyatirim=None, fiyat=None)
    gorunum.satir_yaz(satir_hesapla(TEMEL, fiyat=296.00, temettu_12ay=0.0, ortalama_hacim_tl=1e9))

    satirlar = gorunum.satirlari_sec(hacim_min=1e8)
    assert [s["kod"] for s in satirlar] == ["THYAO"]


def test_gocte_mevcut_veri_korunur(tmp_path):
    yol = tmp_path / "g.db"
    _eski_veritabani(yol)

    gorunum = AnlikGorunum(yol, kap=None, isyatirim=None, fiyat=None)
    kayit = gorunum._baglanti.execute(
        "SELECT unvan, fiyat FROM gorunum WHERE kod = 'THYAO'"
    ).fetchone()
    assert kayit["unvan"] == "THY"
    assert kayit["fiyat"] == 296.0

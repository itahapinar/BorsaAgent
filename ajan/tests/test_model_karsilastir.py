from ajan.model_karsilastir import SORULAR, aday_modelleri_sec, isabet_hesapla


def test_yirmi_soru_var():
    assert len(SORULAR) == 20


def test_her_soru_bir_arac_bekliyor():
    for soru, beklenen in SORULAR:
        assert soru.strip()
        assert beklenen.strip()


def test_sorular_araclarin_cogunu_kapsiyor():
    """Az sayida araci olcen bir test yaniltici bir skor uretir."""
    kapsanan = {beklenen for _, beklenen in SORULAR}
    assert len(kapsanan) >= 12


def test_beklenen_araclar_gercekten_var():
    """Sunucuda olmayan bir arac adi beklersek skor hep dusuk cikardi."""
    from bist_mcp.sunucu import sunucu  # noqa: PLC0415

    assert {beklenen for _, beklenen in SORULAR} <= set(sunucu._tool_manager._tools)


def test_aday_secimi_tool_calling_modellerini_bulur():
    kimlikler = [
        "nvidia/nemotron-3-super-120b-a12b",
        "zai/glm-5.1",
        "moonshotai/kimi-k2.5",
        "stabilityai/sdxl-turbo",
        "nvidia/embed-qa-4",
    ]
    adaylar = aday_modelleri_sec(kimlikler)
    assert "nvidia/nemotron-3-super-120b-a12b" in adaylar
    assert "zai/glm-5.1" in adaylar
    assert "stabilityai/sdxl-turbo" not in adaylar
    assert "nvidia/embed-qa-4" not in adaylar


def test_isabet_yuzdesi():
    assert isabet_hesapla([True] * 18 + [False] * 2) == 90.0
    assert isabet_hesapla([]) == 0.0

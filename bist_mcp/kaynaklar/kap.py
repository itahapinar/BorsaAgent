"""KAP (Kamuyu Aydinlatma Platformu) kaynagi.

Sirket dizini, bildirim sorgusu ve bildirim detayi.
"""

from dataclasses import dataclass

# KAP financialType kodlari: banka, sigorta, finansal kiralama/faktoring,
# katilim bankasi. Bunlar BDDK formatinda raporlar -> UFRS_K.
BANKA_TIPLERI = frozenset({"BNK", "SIG", "FFF", "KTL"})


@dataclass(frozen=True)
class Sirket:
    kod: str
    unvan: str
    mkk_oid: str
    tip: str | None


def dizin_kur(ham: list[dict]) -> dict[str, Sirket]:
    """KAP sirket listesini ticker -> Sirket sozlugune cevirir.

    `stockCode` alani virgulle ayrilmis birden fazla kod tutabilir; GARAN'in
    degeri "GARAN, TGB". Tam eslesme aramak bankalarin cogunu kaybettirir,
    bu yuzden alan virgulle bolunup her kod ayri anahtar yapilir.
    Olculen sonuc: 757 sirket -> 807 ticker.
    """
    dizin: dict[str, Sirket] = {}

    for kayit in ham:
        ham_kod = (kayit.get("stockCode") or "").strip()
        if not ham_kod or ham_kod == "-":
            continue

        unvan = (kayit.get("kapMemberTitle") or "").strip()
        oid = kayit.get("mkkMemberOid") or ""
        tip = kayit.get("financialType") or None

        for parca in ham_kod.split(","):
            kod = parca.strip()
            if kod and kod != "-":
                dizin[kod] = Sirket(kod=kod, unvan=unvan, mkk_oid=oid, tip=tip)

    return dizin


def tablo_grubu_sec(tip: str | None) -> str:
    """Sirket tipinden Is Yatirim financialGroup parametresini secer.

    Tip bos olabilir (807 ticker'in 315'i); o durumda XI_29 denenir ve
    bos donerse cagiran taraf yedek_grup() ile digerini dener.
    """
    return "UFRS_K" if tip in BANKA_TIPLERI else "XI_29"


def yedek_grup(grup: str) -> str:
    return "XI_29" if grup == "UFRS_K" else "UFRS_K"

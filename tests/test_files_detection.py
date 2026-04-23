from app.utils.files import detect_parser


def test_detect_parser_basic():
    assert detect_parser("ALLIANZ CTA CTE 2026-03.xlsx") == "allianz"
    assert detect_parser("ANDINA ART CTA CTE MARZO 2026.xls") == "andina_art"
    assert detect_parser("ASOCIART CTA CTE.xlsx") == "asociart"
    assert detect_parser("SMG CTA CTE.xlsx") == "smg"
    assert detect_parser("SMG ART CTA CTE.xlsx") == "smg_art"
    assert detect_parser("SMG LIFE CTA CTE.xlsx") == "smg_life"


def test_detect_parser_longer_match_wins():
    # SMG ART debe elegirse por sobre SMG
    assert detect_parser("SMG ART CTA CTE MARZO 2026.xlsx") == "smg_art"
    # SAN CRISTOBAL USD debe elegirse por sobre SAN CRISTOBAL
    assert detect_parser("SAN CRISTOBAL USD CTA CTE 2026-03.xlsx") == "san_cristobal_usd"
    assert detect_parser("LA MERCANTIL ANDINA USD CTA CTE 2026-03.xlsx") == "mercantil_andina_usd"


def test_detect_parser_unknown():
    assert detect_parser("INFORME_GENERAL_2026.xlsx") is None
    assert detect_parser("random.pdf") is None


def test_detect_parser_pdfs():
    assert detect_parser("LIBRA CTA CTE MARZO 2026.pdf") == "libra_pdf"
    assert detect_parser("VICTORIA ART CTA CTE MARZO 2026.pdf") == "victoria_art_pdf"

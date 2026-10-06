from oripa.pricing import card_pt, round_pt


def test_round_pt_matches_sheet_rule():
    # 端数 ≤500 → 500、>500 → 次の1000（構築シートの LET 式と同じ）
    assert round_pt(347_655) == 348_000
    assert round_pt(194_048.53) == 194_500
    assert round_pt(1_470) == 1_500
    assert round_pt(2_500) == 2_500
    assert round_pt(2_501) == 3_000
    # 端数0のときもシートの式どおり +500 になる
    assert round_pt(3_000) == 3_500


def test_card_pt_with_fee_and_markup():
    assert card_pt(236_500, 1.05, 1.4) == 348_000
    assert card_pt(39_780, 1.05, 1.3) == 54_500
    assert card_pt(201_500, 1.03, 1.25) == 259_500


def test_card_pt_has_no_float_error_on_boundary():
    # 1000 × 1.05 × 1.4 = 1470 ちょうど（浮動小数だと 1470.0000000000002 になる）
    assert card_pt(1_000, 1.05, 1.4) == 1_500
    # 30,000 × 1.05 × 1.3 = 40,950 → 41,000
    assert card_pt(30_000, 1.05, 1.3) == 41_000

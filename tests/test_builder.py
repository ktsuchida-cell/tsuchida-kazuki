from pathlib import Path

import pytest

from oripa import Card, Filler, PackConfig, PackError, build_pack, load_config

EXAMPLES = Path(__file__).resolve().parent.parent / "packs" / "examples"


def test_reproduces_sheet_1_in_4():
    m = build_pack(load_config(EXAMPLES / "ad_1in4_1000pt.toml")).metrics
    assert m.total_pt == 10_000_000
    assert m.build_pt == 9_888_500
    assert m.return_rate == pytest.approx(0.98885)
    assert m.diff == 111_500
    assert m.ship_only_profit == 207_501
    assert m.expected_charge == 647_000
    assert m.after_coupon == pytest.approx(627_590)
    assert m.est_profit == pytest.approx(299_591)
    assert m.margin == pytest.approx(0.4773673895)


def test_reproduces_sheet_26():
    m = build_pack(load_config(EXAMPLES / "pikachu_240.toml")).metrics
    assert m.build_pt == 4_663_500
    assert m.return_rate == pytest.approx(0.9715625)
    assert m.ship_only_profit == pytest.approx(145_040)
    assert m.expected_charge == 451_500
    assert m.est_profit == pytest.approx(267_995)
    assert m.ad_odds == pytest.approx(10.0)


def test_reproduces_sheet_1100_with_card_markup_override():
    # シート「1/100 高額2つ」: かんこうきゃく だけ S爆 でも掛け率 1.3
    cards = [
        Card("S爆", "ブラッキーvmax", 718_800),
        Card("S爆", "アクア団のカイオーガEX", 342_000),
        Card("S爆", "かんこうきゃく", 200_005, markup=1.3),
        Card("S爆", "ミュウvmax", 182_999),
        Card("S", "ピカチュウ", 57_000),
        Card("S", "ミュウツーgx", 52_999),
        Card("S", "ゲッコウガex", 47_800),
        Card("S", "ミュウ ふしぎなしっぽ", 46_999),
        Card("S", "リザードン", 46_500),
        Card("S", "ニンフィアv", 45_000),
    ]
    fillers = [Filler("A", 100_000, 290), Filler("C", 1, "rest")]
    result = build_pack(PackConfig("1/100 高額2つ", 1100, 30_000, cards, fillers))
    assert [line.pt for line in result.card_lines[:4]] == [1_057_000, 503_000, 273_500, 269_500]
    assert result.filler_lines[1].count == 29_700
    m = result.metrics
    assert m.build_pt == 31_538_200
    assert m.ship_only_profit == 659_196
    assert m.est_profit == pytest.approx(2_057_906)


def _simple_config(**overrides):
    params = dict(
        name="テスト",
        price=1000,
        draws=10_000,
        cards=[Card("S爆", "目玉", 236_500), Card("S", "S賞", 39_780, count=3)],
        fillers=[Filler("A", 2100, "auto"), Filler("B", 500, "rest")],
        target_return_rate=0.99,
        seed=1,
    )
    params.update(overrides)
    return PackConfig(**params)


def test_auto_filler_fills_up_to_target_without_exceeding_it():
    result = build_pack(_simple_config())
    m = result.metrics
    assert m.return_rate <= 0.99
    # 1枚増やすと目標を超える = 目標以下で最大の枚数になっている
    a = result.filler_lines[0]
    assert m.build_pt + (a.pt - 500) > 0.99 * m.total_pt
    assert sum(line.count for line in result.lines) == 10_000


def test_rejects_pack_over_max_return_rate():
    config = _simple_config(fillers=[Filler("A", 2100, 5000), Filler("B", 500, "rest")])
    with pytest.raises(PackError, match="還元率"):
        build_pack(config)


def test_allows_over_100_percent_only_when_max_is_raised():
    fillers = [Filler("A", 2100, 600), Filler("B", 900, "rest")]
    with pytest.raises(PackError):
        build_pack(_simple_config(fillers=fillers))
    result = build_pack(_simple_config(fillers=fillers, max_return_rate=1.05))
    assert 1.0 < result.metrics.return_rate <= 1.05


def test_rejects_when_hits_alone_exceed_target():
    config = _simple_config(draws=300, price=1000)
    with pytest.raises(PackError, match="目標還元率"):
        build_pack(config)


def test_requires_exactly_one_rest_filler():
    with pytest.raises(PackError, match="rest"):
        build_pack(_simple_config(fillers=[Filler("A", 2100, "auto")]))


@pytest.mark.parametrize("count", [1990.0, -1, "なし"])
def test_rejects_invalid_filler_count(count):
    with pytest.raises(PackError, match="count"):
        build_pack(_simple_config(fillers=[Filler("A", 2100, count), Filler("B", 500, "rest")]))


def test_winning_numbers_are_unique_in_range_and_reproducible():
    first = build_pack(_simple_config())
    numbers = [n for line in first.card_lines for n in line.winning_numbers]
    assert len(numbers) == 4 == len(set(numbers))
    assert all(1 <= n <= 10_000 for n in numbers)
    assert len(first.card_lines[1].winning_numbers) == 3
    again = build_pack(_simple_config())
    assert [line.winning_numbers for line in again.card_lines] == [line.winning_numbers for line in first.card_lines]


def test_ship_only_defaults_to_s_baku_tier():
    result = build_pack(_simple_config())
    assert [line.ship_only for line in result.card_lines] == [True, False]


def test_stock_cards_are_split_from_new_purchases():
    cards = [Card("S爆", "在庫の目玉", 236_500, stock=True), Card("S", "新規", 39_780)]
    m = build_pack(_simple_config(cards=cards)).metrics
    assert m.stock_cost == 236_500
    assert m.new_purchase_cost == 39_780

from oripa import load_cards_csv


def test_csv_accepts_sheet_style_values(tmp_path):
    path = tmp_path / "cards.csv"
    path.write_text(
        "賞,商品名,スニダンリンク,仕入れ価格,枚数,配送のみ,在庫,掛け率,メモ\n"
        'S爆,ルギアV,https://snkrdunk.com/apparels/100567,"¥201,500",1,,○,1.45,目玉\n'
        "S,エリカの招待,,35500,2,配送のみ,,,\n"
        ",,,,,,,,\n",
        encoding="utf-8",
    )
    first, second = load_cards_csv(path)
    assert (first.tier, first.name, first.cost, first.stock, first.markup, first.note) == (
        "S爆",
        "ルギアV",
        201_500,
        True,
        1.45,
        "目玉",
    )
    assert first.ship_only is None  # 空欄なら賞から決める
    assert (second.count, second.ship_only, second.stock, second.markup) == (2, True, False, None)

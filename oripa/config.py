"""パック定義ファイル（TOML）とカードリスト（CSV）の読み込み。"""

import csv
import tomllib
from pathlib import Path

from .model import Card, Filler, PackConfig, PackError, Pricing

TRUTHY = {"1", "true", "yes", "y", "はい", "○", "〇", "◯", "あり", "配送のみ", "在庫"}

# CSV の見出し → Card のフィールド名
CSV_COLUMNS = {
    "賞": "tier",
    "名称": "name",
    "商品名": "name",
    "url": "url",
    "スニダンリンク": "url",
    "仕入れ価格": "cost",
    "数量": "count",
    "枚数": "count",
    "配送のみ": "ship_only",
    "在庫": "stock",
    "掛け率": "markup",
    "pt": "pt",
    "メモ": "note",
}


def load_config(path) -> PackConfig:
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)

    pack = data.get("pack", {})
    for key in ("name", "price", "draws"):
        if key not in pack:
            raise PackError(f"[pack] に {key} がありません。")

    cards = [_card_from_dict(c) for c in data.get("cards", [])]
    if "cards_csv" in pack:
        cards += load_cards_csv(path.parent / pack["cards_csv"])

    fillers = [
        Filler(
            tier=str(f["tier"]),
            pt=int(f["pt"]),
            count=f["count"],
            name=f.get("name", "ポイント交換"),
            note=f.get("note", ""),
        )
        for f in data.get("fillers", [])
    ]

    p = data.get("pricing", {})
    defaults = Pricing()
    pricing = Pricing(
        fee=p.get("fee", defaults.fee),
        markup={**defaults.markup, **p.get("markup", {})},
        default_markup=p.get("default_markup", defaults.default_markup),
        ship_only_tiers=tuple(p.get("ship_only_tiers", defaults.ship_only_tiers)),
        coupon_rate=p.get("coupon_rate", defaults.coupon_rate),
    )

    return PackConfig(
        name=pack["name"],
        price=int(pack["price"]),
        draws=int(pack["draws"]),
        cards=cards,
        fillers=fillers,
        pricing=pricing,
        target_return_rate=pack.get("target_return_rate", 0.97),
        max_return_rate=pack.get("max_return_rate", 1.0),
        seed=pack.get("seed"),
        author=pack.get("author", ""),
    )


def load_cards_csv(path) -> list:
    """スプレッドシートからコピーしたカード一覧（CSV）を読む。見出しは CSV_COLUMNS 参照。"""
    cards = []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            values = {}
            for header, value in row.items():
                key = CSV_COLUMNS.get((header or "").strip().lower())
                if key and value is not None and value.strip() != "":
                    values[key] = value.strip()
            if values.get("name"):
                cards.append(_card_from_dict(values))
    return cards


def _card_from_dict(d: dict) -> Card:
    try:
        return Card(
            tier=str(d["tier"]),
            name=str(d["name"]),
            cost=_number(d.get("cost")),
            count=int(_number(d.get("count", 1))),
            url=str(d.get("url", "")),
            ship_only=_bool(d["ship_only"]) if "ship_only" in d else None,
            stock=_bool(d.get("stock", False)),
            markup=_number(d["markup"]) if "markup" in d else None,
            pt=int(_number(d["pt"])) if "pt" in d else None,
            note=str(d.get("note", "")),
        )
    except KeyError as e:
        raise PackError(f"カード定義に {e.args[0]} がありません: {d}") from None


def _number(value):
    if value is None or isinstance(value, (int, float)):
        return value
    text = str(value).replace(",", "").replace("¥", "").replace("円", "").strip()
    return float(text) if "." in text else int(text)


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUTHY

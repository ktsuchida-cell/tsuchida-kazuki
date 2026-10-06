"""コマンドライン: python -m oripa packs/xxx.toml [-o out/xxx.xlsx]"""

import argparse
import sys
import unicodedata
from pathlib import Path

from .builder import build_pack
from .config import load_config
from .excel import write_xlsx
from .model import PackError, PackResult


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="oripa", description="メタオリパのパック構築シートを作る")
    parser.add_argument("config", help="パック定義ファイル（.toml）")
    parser.add_argument("-o", "--output", help="出力する xlsx（省略時は out/<定義ファイル名>.xlsx）")
    args = parser.parse_args(argv)

    try:
        result = build_pack(load_config(args.config))
    except PackError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    output = Path(args.output) if args.output else Path("out") / (Path(args.config).stem + ".xlsx")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(result, output)
    print(format_summary(result))
    print(f"\n書き出し: {output}")
    return 0


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "FW" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    """全角文字を2桁として左寄せする（ターミナルで列がずれないように）。"""
    while _width(text) > width:
        text = text[:-1]
    return text + " " * (width - _width(text))


def format_summary(result: PackResult) -> str:
    m = result.metrics
    out = [f"■ {result.config.name}", ""]
    out.append(f"{_pad('賞', 5)}{_pad('名称', 30)}{'仕入れ':>8}{'PT':>11}{'数量':>6}  {_pad('配送/在庫', 14)}当選番号")
    for line in result.lines:
        flags = "/".join(f for f, on in (("配送のみ", line.ship_only), ("在庫", line.stock)) if on)
        numbers = ", ".join(map(str, line.winning_numbers)) if not line.is_filler else "ランダム"
        out.append(
            f"{_pad(line.tier, 5)}{_pad(line.name, 30)}{line.cost:>11,.0f}{line.pt:>11,}{line.count:>8,}"
            f"  {_pad(flags, 14)}{numbers}"
        )
    odds = f"1/{round(m.ad_odds, 1):g}" if m.ad_odds else "なし"
    out += [
        "",
        f"一回 {m.price:,}PT × 総口 {m.draws:,} = 総PT {m.total_pt:,}",
        f"構築PT {m.build_pt:,}  還元率 {m.return_rate:.2%}  差額 {m.diff:,}",
        f"配送のみ利益 {m.ship_only_profit:,.0f}  期待課金額 {m.expected_charge:,}"
        f"  クーポン利用後 {m.after_coupon:,.0f}",
        f"概算収支 {m.est_profit:,.0f}  粗利率 {m.margin:.2%}  アド確率 {odds}",
        f"新規仕入額 {m.new_purchase_cost:,.0f}  在庫活用額 {m.stock_cost:,.0f}",
    ]
    if result.warnings:
        out += ["", "注意:"] + [f"  - {w}" for w in result.warnings]
    return "\n".join(out)

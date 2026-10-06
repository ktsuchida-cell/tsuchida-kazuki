"""PT（付与ポイント）の計算ルール。

メタオリパ構築シートの式
    =LET(x, 仕入れ価格*手数料*掛け率, y, MOD(x,1000), IF(y<=500, x-y+500, x-y+1000))
をそのまま再現する。浮動小数の誤差で境界がずれないよう Fraction で計算する。
"""

from fractions import Fraction


def to_fraction(value) -> Fraction:
    """1.05 のような小数を誤差なく Fraction にする。"""
    if isinstance(value, Fraction):
        return value
    return Fraction(str(value))


def round_pt(raw) -> int:
    """1000未満の端数が500以下なら500に、500超なら次の1000に切り上げる。"""
    x = to_fraction(raw)
    base = (x // 1000) * 1000
    return int(base + (500 if x - base <= 500 else 1000))


def card_pt(cost, fee, markup) -> int:
    """仕入れ価格からPTを出す（例: 236,500 × 1.05 × 1.4 → 348,000）。"""
    return round_pt(to_fraction(cost) * to_fraction(fee) * to_fraction(markup))

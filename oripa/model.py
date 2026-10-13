"""パック構築の入力と結果のデータ構造。"""

from dataclasses import dataclass, field
from typing import Optional, Union

FillerCount = Union[int, str]  # 固定枚数 / "auto"（還元率から逆算） / "rest"（残り全部）


class PackError(Exception):
    """パックが組めない・ルール違反のときに出すエラー。"""


@dataclass
class Card:
    """当たりカード（S爆・S など）。"""

    tier: str
    name: str
    cost: float
    count: int = 1
    url: str = ""
    ship_only: Optional[bool] = None  # None なら pricing.ship_only_tiers で決める
    stock: bool = False  # 仕入済み在庫なら True
    markup: Optional[float] = None  # カード個別の掛け率（未指定なら賞ごとの既定値）
    pt: Optional[int] = None  # PTを手で決める場合のみ指定
    note: str = ""


@dataclass
class Filler:
    """ポイント交換などのハズレ枠。"""

    tier: str
    pt: int
    count: FillerCount
    name: str = "ポイント交換"
    note: str = ""


@dataclass
class Pricing:
    fee: float = 1.05
    markup: dict = field(default_factory=lambda: {"S爆": 1.4, "S": 1.3})
    default_markup: float = 1.3
    ship_only_tiers: tuple = ("S爆",)
    coupon_rate: float = 0.97  # クーポン利用後課金額 = 期待課金額 × この値


@dataclass
class PackConfig:
    name: str
    price: int  # 一回のPT
    draws: int  # 総口
    cards: list
    fillers: list
    pricing: Pricing = field(default_factory=Pricing)
    target_return_rate: float = 0.97  # "auto" 枠はこの還元率を超えない最大枚数にする
    max_return_rate: float = 1.0  # これを超えたらエラー
    seed: Optional[int] = None  # 当選番号の乱数シード
    top_number_from: float = 0.9  # 一番高い当たりは総口のこの割合以降の番号にする
    author: str = ""


@dataclass
class Line:
    """構築シートの1行。"""

    tier: str
    name: str
    url: str
    cost: float
    pt: int
    count: int
    ship_only: bool
    stock: bool
    is_filler: bool
    markup: Optional[float]  # PTを式で出す行のみ（手入力PT・ハズレ枠は None）
    winning_numbers: list = field(default_factory=list)
    note: str = ""

    @property
    def total_pt(self) -> int:
        return self.pt * self.count


@dataclass
class Metrics:
    price: int
    draws: int
    total_pt: int  # 総PT
    build_pt: int  # 構築PT
    return_rate: float  # 還元率
    diff: int  # 差額
    ship_only_profit: float  # 配送のみ利益
    expected_charge: int  # 期待課金額
    after_coupon: float  # クーポン利用後課金額
    est_profit: float  # 概算収支
    margin: float  # 粗利率
    ad_count: int  # 一回の価格を超えるPTが出る口数
    new_purchase_cost: float  # 新規仕入額（在庫以外の当たりカード）
    stock_cost: float  # 在庫活用額

    @property
    def ad_odds(self) -> Optional[float]:
        """アド確率を「1/◯」の◯で返す。"""
        return self.draws / self.ad_count if self.ad_count else None


@dataclass
class PackResult:
    config: PackConfig
    lines: list
    metrics: Metrics
    warnings: list = field(default_factory=list)

    @property
    def card_lines(self) -> list:
        return [line for line in self.lines if not line.is_filler]

    @property
    def filler_lines(self) -> list:
        return [line for line in self.lines if line.is_filler]

"""カードリストから構築（枚数・PT・当選番号・収支）を組み立てる。"""

import math
import random

from .model import Card, Filler, Line, Metrics, PackConfig, PackError, PackResult
from .pricing import card_pt, to_fraction


def build_pack(config: PackConfig) -> PackResult:
    _validate_config(config)
    card_lines = [_card_line(card, config) for card in config.cards]
    filler_lines = _resolve_fillers(config, card_lines)
    lines = card_lines + filler_lines
    _assign_winning_numbers(lines, config)
    metrics = _metrics(config, lines)

    if metrics.return_rate > config.max_return_rate:
        raise PackError(
            f"還元率 {metrics.return_rate:.2%} が上限 {config.max_return_rate:.0%} を超えています。"
            " 当たりの枚数を減らすか、一回の価格・総口を見直してください。"
        )
    return PackResult(config, lines, metrics, _warnings(config, lines, metrics))


def _validate_config(config: PackConfig) -> None:
    if config.price <= 0:
        raise PackError("一回の価格（price）は1以上にしてください。")
    if config.draws <= 0:
        raise PackError("総口（draws）は1以上にしてください。")
    if not 0 <= config.top_number_from <= 1:
        raise PackError("top_number_from は 0〜1 の割合で指定してください（9割以降なら 0.9）。")
    if not config.cards:
        raise PackError("当たりカード（cards）が1枚もありません。")
    for card in config.cards:
        if card.count < 1:
            raise PackError(f"{card.name}: 枚数は1以上にしてください。")
        if card.pt is None and (card.cost is None or card.cost <= 0):
            raise PackError(f"{card.name}: 仕入れ価格（cost）がありません。")
    modes = [f.count for f in config.fillers if isinstance(f.count, str)]
    if modes.count("rest") != 1:
        raise PackError('ハズレ枠のうち1つだけ count = "rest"（残り全部）にしてください。')
    if modes.count("auto") > 1:
        raise PackError('count = "auto" にできるハズレ枠は1つだけです。')
    for filler in config.fillers:
        valid_int = isinstance(filler.count, int) and not isinstance(filler.count, bool) and filler.count >= 0
        if not valid_int and filler.count not in ("auto", "rest"):
            raise PackError(f'{filler.tier}: count は0以上の整数か "auto" / "rest" で指定してください。')


def _card_line(card: Card, config: PackConfig) -> Line:
    pricing = config.pricing
    ship_only = card.ship_only if card.ship_only is not None else card.tier in pricing.ship_only_tiers
    if card.pt is not None:
        pt, markup = int(card.pt), None
    else:
        markup = card.markup if card.markup is not None else pricing.markup.get(card.tier, pricing.default_markup)
        pt = card_pt(card.cost, pricing.fee, markup)
    return Line(
        tier=card.tier,
        name=card.name,
        url=card.url,
        cost=card.cost or 0,
        pt=pt,
        count=card.count,
        ship_only=ship_only,
        stock=card.stock,
        is_filler=False,
        markup=markup,
        note=card.note,
    )


def _resolve_fillers(config: PackConfig, card_lines: list) -> list:
    hits_n = sum(line.count for line in card_lines)
    hits_pt = sum(line.total_pt for line in card_lines)
    fixed = [f for f in config.fillers if isinstance(f.count, int)]
    auto = next((f for f in config.fillers if f.count == "auto"), None)
    rest = next(f for f in config.fillers if f.count == "rest")

    available = config.draws - hits_n - sum(f.count for f in fixed)
    if available < 0:
        raise PackError(f"当たり＋固定枠の枚数が総口 {config.draws:,} を超えています。")
    base_pt = hits_pt + sum(f.pt * f.count for f in fixed) + rest.pt * available

    counts = {id(f): f.count for f in fixed}
    if auto is not None:
        if auto.pt <= rest.pt:
            raise PackError('"auto" 枠のPTは "rest" 枠のPTより大きくしてください。')
        budget = math.floor(to_fraction(config.target_return_rate) * config.price * config.draws)
        n_auto = (budget - base_pt) // (auto.pt - rest.pt)
        if n_auto < 0:
            raise PackError(
                f"当たりだけで目標還元率 {config.target_return_rate:.0%} を超えます。"
                " 総口を増やすか、当たりを減らしてください。"
            )
        n_auto = min(n_auto, available)
        counts[id(auto)] = n_auto
        available -= n_auto
    counts[id(rest)] = available

    return [
        Line(
            tier=f.tier,
            name=f.name,
            url="",
            cost=f.pt,
            pt=f.pt,
            count=counts[id(f)],
            ship_only=False,
            stock=False,
            is_filler=True,
            markup=None,
            note=f.note,
        )
        for f in config.fillers
    ]


def _assign_winning_numbers(lines: list, config: PackConfig) -> None:
    """当たりカード1枚ごとに 1〜総口 の重複しない当選番号を割り振る。ハズレ枠はランダム。

    高いカード（PTの高い順）ほど後ろの番号にし、一番高いカードは総口の
    top_number_from（既定 9割）以降の番号にする。
    """
    rng = random.Random(config.seed)
    hit_lines = [line for line in lines if not line.is_filler]
    hits = sum(line.count for line in hit_lines)
    numbers = sorted(rng.sample(range(1, config.draws + 1), hits))
    top_from = max(math.ceil(config.draws * config.top_number_from), 1)
    if numbers and numbers[-1] < top_from:
        # ほかの番号はすべて numbers[-1] より小さいので、重複も順番の入れ替わりも起きない
        numbers[-1] = rng.randint(top_from, config.draws)
    for line in sorted(hit_lines, key=lambda line: (line.pt, line.cost)):
        line.winning_numbers = numbers[: line.count]
        numbers = numbers[line.count :]


def _metrics(config: PackConfig, lines: list) -> Metrics:
    total_pt = config.price * config.draws
    build_pt = sum(line.total_pt for line in lines)
    ship = [line for line in lines if line.ship_only]
    ship_only_profit = sum((line.pt - to_fraction(line.cost)) * line.count for line in ship)
    expected_charge = sum(line.total_pt for line in ship)
    after_coupon = to_fraction(expected_charge) * to_fraction(config.pricing.coupon_rate)
    diff = total_pt - build_pt
    est_profit = diff + ship_only_profit + (after_coupon - expected_charge)
    cards = [line for line in lines if not line.is_filler]
    return Metrics(
        price=config.price,
        draws=config.draws,
        total_pt=total_pt,
        build_pt=build_pt,
        return_rate=build_pt / total_pt,
        diff=diff,
        ship_only_profit=float(ship_only_profit),
        expected_charge=expected_charge,
        after_coupon=float(after_coupon),
        est_profit=float(est_profit),
        margin=float(est_profit / after_coupon) if after_coupon else 0.0,
        ad_count=sum(line.count for line in lines if line.pt > config.price),
        new_purchase_cost=float(sum(to_fraction(l.cost) * l.count for l in cards if not l.stock)),
        stock_cost=float(sum(to_fraction(l.cost) * l.count for l in cards if l.stock)),
    )


def _warnings(config: PackConfig, lines: list, metrics: Metrics) -> list:
    warnings = []
    for line in lines:
        if not line.is_filler and not line.cost:
            warnings.append(f"{line.name}: 仕入れ価格がないため、収支・仕入額に入っていません。")
    if metrics.est_profit < 0:
        warnings.append(f"概算収支がマイナスです（{metrics.est_profit:,.0f}円）。")
    if not any(line.ship_only for line in lines):
        warnings.append("配送のみのカードがありません（配送のみ利益・期待課金額は0になります）。")
    for line in lines:
        if line.is_filler and line.count == 0:
            warnings.append(f"ハズレ枠 {line.tier}（{line.pt:,}PT）が0枚になりました。")
    if metrics.return_rate < 0.9:
        warnings.append(f"還元率 {metrics.return_rate:.2%} は低めです。ユーザーの評判に注意してください。")
    return warnings

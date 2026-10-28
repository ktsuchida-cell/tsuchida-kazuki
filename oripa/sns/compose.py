"""パックの構築結果からX投稿のたたき台を作る。

数字（価格・口数・アド確率など）は構築結果から入れるので、手で打ち間違えない。
文章はテンプレート（sns/templates/<種類>.txt）で決める。1ファイルに `---` だけの行で区切って何案でも書ける。
テンプレートの {name} などは pack_context の項目で埋まる。埋まらない項目は {card} のまま残り、check でエラーになる。
"""

import math
import re
from typing import Optional

from ..model import PackResult
from .rules import Rules


def display_name(name: str) -> str:
    """投稿に出すカード名。「カメックスEX SR PSA10 [CP6 092/087]」→「カメックスEX SR PSA10」"""
    return re.sub(r"\s*\[[^\]]*\]", "", name).strip()


def base_context(rules: Rules, url: Optional[str] = None) -> dict:
    return {"url": url or rules.url, "account": rules.account, "hashtags": " ".join(rules.hashtags)}


def pack_context(result: PackResult, rules: Rules, url: Optional[str] = None) -> dict:
    """テンプレートで使える項目。数字は実際より良く見えない向きに丸める。"""
    m = result.metrics
    cards = sorted(result.card_lines, key=lambda line: (line.pt, line.cost), reverse=True)
    hits = sum(line.count for line in cards)
    top_tier = cards[0].tier
    all_psa10 = all("PSA10" in line.name.replace(" ", "").upper() for line in cards)
    min_pt = min((line.pt for line in result.filler_lines), default=None)
    return {
        **base_context(rules, url),
        "name": result.config.name,
        "price": f"{m.price:,}",
        "draws": f"{m.draws:,}",
        "hits": f"{hits:,}",
        "hits_line": _hits_line(hits, all_psa10),
        "top": display_name(cards[0].name),
        "top_tier": "\n".join(_card_item(line) for line in cards if line.tier == top_tier),
        "lineup": "\n".join(_card_item(line) for line in cards[:5]),
        "ad_odds": _odds(m.ad_odds),
        "min_pt": f"{min_pt:,}" if min_pt is not None else "",
        "ad_line": _ad_line(m, min_pt),
        "return_rate": f"{math.floor(m.return_rate * 1000) / 10:g}",  # 0.1%単位で切り捨て
    }


def fill(template: str, context: dict) -> str:
    text = template.format_map(_Keep(context))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_templates(rules: Rules, post_type: str) -> list:
    path = rules.templates_dir / f"{post_type}.txt"
    if not path.exists():
        names = " / ".join(sorted(p.stem for p in rules.templates_dir.glob("*.txt")))
        raise FileNotFoundError(f"テンプレート {path} がありません（あるもの: {names}）。")
    blocks = re.split(r"^-{3,}\s*$", path.read_text(encoding="utf-8"), flags=re.M)
    return [b.strip("\n") for b in blocks if b.strip()]


def _hits_line(hits: int, all_psa10: bool) -> str:
    if not all_psa10:
        return f"当たり{hits:,}枚"
    return "当たりはPSA10" if hits == 1 else f"当たり{hits:,}枚は全部PSA10"


def _ad_line(metrics, min_pt) -> str:
    """「アド確率 1/2.8・最低保証 100PT」。課金ガチャ（最低保証が1回の価格以上）はアド確率を出さない。"""
    if min_pt is None:
        return f"アド確率 {_odds(metrics.ad_odds)}"
    if min_pt >= metrics.price:
        return f"最低保証 {min_pt:,}PT"
    return f"アド確率 {_odds(metrics.ad_odds)}・最低保証 {min_pt:,}PT"


def _card_item(line) -> str:
    return f"・{display_name(line.name)}" + (f" ×{line.count}" if line.count > 1 else "")


def _odds(odds: Optional[float]) -> str:
    """アド確率「1/◯」。◯は0.1単位で切り上げる（実際より当たりやすく見せない）。"""
    if not odds:
        return "なし"
    return f"1/{math.ceil(round(odds * 10, 6)) / 10:g}"


class _Keep(dict):
    """埋まらない項目は {key} のまま残す。"""

    def __missing__(self, key):
        return "{" + key + "}"

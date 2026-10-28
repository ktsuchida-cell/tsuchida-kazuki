"""投稿文のチェック: 文字数・NGワード・埋まっていない項目・パックの数字との食い違い。"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from ..model import PackResult
from .rules import Rules
from .xtext import hashtags, weighted_length

ERROR = "エラー"
CAUTION = "注意"


@dataclass
class Issue:
    level: str  # ERROR / CAUTION
    message: str


def check_post(text: str, rules: Rules, result: Optional[PackResult] = None, remaining: Optional[int] = None) -> list:
    issues = []
    n = weighted_length(text)
    if n > rules.max_length:
        issues.append(Issue(ERROR, f"文字数 {n}/{rules.max_length}（日本語・絵文字は2、URLは23で数える）"))
    for name in dict.fromkeys(re.findall(r"\{(\w+)\}", text)):
        issues.append(Issue(ERROR, f"{{{name}}} が埋まっていません"))
    for rule in rules.ng:
        for word in rule.words:
            if word in text:
                issues.append(Issue(ERROR, f"「{word}」: {rule.reason}"))
    for rule in rules.caution:
        for word in rule.words:
            if word in text:
                issues.append(Issue(CAUTION, f"「{word}」: {rule.reason}"))
    tags = hashtags(text)
    if len(tags) > rules.max_hashtags:
        issues.append(Issue(CAUTION, f"ハッシュタグが {len(tags)} 個あります（目安 {rules.max_hashtags} 個まで）"))
    if result is not None:
        issues += check_numbers(text, result, remaining)
    return issues


def check_numbers(text: str, result: PackResult, remaining: Optional[int] = None) -> list:
    """本文に書いた価格・口数・還元率・アド確率がパックの構築と合っているか。

    還元率とアド確率は、実際より良く見せていないか（実際以下か）を確かめる。
    """
    m = result.metrics
    t = unicodedata.normalize("NFKC", text)
    issues = []
    for value in _numbers(r"(?<![\d,])(?:1|一)\s*(?:回|口)\s*:?\s*([\d,]+)\s*(?:PT|pt|Pt|ポイント|円)", t):
        if value != m.price:
            issues.append(Issue(ERROR, f"1回 {value:,} と書いてありますが、パックは {m.price:,}PT です"))
    for value in _numbers(r"(?:全|総)\s*([\d,]+)\s*口", t):
        if value != m.draws:
            issues.append(Issue(ERROR, f"全{value:,}口 と書いてありますが、パックは {m.draws:,}口 です"))
    for value in _numbers(r"還元率\s*:?\s*約?\s*(\d+(?:\.\d+)?)\s*%", t):
        if value > m.return_rate * 100 + 1e-9:
            issues.append(Issue(ERROR, f"還元率 {value:g}% は実際（{m.return_rate:.2%}）より高いです"))
    for value in _numbers(r"アド[^\n\d]{0,8}1\s*/\s*(\d+(?:\.\d+)?)", t):
        if m.ad_odds is None or value < m.ad_odds - 1e-9:
            actual = f"1/{m.ad_odds:.2f}" if m.ad_odds else "なし"
            issues.append(Issue(ERROR, f"アド確率 1/{value:g} は実際（{actual}）より良く見えます"))
    for value in _numbers(r"残り\s*([\d,]+)\s*口", t):
        if remaining is None:
            issues.append(Issue(CAUTION, f"残り{value:,}口: 投稿する直前にサイトで残り口数を確かめる"))
        elif value != remaining:
            issues.append(Issue(ERROR, f"残り{value:,}口 と書いてありますが、指定された残りは {remaining:,}口 です"))
    if re.search(r"(?:全部|全て|すべて|オール)\s*PSA\s*10", t, re.I) and not all(
        "PSA10" in line.name.replace(" ", "").upper() for line in result.card_lines
    ):
        issues.append(Issue(ERROR, "「全部PSA10」と書いてありますが、PSA10でない当たりがあります"))
    return issues


def _numbers(pattern: str, text: str) -> list:
    return [float(v) if "." in v else int(v) for v in (s.replace(",", "") for s in re.findall(pattern, text)) if v]


def format_issues(issues: list) -> str:
    if not issues:
        return "  問題なし"
    return "\n".join(f"  [{i.level}] {i.message}" for i in issues)

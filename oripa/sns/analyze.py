"""過去のX投稿を分析して、書き方の特徴と反応のよかった投稿を Markdown にまとめる。

投稿文を作るときのお手本（種類ごとに反応のよかった投稿）もここに載せる。
"""

import re
import statistics
from collections import Counter
from urllib.parse import urlparse

from .rules import Rules
from .xtext import emojis, hashtags, mentions, urls, weighted_length

WEEKDAYS = "月火水木金土日"


def analyze(posts: list, rules: Rules, sources=()) -> str:
    own = [p for p in posts if not p.is_reply and not p.is_repost]
    if not own:
        raise ValueError("分析できる投稿がありません（返信・リポストは除いています）。")
    for p in own:
        p.kind = rules.classify(p.text)
    reaction = _Reaction(own)

    out = [f"# X投稿の分析（{rules.account}）", ""]
    out += [
        "> `python -m oripa.sns analyze` が作ったファイル。手で直さない"
        "（書き方のルールは [スタイルガイド.md](スタイルガイド.md) に書く）。",
        "",
    ]
    out += _overview(posts, own, reaction, sources)
    out += _by_type(own, rules, reaction)
    out += _by_time(own, reaction)
    out += _style(own, rules)
    if reaction.available:
        out += _ranking("## 4. 反応がよかった投稿（上位10件）", reaction.top(own, 10), reaction)
        out += _examples(own, rules, reaction)
        out += _ranking("## 6. 反応が少なかった投稿（下位5件）", reaction.top(own, 5, worst=True), reaction)
    else:
        out += [
            "## 4. 種類ごとのお手本",
            "",
            "反応（いいね・リポストなど）のデータがないので、新しい順に3件ずつ載せる。",
            "",
        ]
        for name in rules.type_names():
            items = [p for p in reversed(own) if p.kind == name][:3]
            if items:
                out += [f"### {name}", ""] + [line for p in items for line in _code(p.text)]
    return "\n".join(out).rstrip() + "\n"


class _Reaction:
    """反応の指標。全部の投稿にインプレッションがあればエンゲージメント率、なければ いいね＋リポスト。"""

    def __init__(self, posts):
        self.available = any(p.likes is not None or p.impressions is not None for p in posts)
        self.by_rate = all(p.impressions for p in posts)
        self.label = "エンゲージメント率" if self.by_rate else "いいね＋リポスト"

    def value(self, post) -> float:
        if self.by_rate:
            return post.engagement_rate
        return (post.likes or 0) + (post.reposts or 0)

    def median(self, posts) -> str:
        if not self.available or not posts:
            return "-"
        v = statistics.median(self.value(p) for p in posts)
        return f"{v:.2%}" if self.by_rate else f"{v:,.0f}"

    def top(self, posts, n, worst=False):
        return sorted(posts, key=self.value, reverse=not worst)[:n]

    def describe(self, post) -> str:
        parts = [f"いいね {post.likes or 0:,}", f"リポスト {post.reposts or 0:,}"]
        if post.impressions:
            parts.append(f"表示 {post.impressions:,}（{post.engagement_rate:.2%}）")
        return "／".join(parts)


def _overview(posts, own, reaction, sources):
    dated = [p.created_at for p in own if p.created_at]
    out = []
    if sources:
        out.append(f"- データ: {'、'.join(sources)}")
    if dated:
        days = (max(dated).date() - min(dated).date()).days + 1
        out.append(
            f"- 期間: {min(dated):%Y-%m-%d} 〜 {max(dated):%Y-%m-%d}（{days}日・1日あたり {len(own) / days:.1f}件）"
        )
    replies = sum(p.is_reply for p in posts)
    reposts = sum(p.is_repost for p in posts)
    out.append(f"- 分析した投稿: {len(own):,}件（返信 {replies:,}件・リポスト {reposts:,}件は除いた）")
    out.append(f"- 反応の指標: {reaction.label if reaction.available else 'データなし'}")
    return out + [""]


def _by_type(own, rules, reaction):
    out = ["## 1. 投稿の種類", ""]
    out.append(f"| 種類 | 件数 | 割合 | 文字数 | 行数 | 画像つき | URLつき | タグ数 | 反応（{reaction.label}） |")
    out.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name in rules.type_names():
        items = [p for p in own if p.kind == name]
        if not items:
            continue
        with_media = [p for p in items if p.media is not None]
        media = f"{sum(1 for p in with_media if p.media) / len(with_media):.0%}" if with_media else "-"
        out.append(
            f"| {name} | {len(items):,} | {len(items) / len(own):.0%}"
            f" | {statistics.median(weighted_length(p.text) for p in items):,.0f}"
            f" | {statistics.median(len(p.text.splitlines()) for p in items):g}"
            f" | {media} | {sum(1 for p in items if urls(p.text)) / len(items):.0%}"
            f" | {statistics.mean(len(hashtags(p.text)) for p in items):.1f} | {reaction.median(items)} |"
        )
    purposes = [f"- {t.name}: {t.purpose}" for t in rules.types if t.purpose]
    out += [
        "",
        "文字数はXの数え方（日本語・絵文字は2、URLは23）の中央値。種類の分け方は `sns/rules.toml` の `[[types]]`。",
    ]
    out += ["「その他」が多いときはキーワードを足す。", ""] + purposes + [""]
    return out


def _by_time(own, reaction):
    timed = [p for p in own if p.created_at and p.has_time]
    if not timed:
        return ["## 2. 投稿の時間帯・曜日", "", "時刻のデータがない。", ""]
    out = [
        "## 2. 投稿の時間帯・曜日（日本時間）",
        "",
        f"| 時 | 件数 | 反応（{reaction.label}） |",
        "| ---: | ---: | ---: |",
    ]
    for hour in range(24):
        items = [p for p in timed if p.created_at.hour == hour]
        if items:
            out.append(f"| {hour}時 | {len(items):,} | {reaction.median(items)} |")
    out += ["", f"| 曜日 | 件数 | 反応（{reaction.label}） |", "| --- | ---: | ---: |"]
    for day, name in enumerate(WEEKDAYS):
        items = [p for p in timed if p.created_at.weekday() == day]
        if items:
            out.append(f"| {name} | {len(items):,} | {reaction.median(items)} |")
    return out + [""]


def _style(own, rules):
    n = len(own)
    lengths = [weighted_length(p.text) for p in own]
    with_emoji = [p for p in own if emojis(p.text)]
    with_bracket = [p for p in own if "【" in p.text]
    with_url = [p for p in own if urls(p.text)]
    out = ["## 3. 書き方", ""]
    out.append(
        f"- 文字数: 中央値 {statistics.median(lengths):,.0f}／最大 {max(lengths):,}"
        f"／{rules.max_length}を超える投稿 {sum(1 for x in lengths if x > rules.max_length):,}件"
    )
    blank_line = sum(1 for p in own if re.search(r"\n\s*\n", p.text))
    out.append(
        f"- 行数: 中央値 {statistics.median(len(p.text.splitlines()) for p in own):g}"
        f"／空行で区切る投稿 {blank_line / n:.0%}"
    )
    out.append(
        f"- 絵文字・記号を使う投稿: {len(with_emoji) / n:.0%}（よく使う: {_top(c for p in own for c in emojis(p.text))}）"
    )
    brackets = (b for p in own for b in re.findall(r"【[^】\n]{1,30}】", p.text))
    out.append(
        f"- 【】の見出しを使う投稿: {len(with_bracket) / n:.0%}（よく使う: {_top(_normalize(b) for b in brackets)}）"
    )
    tags = [t for p in own for t in hashtags(p.text)]
    out.append(f"- ハッシュタグ: 1投稿あたり {len(tags) / n:.1f}個（よく使う: {_top(tags, 10)}）")
    out.append(f"- メンション: {_top(m for p in own for m in mentions(p.text)) or 'なし'}")
    domains = (urlparse(u if "://" in u else "https://" + u).netloc for p in own for u in urls(p.text))
    out.append(f"- URLつき: {len(with_url) / n:.0%}（ドメイン: {_top(domains) or 'なし'}）")
    out += ["", "### 書き出し（1行目）でよく使う形", "", "数字は N にまとめた。", ""]
    out += _count_table("1行目", (_normalize(_first_line(p.text)) for p in own))
    out += ["### 締め（URL・ハッシュタグを除いた最後の行）でよく使う形", ""]
    out += _count_table("最後の行", (_normalize(_last_line(p.text)) for p in own))
    return out


def _ranking(title, posts, reaction):
    out = [title, ""]
    for i, p in enumerate(posts, 1):
        out += [f"### {i}. {p.kind}・{_when(p)}・{reaction.describe(p)}", ""] + _code(p.text)
    return out


def _when(post) -> str:
    if not post.created_at:
        return "日時不明"
    return f"{post.created_at:%Y-%m-%d %H:%M}" if post.has_time else f"{post.created_at:%Y-%m-%d}"


def _examples(own, rules, reaction):
    out = ["## 5. 種類ごとのお手本（反応の上位3件）", "", "投稿文を作るときは、この文体・構成に合わせる。", ""]
    for name in rules.type_names():
        items = [p for p in own if p.kind == name]
        if items:
            out += [f"### {name}", ""] + [line for p in reaction.top(items, 3) for line in _code(p.text)]
    return out


def _code(text):
    return ["```text", text, "```", ""]


def _count_table(header, values, n=10):
    counts = Counter(v for v in values if v).most_common(n)
    if not counts:
        return ["なし", ""]
    rows = [f"| {header} | 件数 |", "| --- | ---: |"]
    return rows + [f"| {v.replace('|', '｜')} | {c:,} |" for v, c in counts] + [""]


def _top(values, n=8) -> str:
    return "、".join(f"{v} {c:,}" for v, c in Counter(values).most_common(n))


def _normalize(line: str) -> str:
    """数字を N にまとめる（PSA10・SV2a のような英字に続く数字はそのまま）。"""
    return re.sub(r"(?<![A-Za-z\d])\d[\d,]*", "N", line.strip())


def _first_line(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")


def _last_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        rest = line
        for item in urls(line) + hashtags(line) + mentions(line):
            rest = rest.replace(item, "")
        if rest.strip():
            return line
    return ""

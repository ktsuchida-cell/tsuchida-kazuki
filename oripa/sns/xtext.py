"""X（旧Twitter）の文字数の数え方と、本文からハッシュタグ・絵文字などを取り出す処理。

X は半角英数を1、日本語・絵文字を2として数え、合計280まで投稿できる（無料アカウント）。
URL は長さに関係なく23として数える。twitter-text（v3）の数え方を簡略化して再現する。
"""

import re
import unicodedata

URL_LENGTH = 23

# 1として数える文字の範囲（それ以外は2）。twitter-text v3 の ranges と同じ
_LIGHT_RANGES = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))

# 直前の絵文字にくっついて、数に入らない文字（異体字セレクタ・肌の色・タグ）
_ZERO_WIDTH = ((0xFE0E, 0xFE0F), (0x1F3FB, 0x1F3FF), (0xE0020, 0xE007F))

_URL_RE = re.compile(
    r"https?://[!-~]+"
    r"|(?<![A-Za-z0-9@._-])(?:[A-Za-z0-9-]+\.)+(?:com|net|org|jp|io|co|me|app|shop)(?:/[!-~]*)?"
)
# 日本語の直後に # を続けてもハッシュタグにならない（前に空白か改行が要る）
_HASHTAG_RE = re.compile(r"(?<![\w&])[#＃](\w+)")
# 日本語や①の直後でもメンションになる（英数字の直後はならない）
_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_@＠!#$%&*])[@＠]([A-Za-z0-9_]{1,15})")

# 絵文字と、日本語の投稿で飾りに使われる記号
_PICTOGRAPHIC = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0x2300, 0x23FF),
    (0x2190, 0x21FF),
    (0x25A0, 0x25FF),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
)
_DECORATIONS = set("※♪♫")


def _in(cp: int, ranges) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def urls(text: str) -> list:
    return [_strip_url_tail(m.group())[0] for m in _URL_RE.finditer(text)]


def hashtags(text: str) -> list:
    return ["#" + tag for tag in _HASHTAG_RE.findall(text)]


def mentions(text: str) -> list:
    return ["@" + name for name in _MENTION_RE.findall(text)]


def emojis(text: str) -> list:
    """絵文字・飾りの記号を1文字ずつ返す（異体字セレクタなどは外す）。"""
    return [ch for ch in text if _in(ord(ch), _PICTOGRAPHIC) or ch in _DECORATIONS]


def weighted_length(text: str) -> int:
    """X の数え方での文字数（上限280と比べる値）。"""
    text = unicodedata.normalize("NFC", text)
    n_urls = 0

    def drop_url(m):
        nonlocal n_urls
        n_urls += 1
        return _strip_url_tail(m.group())[1]

    text = _URL_RE.sub(drop_url, text)
    total = n_urls * URL_LENGTH
    prev_emoji = False
    i = 0
    while i < len(text):
        cp = ord(text[i])
        if _in(cp, _ZERO_WIDTH):
            i += 1
            continue
        if cp == 0x200D and prev_emoji:  # ZWJ でつながった絵文字は1つとして数える
            i += 2
            continue
        if cp == 0x20E3:  # キーキャップ（1️⃣）は数字の1と合わせて2
            total += 1
            i += 1
            continue
        if 0x1F1E6 <= cp <= 0x1F1FF:  # 国旗は2文字で1つ
            total += 2
            i += 2 if i + 1 < len(text) and 0x1F1E6 <= ord(text[i + 1]) <= 0x1F1FF else 1
            prev_emoji = True
            continue
        weight = 1 if _in(cp, _LIGHT_RANGES) else 2
        total += weight
        prev_emoji = weight == 2
        i += 1
    return total


def _strip_url_tail(url: str):
    """URLの末尾の句読点はURLに含めない。（URL, 残りの文字）を返す。"""
    stripped = url.rstrip(".,:;!?)]}'\"")
    return stripped, url[len(stripped) :]

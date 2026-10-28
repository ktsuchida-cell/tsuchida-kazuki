"""X の投稿データの読み込み。

読めるもの:
- X のデータアーカイブの tweets.js（いいね・リポスト数つき。インプレッションはない）
- X アナリティクスなどの CSV（見出しは CSV_COLUMNS 参照。日本語の見出しでもよい）
- 手で貼ったテキスト（.txt）。投稿を `---` だけの行で区切り、先頭に `日時: 2026-10-24 19:00` などを書ける
"""

import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

JST = timezone(timedelta(hours=9))
SUFFIXES = (".js", ".json", ".csv", ".txt")

# CSV の見出し（小文字・空白なし） → Post のフィールド名
CSV_COLUMNS = {
    "posttext": "text",
    "tweettext": "text",
    "text": "text",
    "full_text": "text",
    "本文": "text",
    "投稿本文": "text",
    "ポスト本文": "text",
    "ポストのテキスト": "text",
    "date": "created_at",
    "time": "created_at",
    "created_at": "created_at",
    "日時": "created_at",
    "日付": "created_at",
    "投稿日時": "created_at",
    "postid": "id",
    "tweetid": "id",
    "id": "id",
    "ポストid": "id",
    "postlink": "url",
    "tweetpermalink": "url",
    "url": "url",
    "リンク": "url",
    "ポストのリンク": "url",
    "likes": "likes",
    "いいね": "likes",
    "いいね数": "likes",
    "reposts": "reposts",
    "retweets": "reposts",
    "rt": "reposts",
    "リポスト": "reposts",
    "リポスト数": "reposts",
    "replies": "replies",
    "返信": "replies",
    "返信数": "replies",
    "bookmarks": "bookmarks",
    "ブックマーク": "bookmarks",
    "ブックマーク数": "bookmarks",
    "impressions": "impressions",
    "views": "impressions",
    "インプレッション": "impressions",
    "インプレッション数": "impressions",
    "表示": "impressions",
    "表示回数": "impressions",
    "画像": "media",
    "media": "media",
}

_DATE_FORMATS = (
    "%a %b %d %H:%M:%S %z %Y",  # アーカイブ: Thu Oct 24 10:00:00 +0000 2026
    "%Y-%m-%d %H:%M %z",  # 旧アナリティクス: 2026-10-24 10:00 +0000
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)
_DATE_ONLY_FORMATS = ("%a, %b %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y/%m/%d")

# テキスト形式で投稿の先頭に書ける項目
_META_FIELDS = {"created_at", "id", "url", "likes", "reposts", "replies", "bookmarks", "impressions", "media"}
_META_RE = re.compile(r"^\s*([^:：\s]+)\s*[:：]\s*(.+?)\s*$")


@dataclass
class Post:
    text: str
    created_at: Optional[datetime] = None  # 日本時間
    has_time: bool = False  # created_at に時刻まで入っているか（日付だけのデータもある）
    id: str = ""
    url: str = ""
    likes: Optional[int] = None
    reposts: Optional[int] = None
    replies: Optional[int] = None
    bookmarks: Optional[int] = None
    impressions: Optional[int] = None
    media: Optional[int] = None  # 画像・動画の数（分からなければ None）
    is_reply: bool = False
    is_repost: bool = False
    source: str = ""
    kind: str = ""  # 投稿の種類（analyze で rules.toml から決める）

    @property
    def engagements(self) -> int:
        return sum(v or 0 for v in (self.likes, self.reposts, self.replies, self.bookmarks))

    @property
    def engagement_rate(self) -> Optional[float]:
        return self.engagements / self.impressions if self.impressions else None


def load_posts(paths) -> list:
    """ファイル・フォルダを読んで投稿を古い順に返す。同じ投稿（同じIDか同じ日時・本文）は1つにする。"""
    posts, seen = [], set()
    for path in _expand(paths):
        loader = {".js": _load_archive, ".json": _load_archive, ".csv": _load_csv, ".txt": load_text}[path.suffix]
        for post in loader(path):
            key = post.id or (post.created_at, post.text)
            if key not in seen:
                seen.add(key)
                posts.append(post)
    return sorted(posts, key=lambda p: (p.created_at is None, p.created_at or datetime.min.replace(tzinfo=JST)))


def load_text(path) -> list:
    """`---` で区切ったテキストを読む。各投稿の先頭の「日時: …」「いいね: …」などは数字として読む。"""
    path = Path(path)
    posts = []
    for block in re.split(r"^-{3,}\s*$", path.read_text(encoding="utf-8-sig"), flags=re.M):
        values, lines = {}, block.strip("\n").splitlines()
        while lines and (m := _META_RE.match(lines[0])) and _column(m.group(1)) in _META_FIELDS:
            values[_column(m.group(1))] = m.group(2)
            lines.pop(0)
        text = "\n".join(lines).strip()
        if text:
            posts.append(_post_from_values({**values, "text": text}, path.name))
    return posts


def _expand(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(f for f in p.iterdir() if f.suffix in SUFFIXES)
        elif p.suffix in SUFFIXES:
            yield p
        else:
            raise ValueError(f"{p}: 読めない形式です（{' / '.join(SUFFIXES)}）。")


def _load_archive(path) -> list:
    raw = Path(path).read_text(encoding="utf-8-sig")
    raw = raw[raw.index("[") :]  # 先頭の「window.YTD.tweets.part0 = 」を外す
    posts = []
    for item in json.loads(raw):
        t = item.get("tweet", item)
        text = html.unescape(t.get("full_text") or t.get("text") or "")
        entities = t.get("entities", {})
        for u in entities.get("urls", []):  # t.co の短縮URLを元のURLに戻す
            text = text.replace(u["url"], u.get("expanded_url") or u["url"])
        media = (t.get("extended_entities") or entities).get("media", [])
        for m in media:  # 画像の t.co は本文から消す
            text = text.replace(m["url"], "")
        created_at, has_time = _parse_date(t.get("created_at", ""))
        posts.append(
            Post(
                text=text.strip(),
                created_at=created_at,
                has_time=has_time,
                id=str(t.get("id_str") or t.get("id") or ""),
                likes=_int(t.get("favorite_count")),
                reposts=_int(t.get("retweet_count")),
                media=len(media),
                is_reply=bool(t.get("in_reply_to_status_id_str") or t.get("in_reply_to_status_id")),
                is_repost=text.startswith("RT @"),
                source=Path(path).name,
            )
        )
    return posts


def _load_csv(path) -> list:
    posts = []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            values = {}
            for header, value in row.items():
                key = _column(header or "")
                if key and key not in values and value is not None and value.strip() != "":
                    values[key] = value.strip()
            if values.get("text"):
                posts.append(_post_from_values(values, Path(path).name))
    return posts


def _column(header: str):
    return CSV_COLUMNS.get(re.sub(r"\s+", "", header).lower())


def _post_from_values(values: dict, source: str) -> Post:
    created_at, has_time = _parse_date(values.get("created_at", ""))
    text = values["text"]
    return Post(
        text=text,
        created_at=created_at,
        has_time=has_time,
        id=values.get("id", ""),
        url=values.get("url", ""),
        likes=_int(values.get("likes")),
        reposts=_int(values.get("reposts")),
        replies=_int(values.get("replies")),
        bookmarks=_int(values.get("bookmarks")),
        impressions=_int(values.get("impressions")),
        media=_int(values.get("media")),
        is_reply=text.startswith("@"),
        is_repost=text.startswith("RT @"),
        source=source,
    )


def _parse_date(text: str):
    """日時を日本時間で返す。（日時, 時刻まで分かるか）。タイムゾーンがなければ日本時間とみなす。"""
    text = (text or "").strip()
    if not text:
        return None, False
    for formats, has_time in ((_DATE_FORMATS, True), (_DATE_ONLY_FORMATS, False)):
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
            except ValueError:
                continue
            dt = dt.replace(tzinfo=JST) if dt.tzinfo is None else dt.astimezone(JST)
            return dt, has_time
    raise ValueError(f"日時が読めません: {text}")


def _int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(float(str(value).replace(",", "")))

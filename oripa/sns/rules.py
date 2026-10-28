"""投稿の種類・NGワード・ハッシュタグなどのルール（sns/rules.toml）の読み込み。"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RULES = Path("sns") / "rules.toml"


@dataclass
class PostType:
    name: str
    keywords: list
    purpose: str = ""


@dataclass
class WordRule:
    words: list
    reason: str


@dataclass
class Rules:
    account: str = ""
    url: str = ""
    max_length: int = 280
    max_hashtags: int = 3
    hashtags: list = field(default_factory=list)
    types: list = field(default_factory=list)
    ng: list = field(default_factory=list)  # 使わない言葉（エラー）
    caution: list = field(default_factory=list)  # 使うときに確かめる言葉（注意）
    templates_dir: Path = Path("sns") / "templates"

    def classify(self, text: str) -> str:
        """キーワードが一番多く当たった種類を返す。同点ならファイルで先に書いた種類。"""
        best, best_score = "その他", 0
        for post_type in self.types:
            score = sum(1 for kw in post_type.keywords if kw.lower() in text.lower())
            if score > best_score:
                best, best_score = post_type.name, score
        return best

    def type_names(self) -> list:
        return [t.name for t in self.types] + ["その他"]


def load_rules(path=DEFAULT_RULES) -> Rules:
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    account = data.get("account", {})
    post = data.get("post", {})
    return Rules(
        account=account.get("handle", ""),
        url=account.get("url", ""),
        max_length=int(post.get("max_length", 280)),
        max_hashtags=int(post.get("max_hashtags", 3)),
        hashtags=list(post.get("hashtags", [])),
        types=[PostType(t["name"], list(t.get("keywords", [])), t.get("purpose", "")) for t in data.get("types", [])],
        ng=[WordRule(list(r["words"]), r["reason"]) for r in data.get("ng", [])],
        caution=[WordRule(list(r["words"]), r["reason"]) for r in data.get("caution", [])],
        templates_dir=path.parent / post.get("templates", "templates"),
    )

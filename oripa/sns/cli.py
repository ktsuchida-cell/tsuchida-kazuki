"""コマンドライン:

python -m oripa.sns analyze [sns/posts/]                         過去の投稿を分析 → docs/sns/投稿分析.md
python -m oripa.sns draft packs/xxx.toml --type 新ガチャ告知      パックから投稿のたたき台を作る
python -m oripa.sns check 下書き.txt [--pack packs/xxx.toml]      文字数・NGワード・数字の食い違いを確かめる
"""

import argparse
import sys
from pathlib import Path

from ..builder import build_pack
from ..config import load_config
from ..model import PackError
from .analyze import analyze
from .check import ERROR, check_post, format_issues
from .compose import base_context, fill, load_templates, pack_context
from .posts import load_posts, load_text
from .rules import DEFAULT_RULES, load_rules
from .xtext import weighted_length

DEFAULT_POSTS = Path("sns") / "posts"
DEFAULT_REPORT = Path("docs") / "sns" / "投稿分析.md"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m oripa.sns", description="メタオリパのX投稿の分析・たたき台・チェック"
    )
    parser.add_argument("--rules", default=DEFAULT_RULES, help=f"投稿ルール（既定 {DEFAULT_RULES}）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="過去の投稿を分析して Markdown にまとめる")
    p.add_argument("paths", nargs="*", default=[DEFAULT_POSTS], help=f"投稿データ（既定 {DEFAULT_POSTS}/）")
    p.add_argument("-o", "--output", default=DEFAULT_REPORT, help=f"書き出し先（既定 {DEFAULT_REPORT}）")

    p = sub.add_parser("draft", help="テンプレートから投稿のたたき台を作る")
    p.add_argument("pack", nargs="?", help="パック定義ファイル（.toml）。プレゼント企画などパックを使わないときは省略")
    p.add_argument("--type", required=True, help="投稿の種類（sns/templates/<種類>.txt）")
    p.add_argument("--url", help="載せるURL（既定は rules.toml のサイトURL）")
    p.add_argument("--remaining", type=int, help="残り口数（{remaining} に入る）")
    p.add_argument(
        "--set", action="append", default=[], metavar="項目=値", help="テンプレートの項目を埋める（例 card=ピカチュウ）"
    )
    p.add_argument("-o", "--output", help="たたき台を書き出すファイル（check でそのまま確かめられる形式）")

    p = sub.add_parser("check", help="投稿文を確かめる（`---` だけの行で区切って何件でも）")
    p.add_argument("drafts", help="投稿文のテキストファイル")
    p.add_argument("--pack", help="数字を突き合わせるパック定義ファイル（.toml）")
    p.add_argument("--remaining", type=int, help="残り口数（本文の「残り◯口」と突き合わせる）")

    args = parser.parse_args(argv)
    rules = load_rules(args.rules)
    try:
        return {"analyze": _analyze, "draft": _draft, "check": _check}[args.command](args, rules)
    except (PackError, FileNotFoundError, ValueError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


def _analyze(args, rules) -> int:
    posts = load_posts(args.paths)
    if not posts:
        raise ValueError(
            f"{' '.join(map(str, args.paths))} に投稿データがありません（書き出し方は docs/sns/README.md）。"
        )
    sources = sorted({p.source for p in posts})
    report = analyze(posts, rules, [f"{s}（{sum(p.source == s for p in posts):,}件）" for s in sources])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"{len(posts):,}件を読みました。書き出し: {output}")
    return 0


def _draft(args, rules) -> int:
    result = build_pack(load_config(args.pack)) if args.pack else None
    context = pack_context(result, rules, args.url) if result else base_context(rules, args.url)
    if args.remaining is not None:
        context["remaining"] = f"{args.remaining:,}"
    for item in args.set:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"--set は 項目=値 の形で書いてください: {item}")
        context[key.strip()] = value.strip()

    drafts = [fill(t, context) for t in load_templates(rules, args.type)]
    for i, text in enumerate(drafts, 1):
        print(f"■ 案{i}（{weighted_length(text)}/{rules.max_length}）\n{text}\n")
        print(format_issues(check_post(text, rules, result, args.remaining)) + "\n")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n---\n".join(drafts) + "\n", encoding="utf-8")
        print(f"書き出し: {output}")
    return 0


def _check(args, rules) -> int:
    result = build_pack(load_config(args.pack)) if args.pack else None
    has_error = False
    for i, post in enumerate(load_text(args.drafts), 1):
        issues = check_post(post.text, rules, result, args.remaining)
        has_error |= any(issue.level == ERROR for issue in issues)
        first = post.text.splitlines()[0]
        print(f"■ {i}件目（{weighted_length(post.text)}/{rules.max_length}）{first}")
        print(format_issues(issues) + "\n")
    return 1 if has_error else 0

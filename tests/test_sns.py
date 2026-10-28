import json
from datetime import datetime
from pathlib import Path

import pytest

from oripa import Card, Filler, PackConfig, build_pack, load_config
from oripa.sns import analyze, check_post, fill, load_posts, load_rules, load_text, pack_context, weighted_length
from oripa.sns.check import CAUTION, ERROR
from oripa.sns.cli import main
from oripa.sns.posts import JST
from oripa.sns.xtext import emojis, hashtags, mentions

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "sns" / "rules.toml"
EXAMPLES = ROOT / "packs" / "examples"


@pytest.fixture
def rules():
    return load_rules(RULES)


@pytest.fixture
def psa10_pack():
    """当たりが全部PSA10のパック（名前と目玉が長めで、テンプレートの文字数を確かめるのに使う）。"""
    cards = [
        Card("S爆", "カメックスEX SR PSA10 [CP6 092/087]", 348_000),
        Card("S爆", "カイリューEX SR PSA10 [CP6 098/087]", 245_140),
        Card("S爆", "ゲンガー マスターボールミラー PSA10 [SV2a 094/165]", 178_000),
        Card("S", "ミュウex SAR PSA10 [SV2a 205/165]", 72_800, count=2),
    ]
    fillers = [Filler("A", 2000, "auto"), Filler("B", 100, "rest")]
    config = PackConfig(
        "初代151 PSA10ガチャ（1,000円課金）",
        1000,
        5000,
        cards,
        fillers,
        target_return_rate=1.05,
        max_return_rate=1.1,
        seed=1,
    )
    return build_pack(config)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("abc", 3),
        ("あいう", 6),
        ("https://metaoripa.com/oripa/pokemon/12345?ref=x", 23),
        ("見てね https://metaoripa.com/", 6 + 1 + 23),
        ("metaoripa.com で公開", 23 + 1 + 6),
        ("🎉", 2),
        ("👨‍👩‍👧", 2),
        ("🙏🏻", 2),
        ("1️⃣", 2),
        ("🇯🇵", 2),
        ("㊗️", 2),
        ("“PSA10”", 7),  # 引用符は1で数える
    ],
)
def test_weighted_length_counts_like_x(text, expected):
    assert weighted_length(text) == expected


def test_extracts_hashtags_mentions_and_emojis():
    text = "🎉当選報告🎉 #ポケカ #オリパ\n①@metaoripa_ をフォロー ▼今すぐ"
    assert hashtags(text) == ["#ポケカ", "#オリパ"]
    assert mentions(text) == ["@metaoripa_"]
    assert emojis(text) == ["🎉", "🎉", "▼"]


def test_loads_x_archive(tmp_path):
    tweets = [
        {
            "tweet": {
                "id_str": "1",
                "created_at": "Fri Oct 23 10:00:00 +0000 2026",
                "full_text": "新ガチャ公開 &amp; 当選報告 https://t.co/abc https://t.co/img",
                "favorite_count": "12",
                "retweet_count": "3",
                "entities": {"urls": [{"url": "https://t.co/abc", "expanded_url": "https://metaoripa.com/x"}]},
                "extended_entities": {"media": [{"url": "https://t.co/img"}]},
            }
        },
        {
            "tweet": {
                "id_str": "2",
                "created_at": "Fri Oct 23 11:00:00 +0000 2026",
                "full_text": "@someone ありがとうございます",
                "in_reply_to_status_id_str": "9",
                "favorite_count": "0",
                "retweet_count": "0",
            }
        },
    ]
    path = tmp_path / "tweets.js"
    path.write_text("window.YTD.tweets.part0 = " + json.dumps(tweets, ensure_ascii=False), encoding="utf-8")
    first, second = load_posts([path])
    assert first.text == "新ガチャ公開 & 当選報告 https://metaoripa.com/x"
    assert first.created_at == datetime(2026, 10, 23, 19, 0, tzinfo=JST)
    assert (first.has_time, first.likes, first.reposts, first.media, first.is_reply) == (True, 12, 3, 1, False)
    assert second.is_reply


def test_loads_csv_with_english_or_japanese_headers(tmp_path):
    en = tmp_path / "analytics.csv"
    en.write_text(
        "Post id,Date,Post text,Post Link,Impressions,Likes,Reposts,Replies,Bookmarks\n"
        '10,"Fri, Oct 23, 2026",新ガチャ公開,https://x.com/metaoripa_/status/10,"1,000",20,5,1,4\n',
        encoding="utf-8",
    )
    ja = tmp_path / "手入力.csv"
    ja.write_text("日時,本文,いいね,リポスト,表示回数\n2026/10/24 19:30,当選報告,8,2,500\n", encoding="utf-8-sig")
    a, b = load_posts([en, ja])
    assert (a.id, a.impressions, a.engagements, a.has_time) == ("10", 1000, 30, False)
    assert a.engagement_rate == pytest.approx(0.03)
    assert (b.text, b.created_at.hour, b.has_time, b.likes, b.impressions) == ("当選報告", 19, True, 8, 500)


def test_loads_text_blocks_with_metadata(tmp_path):
    path = tmp_path / "posts.txt"
    path.write_text("日時: 2026-10-24 19:00\nいいね: 5\n\n1行目\n2行目\n---\n締切：10/31\n本文\n", encoding="utf-8")
    first, second = load_text(path)
    assert (first.text, first.likes, first.created_at.day) == ("1行目\n2行目", 5, 24)
    assert second.text == "締切：10/31\n本文"  # 締切は項目名ではないので本文に残る


def test_classify_picks_type_with_most_keywords(rules):
    assert rules.classify("【新ガチャ公開】ドラゴン PSA10ガチャ 販売開始") == "新ガチャ告知"
    assert rules.classify("㊗️当選おめでとうございます！") == "当選報告"
    assert rules.classify("フォロー＆リポストで抽選プレゼント") == "プレゼント企画"
    assert rules.classify("おはようございます") == "その他"


def test_check_flags_ng_words_length_and_placeholders(rules):
    issues = check_post("これで稼げる！{card} が当たる" + "あ" * 140, rules)
    errors = [i.message for i in issues if i.level == ERROR]
    assert any("文字数" in m for m in errors)
    assert any("{card}" in m for m in errors)
    assert any("稼げる" in m for m in errors)
    assert [i.level for i in check_post("PSA10確定オリパ", rules)] == [CAUTION]


def test_check_numbers_against_pack(rules):
    result = build_pack(load_config(EXAMPLES / "ad_1in4_1000pt.toml"))  # 1,000PT×10,000口・還元率98.885%・アド1/4
    ok = "1回1,000PT／全10,000口\n還元率98.8%・アド確率1/4"
    assert check_post(ok, rules, result) == []
    bad = "1回 500PT・全１０,０００口\n還元率99%・アド確率 1/3\n全部PSA10"
    messages = [i.message for i in check_post(bad, rules, result)]
    assert any("1回 500" in m for m in messages)
    assert any("還元率 99%" in m for m in messages)
    assert any("1/3" in m for m in messages)
    assert any("PSA10" in m for m in messages)
    assert not any("全10,000口" in m for m in messages)  # 全角数字も読む
    assert [i.level for i in check_post("残り300口", rules, result)] == [CAUTION]
    assert check_post("残り300口", rules, result, remaining=300) == []


def test_pack_context_rounds_in_the_safe_direction(rules, psa10_pack):
    ctx = pack_context(psa10_pack, rules)
    m = psa10_pack.metrics
    assert (m.ad_count, m.return_rate) == (1803, pytest.approx(1.04984))  # 当たり5枚＋A 1,798枚
    assert ctx["ad_odds"] == "1/2.8"  # 1/2.773… を当たりやすく見せないよう切り上げ
    assert ctx["return_rate"] == "104.9"  # 104.984% を切り捨て
    assert ctx["top"] == "カメックスEX SR PSA10"  # [CP6 092/087] は外す
    assert ctx["hits_line"] == "当たり5枚は全部PSA10"
    assert ctx["top_tier"].splitlines() == [
        "・カメックスEX SR PSA10",
        "・カイリューEX SR PSA10",
        "・ゲンガー マスターボールミラー PSA10",
    ]
    assert ctx["lineup"].splitlines()[-1] == "・ミュウex SAR PSA10 ×2"
    assert ctx["ad_line"] == "アド確率 1/2.8・最低保証 100PT"
    assert fill("{name}\n\n\n\n{card}", ctx) == "初代151 PSA10ガチャ（1,000円課金）\n\n{card}"


def test_pack_context_for_charge_gacha_with_one_hit(rules):
    # 課金ガチャは全口が1回の価格以上なので、アド確率は出さない
    cards = [Card("S爆", "カメックスEX SR PSA10 [CP6 092/087]", 348_000)]
    config = PackConfig("課金", 1000, 5200, cards, [Filler("B", 1000, "rest")], max_return_rate=1.1, charge_gacha=True)
    ctx = pack_context(build_pack(config), rules)
    assert (ctx["hits_line"], ctx["ad_line"]) == ("当たりはPSA10", "最低保証 1,000PT")


def test_templates_fit_and_pass_check(rules, psa10_pack):
    result = psa10_pack
    ctx = pack_context(result, rules)
    for path in rules.templates_dir.glob("*.txt"):
        for template in path.read_text(encoding="utf-8").split("\n---\n"):
            text = fill(template, {**ctx, "remaining": "1,200"})
            assert weighted_length(text) <= rules.max_length, path.name
            assert not [i for i in check_post(text, rules, result) if i.level == ERROR and "埋まって" not in i.message]


def _sample_posts():
    def post(text, day, hour, likes, reposts):
        from oripa.sns import Post

        return Post(text, datetime(2026, 10, day, hour, tzinfo=JST), True, likes=likes, reposts=reposts, media=1)

    return [
        post("【新ガチャ公開】ドラゴン\n\n1回5,000PT\nhttps://metaoripa.com/\n#オリパ #ポケカ", 20, 19, 30, 10),
        post("【新ガチャ公開】ブイズ\n\n1回100PT\nhttps://metaoripa.com/\n#オリパ", 21, 12, 10, 2),
        post("㊗️当選おめでとうございます㊗️\nカメックスEX\n#オリパ", 22, 21, 50, 5),
        post("フォロー＆リポストで抽選プレゼント🎁\n締切 10/31", 23, 20, 80, 60),
        post("@user ありがとうございます", 23, 21, 1, 0),
    ]


def test_analyze_report(rules):
    posts = _sample_posts()
    posts[-1].is_reply = True
    report = analyze(posts, rules, ["sample.txt（5件）"])
    assert "分析した投稿: 4件（返信 1件・リポスト 0件は除いた）" in report
    assert "| 新ガチャ告知 | 2 | 50% |" in report
    assert "| 19時 | 1 | 40 |" in report
    assert "【新ガチャ公開】 2" in report
    assert "#オリパ 3" in report
    assert "| 【新ガチャ公開】ドラゴン | 1 |" in report
    # 反応1位はプレゼント企画（いいね＋リポスト 140）
    top = report.split("## 4.")[1]
    assert top.index("プレゼント企画") < top.index("当選報告")
    assert "ありがとうございます" not in report


def test_cli_draft_and_check(tmp_path, capsys):
    out = tmp_path / "draft.txt"
    pack = str(EXAMPLES / "ad_1in4_1000pt.toml")
    assert main(["--rules", str(RULES), "draft", pack, "--type", "新ガチャ告知", "-o", str(out)]) == 0
    assert "1回1,000PT／全10,000口" in capsys.readouterr().out
    assert main(["--rules", str(RULES), "check", str(out), "--pack", pack]) == 0
    out.write_text("1回1,000PT 必ず当たる\n", encoding="utf-8")
    assert main(["--rules", str(RULES), "check", str(out), "--pack", pack]) == 1

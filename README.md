# メタオリパ パック構築ツール

カードリスト（賞・名称・仕入れ価格）から、「メタオリパ 構築」スプレッドシートと同じ形式の構築シートを作る。
PT計算・ハズレ枠の枚数・当選番号・還元率・概算収支までを自動で出し、1本2時間かかっていたパック作成を30分程度にするのが目的。

## 使い方

```
pip install openpyxl            # 初回のみ
cp packs/template.toml packs/2026-10-07_xxx.toml   # カードを書き込む
python -m oripa packs/2026-10-07_xxx.toml          # → out/2026-10-07_xxx.xlsx
```

- 出力の xlsx は「構築」シート（構築スプレッドシートと同じ列・数式入り）と「当選番号」シート（登録用）の2枚。
- 還元率が上限（既定100%）を超えるとエラーで止まる。
- 例: `python -m oripa packs/examples/pikachu_240.toml`（過去の「シート26」を再現）

ルールと手順は [docs/パック作成手順.md](docs/パック作成手順.md)。
Claude Code に「このカードでパックを作って」と頼むと `.claude/skills/oripa-pack` の手順で作る。

## X の投稿（@metaoripa_）

過去の投稿の分析と、パックの構築結果から告知文のたたき台を作る。

```
python -m oripa.sns analyze                                       # sns/posts/ の投稿 → docs/sns/投稿分析.md
python -m oripa.sns draft packs/2026-10-07_xxx.toml --type 新ガチャ告知   # 数字入りのたたき台
python -m oripa.sns check out/sns/xxx.txt --pack packs/2026-10-07_xxx.toml  # 文字数・NGワード・数字の食い違い
```

仕組みと投稿データの入れ方は [docs/sns/README.md](docs/sns/README.md)。
Claude Code に「このパックの告知文を作って」「Xの投稿を分析して」と頼むと `.claude/skills/x-post` の手順でやる。

## テスト

```
pip install pytest formulas
python -m pytest
```

過去パック（シート26・1/4・1/100 高額2つ）の構築PT・還元率・概算収支が元シートと一致すること、
xlsx の数式を再計算した値がツールの計算と一致することを確認している。

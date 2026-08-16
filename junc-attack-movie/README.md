# JUNC アタックムービー制作

愛媛の経営者団体「JUNC」向けアタックムービーを、AI生成ツールを活用して制作するための作業場所です。
背景・方針は [`CLAUDE.md`](./CLAUDE.md) と [`docs/meeting-notes-2026-08-16.md`](./docs/meeting-notes-2026-08-16.md) を参照してください。

## セットアップ

```bash
cd junc-attack-movie
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 実際のAPIキーを記入する（.envはコミットしない）
```

`pydub` は音声処理に `ffmpeg` を使うため、未インストールの場合は別途入れてください
（例: `apt install ffmpeg` / `brew install ffmpeg`）。

## ディレクトリ構成

```
junc-attack-movie/
├── CLAUDE.md                        # プロジェクトの方向性・BGM方針・現状ステータス
├── docs/meeting-notes-2026-08-16.md # 選定MTGの構造化議事録
├── config/media_models.json         # 使うAI生成モデルのレジストリ（API未設定）
├── .env.example                     # APIキーのテンプレート
├── scripts/
│   ├── bgm_stitch.py                # BGM候補曲から良い部分を抜き出して1本に結合
│   └── generate_media.py            # 複数モデルへの一括バリエーション生成
├── assets/
│   ├── bgm_candidates/              # BGM候補曲を置く場所
│   └── footage/                     # 実写素材を置く場所
└── out/                             # 生成物の出力先
```

## BGMを組み合わせる

```bash
python scripts/bgm_stitch.py \
  --tracks assets/bgm_candidates/candidate1.mp3 assets/bgm_candidates/movie_theme.mp3 \
  --duration 20 \
  --output out/junc_bgm_v1.mp3
```

各曲の中で最もエネルギーの高い（盛り上がっている）区間を自動検出して繋ぎます。開始位置を手動指定
したい場合は `--config` でJSONファイルを渡してください（スクリプト冒頭のdocstring参照）。

## 画像・動画をAIで量産する

`config/media_models.json` の `base_url` と `.env` のAPIキーを設定したうえで:

```bash
python scripts/generate_media.py \
  --prompt "交差点を俯瞰で捉えた、尖ったグランジ系のロゴアニメーション" \
  --type video \
  --models minimax-video kling-video \
  --variations 4 \
  --output-dir out/video_variations
```

**注意**: `generate_media.py` の `build_request()` はプロバイダーごとのリクエスト仕様が未実装の
状態です（契約するサービスによってAPI仕様が変わるため）。契約後、実際のAPIドキュメントを見ながら
プロバイダーごとの分岐を実装してください。

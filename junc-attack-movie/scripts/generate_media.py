#!/usr/bin/env python3
"""
generate_media.py — 同一プロンプトを複数のAI生成モデルに投げてバリエーションを量産する。

会議での方針: 同じプロンプトでも各社モデルで出力の質が違うため、比較しながら早くイメージを
掴み、そこから手動での仕上げ・本編集に進む。1モデルにつき複数バリエーションを一度に生成できる。

セットアップ:
    1. .env.example を .env にコピーし、契約したサービスのAPIキーを設定する
    2. config/media_models.json の各モデルエントリに base_url を設定する
       （契約先未確定のため、URLは空のまま用意している。ここをAIに勝手に埋めさせないこと）
    3. build_request() 内の該当プロバイダー分岐に、実際のリクエスト仕様を実装する
       （プロバイダーごとにエンドポイント仕様が異なるため、契約後にドキュメントを見て実装する）

使い方:
    python scripts/generate_media.py \\
        --prompt "交差点を俯瞰で捉えた、尖ったグランジ系のロゴアニメーション" \\
        --type video \\
        --models minimax-video kling-video \\
        --variations 4 \\
        --output-dir out/video_variations
"""
import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).parent.parent / "config" / "media_models.json"


def load_registry() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def resolve_endpoint(model: dict, gateway: dict) -> tuple[str, str]:
    """(base_url, api_key) を返す。統合ゲートウェイが有効ならそちらを優先する。"""
    if gateway.get("enabled") and gateway.get("base_url"):
        api_key = os.environ.get(gateway["api_key_env"], "")
        return gateway["base_url"], api_key

    base_url = model.get("base_url", "")
    api_key = os.environ.get(model["api_key_env"], "")
    return base_url, api_key


def build_request(model: dict, prompt: str, variation_index: int) -> dict:
    """
    プロバイダーごとのリクエストペイロードを組み立てる。
    契約前でエンドポイント仕様が未確定なため、ここはプロバイダーごとに実装が必要な TODO。
    """
    provider = model["provider"]
    raise NotImplementedError(
        f"'{provider}' 用のリクエスト仕様が未実装です。"
        f" 契約したサービスのAPIドキュメントを見て build_request() にこの分岐を追加してください。"
    )


def generate_one(model: dict, gateway: dict, prompt: str, variation_index: int, output_dir: Path) -> None:
    base_url, api_key = resolve_endpoint(model, gateway)
    if not base_url:
        print(f"  [skip] {model['id']}: base_url が未設定です（config/media_models.json を確認）")
        return
    if not api_key:
        print(f"  [skip] {model['id']}: APIキーが未設定です（.env を確認）")
        return

    payload = build_request(model, prompt, variation_index)
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.post(base_url, json=payload, headers=headers, timeout=300)
    response.raise_for_status()

    out_path = output_dir / f"{model['id']}_{variation_index:02d}.json"
    out_path.write_text(response.text, encoding="utf-8")
    print(f"  [ok] {model['id']} #{variation_index} -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompt", required=True, help="全モデル共通で使うプロンプト")
    parser.add_argument("--type", choices=["image", "video", "music"], required=True, help="生成する媒体の種類")
    parser.add_argument("--models", nargs="+", required=True, help="config/media_models.json のモデルid（例: minimax-video kling-video）")
    parser.add_argument("--variations", type=int, default=1, help="モデルごとの生成本数（デフォルト1）")
    parser.add_argument("--output-dir", default="out", help="出力先ディレクトリ")
    args = parser.parse_args()

    load_dotenv()
    registry = load_registry()
    gateway = registry["unified_gateway"]
    models_by_id = {m["id"]: m for m in registry["models"]}

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for model_id in args.models:
        model = models_by_id.get(model_id)
        if model is None:
            print(f"  [skip] 未登録のモデルid: {model_id}")
            continue
        if model["type"] != args.type:
            print(f"  [skip] {model_id} は type={model['type']} で、指定した --type {args.type} と一致しません")
            continue

        print(f"{model_id}: {args.variations}本生成します...")
        for i in range(1, args.variations + 1):
            try:
                generate_one(model, gateway, args.prompt, i, output_dir)
            except NotImplementedError as e:
                print(f"  [todo] {e}")
                break
            except requests.RequestException as e:
                print(f"  [error] {model_id} #{i}: {e}")


if __name__ == "__main__":
    main()

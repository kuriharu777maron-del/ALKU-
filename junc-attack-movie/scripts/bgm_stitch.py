#!/usr/bin/env python3
"""
bgm_stitch.py — 複数のBGM候補曲から「おいしい部分」を抜き出し、1本のBGMに繋ぐ。

会議での方針: 1曲をそのまま使うのではなく、曲ごとに良い部分（盛り上がっていく箇所など）を
切り出して、シーン展開に合わせて1本のBGMとして再構成する。

使い方（シンプルモード。各曲から自動で一番盛り上がる区間を検出して繋ぐ）:
    python scripts/bgm_stitch.py \\
        --tracks assets/bgm_candidates/candidate1.mp3 assets/bgm_candidates/movie_theme.mp3 \\
        --duration 20 \\
        --output out/junc_bgm_v1.mp3

使い方（configモード。曲ごとに開始位置・長さを手動指定、または自動検出を混在させる）:
    python scripts/bgm_stitch.py --config config/bgm_plan.json --output out/junc_bgm_v1.mp3

configの例:
    [
      {"path": "assets/bgm_candidates/candidate1.mp3", "duration": 15},
      {"path": "assets/bgm_candidates/movie_theme.mp3", "start": 42.0, "duration": 25}
    ]
    start を省略すると、その曲の中で最も盛り上がっている区間を自動検出する。
"""
import argparse
import json
import sys
from pathlib import Path

import librosa
import numpy as np
from pydub import AudioSegment


def find_best_segment(path: str, duration: float) -> float:
    """曲の中で最もエネルギーが高い（盛り上がっている）duration秒の区間の開始秒を返す。"""
    y, sr = librosa.load(path, sr=None, mono=True)
    total_duration = len(y) / sr
    if duration >= total_duration:
        return 0.0

    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

    n = min(len(rms), len(onset_env))
    rms, onset_env = rms[:n], onset_env[:n]

    def normalize(x):
        rng = x.max() - x.min()
        return (x - x.min()) / rng if rng > 0 else np.zeros_like(x)

    excitement = normalize(rms) + normalize(onset_env)

    frames_per_window = max(1, int(duration * sr / hop_length))
    if frames_per_window >= n:
        return 0.0

    window_sums = np.convolve(excitement, np.ones(frames_per_window), mode="valid")
    best_frame = int(np.argmax(window_sums))
    best_start_sec = librosa.frames_to_time(best_frame, sr=sr, hop_length=hop_length)

    return float(min(best_start_sec, total_duration - duration))


def load_segment(path: str, start: float, duration: float, peak_target_db: float | None = None) -> AudioSegment:
    audio = AudioSegment.from_file(path)
    start_ms = int(start * 1000)
    end_ms = int((start + duration) * 1000)
    segment = audio[start_ms:end_ms]
    if peak_target_db is not None:
        # 曲ごとにマスタリングの音圧が違うため、ピークを揃えてから繋ぐ。
        # これをやらないと (1) 曲間で音量がガクッと変わる (2) クロスフェード中に
        # 2曲が重なって0dBFSを超え、クリッピング(音割れ)することがある。
        segment = segment.apply_gain(peak_target_db - segment.max_dBFS)
    return segment


def build_config_from_tracks(tracks: list[str], duration: float) -> list[dict]:
    return [{"path": t, "duration": duration} for t in tracks]


def stitch(config: list[dict], crossfade_ms: int, peak_target_db: float | None = None) -> AudioSegment:
    result = None
    for entry in config:
        path = entry["path"]
        duration = float(entry["duration"])
        start = entry.get("start")
        if start is None:
            start = find_best_segment(path, duration)
            print(f"  [auto] {Path(path).name}: {start:.1f}s から {duration:.1f}秒を使用")
        else:
            start = float(start)
            print(f"  [manual] {Path(path).name}: {start:.1f}s から {duration:.1f}秒を使用")

        segment = load_segment(path, start, duration, peak_target_db)
        if result is None:
            result = segment
        else:
            result = result.append(segment, crossfade=min(crossfade_ms, len(segment) - 1, len(result) - 1))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tracks", nargs="+", help="シンプルモード: BGM候補曲のパスを順番に指定")
    parser.add_argument("--duration", type=float, default=20.0, help="シンプルモード: 各曲から抜き出す秒数（デフォルト20秒）")
    parser.add_argument("--config", help="configモード: 曲ごとのstart/durationをJSONファイルで指定")
    parser.add_argument("--crossfade", type=int, default=200, help="曲間のクロスフェード時間(ms)。デフォルト200（短めのハードカット寄り）")
    parser.add_argument("--peak-normalize-db", type=float, default=-3.0, help="各セグメントのピーク音量をこの値(dBFS)に揃えてから繋ぐ。曲間の音量ジャンプとクロスフェード時のクリッピングを防ぐ。無効化するには --no-normalize を指定")
    parser.add_argument("--no-normalize", action="store_true", help="ピーク音量の正規化を行わない")
    parser.add_argument("--output", required=True, help="出力ファイルパス（例: out/junc_bgm_v1.mp3）")
    args = parser.parse_args()

    if not args.tracks and not args.config:
        parser.error("--tracks か --config のどちらかを指定してください")

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = build_config_from_tracks(args.tracks, args.duration)

    for entry in config:
        if not Path(entry["path"]).exists():
            sys.exit(f"エラー: ファイルが見つかりません: {entry['path']}")

    peak_target = None if args.no_normalize else args.peak_normalize_db
    print(f"{len(config)}曲から抜き出して結合します...")
    result = stitch(config, args.crossfade, peak_target)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.export(out_path, format=out_path.suffix.lstrip(".") or "mp3")
    print(f"完成: {out_path} ({len(result) / 1000:.1f}秒)")


if __name__ == "__main__":
    main()

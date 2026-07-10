from __future__ import annotations

from pathlib import Path

from ai_media_lab.common.ffmpeg_service import FFmpegRunner


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "sample_assets" / "sample-reel.mp4"
    runner = FFmpegRunner()
    if not runner.available():
        raise SystemExit("FFmpeg is not available. Install dependencies with pip install -e . first.")
    runner.run(
        [
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=30:size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=30",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output),
        ],
        timeout=120,
    )
    print(output)


if __name__ == "__main__":
    main()


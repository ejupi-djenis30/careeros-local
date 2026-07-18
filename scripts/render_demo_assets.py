"""Build lightweight GitHub preview assets from real CareerOS screenshots."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)


def render_gif(frames: list[Path], output: Path, *, width: int = 960) -> None:
    rendered: list[Image.Image] = []
    for frame in frames:
        with Image.open(frame) as source:
            rendered.append(_fit(source, width).quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered[0].save(
        output,
        save_all=True,
        append_images=rendered[1:],
        duration=[1800, *([1500] * (len(rendered) - 1))],
        loop=0,
        optimize=True,
        disposal=2,
    )


def render_poster(source: Path, output: Path, *, width: int = 1280) -> None:
    with Image.open(source) as image:
        poster = _fit(image, width).convert("RGBA")
    overlay = Image.new("RGBA", poster.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    center_x, center_y = poster.width // 2, poster.height // 2
    radius = max(46, poster.width // 18)
    draw.ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        fill=(12, 16, 14, 220),
        outline=(185, 242, 124, 255),
        width=max(3, poster.width // 400),
    )
    triangle = [
        (center_x - radius // 4, center_y - radius // 2),
        (center_x - radius // 4, center_y + radius // 2),
        (center_x + radius // 2, center_y),
    ]
    draw.polygon(triangle, fill=(185, 242, 124, 255))
    label = "WATCH THE 30-SECOND PRODUCT TOUR"
    font = _font(max(18, poster.width // 52), bold=True)
    box = draw.textbbox((0, 0), label, font=font)
    text_width = box[2] - box[0]
    text_y = poster.height - max(62, poster.height // 10)
    padding_x, padding_y = 22, 12
    draw.rounded_rectangle(
        (
            (poster.width - text_width) // 2 - padding_x,
            text_y - padding_y,
            (poster.width + text_width) // 2 + padding_x,
            text_y + (box[3] - box[1]) + padding_y,
        ),
        radius=18,
        fill=(12, 16, 14, 225),
    )
    draw.text(((poster.width - text_width) // 2, text_y), label, font=font, fill=(241, 246, 242, 255))
    Image.alpha_composite(poster, overlay).convert("RGB").save(output, quality=92, optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", nargs="+", type=Path, required=True)
    parser.add_argument("--gif", type=Path, required=True)
    parser.add_argument("--poster", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if len(args.frames) < 2:
        raise SystemExit("At least two screenshots are required")
    missing = [str(path) for path in args.frames if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing screenshot(s): {', '.join(missing)}")
    render_gif(args.frames, args.gif)
    render_poster(args.frames[0], args.poster)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

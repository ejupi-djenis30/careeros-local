from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from scripts.render_demo_assets import render_gif, render_poster


def _write_frame(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (320, 180), color).save(path)


def test_render_demo_assets_builds_a_multiframe_preview_and_poster() -> None:
    # Do not use pytest's tmp_path here. Some locked-down Windows environments
    # disable following the convenience symlinks created by pytest's temp-dir
    # factory, which can turn an otherwise passing test into a session error.
    with TemporaryDirectory(prefix="careeros-render-assets-") as directory:
        temporary_path = Path(directory)
        first = temporary_path / "first.png"
        second = temporary_path / "second.png"
        preview = temporary_path / "preview.gif"
        poster = temporary_path / "poster.jpg"
        _write_frame(first, (12, 16, 14))
        _write_frame(second, (185, 242, 124))

        render_gif([first, second], preview, width=160)
        render_poster(first, poster, width=320)

        with Image.open(preview) as image:
            assert image.size == (160, 90)
            assert image.n_frames == 2
        with Image.open(poster) as image:
            assert image.size == (320, 180)
            assert image.mode == "RGB"

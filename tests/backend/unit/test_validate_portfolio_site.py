import re
import struct
import zlib
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.validate_portfolio_site import (
    EDITORIAL_ASSET_SPECS,
    ROOT,
    PortfolioParser,
    _validate_png_asset,
    _validate_svg_asset,
    validate,
    validate_editorial_assets,
)


def _parse(fragment: str) -> PortfolioParser:
    parser = PortfolioParser()
    parser.feed(fragment)
    parser.close()
    return parser


def test_decorative_image_may_have_empty_alt_text():
    parser = _parse('<img src="mark.svg" alt="">')

    assert parser.images_missing_alt == []


def test_image_without_alt_attribute_is_reported():
    parser = _parse('<img src="product.png">')

    assert parser.images_missing_alt == [1]


def test_portfolio_media_preserves_its_intrinsic_ratio():
    errors = validate()

    assert errors == []

    css = (ROOT / "docs" / "site" / "styles.css").read_text(encoding="utf-8")
    for selector in (".product-window img", ".feature-image img"):
        declarations = css.split(f"{selector} {{", maxsplit=1)[1].split("}", maxsplit=1)[0]
        assert "height: auto;" in declarations
        assert "object-fit: contain;" in declarations


def test_trust_label_meets_small_text_contrast():
    css = (ROOT / "docs" / "site" / "styles.css").read_text(encoding="utf-8")
    root_declarations = css.split(":root {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    trust_declarations = (
        css.split(".trust-label {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    )

    assert "color: var(--muted);" in trust_declarations

    def read_hex_token(name: str) -> tuple[int, int, int]:
        match = re.search(rf"--{name}:\s*#([0-9a-fA-F]{{6}})", root_declarations)
        assert match is not None
        value = match.group(1)
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    def relative_luminance(color: tuple[int, int, int]) -> float:
        channels = []
        for channel in color:
            normalized = channel / 255
            channels.append(
                normalized / 12.92
                if normalized <= 0.04045
                else ((normalized + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    foreground = relative_luminance(read_hex_token("muted"))
    background = relative_luminance(read_hex_token("dark"))
    contrast = (max(foreground, background) + 0.05) / (
        min(foreground, background) + 0.05
    )

    assert contrast >= 4.5


def test_portfolio_keeps_one_real_product_demo():
    parser = _parse((ROOT / "docs" / "index.html").read_text(encoding="utf-8"))

    assert parser.video_count == 1
    assert any(
        attribute == "src" and reference == "assets/careeros-demo.webm"
        for attribute, reference, _line in parser.references
    )


def test_portfolio_presents_the_bounded_daily_action_agenda():
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    assert 'id="daily-action-agenda"' in html
    assert "Bounded, deterministic ordering with explicit omitted-item counts" in html
    assert "Local-day boundaries remain correct through daylight-saving changes" in html
    assert "Incomplete projections fail closed instead of guessing" in html
    assert "BOUNDED SQL · NO MODEL" in html


def test_portfolio_declares_strict_browser_policies():
    parser = _parse((ROOT / "docs" / "index.html").read_text(encoding="utf-8"))

    assert parser.referrer_policies == ["no-referrer"]
    assert len(parser.csp_policies) == 1
    policy = parser.csp_policies[0]
    assert "default-src 'none'" in policy
    assert "object-src 'none'" in policy
    assert "base-uri 'none'" in policy
    assert "'unsafe-inline'" not in policy
    assert "'unsafe-eval'" not in policy


def _write_changed_svg(tmp_path: Path, changed_source: str) -> Path:
    path = tmp_path / "asset.svg"
    path.write_text(changed_source, encoding="utf-8")
    return path


def _insert_png_chunk(payload: bytes, chunk_type: bytes, chunk_data: bytes) -> bytes:
    assert len(chunk_type) == 4
    offset = len(b"\x89PNG\r\n\x1a\n")
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        if payload[offset + 4 : offset + 8] == b"IEND":
            crc = zlib.crc32(chunk_type)
            crc = zlib.crc32(chunk_data, crc) & 0xFFFFFFFF
            chunk = (
                struct.pack(">I", len(chunk_data))
                + chunk_type
                + chunk_data
                + struct.pack(">I", crc)
            )
            return payload[:offset] + chunk + payload[offset:]
        offset += 12 + length
    raise AssertionError("fixture PNG does not contain IEND")


def _corrupt_first_idat_crc(payload: bytes) -> bytes:
    changed = bytearray(payload)
    offset = len(b"\x89PNG\r\n\x1a\n")
    while offset < len(changed):
        length = struct.unpack(">I", changed[offset : offset + 4])[0]
        if changed[offset + 4 : offset + 8] == b"IDAT":
            changed[offset + 8 + length] ^= 0x01
            return bytes(changed)
        offset += 12 + length
    raise AssertionError("fixture PNG does not contain IDAT")


def test_editorial_assets_pass_native_source_and_png_validation():
    assert validate_editorial_assets() == []


def test_editorial_svg_rejects_invalid_xml():
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.svg_name).read_text(encoding="utf-8")
    with TemporaryDirectory() as directory:
        path = _write_changed_svg(
            Path(directory), source.replace("</svg>", "", 1)
        )
        errors = _validate_svg_asset(path, spec)

    assert any("invalid XML" in error for error in errors)


def test_editorial_svg_requires_dimensions_viewbox_frame_and_center():
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.svg_name).read_text(encoding="utf-8")
    changed = source.replace(f'width="{spec.width}"', 'width="1"', 1)
    changed = changed.replace(
        f'viewBox="0 0 {spec.width} {spec.height}"', 'viewBox="0 0 1 1"', 1
    )
    changed = changed.replace('data-frame="true"', 'data-frame-disabled="true"', 1)
    changed = changed.replace('data-center="true"', 'data-center-disabled="true"', 1)
    with TemporaryDirectory() as directory:
        path = _write_changed_svg(Path(directory), changed)
        errors = _validate_svg_asset(path, spec)

    assert any("dimensions must be" in error for error in errors)
    assert any("viewBox must be" in error for error in errors)
    assert any("exactly one data-frame" in error for error in errors)
    assert any("exactly one data-center" in error for error in errors)


def test_editorial_svg_requires_exactly_four_named_quadrants():
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.svg_name).read_text(encoding="utf-8")
    changed = source.replace(
        'data-quadrant="bottom-right"', 'data-slot="bottom-right"', 1
    )
    with TemporaryDirectory() as directory:
        path = _write_changed_svg(Path(directory), changed)
        errors = _validate_svg_asset(path, spec)

    assert any("exactly four named data-quadrant" in error for error in errors)


@pytest.mark.parametrize("tag", ["image", "script", "foreignObject", "text"])
def test_editorial_svg_rejects_embedded_and_executable_elements(
    tag: str,
):
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.svg_name).read_text(encoding="utf-8")
    with TemporaryDirectory() as directory:
        path = _write_changed_svg(
            Path(directory), source.replace("</svg>", f"<{tag}/></svg>")
        )
        errors = _validate_svg_asset(path, spec)

    assert any(f"<{tag.casefold()}> is not allowed" in error for error in errors)


@pytest.mark.parametrize(
    "target",
    [
        "https://example.test/asset.svg",
        "http://example.test/asset.svg",
        "data:image/svg+xml,asset",
        "file:///tmp/asset.svg",
    ],
)
def test_editorial_svg_rejects_nonlocal_href(target: str):
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.svg_name).read_text(encoding="utf-8")
    changed = source.replace(f'href="#{spec.quadrant_id}"', f'href="{target}"', 1)
    with TemporaryDirectory() as directory:
        path = _write_changed_svg(Path(directory), changed)
        errors = _validate_svg_asset(path, spec)

    assert any("href must reference a local SVG fragment" in error for error in errors)


@pytest.mark.parametrize("chunk_type", [b"tEXt", b"iTXt", b"zTXt", b"eXIf"])
def test_editorial_png_rejects_text_and_exif_chunks(
    chunk_type: bytes,
):
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.png_name).read_bytes()
    with TemporaryDirectory() as directory:
        path = Path(directory) / "asset.png"
        path.write_bytes(_insert_png_chunk(source, chunk_type, b"private metadata"))
        errors = _validate_png_asset(path, spec)

    assert any("unsafe or metadata PNG chunks" in error for error in errors)


def test_editorial_png_rejects_wrong_dimensions():
    spec = EDITORIAL_ASSET_SPECS[0]
    source = ROOT / "docs" / "assets" / spec.png_name

    errors = _validate_png_asset(source, replace(spec, width=spec.width + 1))

    assert any("dimensions must be" in error for error in errors)


def test_editorial_png_rejects_corrupt_chunk_crc():
    spec = EDITORIAL_ASSET_SPECS[0]
    source = (ROOT / "docs" / "assets" / spec.png_name).read_bytes()
    with TemporaryDirectory() as directory:
        path = Path(directory) / "asset.png"
        path.write_bytes(_corrupt_first_idat_crc(source))
        errors = _validate_png_asset(path, spec)

    assert any("CRC mismatch in IDAT" in error for error in errors)

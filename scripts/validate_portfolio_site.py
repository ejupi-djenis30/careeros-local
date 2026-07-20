"""Validate the dependency-free GitHub Pages portfolio before deployment."""

from __future__ import annotations

import base64
import hashlib
import re
import struct
import zlib
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = ROOT / "docs"
INDEX = SITE_ROOT / "index.html"
IGNORED_SCHEMES = {"http", "https", "mailto", "tel", "data"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ALLOWED_PNG_CHUNKS = {b"IHDR", b"IDAT", b"IEND"}
DISALLOWED_SVG_ELEMENTS = {"foreignobject", "image", "script", "text"}
SVG_URL_REFERENCE = re.compile(r"url\(\s*([^)]+?)\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class EditorialAssetSpec:
    """Expected native source and delivery geometry for an editorial asset."""

    stem: str
    quadrant_id: str
    width: int
    height: int
    frame: tuple[float, float, float, float]
    center: tuple[float, float, float, float]

    @property
    def svg_name(self) -> str:
        return f"{self.stem}.svg"

    @property
    def png_name(self) -> str:
        return f"{self.stem}.png"


EDITORIAL_ASSET_SPECS = (
    EditorialAssetSpec(
        stem="careeros-local-hero",
        quadrant_id="hero-quadrant",
        width=1774,
        height=887,
        frame=(48, 48, 1678, 791),
        center=(707, 263.5, 360, 360),
    ),
    EditorialAssetSpec(
        stem="devpost-thumbnail",
        quadrant_id="thumb-quadrant",
        width=1200,
        height=1200,
        frame=(48, 48, 1104, 1104),
        center=(400, 400, 400, 400),
    ),
)


class PortfolioParser(HTMLParser):
    """Collect the small set of structural facts needed for a static-site gate."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.references: list[tuple[str, str, int]] = []
        self.images_missing_alt: list[int] = []
        self.h1_count = 0
        self.main_count = 0
        self.nav_labels: list[str | None] = []
        self.video_count = 0
        self.videos_without_controls: list[int] = []
        self.external_executables: list[tuple[str, int]] = []
        self.referrer_policies: list[str] = []
        self.csp_policies: list[str] = []
        self.inline_scripts: list[tuple[str, int]] = []
        self._inline_script: list[str] | None = None
        self._inline_script_line = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        line, _ = self.getpos()

        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)

        if tag == "h1":
            self.h1_count += 1
        elif tag == "main":
            self.main_count += 1
        elif tag == "nav":
            self.nav_labels.append(attributes.get("aria-label"))
        elif tag == "img" and "alt" not in attributes:
            self.images_missing_alt.append(line)
        elif tag == "video":
            self.video_count += 1
            if "controls" not in attributes:
                self.videos_without_controls.append(line)
        elif tag == "meta" and (attributes.get("name") or "").lower() == "referrer":
            self.referrer_policies.append(attributes.get("content") or "")
        elif tag == "meta" and (attributes.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp_policies.append(attributes.get("content") or "")

        if tag == "script" and not attributes.get("src"):
            self._inline_script = []
            self._inline_script_line = line

        for attribute in ("href", "src", "poster"):
            value = attributes.get(attribute)
            if value:
                self.references.append((attribute, value, line))

        executable = None
        if tag == "script" and attributes.get("src"):
            executable = attributes["src"]
        elif tag == "link" and attributes.get("rel") == "stylesheet":
            executable = attributes.get("href")
        if executable and urlparse(executable).scheme in {"http", "https"}:
            self.external_executables.append((executable, line))

    def handle_data(self, data: str) -> None:
        if self._inline_script is not None:
            self._inline_script.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inline_script is not None:
            self.inline_scripts.append(("".join(self._inline_script), self._inline_script_line))
            self._inline_script = None


def _parse_csp(policy: str) -> tuple[dict[str, set[str]], list[str]]:
    directives: dict[str, set[str]] = {}
    errors: list[str] = []
    for raw_directive in policy.split(";"):
        parts = raw_directive.strip().split()
        if not parts:
            continue
        name, *values = parts
        if name in directives:
            errors.append(f"CSP directive is duplicated: {name}")
            continue
        directives[name] = set(values)
    return directives, errors


def _local_name(qualified_name: str) -> str:
    return qualified_name.rsplit("}", maxsplit=1)[-1].casefold()


def _read_svg_bounds(
    element: ElementTree.Element,
    *,
    label: str,
    role: str,
    errors: list[str],
) -> tuple[float, float, float, float] | None:
    values: list[float] = []
    for attribute in ("x", "y", "width", "height"):
        raw_value = element.get(attribute)
        if raw_value is None:
            errors.append(f"{label}: {role} is missing {attribute}")
            return None
        try:
            values.append(float(raw_value))
        except ValueError:
            errors.append(f"{label}: {role} has an invalid {attribute} value")
            return None
    return values[0], values[1], values[2], values[3]


def _validate_svg_asset(path: Path, spec: EditorialAssetSpec) -> list[str]:
    errors: list[str] = []
    label = path.name
    if not path.is_file():
        return [f"missing native editorial source: {label}"]

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{label}: SVG source must be UTF-8"]

    if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        errors.append(f"{label}: document types and entities are not allowed")
        return errors

    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as exc:
        return [f"{label}: invalid XML: {exc}"]

    if _local_name(root.tag) != "svg":
        errors.append(f"{label}: root element must be svg")
    if root.get("width") != str(spec.width) or root.get("height") != str(spec.height):
        errors.append(
            f"{label}: dimensions must be {spec.width}x{spec.height}"
        )
    expected_view_box = f"0 0 {spec.width} {spec.height}"
    if root.get("viewBox") != expected_view_box:
        errors.append(f"{label}: viewBox must be {expected_view_box}")

    ids = {element.get("id") for element in root.iter() if element.get("id")}
    quadrants: dict[str, ElementTree.Element] = {}
    frame_elements: list[ElementTree.Element] = []
    center_elements: list[ElementTree.Element] = []

    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in DISALLOWED_SVG_ELEMENTS:
            errors.append(f"{label}: <{tag}> is not allowed")
        if any(_local_name(name).startswith("on") for name in element.attrib):
            errors.append(f"{label}: event-handler attributes are not allowed")

        quadrant_name = element.get("data-quadrant")
        if quadrant_name:
            if quadrant_name in quadrants:
                errors.append(f"{label}: duplicate data-quadrant {quadrant_name}")
            quadrants[quadrant_name] = element
            if tag != "use":
                errors.append(f"{label}: data-quadrant elements must be <use>")
        if "data-frame" in element.attrib:
            frame_elements.append(element)
        if "data-center" in element.attrib:
            center_elements.append(element)

        for attribute, value in element.attrib.items():
            attribute_name = _local_name(attribute)
            if attribute_name == "href":
                if not value.startswith("#") or value == "#":
                    errors.append(f"{label}: href must reference a local SVG fragment")
                elif value[1:] not in ids:
                    errors.append(f"{label}: href target does not exist: {value}")
            elif attribute_name == "src":
                errors.append(f"{label}: src attributes are not allowed")

    for match in SVG_URL_REFERENCE.finditer(source):
        target = match.group(1).strip().strip("\"'")
        if not target.startswith("#") or target == "#":
            errors.append(f"{label}: url() must reference a local SVG fragment")

    expected_quadrants = {"top-left", "top-right", "bottom-left", "bottom-right"}
    if len(quadrants) != 4 or set(quadrants) != expected_quadrants:
        errors.append(
            f"{label}: expected exactly four named data-quadrant elements"
        )
    else:
        expected_transforms = {
            "top-left": "",
            "top-right": f"translate({spec.width} 0) scale(-1 1)",
            "bottom-left": f"translate(0 {spec.height}) scale(1 -1)",
            "bottom-right": (
                f"translate({spec.width} {spec.height}) scale(-1 -1)"
            ),
        }
        for name, element in quadrants.items():
            if element.get("href") != f"#{spec.quadrant_id}":
                errors.append(f"{label}: {name} must reuse #{spec.quadrant_id}")
            if (element.get("transform") or "").strip() != expected_transforms[name]:
                errors.append(f"{label}: {name} mirror transform is invalid")

    for role, elements, expected_bounds in (
        ("frame", frame_elements, spec.frame),
        ("center", center_elements, spec.center),
    ):
        if len(elements) != 1:
            errors.append(f"{label}: expected exactly one data-{role} element")
            continue
        if _local_name(elements[0].tag) != "rect":
            errors.append(f"{label}: data-{role} must be a rect")
            continue
        bounds = _read_svg_bounds(
            elements[0], label=label, role=role, errors=errors
        )
        if bounds != expected_bounds:
            errors.append(f"{label}: {role} bounds must be {expected_bounds}")

    return errors


def _validate_png_asset(path: Path, spec: EditorialAssetSpec) -> list[str]:
    errors: list[str] = []
    label = path.name
    if not path.is_file():
        return [f"missing rendered editorial asset: {label}"]

    payload = path.read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        return [f"{label}: invalid PNG signature"]

    chunks: list[bytes] = []
    offset = len(PNG_SIGNATURE)
    while offset < len(payload):
        if len(payload) - offset < 12:
            errors.append(f"{label}: truncated PNG chunk header")
            break
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload):
            errors.append(f"{label}: truncated PNG chunk payload")
            break

        chunk_type = payload[offset + 4 : offset + 8]
        chunk_data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            errors.append(
                f"{label}: CRC mismatch in {chunk_type.decode('ascii', errors='replace')}"
            )

        chunks.append(chunk_type)
        if chunk_type == b"IHDR":
            if length != 13:
                errors.append(f"{label}: IHDR must contain 13 bytes")
            else:
                width, height, bit_depth, color_type, compression, filtering, interlace = (
                    struct.unpack(">IIBBBBB", chunk_data)
                )
                if (width, height) != (spec.width, spec.height):
                    errors.append(
                        f"{label}: dimensions must be {spec.width}x{spec.height}"
                    )
                if bit_depth != 8 or color_type not in {2, 6}:
                    errors.append(f"{label}: expected 8-bit RGB or RGBA pixels")
                if compression != 0 or filtering != 0 or interlace not in {0, 1}:
                    errors.append(f"{label}: unsupported PNG encoding parameters")

        offset = chunk_end
        if chunk_type == b"IEND":
            if offset != len(payload):
                errors.append(f"{label}: data exists after IEND")
            break

    unexpected_chunks = sorted(set(chunks) - ALLOWED_PNG_CHUNKS)
    if unexpected_chunks:
        readable = ", ".join(
            chunk.decode("ascii", errors="replace") for chunk in unexpected_chunks
        )
        errors.append(f"{label}: unsafe or metadata PNG chunks found: {readable}")
    if not chunks or chunks[0] != b"IHDR" or chunks.count(b"IHDR") != 1:
        errors.append(f"{label}: PNG must begin with exactly one IHDR")
    if b"IDAT" not in chunks:
        errors.append(f"{label}: PNG must contain image data")
    if not chunks or chunks[-1] != b"IEND" or chunks.count(b"IEND") != 1:
        errors.append(f"{label}: PNG must end with exactly one IEND")

    return errors


def validate_editorial_assets(site_root: Path = SITE_ROOT) -> list[str]:
    """Validate native SVG sources and metadata-free PNG delivery files."""

    errors: list[str] = []
    asset_root = site_root / "assets"
    for spec in EDITORIAL_ASSET_SPECS:
        errors.extend(_validate_svg_asset(asset_root / spec.svg_name, spec))
        errors.extend(_validate_png_asset(asset_root / spec.png_name, spec))
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    if not INDEX.is_file():
        return [f"missing portfolio entry point: {INDEX.relative_to(ROOT)}"]

    parser = PortfolioParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    parser.close()

    errors.extend(validate_editorial_assets())

    if parser.h1_count != 1:
        errors.append(f"expected exactly one h1, found {parser.h1_count}")
    if parser.main_count != 1:
        errors.append(f"expected exactly one main landmark, found {parser.main_count}")
    if any(not label for label in parser.nav_labels):
        errors.append("every navigation landmark must have an aria-label")
    for line in parser.images_missing_alt:
        errors.append(f"line {line}: image is missing an alt attribute")
    for line in parser.videos_without_controls:
        errors.append(f"line {line}: video must expose browser controls")
    if parser.video_count != 1:
        errors.append(f"expected exactly one real-product demo video, found {parser.video_count}")
    if not any(
        attribute == "src" and reference == "assets/careeros-demo.webm"
        for attribute, reference, _line in parser.references
    ):
        errors.append("portfolio must preserve the CareerOS Local WebM product demo")
    for url, line in parser.external_executables:
        errors.append(f"line {line}: external script or stylesheet is not allowed: {url}")

    if parser.referrer_policies != ["no-referrer"]:
        errors.append("portfolio must declare exactly one no-referrer policy")

    if len(parser.csp_policies) != 1:
        errors.append("portfolio must declare exactly one Content Security Policy")
    else:
        csp, csp_errors = _parse_csp(parser.csp_policies[0])
        errors.extend(csp_errors)
        required_directives = {
            "default-src": {"'none'"},
            "base-uri": {"'none'"},
            "connect-src": {"'none'"},
            "font-src": {"'self'"},
            "form-action": {"'none'"},
            "frame-src": {"'none'"},
            "img-src": {"'self'", "data:"},
            "media-src": {"'self'"},
            "object-src": {"'none'"},
            "style-src": {"'self'"},
            "worker-src": {"'none'"},
        }
        for directive, expected_sources in required_directives.items():
            if csp.get(directive) != expected_sources:
                errors.append(
                    f"CSP {directive} must be {' '.join(sorted(expected_sources))}"
                )

        expected_script_hashes = {
            "'sha256-"
            + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
            + "'"
            for script, _ in parser.inline_scripts
        }
        if csp.get("script-src") != expected_script_hashes:
            errors.append("CSP script-src must contain only the current inline-script hashes")
        if "'unsafe-inline'" in parser.csp_policies[0] or "'unsafe-eval'" in parser.csp_policies[0]:
            errors.append("CSP must not allow unsafe-inline or unsafe-eval")

    for attribute, reference, line in parser.references:
        parsed = urlparse(reference)
        if parsed.scheme in IGNORED_SCHEMES or reference.startswith("//"):
            continue
        if parsed.path:
            local_path = (SITE_ROOT / unquote(parsed.path)).resolve()
            try:
                local_path.relative_to(SITE_ROOT.resolve())
            except ValueError:
                errors.append(f"line {line}: {attribute} escapes docs/: {reference}")
                continue
            if not local_path.is_file():
                errors.append(f"line {line}: missing local {attribute}: {reference}")
        if parsed.fragment and not parsed.path and parsed.fragment not in parser.ids:
            errors.append(f"line {line}: missing fragment target: #{parsed.fragment}")

    css_path = SITE_ROOT / "site" / "styles.css"
    if not css_path.is_file():
        errors.append("missing site/styles.css")
    else:
        css = css_path.read_text(encoding="utf-8").lower()
        if "@import" in css:
            errors.append("CSS imports are not allowed")
        if "http://" in css or "https://" in css:
            errors.append("external CSS resources are not allowed")
        if "prefers-reduced-motion" not in css:
            errors.append("CSS must respect prefers-reduced-motion")
        if ":focus-visible" not in css:
            errors.append("CSS must provide visible keyboard focus")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Portfolio validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Portfolio validation passed: structure, local links, assets, and baseline a11y.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate the dependency-free GitHub Pages portfolio before deployment."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = ROOT / "docs"
INDEX = SITE_ROOT / "index.html"
IGNORED_SCHEMES = {"http", "https", "mailto", "tel", "data"}


class PortfolioParser(HTMLParser):
    """Collect the small set of structural facts needed for a static-site gate."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.references: list[tuple[str, str, int]] = []
        self.images_without_alt: list[int] = []
        self.h1_count = 0
        self.main_count = 0
        self.nav_labels: list[str | None] = []
        self.videos_without_controls: list[int] = []
        self.external_executables: list[tuple[str, int]] = []

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
        elif tag == "img" and not (attributes.get("alt") or "").strip():
            self.images_without_alt.append(line)
        elif tag == "video" and "controls" not in attributes:
            self.videos_without_controls.append(line)

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


def validate() -> list[str]:
    errors: list[str] = []
    if not INDEX.is_file():
        return [f"missing portfolio entry point: {INDEX.relative_to(ROOT)}"]

    parser = PortfolioParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    parser.close()

    if parser.h1_count != 1:
        errors.append(f"expected exactly one h1, found {parser.h1_count}")
    if parser.main_count != 1:
        errors.append(f"expected exactly one main landmark, found {parser.main_count}")
    if any(not label for label in parser.nav_labels):
        errors.append("every navigation landmark must have an aria-label")
    for line in parser.images_without_alt:
        errors.append(f"line {line}: image is missing non-empty alt text")
    for line in parser.videos_without_controls:
        errors.append(f"line {line}: video must expose browser controls")
    for url, line in parser.external_executables:
        errors.append(f"line {line}: external script or stylesheet is not allowed: {url}")

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

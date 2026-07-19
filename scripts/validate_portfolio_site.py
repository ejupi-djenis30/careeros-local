"""Validate the dependency-free GitHub Pages portfolio before deployment."""

from __future__ import annotations

import base64
import hashlib
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
        self.images_missing_alt: list[int] = []
        self.h1_count = 0
        self.main_count = 0
        self.nav_labels: list[str | None] = []
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
        elif tag == "video" and "controls" not in attributes:
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
    for line in parser.images_missing_alt:
        errors.append(f"line {line}: image is missing an alt attribute")
    for line in parser.videos_without_controls:
        errors.append(f"line {line}: video must expose browser controls")
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

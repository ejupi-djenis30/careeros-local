"""A deliberately small non-executable HTML selector and extraction engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_SIMPLE_SELECTOR = re.compile(
    r"^(?P<tag>[a-zA-Z][a-zA-Z0-9-]*)?"
    r"(?P<id>#[a-zA-Z_][a-zA-Z0-9_-]*)?"
    r"(?P<classes>(?:\.[a-zA-Z_][a-zA-Z0-9_-]*)*)"
    r"(?P<attr>\[[a-zA-Z_:][a-zA-Z0-9_:.-]*(?:=(?:[a-zA-Z0-9_.:-]+|\"[^\"]{1,120}\"))?\])?$"
)
_ATTR_SELECTOR = re.compile(
    r"^\[(?P<name>[a-zA-Z_:][a-zA-Z0-9_:.-]*)(?:=(?P<value>[a-zA-Z0-9_.:-]+|\"[^\"]{1,120}\"))?\]$"
)
MAX_HTML_NODES = 20_000
MAX_HTML_DEPTH = 64
MAX_FIELD_TEXT = 20_000


class HtmlExtractionError(ValueError):
    pass


@dataclass(slots=True)
class HtmlNode:
    tag: str
    attrs: dict[str, str]
    parent: "HtmlNode | None" = None
    children: list["HtmlNode"] = field(default_factory=list)
    text: list[str] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document", {})
        self.stack = [self.root]
        self.nodes = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.nodes >= MAX_HTML_NODES or len(self.stack) >= MAX_HTML_DEPTH:
            raise HtmlExtractionError("Provider HTML exceeds the safe structure limit")
        node = HtmlNode(
            tag.casefold(),
            {name.casefold(): value or "" for name, value in attrs[:80]},
            self.stack[-1],
        )
        self.stack[-1].children.append(node)
        self.nodes += 1
        if tag.casefold() not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.casefold():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        target = tag.casefold()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == target:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].text.append(data)


@dataclass(frozen=True, slots=True)
class _SelectorPart:
    tag: str | None
    node_id: str | None
    classes: frozenset[str]
    attribute: tuple[str, str | None] | None


def _parse_part(value: str) -> _SelectorPart:
    match = _SIMPLE_SELECTOR.fullmatch(value)
    if match is None or not any(match.groupdict().values()):
        raise HtmlExtractionError("Provider HTML selector is outside the supported subset")
    attribute = None
    if raw_attribute := match.group("attr"):
        attr_match = _ATTR_SELECTOR.fullmatch(raw_attribute)
        if attr_match is None:
            raise HtmlExtractionError("Provider HTML attribute selector is invalid")
        raw_value = attr_match.group("value")
        attribute = (
            attr_match.group("name").casefold(),
            raw_value.strip('"') if raw_value is not None else None,
        )
    return _SelectorPart(
        tag=match.group("tag").casefold() if match.group("tag") else None,
        node_id=match.group("id")[1:] if match.group("id") else None,
        classes=frozenset(filter(None, match.group("classes").split("."))),
        attribute=attribute,
    )


def validate_selector(selector: str) -> str:
    candidate = " ".join(selector.split())
    if not candidate or len(candidate) > 500 or len(candidate.split(" ")) > 8:
        raise HtmlExtractionError("Provider HTML selector is invalid")
    for part in candidate.split(" "):
        _parse_part(part)
    return candidate


def parse_html(value: str) -> HtmlNode:
    parser = _TreeParser()
    try:
        parser.feed(value)
        parser.close()
    except (HtmlExtractionError, RecursionError) as exc:
        raise HtmlExtractionError("Provider HTML could not be parsed safely") from exc
    return parser.root


def _descendants(node: HtmlNode):
    pending = list(reversed(node.children))
    while pending:
        child = pending.pop()
        yield child
        pending.extend(reversed(child.children))


def _matches(node: HtmlNode, selector: _SelectorPart) -> bool:
    if selector.tag is not None and node.tag != selector.tag:
        return False
    if selector.node_id is not None and node.attrs.get("id") != selector.node_id:
        return False
    if selector.classes and not selector.classes.issubset(node.attrs.get("class", "").split()):
        return False
    if selector.attribute is not None:
        name, expected = selector.attribute
        if name not in node.attrs or (expected is not None and node.attrs[name] != expected):
            return False
    return True


def select_all(node: HtmlNode, selector: str, *, limit: int = 200) -> list[HtmlNode]:
    current = [node]
    for raw_part in validate_selector(selector).split(" "):
        part = _parse_part(raw_part)
        matched: list[HtmlNode] = []
        for parent in current:
            for candidate in _descendants(parent):
                if _matches(candidate, part):
                    matched.append(candidate)
                    if len(matched) >= limit:
                        break
            if len(matched) >= limit:
                break
        current = matched
    return current


def select_one(node: HtmlNode, selector: str) -> HtmlNode | None:
    if selector == ".":
        return node
    matches = select_all(node, selector, limit=1)
    return matches[0] if matches else None


def text_content(node: HtmlNode) -> str:
    parts: list[str] = []
    size = 0
    pending = [node]
    while pending:
        current = pending.pop()
        for text in current.text:
            size += len(text)
            if size > MAX_FIELD_TEXT:
                raise HtmlExtractionError("Provider HTML field exceeds the safe text limit")
            parts.append(text)
        pending.extend(reversed(current.children))
    return " ".join(" ".join(parts).split())

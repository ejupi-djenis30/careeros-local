"""Load bounded source-controlled provider-pack manifests without installing them."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from backend.providers.configuration.schemas import (
    ProviderPackDocument,
    ProviderPackSummaryView,
)

PACK_ROOT = Path(__file__).resolve().with_name("packs")
MAX_BUNDLED_PACK_BYTES = 256 * 1024
MAX_BUNDLED_PACKS = 20


class ProviderPackError(ValueError):
    """A bundled pack is missing, ambiguous or fails its strict contract."""


def _load_pack(path: Path) -> ProviderPackDocument:
    try:
        resolved_root = PACK_ROOT.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root) or path.is_symlink():
            raise ProviderPackError("Provider pack path is outside the bundled pack root")
        size = resolved.stat().st_size
        if not 1 <= size <= MAX_BUNDLED_PACK_BYTES:
            raise ProviderPackError("Provider pack exceeds the bundled size limit")
        return ProviderPackDocument.model_validate_json(resolved.read_bytes())
    except (OSError, ValidationError) as exc:
        raise ProviderPackError("Bundled provider pack is invalid") from exc


def bundled_provider_packs() -> list[ProviderPackDocument]:
    try:
        paths = sorted(PACK_ROOT.glob("*.json"))
    except OSError as exc:
        raise ProviderPackError("Bundled provider packs are unavailable") from exc
    if len(paths) > MAX_BUNDLED_PACKS:
        raise ProviderPackError("Too many bundled provider packs")
    packs = [_load_pack(path) for path in paths]
    ids = [pack.id for pack in packs]
    if len(ids) != len(set(ids)):
        raise ProviderPackError("Bundled provider pack ids must be unique")
    return packs


def bundled_provider_pack(pack_id: str) -> ProviderPackDocument:
    matches = [pack for pack in bundled_provider_packs() if pack.id == pack_id]
    if len(matches) != 1:
        raise ProviderPackError("Bundled provider pack was not found")
    return matches[0]


def bundled_provider_pack_summaries() -> list[ProviderPackSummaryView]:
    return [
        ProviderPackSummaryView(
            id=pack.id,
            version=pack.version,
            name=pack.name,
            description=pack.description,
            provider_keys=[
                entry.configuration.key if entry.kind == "declarative" else entry.key
                for entry in pack.providers
            ],
        )
        for pack in bundled_provider_packs()
    ]

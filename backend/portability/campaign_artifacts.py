"""Validate campaign artifact links, immutable asset identities and portable paths."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Container, Mapping
from pathlib import PurePosixPath
from typing import Any, TypeGuard


def validate_campaign_artifacts(
    campaign_artifacts: list[dict[str, Any]],
    campaign_ids: set[str],
    valid_app_ids: set[Any],
    campaign_app_links: set[tuple[str, str]],
    assets_by_id: Mapping[Any, dict[str, Any]],
    *,
    is_uuid: Callable[[Any], TypeGuard[str]],
    is_hex64: Callable[[Any], TypeGuard[str]],
    allowed_categories: Container[str],
) -> None:
    # Validate campaign artifacts
    art_ids: set[str] = set()
    art_paths: set[tuple[str, str]] = set()

    for art in campaign_artifacts:
        art_id = art.get("id")
        if not is_uuid(art_id):
            raise ValueError(f"Invalid campaign_artifact id: {art_id}")
        if art_id in art_ids:
            raise ValueError(f"Duplicate campaign_artifact id: {art_id}")
        art_ids.add(art_id)

        cid = art.get("campaign_id")
        if cid not in campaign_ids:
            raise ValueError(f"campaign_artifact references missing campaign_id: {cid}")

        target_aid = art.get("application_id")
        if target_aid is not None:
            if target_aid not in valid_app_ids:
                raise ValueError(
                    f"campaign_artifact references missing application_id: {target_aid}"
                )
            if (cid, target_aid) not in campaign_app_links:
                raise ValueError(
                    "campaign_artifact application_id does not belong to the same campaign"
                )

        asset_id = art.get("asset_id")
        if asset_id not in assets_by_id:
            raise ValueError(f"campaign_artifact references missing asset_id: {asset_id}")

        asset = assets_by_id[asset_id]
        if asset.get("kind") != "campaign_document" or asset.get("normalized") is not False:
            raise ValueError("campaign_artifact asset must be unnormalized campaign_document")
        asset_sha = asset.get("sha256")
        if not is_hex64(asset_sha):
            raise ValueError("campaign_artifact asset sha256 must be valid hex digest")
        if asset.get("storage_path") != f"assets/campaign/{asset_sha[:2]}/{asset_sha}":
            raise ValueError(
                "campaign_artifact asset storage_path does not match canonical campaign path"
            )

        category = art.get("category")
        if category not in allowed_categories:
            raise ValueError(f"Invalid campaign_artifact category: {category}")

        rel_path = art.get("relative_path")
        if not isinstance(rel_path, str) or not rel_path.strip() or len(rel_path) > 500:
            raise ValueError("relative_path must be non-empty string <= 500 chars")
        if not unicodedata.is_normalized("NFC", rel_path):
            raise ValueError("relative_path must be NFC normalized")
        if (
            "\\" in rel_path
            or rel_path.startswith("/")
            or ":" in rel_path
            or any(unicodedata.category(c).startswith("C") for c in rel_path)
        ):
            raise ValueError(
                "relative_path cannot contain backslashes, colons, or control characters"
            )

        posix = PurePosixPath(rel_path)
        if (
            posix.is_absolute()
            or ".." in posix.parts
            or "." in posix.parts
            or posix.as_posix() != rel_path
        ):
            raise ValueError("relative_path must be canonical POSIX path without traversal")

        norm_path = unicodedata.normalize("NFC", rel_path).casefold()
        path_key = (cid, norm_path)
        if path_key in art_paths:
            raise ValueError(
                f"Duplicate relative_path under NFC+casefolding in campaign_artifacts: {rel_path}"
            )
        art_paths.add(path_key)

        display_name = art.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 255:
            raise ValueError("display_name must be non-empty string <= 255 chars")
        if not unicodedata.is_normalized("NFC", display_name):
            raise ValueError("display_name must be NFC normalized")
        if (
            "/" in display_name
            or "\\" in display_name
            or ":" in display_name
            or any(unicodedata.category(c).startswith("C") for c in display_name)
            or posix.name != display_name
        ):
            raise ValueError(
                "display_name must match relative_path basename without control characters or colons"
            )

"""Shared utilities for asset dossier tools."""

from __future__ import annotations

import os
import re

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def normalize_asset_id(asset_id: str | None) -> str | None:
    """Prefer a UUID asset id; fall back to ASSET_ID env if needed."""
    if asset_id and _UUID_RE.match(asset_id):
        return asset_id
    fallback = os.getenv("ASSET_ID")
    if fallback and _UUID_RE.match(fallback):
        return fallback
    return asset_id

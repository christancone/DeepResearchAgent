#!/usr/bin/env python3
"""
Asset Dossier Research Agent Entry Point

Analyzes aircraft maintenance dossiers using the full DeepResearchAgent framework.

Usage:
    python examples/run_asset_research.py --asset-id "asset_123" --prompt "Extract all LLPs"
    python examples/run_asset_research.py --asset-id "asset_123" --depth comprehensive
    python examples/run_asset_research.py --asset-id "asset_123" --prompt "Validate AD compliance" --verbose
"""

import asyncio
import argparse
import json
import re
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.logger import logger
from src.models import model_manager
from src.agent import create_agent
from src.agent.reformulator import prepare_response
from src.memory.canvas import WorkingMemoryCanvas
from src.memory import FinalAnswerStep
from src.tools.canvas_tool import CanvasTool
from src.tools.tools import ToolResult
from src.schemas.asset_research_output import AssetResearchOutput, ResearchMetadata
from src.observability.emitter import EventEmitter
from src.observability.console_monitor import SimpleConsoleLogger, print_execution_summary


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Asset Dossier Research Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python examples/run_asset_research.py --asset-id "ESN-12345" --prompt "Extract all LLPs"
    
    # Comprehensive analysis
    python examples/run_asset_research.py --asset-id "ESN-12345" --depth comprehensive
    
    # Verbose output with streaming
    python examples/run_asset_research.py --asset-id "ESN-12345" --prompt "Analyze maintenance history" --verbose --stream
        """
    )
    
    parser.add_argument(
        "--config", 
        default="configs/config_asset_research.py",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--asset-id", 
        required=True, 
        help="Asset ID to analyze"
    )
    parser.add_argument(
        "--prompt", 
        default="Produce a comprehensive analysis of this asset dossier",
        help="Analysis prompt/question"
    )
    parser.add_argument(
        "--depth", 
        choices=["quick", "standard", "comprehensive"],
        default="standard", 
        help="Research depth"
    )
    parser.add_argument(
        "--output", 
        help="Output JSON file path"
    )
    parser.add_argument(
        "--stream", 
        action="store_true", 
        help="Enable streaming output"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Verbose event logging"
    )
    parser.add_argument(
        "--live-monitor", 
        action="store_true", 
        help="Use rich live monitor display"
    )
    parser.add_argument(
        "--cfg-options", 
        nargs="+", 
        default=[],
        help="Override config options (key=value)"
    )
    
    return parser.parse_args()


def _sanitize_json_text(text: str) -> str:
    """Fix common formatting glitches in model JSON output."""
    cleaned = re.sub(r":\s*\|\s*\{", ": [{", text)
    cleaned = re.sub(r":\s*\|\s*\[", ": [", cleaned)
    cleaned = re.sub(r":\s*\|\s*\]", ": []", cleaned)
    cleaned = re.sub(r"\|\s*(\{|\[|\])", r"\1", cleaned)
    return cleaned


def _escape_control_chars_in_json_strings(text: str) -> str:
    """Escape raw control chars that appear inside JSON quoted strings."""
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
    return "".join(out)


def _loads_json_with_repair(raw_text: str):
    """Load JSON with light repair passes for malformed model output."""
    sanitized = _sanitize_json_text(raw_text)
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError as e:
        # Common failure mode in model output: literal newlines in quoted strings.
        if "Invalid control character" in str(e):
            repaired = _escape_control_chars_in_json_strings(sanitized)
            return json.loads(repaired)
        raise


def _unwrap_tool_result(value):
    """Normalize ToolResult payloads into plain serializable values."""
    if isinstance(value, ToolResult):
        if value.error:
            logger.warning(f"ToolResult contains error: {value.error}")
        return value.output
    return value


_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Non-page placeholders that should not be emitted as source citations (drop/quarantine)
_SOURCE_PLACEHOLDER_PREFIXES = ("canvas_", "existing_", "document_tree_", "asset extraction ")
_SOURCE_PLACEHOLDER_VALUES = frozenset({"existing_summary", "document_tree_tool_results"})


def _collect_page_ids(value: Any, page_ids: set[str]) -> None:
    """Recursively collect UUID-like page IDs from arbitrary payloads."""
    if isinstance(value, str):
        for match in _UUID_RE.findall(value):
            page_ids.add(match.lower())
        return
    if isinstance(value, list):
        for item in value:
            _collect_page_ids(item, page_ids)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_page_ids(item, page_ids)


def _collect_source_page_indices(value: Any, page_indices: set[int]) -> None:
    """Collect integer source page indices from citation-like fields."""
    if isinstance(value, list):
        for item in value:
            _collect_source_page_indices(item, page_indices)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source_pages", "sourcePages", "pageIndex", "page_index", "pages"}:
                _collect_source_page_indices(item, page_indices)
            elif isinstance(item, (dict, list)):
                _collect_source_page_indices(item, page_indices)
        return
    if isinstance(value, int) and value >= 0:
        page_indices.add(value)
    elif isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            page_indices.add(int(raw))


async def _fetch_page_lookup(
    page_ids: set[str],
    asset_id: str | None = None,
    page_indices: set[int] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch page metadata for citation enrichment.

    Includes two lookup modes:
    - Direct page UUIDs (exact)
    - Numeric page indices resolved by (asset_id, page_index) only when unique
    """
    if not page_ids and not (asset_id and page_indices):
        return {}
    try:
        from src.tools.asset_dossier.db_client import SupabaseAsyncClient

        db = await SupabaseAsyncClient.get_instance()
        lookup: dict[str, dict[str, Any]] = {}

        if page_ids:
            rows = await db.fetch(
                """
                SELECT
                    dp.id AS page_id,
                    dp.page_index,
                    dp.enhanced_s3_key,
                    dpr.id AS document_id,
                    dpr.file_name AS document_name
                FROM document_pages dp
                JOIN document_processing_records dpr ON dp.document_id = dpr.id
                WHERE dp.id::text = ANY($1::text[])
                """,
                list(page_ids),
            )
            for row in rows:
                lookup[str(row["page_id"]).lower()] = {
                    "pageId": str(row["page_id"]),
                    "pageIndex": row.get("page_index"),
                    "documentId": str(row["document_id"]) if row.get("document_id") else None,
                    "documentName": row.get("document_name"),
                    "enhancedS3Key": row.get("enhanced_s3_key"),
                }

        # Best-effort backfill for numeric source_pages using (asset_id, page_index).
        # Only enrich when a page_index resolves uniquely within the asset.
        if asset_id and page_indices:
            index_rows = await db.fetch(
                """
                SELECT
                    dp.id AS page_id,
                    dp.page_index,
                    dp.enhanced_s3_key,
                    dpr.id AS document_id,
                    dpr.file_name AS document_name
                FROM document_pages dp
                JOIN document_processing_records dpr ON dp.document_id = dpr.id
                WHERE dpr.asset_id = $1 AND dp.page_index = ANY($2::int[])
                """,
                asset_id,
                sorted(page_indices),
            )
            by_index: dict[int, list[dict[str, Any]]] = {}
            for row in index_rows:
                idx = row.get("page_index")
                if isinstance(idx, int):
                    by_index.setdefault(idx, []).append(row)
                # Also keep direct page_id lookup for any rows discovered here.
                if row.get("page_id"):
                    lookup[str(row["page_id"]).lower()] = {
                        "pageId": str(row["page_id"]),
                        "pageIndex": row.get("page_index"),
                        "documentId": str(row["document_id"]) if row.get("document_id") else None,
                        "documentName": row.get("document_name"),
                        "enhancedS3Key": row.get("enhanced_s3_key"),
                    }

            ambiguous_indices: list[int] = []
            for idx, rows_for_index in by_index.items():
                if len(rows_for_index) == 1:
                    row = rows_for_index[0]
                    lookup[f"__page_index__:{idx}"] = {
                        "pageId": str(row["page_id"]),
                        "pageIndex": row.get("page_index"),
                        "documentId": str(row["document_id"]) if row.get("document_id") else None,
                        "documentName": row.get("document_name"),
                        "enhancedS3Key": row.get("enhanced_s3_key"),
                    }
                else:
                    ambiguous_indices.append(idx)
            if ambiguous_indices:
                logger.warning(
                    "Could not uniquely resolve source page indices within asset "
                    f"{asset_id}: {sorted(ambiguous_indices)}"
                )

        return lookup
    except Exception as e:
        logger.warning(f"Could not enrich citations from DB: {e}")
        return {}


def _build_doc_page_index(page_lookup: dict[str, dict[str, Any]]) -> dict[tuple[str, int], str]:
    """Build (document_id, page_index) -> page_id lookup."""
    index: dict[tuple[str, int], str] = {}
    for row in page_lookup.values():
        document_id = row.get("documentId")
        page_index = row.get("pageIndex")
        page_id = row.get("pageId")
        if isinstance(document_id, str) and isinstance(page_index, int) and isinstance(page_id, str):
            index[(document_id.lower(), page_index)] = page_id.lower()
    return index


def _normalize_source_pages(
    source_value: Any,
    page_lookup: dict[str, dict[str, Any]],
    doc_page_index: dict[tuple[str, int], str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize citations to structured source page objects with enhancedS3Key."""
    if source_value is None:
        return []

    items = source_value if isinstance(source_value, list) else [source_value]
    normalized: list[dict[str, Any]] = []

    for item in items:
        if isinstance(item, dict):
            page_id = (
                item.get("pageId")
                or item.get("page_id")
                or item.get("id")
            )
            if isinstance(page_id, str):
                key = page_id.lower()
                enriched = page_lookup.get(key, {})
                normalized.append(
                    {
                        "pageId": page_id,
                        "pageIndex": item.get("pageIndex", item.get("page_index", enriched.get("pageIndex"))),
                        "documentId": item.get("documentId", item.get("document_id", enriched.get("documentId"))),
                        "documentName": item.get("documentName", item.get("document_name", enriched.get("documentName"))),
                        "enhancedS3Key": item.get("enhancedS3Key", item.get("enhanced_s3_key", enriched.get("enhancedS3Key"))),
                    }
                )
                continue

            # Keep page-index-only citations (legacy style) even without page_id.
            page_index_only = item.get("pageIndex", item.get("page_index"))
            if isinstance(page_index_only, int):
                enriched = page_lookup.get(f"__page_index__:{page_index_only}", {})
                normalized.append(
                    {
                        "pageId": enriched.get("pageId"),
                        "pageIndex": page_index_only,
                        "documentId": item.get("documentId", item.get("document_id", enriched.get("documentId"))),
                        "documentName": item.get("documentName", item.get("document_name", enriched.get("documentName"))),
                        "enhancedS3Key": item.get("enhancedS3Key", item.get("enhanced_s3_key", enriched.get("enhancedS3Key"))),
                    }
                )
            continue

        # Legacy source page index as integer.
        if isinstance(item, int):
            enriched = page_lookup.get(f"__page_index__:{item}", {})
            normalized.append(
                {
                    "pageId": enriched.get("pageId"),
                    "pageIndex": item,
                    "documentId": enriched.get("documentId"),
                    "documentName": enriched.get("documentName"),
                    "enhancedS3Key": enriched.get("enhancedS3Key"),
                }
            )
            continue

        if isinstance(item, str):
            raw = item.strip()
            # Numeric page index encoded as string.
            if raw.isdigit():
                page_index = int(raw)
                enriched = page_lookup.get(f"__page_index__:{page_index}", {})
                normalized.append(
                    {
                        "pageId": enriched.get("pageId"),
                        "pageIndex": page_index,
                        "documentId": enriched.get("documentId"),
                        "documentName": enriched.get("documentName"),
                        "enhancedS3Key": enriched.get("enhancedS3Key"),
                    }
                )
                continue
            # Handle "uuid|index" patterns where left side can be document_id.
            if "|" in raw:
                left, right = raw.split("|", 1)
                left_match = _UUID_RE.search(left)
                if left_match:
                    left_uuid = left_match.group(0).lower()
                    if left_uuid in page_lookup:
                        enriched = page_lookup.get(left_uuid, {})
                        normalized.append(
                            {
                                "pageId": enriched.get("pageId"),
                                "pageIndex": enriched.get("pageIndex"),
                                "documentId": enriched.get("documentId"),
                                "documentName": enriched.get("documentName"),
                                "enhancedS3Key": enriched.get("enhancedS3Key"),
                            }
                        )
                        continue

                    # document_id|page_index form
                    page_index_match = re.search(r"\d+", right)
                    if page_index_match and doc_page_index:
                        page_index = int(page_index_match.group(0))
                        page_key = doc_page_index.get((left_uuid, page_index))
                        if page_key and page_key in page_lookup:
                            enriched = page_lookup[page_key]
                            normalized.append(
                                {
                                    "pageId": enriched.get("pageId"),
                                    "pageIndex": enriched.get("pageIndex"),
                                    "documentId": enriched.get("documentId"),
                                    "documentName": enriched.get("documentName"),
                                    "enhancedS3Key": enriched.get("enhancedS3Key"),
                                }
                            )
                            continue
                    logger.warning(
                        f"Unresolved citation reference '{raw}' (document_id|page_index did not resolve to page_id)"
                    )
                    normalized.append(
                        {
                            "pageId": None,
                            "pageIndex": None,
                            "documentId": left_uuid,
                            "documentName": raw,
                            "enhancedS3Key": None,
                            "unresolvedReference": raw,
                        }
                    )
                    continue

            match = _UUID_RE.search(raw)
            if match:
                uuid_value = match.group(0).lower()
                enriched = page_lookup.get(uuid_value, {})
                normalized.append(
                    {
                        "pageId": enriched.get("pageId", match.group(0)),
                        "pageIndex": enriched.get("pageIndex"),
                        "documentId": enriched.get("documentId"),
                        "documentName": enriched.get("documentName"),
                        "enhancedS3Key": enriched.get("enhancedS3Key"),
                    }
                )
            else:
                # Drop known non-page placeholders so they do not become empty citation objects
                raw_lower = raw.lower()
                if raw_lower in _SOURCE_PLACEHOLDER_VALUES or any(
                    raw_lower.startswith(p) for p in _SOURCE_PLACEHOLDER_PREFIXES
                ):
                    logger.warning(f"Quarantining non-page placeholder source reference: {raw}")
                    normalized.append(
                        {
                            "pageId": None,
                            "documentName": str(item),
                            "enhancedS3Key": None,
                            "unresolvedReference": str(item),
                        }
                    )
                    continue
                # Keep other non-UUID textual references as minimal citation (e.g. document names)
                normalized.append(
                    {
                        "pageId": None,
                        "documentName": str(item),
                        "enhancedS3Key": None,
                        "unresolvedReference": str(item),
                    }
                )

    return normalized


def _extract_source_candidates(value: Any) -> list[Any]:
    """Extract raw source reference candidates from mixed payload structures."""
    if value is None:
        return []
    candidates: list[Any] = []
    if isinstance(value, dict):
        source_keys = (
            "source_pages",
            "sourcePages",
            "source_page_ids",
            "sourcePageIds",
            "page_ids",
            "pageIds",
            "citations",
            "sources",
            "pages",
        )
        for key in source_keys:
            if key in value and value[key] is not None:
                candidates.append(value[key])
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                candidates.extend(_extract_source_candidates(nested))
    elif isinstance(value, list):
        for item in value:
            candidates.extend(_extract_source_candidates(item))
    return candidates


def _normalize_with_fallback(
    primary_source: Any,
    page_lookup: dict[str, dict[str, Any]],
    doc_page_index: dict[tuple[str, int], str] | None = None,
    fallback_sources: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Normalize source pages and deterministically fallback to section-level sources when empty."""
    normalized = _normalize_source_pages(primary_source, page_lookup, doc_page_index)
    if normalized:
        return normalized
    for fallback in fallback_sources or []:
        normalized = _normalize_source_pages(fallback, page_lookup, doc_page_index)
        if normalized:
            return normalized
    return []


def _build_richness_policy(total_pages: int) -> dict[str, int]:
    """Adaptive minimum coverage targets based on dossier size."""
    if total_pages >= 120:
        return {"min_key_findings": 12, "min_important_points": 15, "min_critical_risks": 5}
    if total_pages >= 60:
        return {"min_key_findings": 8, "min_important_points": 10, "min_critical_risks": 3}
    if total_pages >= 25:
        return {"min_key_findings": 5, "min_important_points": 7, "min_critical_risks": 2}
    return {"min_key_findings": 3, "min_important_points": 5, "min_critical_risks": 1}


def _source_page_indices(source_pages: list[dict[str, Any]]) -> list[int]:
    """Convert normalized citation objects to sorted unique page_index integers."""
    indices = {
        item.get("pageIndex")
        for item in source_pages
        if isinstance(item, dict) and isinstance(item.get("pageIndex"), int)
    }
    return sorted(indices)


def _normalize_legacy_source_bundle(
    source_value: Any,
    page_lookup: dict[str, dict[str, Any]],
    doc_page_index: dict[tuple[str, int], str] | None = None,
    fallback_sources: list[Any] | None = None,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Return legacy source_pages (indices) plus enriched companion citations."""
    citations = _normalize_with_fallback(
        source_value,
        page_lookup,
        doc_page_index,
        fallback_sources,
    )
    return _source_page_indices(citations), citations


def _normalize_component_status(status: Any) -> str:
    """Normalize component status to legacy uppercase style."""
    if not isinstance(status, str) or not status.strip():
        return "UNKNOWN"
    normalized = status.strip().replace("-", "_").replace(" ", "_").upper()
    aliases = {
        "SERVICEABLE": "SERVICEABLE",
        "UNSERVICEABLE": "UNSERVICEABLE",
        "OVERHAULED": "OVERHAULED",
        "REPAIRED": "REPAIRED",
        "REMOVED": "REMOVED",
        "NEW": "NEW",
        "INSPECTED": "INSPECTED",
        "CORE": "UNSERVICEABLE",
        "SCRAP": "UNSERVICEABLE",
    }
    return aliases.get(normalized, normalized)


def _normalize_nested_sub_components(
    entries: Any,
    page_lookup: dict[str, dict[str, Any]],
    doc_page_index: dict[tuple[str, int], str] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        source_pages, source_citations = _normalize_legacy_source_bundle(
            entry.get("source_pages", entry.get("sourcePages")),
            page_lookup,
            doc_page_index,
            _extract_source_candidates(entry),
        )
        node = {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "part_number": entry.get("part_number", entry.get("partNumber")),
            "serial_number": entry.get("serial_number", entry.get("serialNumber")),
            "source_pages": source_pages,
            "source_citations": source_citations,
        }
        nested = _normalize_nested_sub_components(
            entry.get("sub_components", entry.get("subComponents")),
            page_lookup,
            doc_page_index,
        )
        if nested:
            node["sub_components"] = nested
        normalized.append(node)
    return normalized


def _build_richness_requirements(total_pages: int) -> str:
    """Runtime task addendum to prevent early sparse outputs on large dossiers."""
    policy = _build_richness_policy(total_pages)
    return (
        "\n### Coverage and Completeness Requirements\n"
        f"- This dossier has {total_pages} pages; do not stop at minimal output.\n"
        f"- Provide at least {policy['min_key_findings']} high-value key findings when evidence exists.\n"
        f"- Provide at least {policy['min_important_points']} important points when evidence exists.\n"
        "- Must-capture categories when present: serial mismatches, unserviceable/core/scrap indicators, "
        "physical defects, TSN/TSO/CSN/CSO, major maintenance events, compliance issues, documentation gaps.\n"
        "- Ensure cross-section consistency: critical blockers must appear in key_findings and risk_assessment.\n"
    )


def _canonicalize_output(
    payload: dict[str, Any],
    args,
    asset_context: dict[str, Any],
    page_lookup: dict[str, dict[str, Any]],
    research_metadata: dict[str, Any],
    canvas_stats: dict[str, Any],
) -> dict[str, Any]:
    """Force a single canonical output shape regardless of model's key style."""
    asset_id = payload.get("asset_id") or payload.get("assetId") or args.asset_id
    asset_name = payload.get("asset_name") or payload.get("assetName") or asset_context.get("asset_name", f"Asset {asset_id}")
    summary_payload = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    analysis_payload = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}

    doc_page_index = _build_doc_page_index(page_lookup)
    findings_fallback_sources = _extract_source_candidates(
        payload.get("extracted_facts")
        or payload.get("extractedFacts")
        or payload.get("extracted_data")
        or summary_payload.get("component_findings")
        or summary_payload.get("extracted_data")
        or payload.get("dossier_overview")
        or summary_payload.get("dossier_structure")
    )
    gaps_fallback_sources = _extract_source_candidates(
        payload.get("gaps_and_risks")
        or payload.get("gapsAndRisks")
        or payload.get("cross_component_gaps")
        or summary_payload.get("cross_component_gaps")
        or analysis_payload.get("gaps")
        or payload.get("identified_gaps")
    )
    regulatory_fallback_sources = _extract_source_candidates(
        payload.get("regulatory_validation")
        or payload.get("validated_regulatory_references")
    )

    findings_in = (
        payload.get("key_findings")
        or payload.get("keyFindings")
        or payload.get("findings")
        or payload.get("extracted_facts")
        or payload.get("extracted_data")
        or payload.get("component_findings")
        or summary_payload.get("key_findings")
        or summary_payload.get("findings")
        or summary_payload.get("component_findings")
        or summary_payload.get("extracted_data")
        or []
    )
    gaps_in = (
        payload.get("gaps")
        or payload.get("gapsAndLimitations")
        or payload.get("gaps_and_ambiguities")
        or payload.get("identified_gaps")
        or payload.get("gaps_and_risks")
        or payload.get("gapsAndRisks")
        or payload.get("cross_component_gaps")
        or summary_payload.get("cross_component_gaps")
        or analysis_payload.get("gaps")
        or []
    )
    gap_analysis_in = payload.get("gap_analysis") or payload.get("gapAnalysis") or []
    contradictions_in = (
        payload.get("contradictions")
        or payload.get("contradictions_found")
        or summary_payload.get("contradictions")
        or analysis_payload.get("contradictions")
        or []
    )
    regulatory_in = (
        payload.get("regulatory_validation")
        or payload.get("validated_regulatory_references")
        or summary_payload.get("regulatory_validation")
        or summary_payload.get("regulatory_validation_gaps")
        or []
    )

    components = payload.get("components", [])
    if not isinstance(components, list):
        components = []

    # Derive components + findings from "findings" shape when present.
    key_findings = []
    derived_component_names: set[str] = set()
    for f in findings_in if isinstance(findings_in, list) else []:
        if isinstance(f, str):
            key_findings.append(
                {
                    "title": "finding",
                    "content": f,
                    "source_pages": [],
                    "confidence": "medium",
                    "validation_status": "unverified",
                }
            )
            continue
        if isinstance(f, dict):
            component_name = f.get("component")
            facts = f.get("facts")
            if isinstance(component_name, str) and component_name and component_name not in derived_component_names:
                derived_component_names.add(component_name)
                component_id = re.sub(r"[^a-z0-9]+", "-", component_name.lower()).strip("-")
                components.append({"id": component_id or component_name.lower(), "name": component_name})

            if isinstance(facts, list):
                for fact in facts:
                    if not isinstance(fact, dict):
                        continue
                    key_findings.append(
                        {
                            "title": component_name or "finding",
                            "content": fact.get("description") or fact.get("content") or fact.get("text") or fact.get("value") or "",
                            "source_pages": _normalize_with_fallback(
                                fact.get("source_pages", fact.get("sourcePages")),
                                page_lookup,
                                doc_page_index,
                                findings_fallback_sources,
                            ),
                            "confidence": fact.get("confidence", "medium"),
                            "validation_status": fact.get("validation_status", fact.get("validationStatus", "unverified")),
                        }
                    )
                for gap in f.get("gaps", []) if isinstance(f.get("gaps"), list) else []:
                    if isinstance(gap, str):
                        gaps_in = list(gaps_in) + [f"{component_name}: {gap}" if component_name else gap]
                continue

            key_findings.append(
                {
                    "title": f.get("title") or f.get("name") or "finding",
                    "content": f.get("content") or f.get("value") or f.get("description") or f.get("text") or "",
                    "source_pages": _normalize_with_fallback(
                        f.get("source_pages", f.get("sourcePages")),
                        page_lookup,
                        doc_page_index,
                        findings_fallback_sources,
                    ),
                    "confidence": f.get("confidence", "medium"),
                    "validation_status": f.get("validation_status", f.get("validationStatus", "unverified")),
                }
            )

    gaps = []
    for g in gaps_in if isinstance(gaps_in, list) else []:
        if isinstance(g, dict):
            gaps.append(
                {
                    "title": g.get("title") or g.get("gap_type") or "gap",
                    "description": g.get("description") or g.get("details") or "",
                    "source_pages": _normalize_with_fallback(
                        g.get("source_pages", g.get("sourcePages", g.get("related_pages"))),
                        page_lookup,
                        doc_page_index,
                        gaps_fallback_sources,
                    ),
                    "confidence": g.get("confidence", "medium"),
                }
            )
        elif isinstance(g, str):
            gaps.append({"title": "gap", "description": g, "source_pages": [], "confidence": "medium"})
    for g in gap_analysis_in if isinstance(gap_analysis_in, list) else []:
        if isinstance(g, str):
            gaps.append({"title": "gap_analysis", "description": g, "source_pages": [], "confidence": "medium"})

    contradictions = []
    for c in contradictions_in if isinstance(contradictions_in, list) else []:
        if isinstance(c, dict):
            contradictions.append(
                {
                    "description": c.get("description") or c.get("content") or "",
                    "source_pages": _normalize_with_fallback(
                        c.get("source_pages", c.get("sourcePages", c.get("related_pages", c.get("sources")))),
                        page_lookup,
                        doc_page_index,
                        findings_fallback_sources + gaps_fallback_sources,
                    ),
                    "confidence": c.get("confidence", "medium"),
                }
            )
        elif isinstance(c, str):
            contradictions.append({"description": c, "source_pages": [], "confidence": "medium"})

    regulatory_validation = []
    for r in regulatory_in if isinstance(regulatory_in, list) else []:
        if isinstance(r, dict):
            regulatory_validation.append(
                {
                    "reference": r.get("reference") or r.get("title") or ("regulatory_observation" if r.get("description") else "unknown"),
                    "status": r.get("status") or r.get("validation_status") or "unknown",
                    "notes": r.get("notes") or r.get("validation_notes") or r.get("content") or r.get("description"),
                    "source_pages": _normalize_with_fallback(
                        r.get("source_pages", r.get("sourcePages")),
                        page_lookup,
                        doc_page_index,
                        regulatory_fallback_sources,
                    ),
                    "confidence": r.get("confidence", "medium"),
                }
            )

    # Deterministic fallback: if canonical lists are empty but raw has extractable content, backfill
    raw_facts = (
        payload.get("extracted_facts")
        or payload.get("extractedFacts")
        or payload.get("extracted_data")
        or summary_payload.get("component_findings")
        or summary_payload.get("extracted_data")
        or []
    )
    raw_gaps = (
        payload.get("gaps_and_risks")
        or payload.get("gapsAndRisks")
        or payload.get("gaps_and_ambiguities")
        or payload.get("cross_component_gaps")
        or summary_payload.get("cross_component_gaps")
        or analysis_payload.get("gaps")
        or []
    )
    regulatory_summary = payload.get("regulatory_validation_summary")
    if not regulatory_validation and isinstance(regulatory_summary, dict):
        sb_items = regulatory_summary.get("service_bulletins") or []
        ad_items = regulatory_summary.get("ads") or []
        merged: list[dict[str, Any]] = []
        for item in sb_items if isinstance(sb_items, list) else []:
            if isinstance(item, dict):
                merged.append(
                    {
                        "reference": item.get("code") or item.get("reference") or "service_bulletin",
                        "status": item.get("status") or regulatory_summary.get("validation_status") or "unknown",
                        "notes": item.get("validation_detail") or item.get("notes"),
                        "source_pages": item.get("source_pages") or item.get("sourcePages") or [],
                        "confidence": item.get("confidence", "medium"),
                    }
                )
        for item in ad_items if isinstance(ad_items, list) else []:
            if isinstance(item, dict):
                merged.append(
                    {
                        "reference": item.get("code") or item.get("reference") or "airworthiness_directive",
                        "status": item.get("status") or regulatory_summary.get("validation_status") or "unknown",
                        "notes": item.get("validation_detail") or item.get("notes"),
                        "source_pages": item.get("source_pages") or item.get("sourcePages") or [],
                        "confidence": item.get("confidence", "medium"),
                    }
                )
            elif isinstance(item, str):
                merged.append(
                    {
                        "reference": item,
                        "status": regulatory_summary.get("validation_status", "unknown"),
                        "notes": regulatory_summary.get("validation_notes"),
                        "source_pages": [],
                        "confidence": "medium",
                    }
                )
        if merged:
            for r in merged:
                regulatory_validation.append(
                    {
                        "reference": r.get("reference") or "regulatory_observation",
                        "status": r.get("status") or "unknown",
                        "notes": r.get("notes"),
                        "source_pages": _normalize_with_fallback(
                            r.get("source_pages", r.get("sourcePages")),
                            page_lookup,
                            doc_page_index,
                            regulatory_fallback_sources,
                        ),
                        "confidence": r.get("confidence", "medium"),
                    }
                )
        elif regulatory_summary.get("validation_notes"):
            regulatory_validation = [
                {
                    "reference": "regulatory_validation_summary",
                    "status": regulatory_summary.get("validation_status", "unknown"),
                    "notes": regulatory_summary.get("validation_notes"),
                    "source_pages": [],
                    "confidence": "medium",
                }
            ]
    if not key_findings and isinstance(raw_facts, list) and raw_facts:
        logger.warning("key_findings empty but raw extracted_facts present; backfilling from extracted_facts")
        for f in raw_facts:
            if isinstance(f, dict):
                key_findings.append(
                    {
                        "title": "finding",
                        "content": f.get("description") or f.get("content") or f.get("text") or f.get("value") or "",
                        "source_pages": _normalize_with_fallback(
                            f.get("source_pages", f.get("sourcePages")),
                            page_lookup,
                            doc_page_index,
                            findings_fallback_sources,
                        ),
                        "confidence": f.get("confidence", "medium"),
                        "validation_status": f.get("validation_status", f.get("validationStatus", "unverified")),
                    }
                )
            elif isinstance(f, str):
                key_findings.append(
                    {"title": "finding", "content": f, "source_pages": [], "confidence": "medium", "validation_status": "unverified"}
                )
    if not key_findings and isinstance(components, list) and components:
        logger.warning("key_findings empty but components[].findings present; backfilling from components")
        for component in components:
            if not isinstance(component, dict):
                continue
            component_name = component.get("name") or component.get("component") or "component"
            component_findings = component.get("findings")
            for fact in component_findings if isinstance(component_findings, list) else []:
                if not isinstance(fact, dict):
                    continue
                key_findings.append(
                    {
                        "title": component_name,
                        "content": fact.get("description") or fact.get("content") or fact.get("text") or "",
                        "source_pages": _normalize_with_fallback(
                            fact.get("source_pages", fact.get("sourcePages")),
                            page_lookup,
                            doc_page_index,
                            findings_fallback_sources,
                        ),
                        "confidence": fact.get("confidence", "medium"),
                        "validation_status": fact.get("validation_status", fact.get("validationStatus", "unverified")),
                    }
                )
    if not gaps and isinstance(raw_gaps, list) and raw_gaps:
        logger.warning("gaps empty but raw gaps_and_risks present; backfilling from gaps_and_risks")
        for g in raw_gaps:
            if isinstance(g, dict):
                gaps.append(
                    {
                        "title": g.get("title") or g.get("gap_type") or "gap",
                        "description": g.get("description") or g.get("details") or "",
                        "source_pages": _normalize_with_fallback(
                            g.get("source_pages", g.get("sourcePages")),
                            page_lookup,
                            doc_page_index,
                            gaps_fallback_sources,
                        ),
                        "confidence": g.get("confidence", "medium"),
                    }
                )
            elif isinstance(g, str):
                gaps.append({"title": "gap", "description": g, "source_pages": [], "confidence": "medium"})

    canonical_output = {
        "asset_id": asset_id,
        "asset_name": asset_name,
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_components": len(components),
            "total_helicopters": payload.get("total_helicopters"),
            "total_aircraft": payload.get("total_aircraft"),
            "source_pages_count": asset_context.get("total_pages", 0),
            "components_by_helicopter": payload.get("components_by_helicopter", {}),
            "components_by_aircraft": payload.get("components_by_aircraft", {}),
        },
        "components": components,
        "key_findings": key_findings,
        "regulatory_validation": regulatory_validation,
        "gaps": gaps,
        "contradictions": contradictions,
        "recommendations": payload.get("recommendations", summary_payload.get("recommendations", [])),
        "notes": payload.get("notes", []),
        "_research_metadata": research_metadata,
        "_canvas_stats": canvas_stats,
        "_raw_model_output": payload,
    }

    def _asset_status(status_value: Any) -> str:
        if isinstance(status_value, str) and status_value.strip():
            normalized = status_value.strip().lower()
            if normalized in {"serviceable", "unserviceable", "core", "scrap", "overhauled", "removed", "unknown"}:
                return normalized.capitalize() if normalized != "unknown" else "Unknown"
        joined_findings = " ".join(
            [
                str(f.get("content", ""))
                for f in canonical_output.get("key_findings", [])
                if isinstance(f, dict)
            ]
        ).lower()
        if any(word in joined_findings for word in ("unserviceable", "core", "scrap", "ber", "beyond repair")):
            return "Unserviceable"
        if any(word in joined_findings for word in ("serviceable", "released to service", "airworthy")):
            return "Serviceable"
        return "Unknown"

    def _metric(raw_value: Any, unit: str) -> dict[str, Any]:
        if isinstance(raw_value, dict):
            value = raw_value.get("value")
            raw_unit = raw_value.get("unit") or unit
            return {"value": value if isinstance(value, (int, float)) else None, "unit": str(raw_unit)}
        if isinstance(raw_value, (int, float)):
            return {"value": raw_value, "unit": unit}
        return {"value": None, "unit": unit}

    def _dedupe_text_rows(rows: list[dict[str, Any]], text_key: str) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            text = str(row.get(text_key, "")).strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(row)
        return out

    ai_in = payload.get("asset_identification") if isinstance(payload.get("asset_identification"), dict) else {}
    es_in = payload.get("executive_summary") if isinstance(payload.get("executive_summary"), dict) else {}
    util_in = payload.get("utilization_metrics") if isinstance(payload.get("utilization_metrics"), dict) else {}
    config_in = payload.get("configuration") if isinstance(payload.get("configuration"), dict) else {}
    risk_in = payload.get("risk_assessment") if isinstance(payload.get("risk_assessment"), dict) else {}
    legacy_policy = _build_richness_policy(int(asset_context.get("total_pages", 0) or 0))

    model_pages, model_citations = _normalize_legacy_source_bundle(
        ai_in.get("model_source_pages", ai_in.get("modelSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(ai_in.get("model")),
    )
    serial_pages, serial_citations = _normalize_legacy_source_bundle(
        ai_in.get("serial_number_source_pages", ai_in.get("serialNumberSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(ai_in.get("serial_number")),
    )
    asset_type_pages, asset_type_citations = _normalize_legacy_source_bundle(
        ai_in.get("asset_type_source_pages", ai_in.get("assetTypeSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(ai_in.get("asset_type")),
    )
    part_pages, part_citations = _normalize_legacy_source_bundle(
        ai_in.get("part_number_source_pages", ai_in.get("partNumberSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(ai_in.get("part_number")),
    )
    status_pages, status_citations = _normalize_legacy_source_bundle(
        ai_in.get("status_source_pages", ai_in.get("statusSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(ai_in.get("status")),
    )

    operational_pages, operational_citations = _normalize_legacy_source_bundle(
        es_in.get("operational_state_source_pages", es_in.get("operationalStateSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(es_in.get("operational_state")),
    )
    operator_pages, operator_citations = _normalize_legacy_source_bundle(
        es_in.get("last_operator_source_pages", es_in.get("lastOperatorSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(es_in.get("last_operator")),
    )
    location_pages, location_citations = _normalize_legacy_source_bundle(
        es_in.get("location_source_pages", es_in.get("locationSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(es_in.get("location")),
    )
    preservation_pages, preservation_citations = _normalize_legacy_source_bundle(
        es_in.get("preservation_status_source_pages", es_in.get("preservationStatusSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(es_in.get("preservation_status")),
    )

    tsn_pages, tsn_citations = _normalize_legacy_source_bundle(
        util_in.get("total_time_since_new_source_pages", util_in.get("totalTimeSinceNewSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(util_in.get("total_time_since_new")),
    )
    csn_pages, csn_citations = _normalize_legacy_source_bundle(
        util_in.get("total_cycles_since_new_source_pages", util_in.get("totalCyclesSinceNewSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(util_in.get("total_cycles_since_new")),
    )
    tso_pages, tso_citations = _normalize_legacy_source_bundle(
        util_in.get("time_since_overhaul_source_pages", util_in.get("timeSinceOverhaulSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(util_in.get("time_since_overhaul")),
    )
    cso_pages, cso_citations = _normalize_legacy_source_bundle(
        util_in.get("cycles_since_overhaul_source_pages", util_in.get("cyclesSinceOverhaulSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(util_in.get("cycles_since_overhaul")),
    )
    last_activity_pages, last_activity_citations = _normalize_legacy_source_bundle(
        util_in.get("last_activity_date_source_pages", util_in.get("lastActivityDateSourcePages")),
        page_lookup,
        doc_page_index,
        _extract_source_candidates(util_in.get("last_activity_date")),
    )

    legacy_components: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        source_pages, source_citations = _normalize_legacy_source_bundle(
            component.get("source_pages", component.get("sourcePages")),
            page_lookup,
            doc_page_index,
            _extract_source_candidates(component),
        )
        normalized_component: dict[str, Any] = {
            "id": component.get("id"),
            "name": component.get("name") or component.get("component") or "Component",
            "status": _normalize_component_status(component.get("status", component.get("condition"))),
            "category": component.get("category", component.get("component_type", "OTHER")),
            "part_number": component.get("part_number", component.get("partNumber")),
            "serial_number": component.get("serial_number", component.get("serialNumber")),
            "manufacturer": component.get("manufacturer"),
            "source_pages": source_pages,
            "source_citations": source_citations,
        }
        if isinstance(component.get("last_work"), dict):
            normalized_component["last_work"] = component.get("last_work")
        if isinstance(component.get("life_limit"), dict):
            normalized_component["life_limit"] = component.get("life_limit")
        if isinstance(component.get("utilization"), dict):
            normalized_component["utilization"] = component.get("utilization")
        if isinstance(component.get("work_history"), list):
            work_rows = []
            for row in component.get("work_history"):
                if not isinstance(row, dict):
                    continue
                row_pages, row_citations = _normalize_legacy_source_bundle(
                    row.get("source_pages", row.get("sourcePages")),
                    page_lookup,
                    doc_page_index,
                    _extract_source_candidates(row),
                )
                out_row = dict(row)
                out_row["source_pages"] = row_pages
                out_row["source_citations"] = row_citations
                work_rows.append(out_row)
            normalized_component["work_history"] = work_rows
        if isinstance(component.get("modifications"), list):
            mod_rows = []
            for row in component.get("modifications"):
                if not isinstance(row, dict):
                    continue
                row_pages, row_citations = _normalize_legacy_source_bundle(
                    row.get("source_pages", row.get("sourcePages")),
                    page_lookup,
                    doc_page_index,
                    _extract_source_candidates(row),
                )
                out_row = dict(row)
                out_row["source_pages"] = row_pages
                out_row["source_citations"] = row_citations
                mod_rows.append(out_row)
            normalized_component["modifications"] = mod_rows
        sub_components = _normalize_nested_sub_components(
            component.get("sub_components", component.get("subComponents")),
            page_lookup,
            doc_page_index,
        )
        if sub_components:
            normalized_component["sub_components"] = sub_components
        if component.get("helicopter_id"):
            normalized_component["helicopter_id"] = component.get("helicopter_id")
        legacy_components.append(normalized_component)

    legacy_key_findings: list[dict[str, Any]] = []
    for finding in canonical_output["key_findings"]:
        if not isinstance(finding, dict):
            continue
        finding_text = str(finding.get("content") or finding.get("title") or "").strip()
        if not finding_text:
            continue
        source_citations = finding.get("source_pages") if isinstance(finding.get("source_pages"), list) else []
        legacy_key_findings.append(
            {
                "finding": finding_text,
                "source_pages": _source_page_indices(source_citations),
                "source_citations": source_citations,
            }
        )

    for gap in gaps:
        if len(legacy_key_findings) >= legacy_policy["min_key_findings"]:
            break
        if isinstance(gap, dict):
            text = str(gap.get("description", "")).strip()
            if text:
                source_citations = gap.get("source_pages") if isinstance(gap.get("source_pages"), list) else []
                legacy_key_findings.append(
                    {
                        "finding": text,
                        "source_pages": _source_page_indices(source_citations),
                        "source_citations": source_citations,
                    }
                )

    for component in legacy_components:
        if len(legacy_key_findings) >= legacy_policy["min_key_findings"]:
            break
        status = component.get("status")
        if isinstance(status, str) and status and status != "UNKNOWN":
            legacy_key_findings.append(
                {
                    "finding": f"{component.get('name', 'Component')} status: {status}",
                    "source_pages": component.get("source_pages", []),
                    "source_citations": component.get("source_citations", []),
                }
            )

    legacy_key_findings = _dedupe_text_rows(legacy_key_findings, "finding")

    critical_risks: list[dict[str, Any]] = []
    for risk in risk_in.get("critical_risks", []) if isinstance(risk_in.get("critical_risks"), list) else []:
        if not isinstance(risk, dict):
            continue
        source_pages, source_citations = _normalize_legacy_source_bundle(
            risk.get("source_pages", risk.get("sourcePages")),
            page_lookup,
            doc_page_index,
            _extract_source_candidates(risk),
        )
        critical_risks.append(
            {
                "risk": risk.get("risk", risk.get("description", "")),
                "severity": str(risk.get("severity", "MEDIUM")).upper(),
                "implication": risk.get("implication"),
                "source_pages": source_pages,
                "source_citations": source_citations,
            }
        )

    high_impact_keywords = ("mismatch", "unserviceable", "core", "scrap", "corrosion", "crack", "leak", "damage")
    for finding in legacy_key_findings:
        if len(critical_risks) >= legacy_policy["min_critical_risks"]:
            break
        text = str(finding.get("finding", ""))
        lower = text.lower()
        if any(k in lower for k in high_impact_keywords):
            severity = "CRITICAL" if any(k in lower for k in ("mismatch", "unserviceable", "core", "scrap")) else "HIGH"
            critical_risks.append(
                {
                    "risk": text,
                    "severity": severity,
                    "implication": None,
                    "source_pages": finding.get("source_pages", []),
                    "source_citations": finding.get("source_citations", []),
                }
            )
    critical_risks = _dedupe_text_rows(critical_risks, "risk")

    documentation_gaps: list[dict[str, Any]] = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        description = str(gap.get("description", "")).strip()
        if not description:
            continue
        documentation_gaps.append(
            {
                "document": gap.get("title", "Gap"),
                "impact": description,
                "source_pages": _source_page_indices(gap.get("source_pages", [])),
                "source_citations": gap.get("source_pages", []),
            }
        )
    documentation_gaps = _dedupe_text_rows(documentation_gaps, "impact")

    legacy_important_points: list[dict[str, Any]] = []
    for point in payload.get("important_points", []) if isinstance(payload.get("important_points"), list) else []:
        if not isinstance(point, dict):
            continue
        source_pages, source_citations = _normalize_legacy_source_bundle(
            point.get("source_pages", point.get("sourcePages")),
            page_lookup,
            doc_page_index,
            _extract_source_candidates(point),
        )
        legacy_important_points.append(
            {
                "title": point.get("title", "Point"),
                "data": point.get("data", point.get("value")),
                "source_pages": source_pages,
                "source_citations": source_citations,
            }
        )

    utilization_candidates = [
        ("TSN", util_in.get("total_time_since_new")),
        ("CSN", util_in.get("total_cycles_since_new")),
        ("TSO", util_in.get("time_since_overhaul")),
        ("CSO", util_in.get("cycles_since_overhaul")),
        ("Last Activity Date", util_in.get("last_activity_date")),
    ]
    for title, value in utilization_candidates:
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("value")
        legacy_important_points.append(
            {
                "title": title,
                "data": value,
                "source_pages": [],
                "source_citations": [],
            }
        )
    for finding in legacy_key_findings:
        if len(legacy_important_points) >= legacy_policy["min_important_points"]:
            break
        legacy_important_points.append(
            {
                "title": "Finding",
                "data": finding.get("finding"),
                "source_pages": finding.get("source_pages", []),
                "source_citations": finding.get("source_citations", []),
            }
        )
    legacy_important_points = _dedupe_text_rows(legacy_important_points, "data")

    legacy_modules = config_in.get("modules") if isinstance(config_in.get("modules"), list) else []
    legacy_accessories = config_in.get("accessories") if isinstance(config_in.get("accessories"), list) else []
    if not legacy_modules:
        for component in legacy_components:
            legacy_modules.append(
                {
                    "name": component.get("name"),
                    "part_number": component.get("part_number"),
                    "serial_number": component.get("serial_number"),
                    "status": component.get("status"),
                    "tsn": (component.get("utilization", {}).get("tsn", {}) or {}).get("value")
                    if isinstance(component.get("utilization"), dict)
                    else None,
                    "tso": (component.get("utilization", {}).get("tso", {}) or {}).get("value")
                    if isinstance(component.get("utilization"), dict)
                    else None,
                    "notes": None,
                    "source_pages": component.get("source_pages", []),
                    "source_citations": component.get("source_citations", []),
                }
            )
    if not legacy_accessories:
        for component in legacy_components:
            name = str(component.get("name", "")).lower()
            category = str(component.get("category", "")).upper()
            if "accessor" in name or category in {"AVIONICS", "ELECTRICAL", "SAFETY_EQUIPMENT"}:
                legacy_accessories.append(
                    {
                        "component": component.get("name"),
                        "part_number": component.get("part_number"),
                        "serial_number": component.get("serial_number"),
                        "status": component.get("status"),
                        "source_pages": component.get("source_pages", []),
                        "source_citations": component.get("source_citations", []),
                    }
                )

    legacy_output = {
        "asset_id": canonical_output["asset_id"],
        "metadata": canonical_output["metadata"],
        "asset_name": canonical_output["asset_name"],
        "asset_identification": {
            "model": ai_in.get("model"),
            "model_source_pages": model_pages,
            "model_source_citations": model_citations,
            "serial_number": ai_in.get("serial_number"),
            "serial_number_source_pages": serial_pages,
            "serial_number_source_citations": serial_citations,
            "asset_type": ai_in.get("asset_type", payload.get("asset_type")),
            "asset_type_source_pages": asset_type_pages,
            "asset_type_source_citations": asset_type_citations,
            "part_number": ai_in.get("part_number"),
            "part_number_source_pages": part_pages,
            "part_number_source_citations": part_citations,
            "status": _asset_status(ai_in.get("status", payload.get("status"))),
            "status_source_pages": status_pages,
            "status_source_citations": status_citations,
        },
        "executive_summary": {
            "operational_state": es_in.get("operational_state")
            or (legacy_key_findings[0]["finding"] if legacy_key_findings else None),
            "operational_state_source_pages": operational_pages,
            "operational_state_source_citations": operational_citations,
            "last_operator": es_in.get("last_operator"),
            "last_operator_source_pages": operator_pages,
            "last_operator_source_citations": operator_citations,
            "location": es_in.get("location"),
            "location_source_pages": location_pages,
            "location_source_citations": location_citations,
            "data_confidence": es_in.get("data_confidence", "MEDIUM"),
            "preservation_status": es_in.get("preservation_status"),
            "preservation_status_source_pages": preservation_pages,
            "preservation_status_source_citations": preservation_citations,
        },
        "utilization_metrics": {
            "total_time_since_new": _metric(util_in.get("total_time_since_new"), "hours"),
            "total_time_since_new_source_pages": tsn_pages,
            "total_time_since_new_source_citations": tsn_citations,
            "total_cycles_since_new": _metric(util_in.get("total_cycles_since_new"), "cycles"),
            "total_cycles_since_new_source_pages": csn_pages,
            "total_cycles_since_new_source_citations": csn_citations,
            "time_since_overhaul": _metric(util_in.get("time_since_overhaul"), "hours"),
            "time_since_overhaul_source_pages": tso_pages,
            "time_since_overhaul_source_citations": tso_citations,
            "cycles_since_overhaul": _metric(util_in.get("cycles_since_overhaul"), "cycles"),
            "cycles_since_overhaul_source_pages": cso_pages,
            "cycles_since_overhaul_source_citations": cso_citations,
            "last_activity_date": util_in.get("last_activity_date"),
            "last_activity_date_source_pages": last_activity_pages,
            "last_activity_date_source_citations": last_activity_citations,
            "notes": util_in.get("notes"),
        },
        "components": legacy_components,
        "configuration": {
            "modules": legacy_modules,
            "accessories": legacy_accessories,
        },
        "risk_assessment": {
            "critical_risks": critical_risks,
            "documentation_gaps": documentation_gaps,
        },
        "key_findings": legacy_key_findings,
        "important_points": legacy_important_points,
        # Preserve richer current-agent sections in dual-mode output.
        "regulatory_validation": canonical_output["regulatory_validation"],
        "gaps": canonical_output["gaps"],
        "contradictions": canonical_output["contradictions"],
        "recommendations": canonical_output["recommendations"],
        "notes": canonical_output["notes"],
        "_research_metadata": canonical_output["_research_metadata"],
        "_canvas_stats": canonical_output["_canvas_stats"],
        "_raw_model_output": canonical_output["_raw_model_output"],
    }

    cited_pages = {
        idx
        for section in (
            legacy_key_findings,
            legacy_important_points,
            legacy_components,
            critical_risks,
            documentation_gaps,
        )
        for idx in (
            section.get("source_pages", [])
            if isinstance(section, dict)
            else [
                i
                for row in section
                if isinstance(row, dict)
                for i in row.get("source_pages", [])
            ]
        )
        if isinstance(idx, int)
    }
    total_pages = int(asset_context.get("total_pages", 0) or 0)
    uncited_ratio = (max(total_pages - len(cited_pages), 0) / total_pages) if total_pages > 0 else 0.0
    legacy_output["_coverage"] = {
        "total_pages": total_pages,
        "cited_page_count": len(cited_pages),
        "uncited_page_ratio": round(uncited_ratio, 3),
        "adaptive_policy": legacy_policy,
        "second_pass_triggered": uncited_ratio > 0.8 and total_pages >= 25,
    }

    return legacy_output


async def get_asset_context(asset_id: str) -> dict:
    """
    Fetch asset metadata for context injection.
    
    In production, this would query the Supabase database.
    For now, returns a placeholder structure.
    """
    # TODO: Implement actual database query when Supabase tools are connected
    # This is a placeholder that returns mock data
    
    # Check if we have a database connection
    try:
        from src.tools.asset_dossier.db_client import SupabaseAsyncClient
        
        db = await SupabaseAsyncClient.get_instance()
        
        # Get asset overview
        asset = await db.fetchrow("""
            SELECT a.id, a.name, a.status,
                   COALESCE(a.total_documents, COUNT(DISTINCT dpr.id)) as total_documents,
                   COALESCE(a.total_pages, COUNT(DISTINCT dp.id)) as total_pages
            FROM assets a
            LEFT JOIN document_processing_records dpr ON dpr.asset_id = a.id
            LEFT JOIN document_pages dp ON dp.document_id = dpr.id
            WHERE a.id = $1
            GROUP BY a.id
        """, asset_id)
        
        if not asset:
            logger.warning(f"Asset not found in database: {asset_id}")
            return _get_mock_asset_context(asset_id)
        
        # Get document types
        doc_types = await db.fetch("""
            SELECT DISTINCT 
                CASE 
                    WHEN original_path ILIKE '%logbook%' THEN 'Logbook'
                    WHEN original_path ILIKE '%workorder%' OR original_path ILIKE '%work order%' THEN 'Work Order'
                    WHEN original_path ILIKE '%sb%' OR original_path ILIKE '%service bulletin%' THEN 'Service Bulletin'
                    WHEN original_path ILIKE '%ad%' OR original_path ILIKE '%airworthiness%' THEN 'AD Compliance'
                    ELSE 'Other'
                END as doc_type
            FROM document_processing_records
            WHERE asset_id = $1
        """, asset_id)
        
        return {
            "asset_id": asset_id,
            "asset_name": asset["name"],
            "status": asset["status"],
            "total_documents": asset["total_documents"],
            "total_pages": asset["total_pages"],
            "document_types": [d["doc_type"] for d in doc_types],
            "database_connected": True
        }
        
    except Exception as e:
        logger.warning(f"Could not connect to database: {e}")
        return _get_mock_asset_context(asset_id)


def _get_mock_asset_context(asset_id: str) -> dict:
    """Return mock asset context for testing."""
    return {
        "asset_id": asset_id,
        "asset_name": f"Test Asset {asset_id}",
        "status": "pending_analysis",
        "total_documents": 0,
        "total_pages": 0,
        "document_types": ["Unknown"],
        "database_connected": False
    }


async def run_asset_research_programmatic(
    asset_id: str,
    prompt: str = "Produce a comprehensive analysis of this asset dossier",
    depth: str = "standard",
) -> dict[str, Any]:
    """
    Programmatic entry point for API use.
    Returns the research output dict without saving to file.
    """
    from argparse import Namespace

    args = Namespace(
        config="configs/config_asset_research.py",
        asset_id=asset_id,
        prompt=prompt,
        depth=depth,
        output=None,
        stream=False,
        verbose=False,
        live_monitor=False,
        cfg_options=[],
    )
    return await _execute_research(args, save_to_file=True)


async def _execute_research(args, save_to_file: bool = True) -> dict[str, Any]:
    """Core research execution - shared by CLI and API."""
    start_time = datetime.utcnow()

    print(f"\n{'='*60}")
    print("  Asset Dossier Research Agent")
    print(f"{'='*60}\n")
    
    # 0. Ensure workdir exists before config initialization
    workdir = Path("workdir")
    workdir.mkdir(parents=True, exist_ok=True)
    
    # 1. Initialize configuration
    print(f"Loading configuration from: {args.config}")
    config.init_config(args.config, args)

    # Fallback from Anthropic to Gemini/OpenAI when Anthropic key is missing.
    if not os.getenv("ANTHROPIC_API_KEY"):
        fallback_model_id = "gemini-3-pro-preview" if os.getenv("GOOGLE_API_KEY") else "gpt-4.1"
        for key in [
            "agent_config",
            "planning_agent_config",
            "asset_extractor_agent_config",
            "deep_analyzer_agent_config",
        ]:
            agent_cfg = config.get(key)
            if isinstance(agent_cfg, dict) and str(agent_cfg.get("model_id", "")).startswith("claude"):
                agent_cfg["model_id"] = fallback_model_id
    
    # 2. Initialize logger
    logger.init_logger(log_path=config.log_path)
    logger.info(f"Starting Asset Research for: {args.asset_id}")
    
    # 3. Initialize observability
    emitter = EventEmitter.get_instance()
    trace_id = emitter.start_trace()
    print(f"Trace ID: {trace_id}")
    
    # Set up console logging
    if args.live_monitor:
        try:
            from src.observability.console_monitor import ConsoleLiveMonitor
            monitor = ConsoleLiveMonitor()
            monitor.start()
        except ImportError:
            print("Rich library not available for live monitor, using simple logger")
            console_logger = SimpleConsoleLogger(verbose=args.verbose)
            console_logger.attach()
    else:
        console_logger = SimpleConsoleLogger(verbose=args.verbose)
        console_logger.attach()
    
    # 4. Initialize models
    print("Initializing models...")
    model_manager.init_models(use_local_proxy=config.use_local_proxy)
    
    # 5. Initialize shared canvas
    print("Setting up working memory canvas...")
    canvas = WorkingMemoryCanvas(
        max_entries=config.get("canvas_config", {}).get("max_entries", 1000),
        auto_summarize=config.get("canvas_config", {}).get("auto_summarize", True)
    )
    CanvasTool.set_shared_canvas(canvas)

    # 5b. Create run_dir early when saving, so we can persist canvas after each step
    run_dir = None
    output_path = None
    canvas_path = None
    if save_to_file:
        run_stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        run_dir = Path("workdir") / f"asset_research_{args.asset_id}_{run_stamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = args.output or str(run_dir / "output.json")
        canvas_path = str(run_dir / "canvas.json")

    # 6. Get asset context
    print(f"Fetching asset context for: {args.asset_id}")
    try:
        asset_context = await get_asset_context(args.asset_id)
    except Exception as e:
        logger.warning(f"Could not get asset context: {e}")
        asset_context = _get_mock_asset_context(args.asset_id)
    
    print(f"Asset: {asset_context.get('asset_name', 'Unknown')}")
    print(f"Pages: {asset_context.get('total_pages', 'Unknown')}")
    print(f"Documents: {asset_context.get('total_documents', 'Unknown')}")
    print(f"Database connected: {asset_context.get('database_connected', False)}")

    # Inject asset context into config for prompt templates
    config.asset_id = args.asset_id
    config.asset_name = asset_context.get("asset_name", "")
    config.total_pages = asset_context.get("total_pages", 0)
    config.total_documents = asset_context.get("total_documents", 0)
    config.document_types = asset_context.get("document_types", [])
    os.environ["ASSET_ID"] = args.asset_id
    
    # 7. Build the task with context
    coverage_requirements = _build_richness_requirements(int(asset_context.get("total_pages", 0) or 0))
    task = f"""
## Asset Dossier Research Task

### Asset Information
- Asset ID: {args.asset_id}
- Asset Name: {asset_context.get('asset_name', 'Unknown')}
- Total Documents: {asset_context.get('total_documents', 'Unknown')}
- Total Pages: {asset_context.get('total_pages', 'Unknown')}
- Document Types: {', '.join(asset_context.get('document_types', ['Unknown']))}

### Research Request
{args.prompt}

### Research Depth
{args.depth}

### Requirements
1. Every extracted fact MUST include source page citations
2. Validate regulatory references (ADs, SBs) against FAA/EASA databases
3. Report confidence levels for each finding
4. Identify gaps and contradictions
5. Output must be valid JSON matching AssetResearchOutput schema
{coverage_requirements}
"""
    
    print(f"\n{'='*60}")
    print("  Starting Analysis")
    print(f"{'='*60}\n")
    
    # 8. Create agent
    agent = await create_agent(config)

    # 8b. Register step callback to persist canvas after each agent step
    if save_to_file and canvas_path:

        def _save_canvas_after_step(memory_step, agent=None):
            if canvas.entries:
                try:
                    canvas.save_to_file(canvas_path)
                    logger.debug(f"Canvas persisted ({len(canvas.entries)} entries) after step")
                except Exception as e:
                    logger.warning(f"Failed to persist canvas after step: {e}")

        agent.step_callbacks.append(_save_canvas_after_step)

    # 9. Run the agent
    try:
        additional_args = {
            "asset_id": args.asset_id,
            "asset_name": asset_context.get("asset_name", ""),
            "total_pages": asset_context.get("total_pages", 0),
            "total_documents": asset_context.get("total_documents", 0),
            "document_types": asset_context.get("document_types", []),
        }
        if args.stream:
            # Streaming mode
            print("Running in streaming mode...\n")
            final_result = None
            async for chunk in agent.run_stream(task, additional_args=additional_args):
                if isinstance(chunk, FinalAnswerStep):
                    final_result = chunk.output
                else:
                    print(chunk, end="", flush=True)
            result = final_result
        else:
            # Normal mode
            result = await agent.run(task, additional_args=additional_args)
        
        # 10. Prepare final response with reformulation
        if config.get("reformulation_model_id"):
            final_result = await prepare_response(
                task=task,
                agent_memory=agent.memory,
                reformulation_model=model_manager.registed_models.get(
                    config.get("reformulation_model_id", "gemini-3-pro-preview")
                )
            )
        else:
            final_result = result

        # Normalize ToolResult payload (e.g. from final_answer_tool)
        final_result = _unwrap_tool_result(final_result)

        # Debug: Log what we got from the agent
        logger.debug(f"Agent returned type: {type(final_result)}")
        if isinstance(final_result, str):
            logger.debug(f"Agent returned string (first 200 chars): {final_result[:200]}")

        # Ensure final_result is parsed JSON, not a string
        if isinstance(final_result, str):
            try:
                parsed = _loads_json_with_repair(final_result)
                # Handle double-encoded JSON
                if isinstance(parsed, str):
                    logger.debug("Detected double-encoded JSON, parsing again...")
                    parsed = _loads_json_with_repair(parsed)
                final_result = parsed
                logger.debug(f"Successfully parsed JSON, type: {type(final_result)}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error at position {e.pos}: {e.msg}")
                logger.error(f"Context around error: {final_result[max(0, e.pos-50):e.pos+50]}")
                # If parsing fails, wrap the string in a dict
                final_result = {"raw_output": final_result, "parse_error": str(e)}
            except Exception as e:
                logger.error(f"Failed to sanitize/parse JSON output: {e}", exc_info=True)
                # If parsing fails, wrap the string in a dict
                final_result = {"raw_output": final_result, "parse_error": str(e)}
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        final_result = {"error": str(e)}
        result = None
    
    # 11. Build output with metadata
    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

    # Defensive normalization in case a ToolResult slipped through
    final_result = _unwrap_tool_result(final_result)
    
    # Final parsing attempt - ensure result is always a dict, never a string
    if isinstance(final_result, str):
        logger.warning(f"final_result is still a string before save! Attempting final parse...")
        try:
            parsed = _loads_json_with_repair(final_result)
            if isinstance(parsed, str):
                logger.debug("Double-encoded JSON detected in final parse")
                parsed = _loads_json_with_repair(parsed)
            final_result = parsed
            logger.info(f"Successfully parsed final_result, now type: {type(final_result)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in final parse at position {e.pos}: {e.msg}")
            logger.error(f"Context: {final_result[max(0, e.pos-100):e.pos+100]}")
            # Store as structured error instead of string
            final_result = {
                "error": "Failed to parse agent output as JSON",
                "parse_error": str(e),
                "raw_output_preview": final_result[:1000] if len(final_result) > 1000 else final_result
            }

    # If previous fallback stored JSON text in parsed_result, parse and merge it now.
    if (
        isinstance(final_result, dict)
        and isinstance(final_result.get("parsed_result"), str)
        and final_result["parsed_result"].lstrip().startswith(("{", "["))
    ):
        try:
            reparsed = _loads_json_with_repair(final_result["parsed_result"])
            if isinstance(reparsed, str):
                reparsed = _loads_json_with_repair(reparsed)
            if isinstance(reparsed, dict):
                warning = final_result.get("_warning")
                final_result = reparsed
                if warning:
                    final_result["_warning"] = warning
                logger.info("Recovered dict from stringified parsed_result")
            else:
                final_result["parsed_result"] = reparsed
        except Exception as e:
            logger.warning(f"Could not parse parsed_result field: {e}")
        except Exception as e:
            logger.error(f"Failed to parse JSON output before save: {e}", exc_info=True)
            logger.error(f"Raw output (first 500 chars): {final_result[:500]}")
            # Store as structured error instead of string
            final_result = {
                "error": "Failed to parse agent output as JSON",
                "parse_error": str(e),
                "raw_output_preview": final_result[:1000] if len(final_result) > 1000 else final_result
            }
    
    # Ensure final_result is a dict, not a string
    if not isinstance(final_result, dict):
        logger.error(f"CRITICAL: final_result is not a dict before output building! Type: {type(final_result)}, Value: {str(final_result)[:200]}")
        final_result = {"parsed_result": final_result, "_warning": "Output was not a dict"}

    # Build output structure matching SummaryJson schema
    # Use final_result as the base, ensuring it's a dict with proper structure
    logger.info(f"Building output structure. final_result type: {type(final_result)}")
    
    if isinstance(final_result, dict):
        logger.info(f"final_result is dict with keys: {list(final_result.keys())[:10]}")
        # Start with final_result as base
        output = final_result.copy()
        
        # Ensure required top-level fields exist
        output["asset_id"] = output.get("asset_id", args.asset_id)
        output["asset_name"] = output.get("asset_name", asset_context.get("asset_name", f"Asset {args.asset_id}"))
        
        # Build/update metadata section
        if "metadata" not in output:
            output["metadata"] = {}
        output["metadata"].update({
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_components": output.get("total_components", len(output.get("components", []))),
            "total_helicopters": output.get("total_helicopters"),
            "total_aircraft": output.get("total_aircraft"),
            "source_pages_count": asset_context.get("total_pages", 0),
            "components_by_helicopter": output.get("components_by_helicopter", {}),
            "components_by_aircraft": output.get("components_by_aircraft", {}),
        })
        
        # Add research metadata for debugging/tracking (optional)
        output["_research_metadata"] = {
            "prompt": args.prompt,
            "total_pages_analyzed": asset_context.get("total_pages", 0),
            "research_depth": args.depth,
            "processing_time_ms": int(processing_time),
            "agent_version": "1.0.0",
            "trace_id": trace_id,
            "database_connected": asset_context.get("database_connected", False),
            "agents_used": list(agent.managed_agents.keys()) if hasattr(agent, 'managed_agents') and agent.managed_agents else [],
        }
        
        # Add canvas stats for debugging (optional)
        output["_canvas_stats"] = canvas.get_stats()
        
        logger.info(f"Output structure built. Top-level keys: {list(output.keys())[:15]}")
    else:
        # Fallback: if final_result is not a dict, create structured error output
        output = {
            "asset_id": args.asset_id,
            "asset_name": asset_context.get("asset_name", f"Asset {args.asset_id}"),
            "metadata": {
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "total_components": 0,
                "source_pages_count": asset_context.get("total_pages", 0),
            },
            "components": [],
            "key_findings": [],
            "error": "Agent output was not in expected JSON format",
            "raw_output": str(final_result)[:1000] if isinstance(final_result, str) else str(final_result),
            "_research_metadata": {
                "prompt": args.prompt,
                "processing_time_ms": int(processing_time),
                "trace_id": trace_id,
            }
        }
    
    # 12. Save output (run_dir/output_path already set in step 5b when save_to_file)
    
    # Final validation: ensure output is proper JSON structure, not stringified
    # Check for old structure and fix it
    if isinstance(output, dict):
        # If output has old structure (research_metadata, result, canvas_stats), transform it
        if "research_metadata" in output and "result" in output and "canvas_stats" in output:
            logger.warning("Detected old output structure. Transforming to new format...")
            try:
                # Parse the stringified result
                result_str = output.pop("result")
                if isinstance(result_str, str):
                    parsed_result = _loads_json_with_repair(result_str)
                    if isinstance(parsed_result, str):
                        parsed_result = _loads_json_with_repair(parsed_result)
                else:
                    parsed_result = result_str
                
                # Start fresh with parsed result as base
                if isinstance(parsed_result, dict):
                    output = parsed_result.copy()
                else:
                    output = {"parsed_result": parsed_result}
                
                # Extract old metadata before it gets lost
                old_meta = {}
                if "research_metadata" in output:
                    old_meta = output.pop("research_metadata")
                elif isinstance(output, dict) and "research_metadata" in output:
                    old_meta = output.pop("research_metadata")
                
                # Ensure asset_id and asset_name are set
                output["asset_id"] = output.get("asset_id", old_meta.get("asset_id", args.asset_id) if isinstance(old_meta, dict) else args.asset_id)
                output["asset_name"] = output.get("asset_name", old_meta.get("asset_name", asset_context.get("asset_name")) if isinstance(old_meta, dict) else asset_context.get("asset_name", f"Asset {args.asset_id}"))
                
                if "metadata" not in output:
                    output["metadata"] = {}
                output["metadata"].update({
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "total_components": output.get("total_components", len(output.get("components", []))),
                    "total_helicopters": output.get("total_helicopters"),
                    "total_aircraft": output.get("total_aircraft"),
                    "source_pages_count": old_meta.get("total_pages_analyzed", asset_context.get("total_pages", 0)),
                    "components_by_helicopter": output.get("components_by_helicopter", {}),
                    "components_by_aircraft": output.get("components_by_aircraft", {}),
                })
                
                # Move canvas_stats to _canvas_stats
                canvas_stats = output.pop("canvas_stats", {})
                output["_canvas_stats"] = canvas_stats
                
                # Add research metadata as _research_metadata
                output["_research_metadata"] = old_meta
                
                logger.info("Successfully transformed old output structure to new format")
            except Exception as e:
                logger.error(f"Failed to transform old structure: {e}", exc_info=True)
        # If output has stringified result field, fix it
        elif "result" in output and isinstance(output["result"], str):
            logger.error("CRITICAL: Output contains stringified 'result' field! Attempting to fix...")
            try:
                # Try to parse the result field
                parsed_result = _loads_json_with_repair(output["result"])
                if isinstance(parsed_result, str):
                    parsed_result = _loads_json_with_repair(parsed_result)
                # Merge parsed result into output, removing the stringified version
                output.pop("result")
                if isinstance(parsed_result, dict):
                    output.update(parsed_result)
                else:
                    output["parsed_result"] = parsed_result
                logger.info("Fixed stringified result field")
            except Exception as e:
                logger.error(f"Failed to fix stringified result: {e}", exc_info=True)
    
    # Ensure output is a dict before saving
    if not isinstance(output, dict):
        logger.error(f"Output is not a dict! Type: {type(output)}. Converting...")
        output = {"error": "Output format error", "raw_output": str(output)}
    
    # Final check: ensure no stringified JSON fields remain
    def check_and_fix_stringified(obj, path=""):
        """Recursively check for stringified JSON and fix it."""
        if isinstance(obj, dict):
            for key, value in list(obj.items()):
                if isinstance(value, str) and (value.strip().startswith("{") or value.strip().startswith("[")):
                    try:
                        parsed = _loads_json_with_repair(value)
                        obj[key] = parsed
                        logger.debug(f"Fixed stringified JSON at {path}.{key}")
                        check_and_fix_stringified(parsed, f"{path}.{key}")
                    except:
                        pass
                else:
                    check_and_fix_stringified(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_and_fix_stringified(item, f"{path}[{i}]")
    
    check_and_fix_stringified(output)

    # Canonicalize output into one stable schema and enrich source citations.
    page_ids: set[str] = set()
    page_indices: set[int] = set()
    _collect_page_ids(output, page_ids)
    _collect_source_page_indices(output, page_indices)
    page_lookup = await _fetch_page_lookup(page_ids, args.asset_id, page_indices)
    output = _canonicalize_output(
        payload=output,
        args=args,
        asset_context=asset_context,
        page_lookup=page_lookup,
        research_metadata=output.get("_research_metadata", {}),
        canvas_stats=output.get("_canvas_stats", {}),
    )

    if save_to_file:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str, ensure_ascii=False)

        # Save canvas if it has entries
        if canvas.entries:
            canvas_path = str(run_dir / "canvas.json")
            canvas.save_to_file(canvas_path)
            print(f"Canvas saved to: {canvas_path}")

    # 13. Print summary (skip when API mode)
    if save_to_file:
        print(f"\n{'='*60}")
        print("  Execution Complete")
        print(f"{'='*60}\n")
        print(f"Output saved to: {output_path}")
        print(f"Run folder: {run_dir}")
        print(f"Processing time: {processing_time/1000:.1f}s")
        print_execution_summary(emitter.get_history())
        if args.live_monitor:
            try:
                monitor.stop()
            except Exception:
                pass
        logger.info(f"Research complete. Output saved to: {output_path}")

    return output


async def main():
    """CLI entry point."""
    args = parse_args()
    output = await _execute_research(args)
    # _execute_research already saves and prints when run from CLI
    return output


if __name__ == "__main__":
    asyncio.run(main())

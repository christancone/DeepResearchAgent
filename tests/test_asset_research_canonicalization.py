"""
Unit tests for asset research output canonicalization and citation normalization.

Covers: extracted_facts -> key_findings, gaps_and_risks -> gaps, mixed citation formats,
placeholder filtering, and fallback backfill behavior.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

# Load run_asset_research without requiring examples as a package
_spec = importlib.util.spec_from_file_location(
    "run_asset_research",
    root / "examples" / "run_asset_research.py",
)
_run_asset_research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_run_asset_research)

_canonicalize_output = _run_asset_research._canonicalize_output
_normalize_source_pages = _run_asset_research._normalize_source_pages
_build_doc_page_index = _run_asset_research._build_doc_page_index


def _make_args(asset_id: str = "test-asset-1"):
    return argparse.Namespace(asset_id=asset_id)


def _empty_context(asset_id: str = "test-asset-1"):
    return {"asset_name": f"Asset {asset_id}", "total_pages": 0}


# --- _normalize_source_pages ---


def test_normalize_source_pages_none():
    assert _normalize_source_pages(None, {}, None) == []


def test_normalize_source_pages_placeholder_skipped():
    """Placeholders like existing_summary, canvas_*, document_tree_* are dropped."""
    page_lookup = {}
    assert _normalize_source_pages("existing_summary", page_lookup, None) == []
    assert _normalize_source_pages("document_tree_tool_results", page_lookup, None) == []
    assert _normalize_source_pages("canvas_abc", page_lookup, None) == []
    assert _normalize_source_pages("document_tree_xyz", page_lookup, None) == []
    assert _normalize_source_pages("asset extraction foo", page_lookup, None) == []


def test_normalize_source_pages_uuid_string_resolved():
    """UUID string resolved via page_lookup to citation with enhancedS3Key."""
    page_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    page_lookup = {
        page_id.lower(): {
            "pageId": page_id,
            "pageIndex": 0,
            "documentId": "doc-1",
            "documentName": "Doc1.pdf",
            "enhancedS3Key": "s3://bucket/doc1/p0",
        }
    }
    out = _normalize_source_pages(page_id, page_lookup, None)
    assert len(out) == 1
    assert out[0]["pageId"] == page_id
    assert out[0]["enhancedS3Key"] == "s3://bucket/doc1/p0"


def test_normalize_source_pages_dict_with_page_id():
    """Dict with pageId enriched from page_lookup."""
    page_lookup = {
        "pid-1": {
            "pageId": "pid-1",
            "pageIndex": 1,
            "documentId": "d1",
            "documentName": "D1",
            "enhancedS3Key": "s3://d1/p1",
        }
    }
    out = _normalize_source_pages([{"pageId": "pid-1", "page_index": 1}], page_lookup, None)
    assert len(out) == 1
    assert out[0]["enhancedS3Key"] == "s3://d1/p1"


def test_normalize_source_pages_doc_index_form():
    """document_id|page_index form resolved when doc_page_index and page_lookup exist."""
    page_lookup = {
        "pid-0": {
            "pageId": "pid-0",
            "pageIndex": 0,
            "documentId": "doc-uuid",
            "documentName": "Doc",
            "enhancedS3Key": "s3://doc/0",
        }
    }
    doc_page_index = {("doc-uuid", 0): "pid-0"}
    out = _normalize_source_pages("doc-uuid|0", page_lookup, doc_page_index)
    assert len(out) == 1
    assert out[0].get("enhancedS3Key") == "s3://doc/0"


# --- _canonicalize_output ---


def test_canonicalize_extracted_facts_to_key_findings():
    """extracted_facts is mapped into key_findings."""
    payload = {
        "asset_id": "A1",
        "extracted_facts": [
            {"description": "Fact one", "confidence": "high"},
            "Plain string fact",
        ],
    }
    args = _make_args("A1")
    out = _canonicalize_output(
        payload, args, _empty_context("A1"), {}, {}, {}
    )
    assert "key_findings" in out
    assert len(out["key_findings"]) >= 2
    contents = [f.get("content") for f in out["key_findings"]]
    assert "Fact one" in contents
    assert "Plain string fact" in contents


def test_canonicalize_gaps_and_risks_to_gaps():
    """gaps_and_risks / identified_gaps / gapsAndRisks mapped to gaps."""
    payload = {
        "asset_id": "A1",
        "gaps_and_risks": [
            {"title": "Gap1", "description": "Missing data"},
            "Plain gap text",
        ],
    }
    args = _make_args("A1")
    out = _canonicalize_output(
        payload, args, _empty_context("A1"), {}, {}, {}
    )
    assert "gaps" in out
    assert len(out["gaps"]) >= 2
    descs = [g.get("description") for g in out["gaps"]]
    assert "Missing data" in descs
    assert "Plain gap text" in descs


def test_canonicalize_fallback_from_raw_facts():
    """When key_findings would be empty but extracted_facts present, backfill."""
    payload = {
        "asset_id": "A1",
        "extracted_facts": [{"description": "Only fact"}],
        "key_findings": [],
        "keyFindings": [],
        "findings": [],
    }
    args = _make_args("A1")
    out = _canonicalize_output(
        payload, args, _empty_context("A1"), {}, {}, {}
    )
    assert len(out["key_findings"]) == 1
    assert out["key_findings"][0]["content"] == "Only fact"


def test_canonicalize_fallback_from_raw_gaps():
    """When gaps empty but gaps_and_risks present, backfill."""
    payload = {
        "asset_id": "A1",
        "gaps_and_risks": [{"description": "Only gap"}],
        "gaps": [],
        "gapsAndLimitations": [],
    }
    args = _make_args("A1")
    out = _canonicalize_output(
        payload, args, _empty_context("A1"), {}, {}, {}
    )
    assert len(out["gaps"]) == 1
    assert out["gaps"][0]["description"] == "Only gap"


def test_canonicalize_regulatory_validation_notes():
    """regulatory_validation items get notes from validation_notes."""
    payload = {
        "asset_id": "A1",
        "regulatory_validation": [
            {"reference": "AD-123", "validation_notes": "Compliant"},
        ],
    }
    args = _make_args("A1")
    out = _canonicalize_output(
        payload, args, _empty_context("A1"), {}, {}, {}
    )
    assert len(out["regulatory_validation"]) == 1
    assert out["regulatory_validation"][0]["notes"] == "Compliant"


def test_canonicalize_components_preserved():
    """components list is preserved."""
    payload = {
        "asset_id": "A1",
        "components": [{"id": "c1", "name": "Component 1"}],
    }
    args = _make_args("A1")
    out = _canonicalize_output(
        payload, args, _empty_context("A1"), {}, {}, {}
    )
    assert out["components"] == [{"id": "c1", "name": "Component 1"}]


def test_build_doc_page_index():
    """_build_doc_page_index builds (doc_id, page_index) -> page_id."""
    page_lookup = {
        "p1": {"documentId": "d1", "pageIndex": 0, "pageId": "p1"},
        "p2": {"documentId": "d1", "pageIndex": 1, "pageId": "p2"},
    }
    idx = _build_doc_page_index(page_lookup)
    assert idx.get(("d1", 0)) == "p1"
    assert idx.get(("d1", 1)) == "p2"

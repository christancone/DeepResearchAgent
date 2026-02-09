"""
Tests for MCP tool registration: dependency checks and script sanitization.
"""
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, root)

from src.mcp.server import _check_script_requires, _sanitize_script_content


def test_check_script_requires_empty():
    """No requires -> no missing."""
    assert _check_script_requires({}) == []
    assert _check_script_requires({"metadata": {}}) == []
    assert _check_script_requires({"metadata": {"requires": ""}}) == []
    assert _check_script_requires({"metadata": {"requires": "   "}}) == []


def test_check_script_requires_none_literal():
    """requires like 'none', 'N/A', 'n/a' are treated as no deps."""
    assert _check_script_requires({"metadata": {"requires": "none"}}) == []
    assert _check_script_requires({"metadata": {"requires": "N/A"}}) == []
    assert _check_script_requires({"metadata": {"requires": "# no external libraries needed"}}) == []


def test_check_script_requires_stdlib_present():
    """Standard library (e.g. json) is present -> not missing."""
    assert _check_script_requires({"metadata": {"requires": "json"}}) == []


def test_check_script_requires_missing_reported():
    """Non-installed module is reported as missing."""
    missing = _check_script_requires({"metadata": {"requires": "nonexistent_module_xyz_12345"}})
    assert "nonexistent_module_xyz_12345" in missing or len(missing) == 1


def test_sanitize_script_content_empty():
    """Empty or whitespace -> empty string."""
    assert _sanitize_script_content("") == ""
    assert _sanitize_script_content("   \n  ") == ""


def test_sanitize_script_content_first_block_only():
    """Only the first code block is kept; trailing ``` and junk removed."""
    raw = "```python\ndef foo():\n    return 1\n```\n\nSome trailing text\n```\nmore"
    out = _sanitize_script_content(raw)
    assert "def foo():" in out
    assert "return 1" in out
    assert "Some trailing text" not in out
    assert "more" not in out
    assert "```" not in out or out.count("```") == 0


def test_sanitize_script_content_no_fence():
    """Plain code without fences is returned as-is (trimmed)."""
    code = "x = 1\ny = 2"
    assert _sanitize_script_content(code) == "x = 1\ny = 2"


def test_sanitize_script_content_strips_crlf():
    """CRLF normalized so no accidental trailing content."""
    raw = "```\na = 1\n```\r\n"
    out = _sanitize_script_content(raw)
    assert out.strip() == "a = 1"

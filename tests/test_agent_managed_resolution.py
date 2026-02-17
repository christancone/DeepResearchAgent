"""
Tests that managed_agents in asset research config resolve to AGENT registry keys.
"""
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, root)

from src.registry import AGENT


def test_asset_research_managed_agent_keys_in_registry():
    """Config managed_agents (deep_researcher_agent, deep_analyzer_agent) must be in AGENT registry."""
    required = {"deep_researcher_agent", "deep_analyzer_agent"}
    for name in required:
        assert name in AGENT, (
            f"Managed agent '{name}' should be in AGENT registry. "
            "Use registry keys in config managed_agents (e.g. deep_researcher_agent, deep_analyzer_agent)."
        )


def test_asset_extractor_agent_in_registry():
    """Asset research orchestrator also uses asset_extractor_agent."""
    assert "asset_extractor_agent" in AGENT

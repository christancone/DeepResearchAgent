from types import SimpleNamespace

from examples.run_asset_research import _canonicalize_output, _normalize_source_pages
from src.agent import agent as agent_module
from src.mcp.server import _check_script_requires, _sanitize_script_content


class AttrDict(dict):
    def __getattr__(self, item):
        return self[item]


def test_normalize_source_pages_mixed_formats_and_placeholders():
    page_lookup = {
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {
            "pageId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "pageIndex": 7,
            "documentId": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "documentName": "doc-1",
            "enhancedS3Key": "enhanced/doc-1/7.png",
        }
    }
    doc_page_index = {("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", 7): "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}

    out = _normalize_source_pages(
        [
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb|7",
            "existing_summary",
            {"pageId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
        ],
        page_lookup,
        doc_page_index,
    )

    assert len(out) == 2
    assert out[0]["pageId"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert out[1]["enhancedS3Key"] == "enhanced/doc-1/7.png"


def test_canonicalize_backfills_from_raw_extracted_fact_fields():
    args = SimpleNamespace(asset_id="asset-1")
    asset_context = {"asset_name": "Asset 1", "total_pages": 10}
    page_lookup = {}
    research_metadata = {"trace_id": "trace-1"}
    canvas_stats = {"total_entries": 0}

    payload = {
        "extracted_facts": [{"description": "Found LLP gap", "source_pages": ["canvas_temp_1", "existing_summary"]}],
        "gaps_and_risks": [{"description": "Missing AD reference"}],
    }

    out = _canonicalize_output(
        payload=payload,
        args=args,
        asset_context=asset_context,
        page_lookup=page_lookup,
        research_metadata=research_metadata,
        canvas_stats=canvas_stats,
    )

    assert out["asset_id"] == "asset-1"
    assert out["key_findings"]
    assert out["gaps"]
    assert out["key_findings"][0]["content"] == "Found LLP gap"
    # Placeholder-only sources are dropped.
    assert out["key_findings"][0]["source_pages"] == []


async def test_build_agent_resolves_managed_agents_by_key_and_name():
    captured = {}

    class DummyTool:
        def __init__(self, name):
            self.name = name

    class DummyManagedAgent:
        def __init__(self, name):
            self.name = name
            self.description = "managed"

    def fake_agent_build(cfg):
        captured["built"] = cfg
        return cfg

    original_agent_build = agent_module.AGENT.build
    original_models = agent_module.model_manager.registed_models
    original_make_tool_instance = agent_module.make_tool_instance
    agent_module.AGENT.build = fake_agent_build
    agent_module.model_manager.registed_models = {"test-model": object()}
    agent_module.make_tool_instance = lambda managed: DummyTool(managed.name)

    agent_config = AttrDict(
        type="planning_agent",
        name="orchestrator",
        description="desc",
        model_id="test-model",
        max_steps=3,
        provide_run_summary=True,
        tools=[],
        managed_agents=["deep_researcher_agent", "regulatory_researcher_agent"],
        get=dict.get,
    )
    cfg = {}
    default_managed_agents = {
        "deep_researcher_agent": DummyManagedAgent("regulatory_researcher_agent"),
    }

    try:
        result = await agent_module.build_agent(
            cfg,
            agent_config,
            default_tools={},
            default_mcp_tools={},
            default_managed_agents=default_managed_agents,
        )
    finally:
        agent_module.AGENT.build = original_agent_build
        agent_module.model_manager.registed_models = original_models
        agent_module.make_tool_instance = original_make_tool_instance

    assert result["name"] == "orchestrator"
    # Dedupe by actual managed agent instance name.
    managed_tool_names = [tool.name for tool in captured["built"]["tools"]]
    assert managed_tool_names.count("regulatory_researcher_agent") == 1


def test_mcp_registration_helpers_handle_requires_and_sanitization():
    assert _check_script_requires({"metadata": {"requires": "None"}}) == []
    assert _check_script_requires({"metadata": {"requires": "# No external libraries needed"}}) == []
    missing = _check_script_requires({"metadata": {"requires": "definitely_missing_mod_xyz"}})
    assert missing == ["definitely_missing_mod_xyz"]

    script = "```python\nprint('ok')\n```\nEXTRA TEXT"
    assert _sanitize_script_content(script) == "print('ok')"

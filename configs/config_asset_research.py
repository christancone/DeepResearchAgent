"""
Asset Research Configuration

Configuration for the Asset Dossier Research Agent system.
Leverages existing agents with custom prompts for aircraft maintenance analysis.
"""

_base_ = './base.py'

# ============================================================================
# GENERAL CONFIG
# ============================================================================
tag = "asset_research"
concurrency = 4
workdir = "workdir"
log_path = "asset_research.log"
save_path = "asset_research_output.json"
use_local_proxy = False

use_hierarchical_agent = True

# ============================================================================
# CONTEXT & MEMORY CONFIGURATION
# ============================================================================

# Token budget allocation
budget_allocation = dict(
    system_prompt=3000,
    task_context=8000,
    tool_results=60000,
    conversation_history=30000,
    working_memory=40000,  # Canvas findings
    reserved_for_output=10000
)

# Canvas configuration
canvas_config = dict(
    max_entries=1000,
    auto_summarize=True,
    embedding_model="text-embedding-3-small",
    persistence_path="workdir/canvas_{asset_id}.json"
)

# ============================================================================
# OBSERVABILITY CONFIGURATION
# ============================================================================

observability_config = dict(
    # Console output
    live_monitor=False,  # Use rich live display (fancy)
    verbose=True,  # Show all events vs just major ones
    
    # Event history
    max_history=1000,
    
    # External integrations
    langfuse_enabled=False,  # Set True + env vars to enable
    langsmith_enabled=False,
    
    # What to log
    log_thinking=True,  # Show agent reasoning
    log_tool_args=True,  # Show tool arguments
    log_tool_results=False,  # Show full tool results (verbose!)
)

# ============================================================================
# ASSET EXTRACTOR AGENT: New agent for structured extraction with citations
# ============================================================================
asset_extractor_agent_config = dict(
    type="asset_extractor_agent",
    name="asset_extractor_agent",
    model_id="claude-3.7-sonnet-thinking",
    description="Specialized agent for extracting structured data from asset dossiers with full citation tracking.",
    max_steps=20,
    template_path="src/agent/asset_extractor_agent/prompts/asset_extractor_agent.yaml",
    provide_run_summary=True,
    tools=[
        # Asset dossier tools
        "asset_metadata_tool",
        "asset_rag_search_tool",
        "asset_page_read_tool",
        "document_tree_tool",
        "asset_batch_summary_tool",
        # Working memory
        "canvas_tool",
        # Existing tools for processing
        "python_interpreter_tool",
        "file_reader_tool"
    ]
)

# ============================================================================
# DEEP RESEARCHER AGENT: Reuse existing for web validation + regulatory lookups
# ============================================================================
deep_researcher_agent_config = dict(
    type="deep_researcher_agent",
    name="regulatory_researcher_agent",
    model_id="gpt-4.1",
    description="Specialized regulatory research agent for validating ADs, SBs, and compliance against FAA/EASA databases.",
    max_steps=15,
    template_path="src/agent/asset_research_prompts/regulatory_researcher.yaml",
    provide_run_summary=True,
    tools=[
        "deep_researcher_tool",    # EXISTING: multi-level web research
        # "archive_searcher_tool",   # EXISTING: Wayback Machine for superseded SBs
        # "web_searcher_tool",       # EXISTING: multi-engine search
        # "web_fetcher_tool",        # EXISTING: page fetching
        "canvas_tool",             # Working memory
    ]
)

# ============================================================================
# DEEP ANALYZER AGENT: Reuse existing for complex document analysis
# ============================================================================
deep_analyzer_agent_config = dict(
    type="deep_analyzer_agent",
    name="document_analyzer_agent",
    model_id="claude-3.7-sonnet-thinking",
    description="Specialized document analysis agent for cross-referencing, trend analysis, and contradiction detection.",
    max_steps=15,
    template_path="src/agent/asset_research_prompts/document_analyzer.yaml",
    provide_run_summary=True,
    tools=[
        "deep_analyzer_tool",      # EXISTING: multi-model analysis
        "python_interpreter_tool", # EXISTING: calculations and data processing
        "file_reader_tool",        # EXISTING: read various file formats
        "canvas_tool",             # Working memory
    ]
)

# ============================================================================
# BROWSER AGENT: Reuse existing for FAA/EASA scraping (optional)
# ============================================================================
browser_use_agent_config = dict(
    type="browser_use_agent",
    name="regulatory_scraper_agent",
    model_id="gpt-4.1",
    description="Specialized browser agent for scraping FAA/EASA regulatory websites when APIs are unavailable.",
    max_steps=10,
    template_path="src/agent/asset_research_prompts/regulatory_scraper.yaml",
    provide_run_summary=True,
    tools=[
        "auto_browser_use_tool",   # EXISTING: high-level browser automation
        # "browser_use_tool",        # EXISTING: low-level browser control
    ]
)

# ============================================================================
# PLANNING AGENT: Orchestrates multi-phase research with asset-specific prompts
# ============================================================================
planning_agent_config = dict(
    type="planning_agent",
    name="asset_research_orchestrator",
    model_id="claude-3.7-sonnet-thinking",
    description="Orchestrator agent that coordinates multi-phase research on asset dossiers.",
    max_steps=30,
    template_path="src/agent/asset_research_prompts/orchestrator.yaml",
    provide_run_summary=True,
    tools=[
        "planning_tool",
        "canvas_tool",
    ],
    managed_agents=[
        "asset_extractor_agent",
        "regulatory_researcher_agent",
        "document_analyzer_agent",
        # "regulatory_scraper_agent"  # Uncomment if browser scraping is needed
    ]
)

# ============================================================================
# TOOL CONFIGURATIONS
# ============================================================================

# Planning tool
planning_tool_config = dict(type="planning_tool")

# Canvas tool (working memory)
canvas_tool_config = dict(type="canvas_tool")

# Python interpreter (sandboxed)
python_interpreter_tool_config = dict(
    type="python_interpreter_tool",
    timeout=60
)

# File reader
file_reader_tool_config = dict(type="file_reader_tool")

# Deep researcher tool (for regulatory lookups)
deep_researcher_tool_config = dict(
    type="deep_researcher_tool",
    max_depth=3,  # Deeper research for regulatory validation
    time_limit=120
)

# Deep analyzer tool (for document analysis)
deep_analyzer_tool_config = dict(
    type="deep_analyzer_tool"
)

# Browser automation
auto_browser_use_tool_config = dict(
    type="auto_browser_use_tool"
)

# Asset dossier tools
asset_metadata_tool_config = dict(type="asset_metadata_tool")
asset_rag_search_tool_config = dict(type="asset_rag_search_tool", default_limit=20)
asset_page_read_tool_config = dict(type="asset_page_read_tool", max_pages_per_request=10)
document_tree_tool_config = dict(type="document_tree_tool")
asset_batch_summary_tool_config = dict(type="asset_batch_summary_tool")

# ============================================================================
# MCP TOOLS (Direct Supabase access - to be configured)
# ============================================================================
mcp_tools = []  # Add after verifying available tools in mcps/user-supabase/

mcp_tools_config = dict(
    # Supabase MCP configuration will go here
)

# ============================================================================
# MAIN AGENT CONFIG (Entry point)
# ============================================================================
agent_config = planning_agent_config

# ============================================================================
# ALTERNATIVE: Simplified Config (single agent, no orchestration)
# ============================================================================
# Uncomment below to use a single extractor agent without orchestration

# use_hierarchical_agent = False
# agent_config = asset_extractor_agent_config

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


async def main():
    """Main entry point."""
    args = parse_args()
    start_time = datetime.utcnow()
    
    print(f"\n{'='*60}")
    print("  Asset Dossier Research Agent")
    print(f"{'='*60}\n")
    
    # 1. Initialize configuration
    print(f"Loading configuration from: {args.config}")
    config.init_config(args.config, args)

    # Fallback to OpenAI if Anthropic key is missing
    if not os.getenv("ANTHROPIC_API_KEY"):
        fallback_model_id = "gpt-4.1"
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
"""
    
    print(f"\n{'='*60}")
    print("  Starting Analysis")
    print(f"{'='*60}\n")
    
    # 8. Create agent
    agent = await create_agent(config)
    
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
                    config.get("reformulation_model_id", "gpt-4.1")
                )
            )
        else:
            final_result = result

        if isinstance(final_result, str):
            try:
                sanitized = _sanitize_json_text(final_result)
                parsed = json.loads(sanitized)
                if isinstance(parsed, str):
                    parsed = json.loads(_sanitize_json_text(parsed))
                final_result = parsed
            except Exception as e:
                logger.warning(f"Failed to sanitize/parse JSON output: {e}")
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        final_result = {"error": str(e)}
        result = None
    
    # 11. Build output with metadata
    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    if isinstance(final_result, str):
        try:
            sanitized = _sanitize_json_text(final_result)
            parsed = json.loads(sanitized)
            if isinstance(parsed, str):
                parsed = json.loads(_sanitize_json_text(parsed))
            final_result = parsed
        except Exception as e:
            logger.warning(f"Failed to sanitize/parse JSON output before save: {e}")

    output = {
        "research_metadata": {
            "asset_id": args.asset_id,
            "asset_name": asset_context.get("asset_name"),
            "prompt": args.prompt,
            "total_pages_analyzed": asset_context.get("total_pages", 0),
            "total_pages_in_asset": asset_context.get("total_pages", 0),
            "research_depth": args.depth,
            "processing_time_ms": int(processing_time),
            "agent_version": "1.0.0",
            "trace_id": trace_id,
            "database_connected": asset_context.get("database_connected", False),
            "agents_used": list(agent.managed_agents.keys()) if hasattr(agent, 'managed_agents') and agent.managed_agents else [],
        },
        "result": final_result,
        "canvas_stats": canvas.get_stats()
    }
    
    # 12. Save output
    run_stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = Path("workdir") / f"asset_research_{args.asset_id}_{run_stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(run_dir / "output.json")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    
    # Save canvas if it has entries
    if canvas.entries:
        canvas_path = str(run_dir / "canvas.json")
        canvas.save_to_file(canvas_path)
        print(f"Canvas saved to: {canvas_path}")
    
    # 13. Print summary
    print(f"\n{'='*60}")
    print("  Execution Complete")
    print(f"{'='*60}\n")
    
    print(f"Output saved to: {output_path}")
    print(f"Run folder: {run_dir}")
    print(f"Processing time: {processing_time/1000:.1f}s")
    
    # Print execution summary
    print_execution_summary(emitter.get_history())
    
    # Stop live monitor if running
    if args.live_monitor:
        try:
            monitor.stop()
        except:
            pass
    
    logger.info(f"Research complete. Output saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    asyncio.run(main())

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
                   COUNT(DISTINCT dpr.id) as total_documents,
                   COUNT(DISTINCT dp.id) as total_pages
            FROM assets a
            LEFT JOIN document_processing_records dpr ON dpr.asset_id = a.id
            LEFT JOIN document_pages dp ON dp.document_processing_record_id = dpr.id
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
        if args.stream:
            # Streaming mode
            print("Running in streaming mode...\n")
            async for chunk in agent.run_stream(task):
                print(chunk, end="", flush=True)
            result = agent.final_answer
        else:
            # Normal mode
            result = await agent.run(task)
        
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
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        final_result = {"error": str(e)}
        result = None
    
    # 11. Build output with metadata
    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
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
    output_path = args.output or f"workdir/asset_research_{args.asset_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    
    # Save canvas if it has entries
    if canvas.entries:
        canvas_path = f"workdir/canvas_{args.asset_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        canvas.save_to_file(canvas_path)
        print(f"Canvas saved to: {canvas_path}")
    
    # 13. Print summary
    print(f"\n{'='*60}")
    print("  Execution Complete")
    print(f"{'='*60}\n")
    
    print(f"Output saved to: {output_path}")
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

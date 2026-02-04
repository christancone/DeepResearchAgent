"""AssetBatchSummaryTool - Retrieve existing aggregation batches."""

from typing import Optional, List, Dict, Any
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src.tools.asset_dossier.db_client import SupabaseAsyncClient


_ASSET_BATCH_SUMMARY_DESCRIPTION = """Retrieve existing aggregation batches (pre-computed summaries).
Useful for large assets where Tier 2/3 aggregation exists."""


@TOOL.register_module(name="asset_batch_summary_tool", force=True)
class AssetBatchSummaryTool(AsyncTool):
    """Tool to retrieve existing aggregation batches."""
    
    name = "asset_batch_summary_tool"
    description = _ASSET_BATCH_SUMMARY_DESCRIPTION
    parameters = {
        "type": "object",
        "properties": {
            "asset_id": {
                "type": "string",
                "description": "The asset ID"
            },
            "tier": {
                "type": "integer",
                "description": "Aggregation tier (2 or 3)",
                "default": 2
            }
        },
        "required": ["asset_id"]
    }
    output_type = "object"
    
    async def forward(
        self,
        asset_id: str,
        tier: int = 2
    ) -> ToolResult:
        """Retrieve aggregation batches."""
        try:
            db = await SupabaseAsyncClient.get_instance()
            
            # Query aggregation batches
            batches = await db.fetch("""
                SELECT 
                    ab.id as batch_id,
                    ab.tier,
                    ab.summary_json,
                    ab.created_at,
                    ARRAY_AGG(DISTINCT am.source_page_id) as source_page_ids
                FROM aggregation_batches ab
                LEFT JOIN aggregation_merges am ON am.batch_id = ab.id
                WHERE ab.asset_id = $1
                AND ab.tier = $2
                GROUP BY ab.id, ab.tier, ab.summary_json, ab.created_at
                ORDER BY ab.created_at DESC
            """, asset_id, tier)
            
            # Format results
            formatted_batches = []
            for row in batches:
                formatted_batches.append({
                    "batch_id": str(row["batch_id"]),
                    "tier": row["tier"],
                    "summary_json": row["summary_json"],
                    "source_page_ids": [str(pid) for pid in (row["source_page_ids"] or [])],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                })
            
            return ToolResult(output={
                "asset_id": asset_id,
                "tier": tier,
                "batches": formatted_batches,
                "count": len(formatted_batches)
            })
        
        except Exception as e:
            return ToolResult(
                output=None,
                error=f"Error retrieving batch summaries: {str(e)}"
            )

"""AssetMetadataTool - Retrieve asset overview and file structure."""

from typing import Optional, List, Dict, Any
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src.tools.asset_dossier.db_client import SupabaseAsyncClient


_ASSET_METADATA_DESCRIPTION = """Retrieve comprehensive asset overview including:
- Asset ID, name, and status
- Total documents and pages
- Document types and folder structure
- Existing summary_json if available
- Processing metadata

Use this as the first step when analyzing a new asset to understand its structure."""


@TOOL.register_module(name="asset_metadata_tool", force=True)
class AssetMetadataTool(AsyncTool):
    """Tool to retrieve asset metadata and overview."""
    
    name = "asset_metadata_tool"
    description = _ASSET_METADATA_DESCRIPTION
    parameters = {
        "type": "object",
        "properties": {
            "asset_id": {
                "type": "string",
                "description": "The asset ID to retrieve metadata for"
            },
            "include_file_tree": {
                "type": "boolean",
                "description": "Include the document file tree structure",
                "default": True
            },
            "include_summary": {
                "type": "boolean",
                "description": "Include existing summary_json if available",
                "default": True
            }
        },
        "required": ["asset_id"]
    }
    output_type = "object"
    
    async def forward(
        self,
        asset_id: str,
        include_file_tree: bool = True,
        include_summary: bool = True
    ) -> ToolResult:
        """Retrieve asset metadata."""
        try:
            db = await SupabaseAsyncClient.get_instance()
            
            # Get basic asset info
            asset = await db.fetchrow("""
                SELECT 
                    a.id,
                    a.name,
                    a.status,
                    a.created_at,
                    a.updated_at,
                    a.summary_json,
                    a.user_id,
                    COUNT(DISTINCT dpr.id) as total_documents,
                    COUNT(DISTINCT dp.id) as total_pages,
                    SUM(CASE WHEN dp.status = 'completed' THEN 1 ELSE 0 END) as processed_pages,
                    SUM(CASE WHEN dp.status = 'failed' THEN 1 ELSE 0 END) as failed_pages
                FROM assets a
                LEFT JOIN document_processing_records dpr ON dpr.asset_id = a.id
                LEFT JOIN document_pages dp ON dp.document_processing_record_id = dpr.id
                WHERE a.id = $1
                GROUP BY a.id
            """, asset_id)
            
            if not asset:
                return ToolResult(
                    output=None,
                    error=f"Asset not found: {asset_id}"
                )
            
            result = {
                "asset_id": str(asset["id"]),
                "name": asset["name"],
                "status": asset["status"],
                "created_at": asset["created_at"].isoformat() if asset["created_at"] else None,
                "updated_at": asset["updated_at"].isoformat() if asset["updated_at"] else None,
                "total_documents": asset["total_documents"] or 0,
                "total_pages": asset["total_pages"] or 0,
                "processed_pages": asset["processed_pages"] or 0,
                "failed_pages": asset["failed_pages"] or 0,
                "processing_progress": (
                    round((asset["processed_pages"] or 0) / asset["total_pages"] * 100, 1)
                    if asset["total_pages"] else 0
                )
            }
            
            # Get document types breakdown
            doc_types = await db.fetch("""
                SELECT 
                    CASE 
                        WHEN original_path ILIKE '%logbook%' THEN 'Logbook'
                        WHEN original_path ILIKE '%workorder%' OR original_path ILIKE '%work order%' THEN 'Work Order'
                        WHEN original_path ILIKE '%sb%' OR original_path ILIKE '%service bulletin%' THEN 'Service Bulletin'
                        WHEN original_path ILIKE '%ad%' OR original_path ILIKE '%airworthiness%' THEN 'AD Compliance'
                        WHEN original_path ILIKE '%teardown%' THEN 'Teardown Report'
                        WHEN original_path ILIKE '%borescope%' THEN 'Borescope Report'
                        WHEN original_path ILIKE '%invoice%' THEN 'Invoice'
                        WHEN original_path ILIKE '%certificate%' OR original_path ILIKE '%8130%' THEN 'Certificate'
                        ELSE 'Other'
                    END as doc_type,
                    COUNT(*) as count,
                    SUM(page_count) as total_pages
                FROM document_processing_records
                WHERE asset_id = $1
                GROUP BY doc_type
                ORDER BY count DESC
            """, asset_id)
            
            result["document_types"] = [
                {
                    "type": row["doc_type"],
                    "document_count": row["count"],
                    "page_count": row["total_pages"] or 0
                }
                for row in doc_types
            ]
            
            # Include file tree if requested
            if include_file_tree:
                documents = await db.fetch("""
                    SELECT 
                        id,
                        original_path,
                        file_name,
                        page_count,
                        status
                    FROM document_processing_records
                    WHERE asset_id = $1
                    ORDER BY original_path
                """, asset_id)
                
                # Build hierarchical tree
                tree = {}
                for doc in documents:
                    path_parts = (doc["original_path"] or doc["file_name"]).split("/")
                    current = tree
                    for part in path_parts[:-1]:
                        if part not in current:
                            current[part] = {"_files": [], "_subdirs": {}}
                        current = current[part]["_subdirs"]
                    
                    # Add file to current directory
                    if "_files" not in current:
                        current["_files"] = []
                    current["_files"].append({
                        "document_id": str(doc["id"]),
                        "file_name": path_parts[-1] if path_parts else doc["file_name"],
                        "page_count": doc["page_count"],
                        "status": doc["status"]
                    })
                
                result["file_tree"] = tree
            
            # Include existing summary if requested
            if include_summary and asset["summary_json"]:
                result["existing_summary"] = asset["summary_json"]
            
            return ToolResult(output=result)
        
        except Exception as e:
            return ToolResult(
                output=None,
                error=f"Error retrieving asset metadata: {str(e)}"
            )

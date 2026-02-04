"""DocumentTreeTool - Navigate and filter document hierarchy."""

from typing import Optional, List, Dict, Any
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src.tools.asset_dossier.db_client import SupabaseAsyncClient


_DOCUMENT_TREE_DESCRIPTION = """Navigate and filter the document tree for an asset.

Allows filtering by:
- Document type (logbook, work order, service bulletin, etc.)
- Path pattern (e.g., "Engine/Logbook/*")
- File name pattern
- Status

Returns filtered document list with:
- Document IDs and paths
- Page counts and status
- Relevant page IDs for the filter criteria"""


@TOOL.register_module(name="document_tree_tool", force=True)
class DocumentTreeTool(AsyncTool):
    """Tool to navigate and filter document tree."""
    
    name = "document_tree_tool"
    description = _DOCUMENT_TREE_DESCRIPTION
    parameters = {
        "type": "object",
        "properties": {
            "asset_id": {
                "type": "string",
                "description": "The asset ID to browse"
            },
            "path_filter": {
                "type": "string",
                "description": "Filter by path pattern (supports * wildcard)"
            },
            "doc_type_filter": {
                "type": "string",
                "enum": ["logbook", "work_order", "service_bulletin", "ad_compliance", 
                        "teardown", "borescope", "invoice", "certificate", "other"],
                "description": "Filter by document type"
            },
            "name_contains": {
                "type": "string",
                "description": "Filter documents containing this text in name"
            },
            "status_filter": {
                "type": "string",
                "enum": ["completed", "processing", "failed", "pending"],
                "description": "Filter by processing status"
            },
            "include_page_ids": {
                "type": "boolean",
                "description": "Include list of page IDs for each document",
                "default": False
            },
            "limit": {
                "type": "integer",
                "description": "Maximum documents to return",
                "default": 50
            }
        },
        "required": ["asset_id"]
    }
    output_type = "object"
    
    # Document type patterns for classification
    DOC_TYPE_PATTERNS = {
        "logbook": ["%logbook%", "%log book%"],
        "work_order": ["%workorder%", "%work order%", "%shop visit%"],
        "service_bulletin": ["%sb%", "%service bulletin%"],
        "ad_compliance": ["%ad%", "%airworthiness%", "%directive%"],
        "teardown": ["%teardown%", "%tear down%", "%disassembly%"],
        "borescope": ["%borescope%", "%bore scope%", "%bsi%"],
        "invoice": ["%invoice%", "%quotation%", "%quote%"],
        "certificate": ["%certificate%", "%8130%", "%easa form%", "%faa form%"],
    }
    
    async def forward(
        self,
        asset_id: str,
        path_filter: Optional[str] = None,
        doc_type_filter: Optional[str] = None,
        name_contains: Optional[str] = None,
        status_filter: Optional[str] = None,
        include_page_ids: bool = False,
        limit: int = 50
    ) -> ToolResult:
        """Navigate and filter document tree."""
        try:
            db = await SupabaseAsyncClient.get_instance()
            
            # Build query with filters
            conditions = ["dpr.asset_id = $1"]
            params = [asset_id]
            param_idx = 2
            
            # Path filter
            if path_filter:
                # Convert wildcard to SQL LIKE pattern
                sql_pattern = path_filter.replace("*", "%")
                conditions.append(f"dpr.original_path ILIKE ${param_idx}")
                params.append(sql_pattern)
                param_idx += 1
            
            # Document type filter
            if doc_type_filter and doc_type_filter in self.DOC_TYPE_PATTERNS:
                patterns = self.DOC_TYPE_PATTERNS[doc_type_filter]
                type_conditions = [f"dpr.original_path ILIKE ${param_idx + i}" for i in range(len(patterns))]
                conditions.append(f"({' OR '.join(type_conditions)})")
                params.extend(patterns)
                param_idx += len(patterns)
            
            # Name contains filter
            if name_contains:
                conditions.append(f"(dpr.file_name ILIKE ${param_idx} OR dpr.original_path ILIKE ${param_idx})")
                params.append(f"%{name_contains}%")
                param_idx += 1
            
            # Status filter
            if status_filter:
                conditions.append(f"dpr.status = ${param_idx}")
                params.append(status_filter)
                param_idx += 1
            
            # Add limit
            params.append(limit)
            
            # Execute query
            query = f"""
                SELECT 
                    dpr.id as document_id,
                    dpr.original_path,
                    dpr.file_name,
                    dpr.page_count,
                    dpr.status,
                    dpr.created_at,
                    CASE 
                        WHEN dpr.original_path ILIKE '%logbook%' THEN 'Logbook'
                        WHEN dpr.original_path ILIKE '%workorder%' OR dpr.original_path ILIKE '%work order%' THEN 'Work Order'
                        WHEN dpr.original_path ILIKE '%sb%' OR dpr.original_path ILIKE '%service bulletin%' THEN 'Service Bulletin'
                        WHEN dpr.original_path ILIKE '%ad%' OR dpr.original_path ILIKE '%airworthiness%' THEN 'AD Compliance'
                        WHEN dpr.original_path ILIKE '%teardown%' THEN 'Teardown Report'
                        WHEN dpr.original_path ILIKE '%borescope%' THEN 'Borescope Report'
                        WHEN dpr.original_path ILIKE '%invoice%' THEN 'Invoice'
                        WHEN dpr.original_path ILIKE '%certificate%' OR dpr.original_path ILIKE '%8130%' THEN 'Certificate'
                        ELSE 'Other'
                    END as doc_type
                FROM document_processing_records dpr
                WHERE {' AND '.join(conditions)}
                ORDER BY dpr.original_path
                LIMIT ${param_idx}
            """
            
            documents = await db.fetch(query, *params)
            
            # Format results
            formatted_docs = []
            for doc in documents:
                doc_data = {
                    "document_id": str(doc["document_id"]),
                    "path": doc["original_path"],
                    "file_name": doc["file_name"],
                    "page_count": doc["page_count"],
                    "status": doc["status"],
                    "doc_type": doc["doc_type"],
                    "created_at": doc["created_at"].isoformat() if doc["created_at"] else None
                }
                
                # Include page IDs if requested
                if include_page_ids:
                    pages = await db.fetch("""
                        SELECT id, page_index
                        FROM document_pages
                        WHERE document_processing_record_id = $1
                        ORDER BY page_index
                    """, doc["document_id"])
                    
                    doc_data["page_ids"] = [
                        {"page_id": str(p["id"]), "page_index": p["page_index"]}
                        for p in pages
                    ]
                
                formatted_docs.append(doc_data)
            
            # Build summary
            type_counts = {}
            for doc in formatted_docs:
                doc_type = doc["doc_type"]
                if doc_type not in type_counts:
                    type_counts[doc_type] = 0
                type_counts[doc_type] += 1
            
            return ToolResult(output={
                "asset_id": asset_id,
                "documents": formatted_docs,
                "count": len(formatted_docs),
                "type_breakdown": type_counts,
                "filters_applied": {
                    "path_filter": path_filter,
                    "doc_type_filter": doc_type_filter,
                    "name_contains": name_contains,
                    "status_filter": status_filter
                }
            })
        
        except Exception as e:
            return ToolResult(
                output=None,
                error=f"Error navigating document tree: {str(e)}"
            )

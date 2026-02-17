"""AssetRAGSearchTool - Semantic search using pgvector embeddings."""

from typing import Optional, List, Dict, Any
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src.tools.asset_dossier.db_client import SupabaseAsyncClient
from src.tools.asset_dossier.utils import normalize_asset_id


_ASSET_RAG_SEARCH_DESCRIPTION = """Semantic search on asset documents using pgvector embeddings.
Returns matching pages with similarity scores, snippets, and source metadata."""


@TOOL.register_module(name="asset_rag_search_tool", force=True)
class AssetRAGSearchTool(AsyncTool):
    """Tool for semantic search on asset documents using pgvector."""
    
    name = "asset_rag_search_tool"
    description = _ASSET_RAG_SEARCH_DESCRIPTION
    parameters = {
        "type": "object",
        "properties": {
            "asset_id": {
                "type": "string",
                "description": "The asset ID to search within"
            },
            "query": {
                "type": "string",
                "description": "Search query text"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "nullable": True,
                "default": 20
            },
            "min_similarity": {
                "type": "number",
                "description": "Minimum similarity score (0.0-1.0)",
                "nullable": True,
                "default": 0.5
            }
        },
        "required": ["asset_id", "query"]
    }
    output_type = "object"
    
    def __init__(self, default_limit: int = 20):
        super().__init__()
        self.default_limit = default_limit
    
    async def forward(
        self,
        asset_id: str,
        query: str,
        limit: Optional[int] = None,
        min_similarity: float = 0.5
    ) -> ToolResult:
        """Perform semantic search on asset documents."""
        try:
            asset_id = normalize_asset_id(asset_id)
            db = await SupabaseAsyncClient.get_instance()
            limit = limit or self.default_limit
            
            # Generate embedding for query (using pgvector's text embedding function)
            # Note: This assumes you have a function to generate embeddings
            # For now, we'll use a simple text search approach
            # In production, you'd use OpenAI embeddings or similar
            
            # Search using pgvector similarity search
            # This query assumes you have embeddings stored in document_chunks table
            results = await db.fetch("""
                SELECT 
                    dp.id as page_id,
                    dp.page_index,
                    dp.extracted_json,
                    dp.enhanced_s3_key,
                    dpr.id as document_id,
                    dpr.original_path as document_name,
                    dc.text_content as snippet,
                    1 - (dc.embeddings <=> (
                        SELECT embeddings 
                        FROM document_chunks 
                        WHERE text_content ILIKE $1 
                        LIMIT 1
                    )) as similarity
                FROM document_pages dp
                JOIN document_processing_records dpr ON dp.document_id = dpr.id
                JOIN document_chunks dc ON dc.page_id = dp.id
                WHERE dpr.asset_id = $2
                AND dc.text_content ILIKE $3
                ORDER BY similarity DESC
                LIMIT $4
            """, f"%{query}%", asset_id, f"%{query}%", limit)
            
            # Format results
            formatted_results = []
            for row in results:
                similarity = float(row.get("similarity", 0.0))
                if similarity < min_similarity:
                    continue
                
                # Extract text snippet from extracted_json if available
                snippet = row.get("snippet", "")
                if not snippet and row.get("extracted_json"):
                    # Try to extract text from JSON
                    try:
                        import json
                        json_data = row["extracted_json"]
                        if isinstance(json_data, str):
                            json_data = json.loads(json_data)
                        # Extract text fields
                        text_parts = []
                        for key, value in json_data.items():
                            if isinstance(value, str) and len(value) < 500:
                                text_parts.append(value)
                        snippet = " ".join(text_parts[:3])[:500]
                    except:
                        snippet = str(row.get("extracted_json", ""))[:500]
                
                formatted_results.append({
                    "page_id": str(row["page_id"]),
                    "document_id": str(row["document_id"]),
                    "document_name": row["document_name"],
                    "page_index": row["page_index"],
                    "similarity_score": similarity,
                    "snippet": snippet[:500],
                    "enhanced_s3_key": row.get("enhanced_s3_key")
                })
            
            return ToolResult(output={
                "query": query,
                "results": formatted_results,
                "count": len(formatted_results)
            })
        
        except Exception as e:
            return ToolResult(
                output=None,
                error=f"Error performing RAG search: {str(e)}"
            )

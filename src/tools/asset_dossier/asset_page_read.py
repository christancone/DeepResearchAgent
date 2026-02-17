"""AssetPageReadTool - Read specific page content from asset documents."""

from typing import Optional, List, Dict, Any, Union
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src.tools.asset_dossier.db_client import SupabaseAsyncClient
import json


_ASSET_PAGE_READ_DESCRIPTION = """Read the full extracted content from specific pages.

Input can be:
- A list of page IDs
- A document path with page range (start/end treated as inclusive)

Returns the complete extracted_json content for each page, including:
- Extracted text and structured data
- OCR results
- Page metadata
- Source information for citations"""


@TOOL.register_module(name="asset_page_read_tool", force=True)
class AssetPageReadTool(AsyncTool):
    """Tool to read specific page content from asset documents."""
    
    name = "asset_page_read_tool"
    description = _ASSET_PAGE_READ_DESCRIPTION
    parameters = {
        "type": "object",
        "properties": {
            "page_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of page IDs to read",
                "nullable": True
            },
            "document_id": {
                "type": "string",
                "description": "Document ID to read pages from (use with page_range)",
                "nullable": True
            },
            "page_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer"},
                    "end": {"type": "integer"}
                },
                "description": "Page range within document (0-indexed, inclusive start/end)",
                "nullable": True
            },
            "include_raw_text": {
                "type": "boolean",
                "description": "Include raw OCR text in addition to structured data",
                "nullable": True,
                "default": True
            }
        },
        "required": []
    }
    output_type = "object"
    
    def __init__(self, max_pages_per_request: int = 10):
        super().__init__()
        self.max_pages_per_request = max_pages_per_request
    
    async def forward(
        self,
        page_ids: Optional[List[str]] = None,
        document_id: Optional[str] = None,
        page_range: Optional[Dict[str, int]] = None,
        include_raw_text: bool = True
    ) -> ToolResult:
        """Read page content."""
        try:
            db = await SupabaseAsyncClient.get_instance()
            
            pages_to_fetch = []
            
            # When both document_id and page_ids are present and page_ids look like indices
            # (e.g. ["1","2","3"]), treat them as page_index values, not UUIDs.
            if document_id and page_ids and all(
                str(p).strip().isdigit() for p in page_ids[:self.max_pages_per_request]
            ):
                page_indices = [int(str(p).strip()) for p in page_ids[:self.max_pages_per_request]]
                page_records = await db.fetch(
                    """
                    SELECT id FROM document_pages
                    WHERE document_id = $1 AND page_index = ANY($2)
                    ORDER BY page_index
                    LIMIT $3
                    """,
                    document_id,
                    page_indices,
                    self.max_pages_per_request,
                )
                pages_to_fetch = [str(row["id"]) for row in page_records]
                # Fallback: if no rows, try page_range with min/max indices (handles 0-based vs 1-based)
                if not pages_to_fetch and page_indices:
                    lo, hi = min(page_indices), max(page_indices)
                    page_records = await db.fetch(
                        """
                        SELECT id FROM document_pages
                        WHERE document_id = $1 AND page_index >= $2 AND page_index <= $3
                        ORDER BY page_index
                        LIMIT $4
                        """,
                        document_id,
                        max(0, lo - 1),
                        hi,
                        self.max_pages_per_request,
                    )
                    pages_to_fetch = [str(row["id"]) for row in page_records]
            
            # Method 1: Direct page IDs (UUIDs only when document_id not used for indices)
            elif page_ids:
                pages_to_fetch = page_ids[:self.max_pages_per_request]
            
            # Method 2: Document + page range
            elif document_id:
                # Treat page_range as inclusive bounds to match natural tool-calling behavior.
                start_page = page_range.get("start", 0) if page_range else 0
                start_page = max(int(start_page), 0)

                if page_range and page_range.get("end") is not None:
                    requested_end = int(page_range["end"])
                else:
                    requested_end = start_page + self.max_pages_per_request - 1

                if requested_end < start_page:
                    requested_end = start_page

                # Clamp to max pages per request.
                end_page = min(requested_end, start_page + self.max_pages_per_request - 1)
                
                # Get page IDs for the range
                page_records = await db.fetch("""
                    SELECT id
                    FROM document_pages
                    WHERE document_id = $1
                    AND page_index >= $2
                    AND page_index <= $3
                    ORDER BY page_index
                """, document_id, start_page, end_page)
                
                pages_to_fetch = [str(row["id"]) for row in page_records]
            
            if not pages_to_fetch:
                if document_id:
                    return ToolResult(
                        output={
                            "pages": [],
                            "count": 0,
                            "warning": (
                                f"No pages found for document_id={document_id} "
                                f"with page_range={page_range or {'start': 0, 'end': self.max_pages_per_request - 1}}."
                            ),
                        },
                    )
                return ToolResult(
                    output={"pages": [], "count": 0},
                    error="No pages specified. Provide either page_ids or document_id with page_range."
                )
            
            # Fetch page content
            # Note: We need to handle UUID array properly
            pages = await db.fetch("""
                SELECT 
                    dp.id as page_id,
                    dp.page_index,
                    dp.extracted_json,
                    dp.enhanced_s3_key,
                    dp.created_at,
                    dpr.id as document_id,
                    dpr.original_path as document_path,
                    dpr.file_name as document_name,
                    dpr.asset_id
                FROM document_pages dp
                JOIN document_processing_records dpr ON dp.document_id = dpr.id
                WHERE dp.id::text = ANY($1::text[])
                ORDER BY dpr.original_path, dp.page_index
            """, pages_to_fetch)
            if pages is None:
                pages = []
            
            # Format results
            formatted_pages = []
            for row in pages:
                page_data = {
                    "page_id": str(row["page_id"]),
                    "document_id": str(row["document_id"]),
                    "document_path": row["document_path"],
                    "document_name": row["document_name"],
                    "asset_id": str(row["asset_id"]),
                    "page_index": row["page_index"],
                    "enhanced_s3_key": row.get("enhanced_s3_key"),
                    # Citation metadata
                    "citation": {
                        "page_id": str(row["page_id"]),
                        "document_id": str(row["document_id"]),
                        "document_name": row["document_name"] or row["document_path"],
                        "page_index": row["page_index"],
                        "enhanced_s3_key": row.get("enhanced_s3_key"),
                    },
                    "source_citation": {
                        "page_id": str(row["page_id"]),
                        "document_id": str(row["document_id"]),
                        "document_name": row["document_name"] or row["document_path"],
                        "page_index": row["page_index"],
                        "enhanced_s3_key": row.get("enhanced_s3_key"),
                    },
                }
                
                # Parse extracted_json
                extracted = row["extracted_json"]
                if extracted:
                    if isinstance(extracted, str):
                        try:
                            extracted = json.loads(extracted)
                        except json.JSONDecodeError:
                            extracted = {"raw_text": extracted}
                    
                    page_data["extracted_content"] = extracted
                    
                    # Extract raw text if requested
                    if include_raw_text:
                        raw_text = self._extract_raw_text(extracted)
                        page_data["raw_text"] = raw_text
                else:
                    page_data["extracted_content"] = None
                    page_data["raw_text"] = None
                
                formatted_pages.append(page_data)
            
            return ToolResult(output={
                "pages": formatted_pages,
                "count": len(formatted_pages),
                "requested": len(pages_to_fetch)
            })
        
        except Exception as e:
            return ToolResult(
                output=None,
                error=f"Error reading pages: {str(e)}"
            )
    
    def _extract_raw_text(self, extracted: Dict[str, Any]) -> str:
        """Extract raw text from extracted_json structure."""
        text_parts = []
        
        # Common text field names
        text_fields = ["text", "raw_text", "content", "ocr_text", "extracted_text"]
        
        for field in text_fields:
            if field in extracted and isinstance(extracted[field], str):
                text_parts.append(extracted[field])
        
        # Check for nested structures
        if "blocks" in extracted and isinstance(extracted["blocks"], list):
            for block in extracted["blocks"]:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
        
        if "lines" in extracted and isinstance(extracted["lines"], list):
            for line in extracted["lines"]:
                if isinstance(line, str):
                    text_parts.append(line)
                elif isinstance(line, dict) and "text" in line:
                    text_parts.append(line["text"])
        
        # If nothing found, try to stringify the whole thing
        if not text_parts:
            return json.dumps(extracted, indent=2)[:5000]
        
        return "\n".join(text_parts)

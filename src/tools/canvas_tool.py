"""
Canvas Tool

Tool for agents to interact with the working memory canvas.
Allows agents to store findings, retrieve relevant context,
and manage their working memory efficiently.
"""

from typing import Optional, List, Dict, Any

from src.tools.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src.memory.canvas import WorkingMemoryCanvas


@TOOL.register_module(name="canvas_tool", force=True)
class CanvasTool(AsyncTool):
    """
    Tool for agents to interact with the working memory canvas.
    
    Allows agents to store findings, retrieve relevant context,
    and manage their working memory efficiently.
    """
    
    name = "canvas_tool"
    description = """Store and retrieve findings in the working memory canvas.

Actions:
- add: Store a new finding with tags and citations
- get_by_tags: Retrieve findings by tags
- search: Semantic search for relevant findings
- get_recent: Get recently added findings
- get_overview: Get summaries of all findings (low tokens)
- get_entry: Get a specific entry by ID (full content)
- update: Update an existing finding
- delete: Delete a finding by ID
- stats: Get canvas statistics
- list_tags: List all available tags

Use this tool to:
1. Store extracted facts with proper tagging for later retrieval
2. Retrieve only relevant findings instead of loading everything into context
3. Get a low-token overview before deciding what to retrieve in full
4. Track citations and confidence levels for each finding
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform: add, get_by_tags, search, get_recent, get_overview, get_entry, update, delete, stats, list_tags"
            },
            "title": {
                "type": "string",
                "description": "Title for the finding (for 'add' action)",
                "nullable": True
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization or retrieval",
                "nullable": True
            },
            "content": {
                "type": "string",
                "description": "Full content of the finding (for 'add' or 'update' action)",
                "nullable": True
            },
            "summary": {
                "type": "string",
                "description": "Short summary of the finding (for 'add' action, optional)",
                "nullable": True
            },
            "citations": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Source citations for the finding [{page_id, document_id, excerpt, confidence}, ...]",
                "nullable": True
            },
            "query": {
                "type": "string",
                "description": "Search query (for 'search' action)",
                "nullable": True
            },
            "entry_id": {
                "type": "string",
                "description": "Entry ID (for 'get_entry', 'update', or 'delete' action)",
                "nullable": True
            },
            "limit": {
                "type": "integer",
                "description": "Maximum entries to return (default: 10)",
                "nullable": True
            },
            "include_full_content": {
                "type": "boolean",
                "description": "Include full content or just summaries (default: false)",
                "nullable": True
            },
            "confidence": {
                "type": "string",
                "description": "Confidence level: high, medium, low (for 'add' action)",
                "nullable": True
            },
            "category": {
                "type": "string",
                "description": "Category for grouping (for 'add' action)",
                "nullable": True
            },
            "match_all_tags": {
                "type": "boolean",
                "description": "If true, entry must have ALL specified tags (for 'get_by_tags')",
                "nullable": True
            },
            "agent_name": {
                "type": "string",
                "description": "Optional agent name for attribution",
                "nullable": True
            }
        },
        "required": ["action"]
    }
    output_type = "object"
    
    # Shared canvas instance (can be set externally or created on first use)
    _shared_canvas: Optional[WorkingMemoryCanvas] = None
    
    def __init__(self, canvas: Optional[WorkingMemoryCanvas] = None, **kwargs):
        """
        Initialize the canvas tool.
        
        Args:
            canvas: Optional pre-configured canvas instance. If not provided,
                   a shared canvas will be created on first use.
        """
        super().__init__(**kwargs)
        self._canvas = canvas
    
    @property
    def canvas(self) -> WorkingMemoryCanvas:
        """Get or create the canvas instance."""
        if self._canvas is not None:
            return self._canvas
        
        # Use shared canvas
        if CanvasTool._shared_canvas is None:
            CanvasTool._shared_canvas = WorkingMemoryCanvas(
                max_entries=1000,
                auto_summarize=True
            )
        return CanvasTool._shared_canvas
    
    @classmethod
    def set_shared_canvas(cls, canvas: WorkingMemoryCanvas):
        """Set the shared canvas instance for all CanvasTool instances."""
        cls._shared_canvas = canvas
    
    @classmethod
    def get_shared_canvas(cls) -> Optional[WorkingMemoryCanvas]:
        """Get the shared canvas instance."""
        return cls._shared_canvas
    
    async def forward(
        self,
        action: str,
        title: str = "",
        tags: Optional[List[str]] = None,
        content: str = "",
        summary: Optional[str] = None,
        citations: Optional[List[Dict]] = None,
        query: str = "",
        entry_id: str = "",
        limit: int = 10,
        include_full_content: bool = False,
        confidence: str = "medium",
        category: Optional[str] = None,
        match_all_tags: bool = False,
        agent_name: str = ""
    ) -> ToolResult:
        """
        Execute a canvas action.
        
        Args:
            action: The action to perform
            title: Title for new entries
            tags: Tags for filtering or categorization
            content: Content for new/updated entries
            summary: Optional summary
            citations: Source citations
            query: Search query
            entry_id: Entry ID for specific operations
            limit: Maximum results
            include_full_content: Whether to include full content
            confidence: Confidence level (high/medium/low)
            category: Category for grouping
            match_all_tags: Whether to require all tags to match
            
        Returns:
            ToolResult with operation result or error
        """
        tags = tags or []
        citations = citations or []
        
        try:
            if action == "add":
                if not title or not content:
                    return ToolResult(error="'add' action requires 'title' and 'content'")
                
                new_entry_id = await self.canvas.add_entry(
                    title=title,
                    tags=tags,
                    content=content,
                    summary=summary,
                    citations=citations,
                    agent=agent_name,
                    confidence=confidence,
                    category=category
                )
                return ToolResult(output={
                    "status": "success",
                    "entry_id": new_entry_id,
                    "message": f"Added finding: {title}"
                })
            
            elif action == "get_by_tags":
                if not tags:
                    return ToolResult(error="'get_by_tags' action requires 'tags'")
                
                entries = self.canvas.get_by_tags(
                    tags=tags,
                    match_all=match_all_tags,
                    limit=limit
                )
                return ToolResult(output={
                    "status": "success",
                    "count": len(entries),
                    "entries": [
                        e.to_dict() if include_full_content else e.to_summary_dict()
                        for e in entries
                    ]
                })
            
            elif action == "search":
                if not query:
                    return ToolResult(error="'search' action requires 'query'")
                
                results = await self.canvas.search_semantic(query, limit=limit)
                return ToolResult(output={
                    "status": "success",
                    "count": len(results),
                    "entries": [
                        {
                            **(e.to_dict() if include_full_content else e.to_summary_dict()),
                            "relevance_score": round(score, 3)
                        }
                        for e, score in results
                    ]
                })
            
            elif action == "get_recent":
                entries = self.canvas.get_recent(n=limit)
                return ToolResult(output={
                    "status": "success",
                    "count": len(entries),
                    "entries": [
                        e.to_dict() if include_full_content else e.to_summary_dict()
                        for e in entries
                    ]
                })
            
            elif action == "get_overview":
                # Low-token overview of all findings
                summaries = self.canvas.get_summaries_only(
                    tags=tags if tags else None,
                    category=category,
                    limit=limit
                )
                return ToolResult(output={
                    "status": "success",
                    "total_in_canvas": len(self.canvas.entries),
                    "showing": len(summaries),
                    "summaries": summaries
                })
            
            elif action == "get_entry":
                if not entry_id:
                    return ToolResult(error="'get_entry' action requires 'entry_id'")
                
                entry = self.canvas.get_entry(entry_id)
                if entry is None:
                    return ToolResult(output={
                        "status": "not_found",
                        "entry_id": entry_id
                    })
                
                return ToolResult(output={
                    "status": "success",
                    "entry": entry.to_dict()
                })
            
            elif action == "update":
                if not entry_id:
                    return ToolResult(error="'update' action requires 'entry_id'")
                
                success = self.canvas.update_entry(
                    entry_id=entry_id,
                    content=content if content else None,
                    summary=summary,
                    tags=tags if tags else None,
                    citations=citations if citations else None,
                    confidence=confidence if confidence != "medium" else None
                )
                return ToolResult(output={
                    "status": "success" if success else "not_found",
                    "entry_id": entry_id,
                    "updated": success
                })
            
            elif action == "delete":
                if not entry_id:
                    return ToolResult(error="'delete' action requires 'entry_id'")
                
                success = self.canvas.delete_entry(entry_id)
                return ToolResult(output={
                    "status": "success" if success else "not_found",
                    "entry_id": entry_id,
                    "deleted": success
                })
            
            elif action == "stats":
                stats = self.canvas.get_stats()
                return ToolResult(output={
                    "status": "success",
                    **stats
                })
            
            elif action == "list_tags":
                tag_counts = self.canvas.list_all_tags()
                return ToolResult(output={
                    "status": "success",
                    "tag_count": len(tag_counts),
                    "tags": tag_counts
                })
            
            else:
                return ToolResult(error=f"Unknown action: {action}. Valid actions: add, get_by_tags, search, get_recent, get_overview, get_entry, update, delete, stats, list_tags")
        
        except Exception as e:
            return ToolResult(error=f"Canvas operation failed: {str(e)}")


# Convenience function to create a canvas tool with a specific canvas
def create_canvas_tool(canvas: Optional[WorkingMemoryCanvas] = None) -> CanvasTool:
    """Create a canvas tool with an optional pre-configured canvas."""
    return CanvasTool(canvas=canvas)

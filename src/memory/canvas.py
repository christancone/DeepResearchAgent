"""
Working Memory Canvas

Canvas-based working memory for LLM agents.
Stores findings with tags and titles for efficient retrieval.
Supports multiple retrieval modes to minimize token usage.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
import json
import hashlib
from collections import defaultdict
import math


@dataclass
class CanvasEntry:
    """A single finding/memory entry in the canvas."""
    id: str
    title: str
    tags: List[str]
    content: str
    summary: str  # Short summary for low-token retrieval
    citations: List[Dict[str, Any]]
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    agent: str = ""
    confidence: str = "medium"  # high, medium, low
    token_count: int = 0
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert entry to full dictionary representation."""
        return {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "content": self.content,
            "summary": self.summary,
            "citations": self.citations,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "agent": self.agent,
            "confidence": self.confidence,
            "token_count": self.token_count,
            "metadata": self.metadata
        }
    
    def to_summary_dict(self) -> dict:
        """Minimal representation for low-token retrieval."""
        return {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "summary": self.summary,
            "confidence": self.confidence,
            "agent": self.agent
        }
    
    def to_reference_dict(self) -> dict:
        """Ultra-minimal reference for listings."""
        return {
            "id": self.id,
            "title": self.title,
            "tags": self.tags[:3],  # First 3 tags only
            "confidence": self.confidence
        }


class WorkingMemoryCanvas:
    """
    Canvas-based working memory for LLM agents.
    
    Stores findings with tags and titles for efficient retrieval.
    Supports multiple retrieval modes to minimize token usage.
    
    Features:
    - Tag-based indexing for fast retrieval
    - Semantic search via embeddings (optional)
    - Multi-level retrieval (references, summaries, full content)
    - Automatic eviction of old entries
    - Persistence to/from JSON files
    """
    
    def __init__(
        self,
        embedding_model: Optional[Any] = None,
        max_entries: int = 1000,
        auto_summarize: bool = True,
        default_model_id: str = "gpt-4o"
    ):
        """
        Initialize the canvas.
        
        Args:
            embedding_model: Optional model for generating embeddings
            max_entries: Maximum entries before eviction
            auto_summarize: Whether to auto-generate summaries
            default_model_id: Default model for token counting
        """
        self.entries: Dict[str, CanvasEntry] = {}
        self.tag_index: Dict[str, Set[str]] = defaultdict(set)
        self.category_index: Dict[str, Set[str]] = defaultdict(set)  # Category -> entry IDs
        self.embedding_model = embedding_model
        self.max_entries = max_entries
        self.auto_summarize = auto_summarize
        self.default_model_id = default_model_id
        self._embeddings_dirty = False
    
    def _generate_id(self, content: str) -> str:
        """Generate unique ID for an entry."""
        hash_input = f"{content[:100]}{datetime.utcnow().isoformat()}"
        return f"canvas_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"
    
    async def add_entry(
        self,
        title: str,
        tags: List[str],
        content: str,
        summary: Optional[str] = None,
        citations: Optional[List[Dict]] = None,
        agent: str = "",
        confidence: str = "medium",
        category: Optional[str] = None,
        metadata: Optional[Dict] = None,
        entry_id: Optional[str] = None
    ) -> str:
        """
        Add a new finding to the canvas.
        
        Args:
            title: Title for the finding
            tags: List of tags for categorization
            content: Full content of the finding
            summary: Optional short summary (auto-generated if not provided)
            citations: List of source citation dictionaries
            agent: Name of the agent that created this entry
            confidence: Confidence level (high, medium, low)
            category: Optional category for grouping
            metadata: Additional metadata
            entry_id: Optional custom ID (auto-generated if not provided)
            
        Returns:
            The entry ID
        """
        from src.utils.token_counter import TokenCounter
        
        if entry_id is None:
            entry_id = self._generate_id(content)
        
        # Auto-generate summary if not provided
        if summary is None and self.auto_summarize:
            summary = await self._generate_summary(content)
        elif summary is None:
            summary = content[:200] + "..." if len(content) > 200 else content
        
        # Count tokens
        token_count = TokenCounter.count_tokens(content, self.default_model_id)
        
        # Generate embedding if model available
        embedding = None
        if self.embedding_model:
            try:
                embedding = await self._generate_embedding(content)
            except Exception:
                pass  # Embedding is optional
        
        # Normalize tags
        normalized_tags = [t.lower().strip() for t in tags if t]
        
        entry = CanvasEntry(
            id=entry_id,
            title=title,
            tags=normalized_tags,
            content=content,
            summary=summary,
            citations=citations or [],
            agent=agent,
            confidence=confidence,
            token_count=token_count,
            embedding=embedding,
            metadata=metadata or {}
        )
        
        # Store entry
        self.entries[entry_id] = entry
        
        # Update tag index
        for tag in entry.tags:
            self.tag_index[tag].add(entry_id)
        
        # Update category index
        if category:
            self.category_index[category].add(entry_id)
            entry.metadata["category"] = category
        
        # Evict old entries if needed
        if len(self.entries) > self.max_entries:
            self._evict_oldest()
        
        return entry_id
    
    def add_entry_sync(
        self,
        title: str,
        tags: List[str],
        content: str,
        summary: Optional[str] = None,
        citations: Optional[List[Dict]] = None,
        agent: str = "",
        confidence: str = "medium",
        category: Optional[str] = None,
        metadata: Optional[Dict] = None,
        entry_id: Optional[str] = None
    ) -> str:
        """
        Synchronous version of add_entry (no auto-summarization or embedding).
        """
        from src.utils.token_counter import TokenCounter
        
        if entry_id is None:
            entry_id = self._generate_id(content)
        
        # Simple summary if not provided
        if summary is None:
            summary = content[:200] + "..." if len(content) > 200 else content
        
        token_count = TokenCounter.count_tokens(content, self.default_model_id)
        
        normalized_tags = [t.lower().strip() for t in tags if t]
        
        entry = CanvasEntry(
            id=entry_id,
            title=title,
            tags=normalized_tags,
            content=content,
            summary=summary,
            citations=citations or [],
            agent=agent,
            confidence=confidence,
            token_count=token_count,
            metadata=metadata or {}
        )
        
        self.entries[entry_id] = entry
        
        for tag in entry.tags:
            self.tag_index[tag].add(entry_id)
        
        if category:
            self.category_index[category].add(entry_id)
            entry.metadata["category"] = category
        
        if len(self.entries) > self.max_entries:
            self._evict_oldest()
        
        return entry_id
    
    def update_entry(
        self,
        entry_id: str,
        content: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        citations: Optional[List[Dict]] = None,
        confidence: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update an existing entry.
        
        Returns:
            True if entry was found and updated, False otherwise
        """
        if entry_id not in self.entries:
            return False
        
        entry = self.entries[entry_id]
        
        if content is not None:
            entry.content = content
            from src.utils.token_counter import TokenCounter
            entry.token_count = TokenCounter.count_tokens(content, self.default_model_id)
            self._embeddings_dirty = True
        
        if summary is not None:
            entry.summary = summary
        
        if tags is not None:
            # Update tag index
            for old_tag in entry.tags:
                self.tag_index[old_tag].discard(entry_id)
            entry.tags = [t.lower().strip() for t in tags if t]
            for new_tag in entry.tags:
                self.tag_index[new_tag].add(entry_id)
        
        if citations is not None:
            entry.citations = citations
        
        if confidence is not None:
            entry.confidence = confidence
        
        if metadata is not None:
            entry.metadata.update(metadata)
        
        entry.updated_at = datetime.utcnow()
        return True
    
    def delete_entry(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        if entry_id not in self.entries:
            return False
        
        entry = self.entries[entry_id]
        
        # Remove from tag index
        for tag in entry.tags:
            self.tag_index[tag].discard(entry_id)
        
        # Remove from category index
        category = entry.metadata.get("category")
        if category:
            self.category_index[category].discard(entry_id)
        
        del self.entries[entry_id]
        return True
    
    # =========================================================================
    # RETRIEVAL METHODS
    # =========================================================================
    
    def get_entry(self, entry_id: str) -> Optional[CanvasEntry]:
        """Get a specific entry by ID."""
        return self.entries.get(entry_id)
    
    def get_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: Optional[int] = None,
        min_confidence: Optional[str] = None
    ) -> List[CanvasEntry]:
        """
        Retrieve entries by tags.
        
        Args:
            tags: Tags to search for
            match_all: If True, entry must have ALL tags. If False, ANY tag.
            limit: Maximum entries to return
            min_confidence: Minimum confidence level ("high", "medium", "low")
            
        Returns:
            List of matching entries sorted by update time (newest first)
        """
        if not tags:
            return []
            
        tags = [t.lower().strip() for t in tags]
        
        if match_all:
            # Intersection of all tag sets
            matching_ids: Optional[Set[str]] = None
            for tag in tags:
                tag_entries = self.tag_index.get(tag, set())
                if matching_ids is None:
                    matching_ids = tag_entries.copy()
                else:
                    matching_ids &= tag_entries
            matching_ids = matching_ids or set()
        else:
            # Union of all tag sets
            matching_ids = set()
            for tag in tags:
                matching_ids |= self.tag_index.get(tag, set())
        
        entries = [self.entries[eid] for eid in matching_ids if eid in self.entries]
        
        # Filter by confidence
        if min_confidence:
            confidence_levels = {"high": 3, "medium": 2, "low": 1}
            min_level = confidence_levels.get(min_confidence, 0)
            entries = [e for e in entries if confidence_levels.get(e.confidence, 0) >= min_level]
        
        # Sort by update time (newest first)
        entries.sort(key=lambda e: e.updated_at, reverse=True)
        
        if limit:
            entries = entries[:limit]
        
        return entries
    
    def get_by_category(
        self,
        category: str,
        limit: Optional[int] = None
    ) -> List[CanvasEntry]:
        """Get entries by category."""
        entry_ids = self.category_index.get(category, set())
        entries = [self.entries[eid] for eid in entry_ids if eid in self.entries]
        entries.sort(key=lambda e: e.updated_at, reverse=True)
        
        if limit:
            entries = entries[:limit]
        
        return entries
    
    async def search_semantic(
        self,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[Tuple[CanvasEntry, float]]:
        """
        Semantic search using embeddings.
        
        Args:
            query: Search query
            limit: Maximum results to return
            min_similarity: Minimum similarity score (0-1)
            
        Returns:
            List of (entry, similarity_score) tuples
        """
        if not self.embedding_model:
            # Fallback to keyword search
            return [(e, 1.0) for e in self._keyword_search(query, limit)]
        
        try:
            query_embedding = await self._generate_embedding(query)
        except Exception:
            return [(e, 1.0) for e in self._keyword_search(query, limit)]
        
        results = []
        for entry in self.entries.values():
            if entry.embedding:
                similarity = self._cosine_similarity(query_embedding, entry.embedding)
                if similarity >= min_similarity:
                    results.append((entry, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    def get_recent(self, n: int = 10) -> List[CanvasEntry]:
        """Get most recently updated entries."""
        entries = list(self.entries.values())
        entries.sort(key=lambda e: e.updated_at, reverse=True)
        return entries[:n]
    
    def get_by_agent(self, agent: str, limit: Optional[int] = None) -> List[CanvasEntry]:
        """Get all entries created by a specific agent."""
        entries = [e for e in self.entries.values() if e.agent == agent]
        entries.sort(key=lambda e: e.updated_at, reverse=True)
        
        if limit:
            entries = entries[:limit]
        
        return entries
    
    def get_summaries_only(
        self,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[dict]:
        """
        Get only summaries (minimal tokens) for filtered entries.
        
        Useful for giving LLM an overview without full content.
        """
        if tags:
            entries = self.get_by_tags(tags, limit=limit)
        elif category:
            entries = self.get_by_category(category, limit=limit)
        else:
            entries = list(self.entries.values())
            entries.sort(key=lambda e: e.updated_at, reverse=True)
            if limit:
                entries = entries[:limit]
        
        return [e.to_summary_dict() for e in entries]
    
    def get_references_only(
        self,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[dict]:
        """
        Get ultra-minimal references (just ID, title, tags).
        
        Useful for listing available findings.
        """
        if tags:
            entries = self.get_by_tags(tags, limit=limit)
        else:
            entries = list(self.entries.values())
            entries.sort(key=lambda e: e.updated_at, reverse=True)
            if limit:
                entries = entries[:limit]
        
        return [e.to_reference_dict() for e in entries]
    
    def get_for_context(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_tokens: int = 10000,
        include_full_content: bool = False
    ) -> Dict[str, Any]:
        """
        Get canvas content optimized for LLM context.
        
        Intelligently selects entries to fit within token budget.
        
        Args:
            query: Optional query for relevance ranking
            tags: Optional tags to filter by
            max_tokens: Maximum token budget
            include_full_content: Include full content or just summaries
            
        Returns:
            Dictionary with selected entries and metadata
        """
        # Gather candidate entries
        if tags:
            candidates = self.get_by_tags(tags, limit=50)
        else:
            candidates = self.get_recent(50)
        
        # If query provided and we have embeddings, re-sort by relevance
        if query and any(e.embedding for e in candidates):
            # Simple keyword relevance for sync operation
            query_lower = query.lower()
            candidates.sort(
                key=lambda e: (
                    sum(1 for term in query_lower.split() if term in e.title.lower() or term in e.content.lower()),
                    e.updated_at
                ),
                reverse=True
            )
        
        # Select entries within budget
        selected = []
        total_tokens = 0
        
        for entry in candidates:
            entry_tokens = (
                entry.token_count if include_full_content
                else len(entry.summary) // 4  # Approximate summary tokens
            )
            
            if total_tokens + entry_tokens <= max_tokens:
                selected.append(entry)
                total_tokens += entry_tokens
        
        return {
            "entries": [
                e.to_dict() if include_full_content else e.to_summary_dict()
                for e in selected
            ],
            "total_in_canvas": len(self.entries),
            "selected_count": len(selected),
            "approximate_tokens": total_tokens
        }
    
    # =========================================================================
    # TAG MANAGEMENT
    # =========================================================================
    
    def list_all_tags(self) -> Dict[str, int]:
        """List all tags with their entry counts."""
        return {tag: len(ids) for tag, ids in self.tag_index.items() if ids}
    
    def list_categories(self) -> Dict[str, int]:
        """List all categories with their entry counts."""
        return {cat: len(ids) for cat, ids in self.category_index.items() if ids}
    
    def rename_tag(self, old_tag: str, new_tag: str) -> int:
        """
        Rename a tag across all entries.
        
        Returns:
            Number of entries updated
        """
        old_tag = old_tag.lower().strip()
        new_tag = new_tag.lower().strip()
        
        if old_tag not in self.tag_index:
            return 0
        
        entry_ids = self.tag_index[old_tag].copy()
        count = 0
        
        for entry_id in entry_ids:
            if entry_id in self.entries:
                entry = self.entries[entry_id]
                entry.tags = [new_tag if t == old_tag else t for t in entry.tags]
                count += 1
        
        # Update index
        self.tag_index[new_tag] |= self.tag_index[old_tag]
        del self.tag_index[old_tag]
        
        return count
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    async def _generate_summary(self, content: str) -> str:
        """Generate a short summary of content."""
        try:
            from src.models import model_manager
            
            summarizer = model_manager.registed_models.get("gpt-4o-mini")
            if not summarizer:
                return content[:200] + "..." if len(content) > 200 else content
            
            prompt = f"Summarize in 1-2 sentences, preserving key facts and any source references:\n\n{content[:3000]}"
            messages = [{"role": "user", "content": prompt}]
            response = await summarizer.generate(messages)
            
            return response.content if hasattr(response, 'content') else str(response)
        except Exception:
            return content[:200] + "..." if len(content) > 200 else content
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        if hasattr(self.embedding_model, 'embed'):
            return await self.embedding_model.embed(text)
        elif hasattr(self.embedding_model, 'create'):
            # OpenAI-style embedding
            response = await self.embedding_model.create(input=text)
            return response.data[0].embedding
        return []
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
    
    def _keyword_search(self, query: str, limit: int) -> List[CanvasEntry]:
        """Simple keyword-based search fallback."""
        query_terms = query.lower().split()
        
        scored = []
        for entry in self.entries.values():
            text = f"{entry.title} {' '.join(entry.tags)} {entry.content}".lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0:
                scored.append((entry, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:limit]]
    
    def _evict_oldest(self):
        """Remove oldest entries when at capacity."""
        entries = list(self.entries.values())
        entries.sort(key=lambda e: e.updated_at)
        
        # Remove oldest 10%
        to_remove = entries[:max(1, len(entries) // 10)]
        for entry in to_remove:
            self.delete_entry(entry.id)
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def save_to_file(self, path: str):
        """Save canvas to JSON file."""
        data = {
            "entries": [e.to_dict() for e in self.entries.values()],
            "metadata": {
                "saved_at": datetime.utcnow().isoformat(),
                "total_entries": len(self.entries),
                "tags": list(self.tag_index.keys()),
                "categories": list(self.category_index.keys())
            }
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    
    @classmethod
    def load_from_file(cls, path: str) -> 'WorkingMemoryCanvas':
        """Load canvas from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        canvas = cls()
        for entry_data in data.get("entries", []):
            entry = CanvasEntry(
                id=entry_data["id"],
                title=entry_data["title"],
                tags=entry_data["tags"],
                content=entry_data["content"],
                summary=entry_data["summary"],
                citations=entry_data["citations"],
                created_at=datetime.fromisoformat(entry_data["created_at"]),
                updated_at=datetime.fromisoformat(entry_data.get("updated_at", entry_data["created_at"])),
                agent=entry_data.get("agent", ""),
                confidence=entry_data.get("confidence", "medium"),
                token_count=entry_data.get("token_count", 0),
                metadata=entry_data.get("metadata", {})
            )
            canvas.entries[entry.id] = entry
            for tag in entry.tags:
                canvas.tag_index[tag].add(entry.id)
            
            category = entry.metadata.get("category")
            if category:
                canvas.category_index[category].add(entry.id)
        
        return canvas
    
    def get_stats(self) -> Dict[str, Any]:
        """Get canvas statistics."""
        total_tokens = sum(e.token_count for e in self.entries.values())
        
        tag_counts = {
            tag: len(ids) for tag, ids in self.tag_index.items() if ids
        }
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        confidence_counts = {"high": 0, "medium": 0, "low": 0}
        for entry in self.entries.values():
            if entry.confidence in confidence_counts:
                confidence_counts[entry.confidence] += 1
        
        agent_counts: Dict[str, int] = {}
        for entry in self.entries.values():
            if entry.agent:
                agent_counts[entry.agent] = agent_counts.get(entry.agent, 0) + 1
        
        return {
            "total_entries": len(self.entries),
            "total_tokens": total_tokens,
            "average_tokens_per_entry": total_tokens // len(self.entries) if self.entries else 0,
            "unique_tags": len(tag_counts),
            "top_tags": dict(top_tags),
            "entries_by_confidence": confidence_counts,
            "entries_by_agent": agent_counts,
            "categories": list(self.category_index.keys()),
            "has_embeddings": any(e.embedding for e in self.entries.values())
        }
    
    def clear(self):
        """Clear all entries from the canvas."""
        self.entries.clear()
        self.tag_index.clear()
        self.category_index.clear()

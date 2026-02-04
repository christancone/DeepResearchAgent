"""
Context Budget Manager

Manages context budget across different content types.
Ensures we never exceed model limits and gracefully degrades with truncation/summarization.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Awaitable
from enum import Enum
from datetime import datetime

# Use relative import to avoid circular dependency during src.utils initialization
from .token_counter import TokenCounter

# Note: get_model_limits is imported lazily to avoid circular imports


def _get_model_limits(model_id: str):
    """Lazy import wrapper to avoid circular imports."""
    from src.config.model_limits import get_model_limits
    return get_model_limits(model_id)


class TruncationStrategy(Enum):
    """How to handle content that exceeds budget."""
    HEAD = "head"  # Keep beginning, truncate end
    TAIL = "tail"  # Keep end, truncate beginning (keep recent)
    MIDDLE = "middle"  # Keep start and end, truncate middle
    SUMMARIZE = "summarize"  # Use LLM to summarize
    SMART = "smart"  # Auto-select best strategy based on content type
    FAIL = "fail"  # Raise error if exceeded


@dataclass
class BudgetAllocation:
    """Token budget allocation for different content types."""
    system_prompt: int = 3000
    task_context: int = 8000
    tool_results: int = 60000
    conversation_history: int = 30000
    working_memory: int = 40000  # Canvas/findings
    reserved_for_output: int = 10000
    
    def total_input_budget(self) -> int:
        """Total tokens allocated for input."""
        return (
            self.system_prompt + 
            self.task_context + 
            self.tool_results + 
            self.conversation_history + 
            self.working_memory
        )


@dataclass
class ContentBlock:
    """A block of content with metadata for budget management."""
    content: str
    content_type: str  # "system", "task", "tool_result", "history", "memory"
    priority: int = 5  # 1-10, higher = more important to keep
    can_truncate: bool = True
    can_summarize: bool = True
    source_id: Optional[str] = None  # For tracking source (e.g., tool name, page ID)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _token_count: Optional[int] = None
    
    def get_tokens(self, model_id: str) -> int:
        """Get token count, caching the result."""
        if self._token_count is None:
            self._token_count = TokenCounter.count_tokens(self.content, model_id)
        return self._token_count
    
    def invalidate_cache(self):
        """Invalidate cached token count after content modification."""
        self._token_count = None


class ContextOverflowError(Exception):
    """Raised when context budget is exceeded and cannot be handled."""
    pass


class ContextBudgetManager:
    """
    Manages context budget across different content types.
    Ensures we never exceed model limits and gracefully degrades.
    """
    
    def __init__(
        self,
        model_id: str,
        allocation: Optional[BudgetAllocation] = None,
        summarizer: Optional[Callable[[str, int], Awaitable[str]]] = None
    ):
        """
        Initialize the context budget manager.
        
        Args:
            model_id: The model identifier for token counting
            allocation: Custom budget allocation, or None for defaults
            summarizer: Async function to summarize content (text, target_tokens) -> summarized_text
        """
        self.model_id = model_id
        self.limits = _get_model_limits(model_id)
        self.allocation = allocation or BudgetAllocation()
        self.summarizer = summarizer
        self.content_blocks: List[ContentBlock] = []
        self._warnings: List[str] = []
        self._truncation_log: List[Dict[str, Any]] = []
    
    @property
    def total_budget(self) -> int:
        """Total tokens available for input."""
        return self.limits.effective_input_limit
    
    @property
    def used_tokens(self) -> int:
        """Total tokens currently used."""
        return sum(b.get_tokens(self.model_id) for b in self.content_blocks)
    
    @property
    def remaining_tokens(self) -> int:
        """Tokens still available."""
        return max(0, self.total_budget - self.used_tokens)
    
    def _get_budget_for_type(self, content_type: str) -> int:
        """Get allocated budget for a content type."""
        mapping = {
            "system": self.allocation.system_prompt,
            "task": self.allocation.task_context,
            "tool_result": self.allocation.tool_results,
            "history": self.allocation.conversation_history,
            "memory": self.allocation.working_memory,
        }
        return mapping.get(content_type, 10000)
    
    def _get_current_type_usage(self, content_type: str) -> int:
        """Get current token usage for a content type."""
        return sum(
            b.get_tokens(self.model_id)
            for b in self.content_blocks
            if b.content_type == content_type
        )
    
    def add_content(
        self,
        content: str,
        content_type: str,
        priority: int = 5,
        strategy: TruncationStrategy = TruncationStrategy.SMART,
        source_id: Optional[str] = None,
        **metadata
    ) -> bool:
        """
        Add content to the context, handling overflow gracefully.
        
        Args:
            content: The text content to add
            content_type: Category of content ("system", "task", "tool_result", "history", "memory")
            priority: Importance 1-10 (higher = more important to keep)
            strategy: How to handle if content exceeds budget
            source_id: Optional identifier for the content source
            **metadata: Additional metadata to store with the content
            
        Returns:
            True if content was added (possibly truncated), False if rejected.
        """
        if not content:
            return True
            
        block = ContentBlock(
            content=content,
            content_type=content_type,
            priority=priority,
            source_id=source_id,
            metadata=metadata
        )
        
        tokens_needed = block.get_tokens(self.model_id)
        budget_for_type = self._get_budget_for_type(content_type)
        current_type_usage = self._get_current_type_usage(content_type)
        
        # Calculate available space
        available_for_type = min(
            budget_for_type - current_type_usage,
            self.remaining_tokens
        )
        
        if tokens_needed <= available_for_type:
            # Fits within budget
            self.content_blocks.append(block)
            return True
        
        # Need to handle overflow
        if strategy == TruncationStrategy.FAIL:
            raise ContextOverflowError(
                f"Content exceeds budget: {tokens_needed} tokens > {available_for_type} available"
            )
        
        # Determine effective strategy
        if strategy == TruncationStrategy.SMART:
            strategy = self._select_smart_strategy(content_type, tokens_needed, available_for_type)
        
        # Apply truncation/summarization
        if strategy == TruncationStrategy.SUMMARIZE and self.summarizer:
            # Will need async handling - for now, fallback to truncation
            target_tokens = int(available_for_type * 0.9)
            block.content = self._truncate(content, target_tokens, TruncationStrategy.HEAD)
            block.invalidate_cache()
            self._log_truncation(content_type, tokens_needed, block.get_tokens(self.model_id), "summarize->truncate")
        
        elif strategy in [TruncationStrategy.HEAD, TruncationStrategy.TAIL, TruncationStrategy.MIDDLE]:
            target_tokens = int(available_for_type * 0.95)  # 5% buffer
            block.content = self._truncate(content, target_tokens, strategy)
            block.invalidate_cache()
            self._log_truncation(content_type, tokens_needed, block.get_tokens(self.model_id), strategy.value)
        
        self.content_blocks.append(block)
        return True
    
    async def add_content_async(
        self,
        content: str,
        content_type: str,
        priority: int = 5,
        strategy: TruncationStrategy = TruncationStrategy.SMART,
        source_id: Optional[str] = None,
        **metadata
    ) -> bool:
        """
        Add content with async summarization support.
        """
        if not content:
            return True
            
        block = ContentBlock(
            content=content,
            content_type=content_type,
            priority=priority,
            source_id=source_id,
            metadata=metadata
        )
        
        tokens_needed = block.get_tokens(self.model_id)
        budget_for_type = self._get_budget_for_type(content_type)
        current_type_usage = self._get_current_type_usage(content_type)
        
        available_for_type = min(
            budget_for_type - current_type_usage,
            self.remaining_tokens
        )
        
        if tokens_needed <= available_for_type:
            self.content_blocks.append(block)
            return True
        
        if strategy == TruncationStrategy.FAIL:
            raise ContextOverflowError(
                f"Content exceeds budget: {tokens_needed} tokens > {available_for_type} available"
            )
        
        if strategy == TruncationStrategy.SMART:
            strategy = self._select_smart_strategy(content_type, tokens_needed, available_for_type)
        
        if strategy == TruncationStrategy.SUMMARIZE and self.summarizer:
            target_tokens = int(available_for_type * 0.9)
            try:
                block.content = await self.summarizer(content, target_tokens)
                block.invalidate_cache()
                self._log_truncation(content_type, tokens_needed, block.get_tokens(self.model_id), "summarize")
            except Exception as e:
                # Fallback to truncation
                block.content = self._truncate(content, target_tokens, TruncationStrategy.HEAD)
                block.invalidate_cache()
                self._log_truncation(content_type, tokens_needed, block.get_tokens(self.model_id), f"summarize_failed:{e}")
        
        elif strategy in [TruncationStrategy.HEAD, TruncationStrategy.TAIL, TruncationStrategy.MIDDLE]:
            target_tokens = int(available_for_type * 0.95)
            block.content = self._truncate(content, target_tokens, strategy)
            block.invalidate_cache()
            self._log_truncation(content_type, tokens_needed, block.get_tokens(self.model_id), strategy.value)
        
        self.content_blocks.append(block)
        return True
    
    def _select_smart_strategy(
        self,
        content_type: str,
        tokens_needed: int,
        available: int
    ) -> TruncationStrategy:
        """Select the best truncation strategy based on content type."""
        # If content is very large (>2x available), prefer summarization
        if tokens_needed > available * 2 and self.summarizer:
            return TruncationStrategy.SUMMARIZE
        
        # Strategy by content type
        if content_type == "history":
            # For conversation history, keep recent (tail)
            return TruncationStrategy.TAIL
        elif content_type == "tool_result":
            # For tool results, keep beginning (head) - usually has key data first
            return TruncationStrategy.HEAD
        elif content_type == "memory":
            # For memory/canvas, keep both ends
            return TruncationStrategy.MIDDLE
        else:
            # Default to keeping the beginning
            return TruncationStrategy.HEAD
    
    def _truncate(
        self,
        content: str,
        max_tokens: int,
        strategy: TruncationStrategy
    ) -> str:
        """Truncate content to fit within token budget."""
        return TokenCounter.truncate_text_to_tokens(
            content,
            max_tokens,
            self.model_id,
            truncation_side=strategy.value if strategy != TruncationStrategy.SMART else "end"
        )
    
    def _log_truncation(
        self,
        content_type: str,
        original_tokens: int,
        new_tokens: int,
        method: str
    ):
        """Log a truncation event."""
        self._truncation_log.append({
            "content_type": content_type,
            "original_tokens": original_tokens,
            "new_tokens": new_tokens,
            "reduction_percent": ((original_tokens - new_tokens) / original_tokens) * 100,
            "method": method,
            "timestamp": datetime.utcnow().isoformat()
        })
        self._warnings.append(
            f"Truncated {content_type}: {original_tokens} -> {new_tokens} tokens ({method})"
        )
    
    def evict_low_priority(self, tokens_to_free: int) -> int:
        """
        Remove low-priority content to free up space.
        
        Args:
            tokens_to_free: Target number of tokens to free
            
        Returns:
            Actual number of tokens freed
        """
        # Sort by priority (ascending) to remove lowest first
        blocks_by_priority = sorted(
            [(i, b) for i, b in enumerate(self.content_blocks) if b.can_truncate],
            key=lambda x: (x[1].priority, x[1].timestamp)
        )
        
        freed = 0
        indices_to_remove = []
        
        for idx, block in blocks_by_priority:
            if freed >= tokens_to_free:
                break
            tokens = block.get_tokens(self.model_id)
            indices_to_remove.append(idx)
            freed += tokens
            self._warnings.append(f"Evicted {block.content_type} (priority={block.priority}): {tokens} tokens")
        
        # Remove in reverse order to maintain indices
        for idx in sorted(indices_to_remove, reverse=True):
            self.content_blocks.pop(idx)
        
        return freed
    
    def get_content_by_type(self, content_type: str) -> List[ContentBlock]:
        """Get all content blocks of a specific type."""
        return [b for b in self.content_blocks if b.content_type == content_type]
    
    def clear_content_type(self, content_type: str):
        """Remove all content of a specific type."""
        self.content_blocks = [b for b in self.content_blocks if b.content_type != content_type]
    
    def get_all_content(self) -> str:
        """Get all content concatenated."""
        return "\n\n".join(b.content for b in self.content_blocks)
    
    def get_report(self) -> Dict[str, Any]:
        """Get a detailed report of current context usage."""
        by_type: Dict[str, Dict[str, Any]] = {}
        
        for block in self.content_blocks:
            if block.content_type not in by_type:
                by_type[block.content_type] = {
                    "count": 0,
                    "tokens": 0,
                    "budget": self._get_budget_for_type(block.content_type)
                }
            by_type[block.content_type]["count"] += 1
            by_type[block.content_type]["tokens"] += block.get_tokens(self.model_id)
        
        # Add usage percentage for each type
        for content_type, data in by_type.items():
            data["usage_percent"] = (data["tokens"] / data["budget"]) * 100 if data["budget"] > 0 else 0
        
        return {
            "model_id": self.model_id,
            "context_window": self.limits.context_window,
            "total_budget": self.total_budget,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "usage_percent": (self.used_tokens / self.total_budget) * 100 if self.total_budget > 0 else 0,
            "by_content_type": by_type,
            "warnings": self._warnings.copy(),
            "truncation_log": self._truncation_log.copy(),
            "block_count": len(self.content_blocks),
            "estimated_cost": TokenCounter.estimate_cost(
                self.used_tokens,
                self.limits.max_output_tokens,
                self.model_id
            )
        }
    
    def reset(self):
        """Clear all content and warnings."""
        self.content_blocks = []
        self._warnings = []
        self._truncation_log = []


# Convenience function to create a summarizer using the model manager
def create_summarizer(summarizer_model_id: str = "gpt-4o-mini"):
    """
    Create a summarizer function that uses an LLM to summarize content.
    
    Args:
        summarizer_model_id: Model to use for summarization
        
    Returns:
        Async function that summarizes text to target token count
    """
    async def summarize(content: str, target_tokens: int) -> str:
        try:
            from src.models import model_manager
            
            summarizer = model_manager.registed_models.get(summarizer_model_id)
            if not summarizer:
                # Fallback to truncation
                return TokenCounter.truncate_text_to_tokens(
                    content, target_tokens, summarizer_model_id, "end"
                )
            
            prompt = f"""Summarize the following content in approximately {target_tokens} tokens.
Preserve the most important information, especially:
- Key facts and findings
- Source references and citations
- Critical data points and values
- Important names, dates, and identifiers

Content:
{content[:50000]}"""  # Limit input to avoid issues
            
            messages = [{"role": "user", "content": prompt}]
            response = await summarizer.generate(messages)
            
            return response.content if hasattr(response, 'content') else str(response)
            
        except Exception as e:
            # Fallback to truncation on any error
            return TokenCounter.truncate_text_to_tokens(
                content, target_tokens, "gpt-4o", "end"
            )
    
    return summarize

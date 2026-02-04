"""
Context-Aware Mixin

Mixin for agents to manage context budget automatically.
Prevents exceeding LLM context limits and gracefully handles overflow.
"""

from typing import Dict, List, Any, Optional
import asyncio

from src.utils.context_budget import (
    ContextBudgetManager,
    BudgetAllocation,
    TruncationStrategy,
    create_summarizer,
)
from src.utils.token_counter import TokenCounter
from src.config.model_limits import get_model_limits


class ContextAwareMixin:
    """
    Mixin for agents to manage context budget automatically.
    
    Provides:
    - Token counting before LLM calls
    - Automatic truncation/summarization when needed
    - Context usage reporting
    
    Usage:
        class MyAgent(AsyncMultiStepAgent, ContextAwareMixin):
            def __init__(self, config, ...):
                super().__init__(...)
                self.initialize_budget_manager(config.model_id)
    """
    
    def initialize_budget_manager(
        self,
        model_id: Optional[str] = None,
        allocation: Optional[BudgetAllocation] = None,
        enable_summarization: bool = True
    ):
        """
        Initialize the budget manager for this agent.
        
        Args:
            model_id: Model ID for token counting (uses self.model.model_id if not provided)
            allocation: Custom budget allocation
            enable_summarization: Whether to use LLM summarization for overflow
        """
        # Get model ID from config or model
        if model_id is None:
            if hasattr(self, 'config') and hasattr(self.config, 'model_id'):
                model_id = self.config.model_id
            elif hasattr(self, 'model') and hasattr(self.model, 'model_id'):
                model_id = self.model.model_id
            else:
                model_id = "gpt-4o"  # Default fallback
        
        # Create summarizer if enabled
        summarizer = None
        if enable_summarization:
            summarizer = create_summarizer("gpt-4o-mini")
        
        self._budget_manager = ContextBudgetManager(
            model_id=model_id,
            allocation=allocation,
            summarizer=summarizer
        )
        self._model_id = model_id
        self._context_warnings_emitted = set()
    
    @property
    def budget_manager(self) -> ContextBudgetManager:
        """Get the budget manager, initializing if needed."""
        if not hasattr(self, '_budget_manager') or self._budget_manager is None:
            self.initialize_budget_manager()
        return self._budget_manager
    
    def check_context_before_call(
        self,
        messages: List[Dict[str, Any]],
        warn_threshold: float = 0.8
    ) -> Dict[str, Any]:
        """
        Check if messages fit within context and warn if approaching limit.
        
        Args:
            messages: Messages to check
            warn_threshold: Emit warning if usage exceeds this percentage (0-1)
            
        Returns:
            Status dictionary with fit information
        """
        model_id = getattr(self, '_model_id', 'gpt-4o')
        status = TokenCounter.check_fits_in_context(messages, model_id)
        
        # Emit warning if needed (only once per threshold)
        usage_percent = status['usage_percent']
        threshold_key = int(usage_percent / 10) * 10  # Round to nearest 10%
        
        if usage_percent >= warn_threshold * 100 and threshold_key not in self._context_warnings_emitted:
            self._context_warnings_emitted.add(threshold_key)
            
            # Emit observability event if mixin is available
            if hasattr(self, 'emit_context_warning'):
                self.emit_context_warning(
                    usage_percent=usage_percent,
                    tokens_used=status['tokens'],
                    limit=status['limit']
                )
        
        return status
    
    def add_to_context(
        self,
        content: str,
        content_type: str,
        priority: int = 5,
        strategy: TruncationStrategy = TruncationStrategy.SMART,
        **metadata
    ) -> bool:
        """
        Add content to the context budget.
        
        Args:
            content: Text content to add
            content_type: Category (system, task, tool_result, history, memory)
            priority: Importance (1-10, higher = more important)
            strategy: How to handle overflow
            **metadata: Additional metadata
            
        Returns:
            True if content was added
        """
        return self.budget_manager.add_content(
            content=content,
            content_type=content_type,
            priority=priority,
            strategy=strategy,
            **metadata
        )
    
    async def add_to_context_async(
        self,
        content: str,
        content_type: str,
        priority: int = 5,
        strategy: TruncationStrategy = TruncationStrategy.SMART,
        **metadata
    ) -> bool:
        """
        Add content with async summarization support.
        """
        return await self.budget_manager.add_content_async(
            content=content,
            content_type=content_type,
            priority=priority,
            strategy=strategy,
            **metadata
        )
    
    def prepare_messages_within_budget(
        self,
        messages: List[Dict[str, Any]],
        preserve_system: bool = True,
        preserve_recent: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Prepare messages to fit within context budget.
        
        Args:
            messages: Original messages
            preserve_system: Keep system message intact
            preserve_recent: Number of recent messages to always keep
            
        Returns:
            Messages that fit within budget
        """
        model_id = getattr(self, '_model_id', 'gpt-4o')
        limits = get_model_limits(model_id)
        max_tokens = limits.effective_input_limit
        
        # Calculate current usage
        current_tokens = TokenCounter.count_messages_tokens(messages, model_id)
        
        if current_tokens <= max_tokens:
            return messages
        
        # Need to truncate
        result = []
        tokens_used = 0
        
        # Preserve system message
        if preserve_system and messages and messages[0].get('role') == 'system':
            system_msg = messages[0]
            system_tokens = TokenCounter.count_messages_tokens([system_msg], model_id)
            result.append(system_msg)
            tokens_used += system_tokens
            messages = messages[1:]
        
        # Preserve recent messages
        recent_messages = messages[-preserve_recent:] if preserve_recent > 0 else []
        recent_tokens = TokenCounter.count_messages_tokens(recent_messages, model_id)
        
        # Calculate remaining budget for middle messages
        remaining_budget = max_tokens - tokens_used - recent_tokens - 500  # Buffer
        
        # Add as many middle messages as fit
        middle_messages = messages[:-preserve_recent] if preserve_recent > 0 else messages
        
        for msg in middle_messages:
            msg_tokens = TokenCounter.count_messages_tokens([msg], model_id)
            if tokens_used + msg_tokens <= remaining_budget:
                result.append(msg)
                tokens_used += msg_tokens
            else:
                # Truncate this message
                truncated_content = TokenCounter.truncate_text_to_tokens(
                    msg.get('content', ''),
                    remaining_budget - tokens_used,
                    model_id,
                    truncation_side="end"
                )
                if truncated_content:
                    result.append({**msg, 'content': truncated_content})
                break
        
        # Add recent messages
        result.extend(recent_messages)
        
        # Emit truncation event if available
        tokens_saved = current_tokens - TokenCounter.count_messages_tokens(result, model_id)
        if tokens_saved > 0 and hasattr(self, 'emit_context_truncated'):
            self.emit_context_truncated(
                tokens_saved=tokens_saved,
                strategy="message_trimming"
            )
        
        return result
    
    def truncate_tool_result(
        self,
        tool_result: str,
        max_tokens: Optional[int] = None,
        strategy: str = "end"
    ) -> str:
        """
        Truncate a tool result to fit within budget.
        
        Args:
            tool_result: The tool result string
            max_tokens: Maximum tokens (uses budget allocation if not specified)
            strategy: Truncation side ("end", "start", "middle")
            
        Returns:
            Truncated tool result
        """
        model_id = getattr(self, '_model_id', 'gpt-4o')
        
        if max_tokens is None:
            # Use a reasonable default based on tool_result allocation
            allocation = getattr(self.budget_manager, 'allocation', BudgetAllocation())
            max_tokens = allocation.tool_results // 10  # Per-tool limit
        
        current_tokens = TokenCounter.count_tokens(tool_result, model_id)
        
        if current_tokens <= max_tokens:
            return tool_result
        
        return TokenCounter.truncate_text_to_tokens(
            tool_result,
            max_tokens,
            model_id,
            truncation_side=strategy
        )
    
    def get_context_report(self) -> Dict[str, Any]:
        """Get a detailed report of context usage."""
        return self.budget_manager.get_report()
    
    def reset_context_budget(self):
        """Reset the context budget for a new task."""
        self.budget_manager.reset()
        self._context_warnings_emitted = set()
    
    def estimate_request_cost(
        self,
        messages: List[Dict[str, Any]],
        expected_output_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Estimate the cost of an LLM request.
        
        Args:
            messages: Input messages
            expected_output_tokens: Expected output size (uses model max if not specified)
            
        Returns:
            Cost estimate dictionary
        """
        model_id = getattr(self, '_model_id', 'gpt-4o')
        limits = get_model_limits(model_id)
        
        input_tokens = TokenCounter.count_messages_tokens(messages, model_id)
        output_tokens = expected_output_tokens or limits.max_output_tokens
        
        cost = TokenCounter.estimate_cost(input_tokens, output_tokens, model_id)
        
        return {
            "model_id": model_id,
            "input_tokens": input_tokens,
            "expected_output_tokens": output_tokens,
            "estimated_cost_usd": cost,
            "cost_per_1k_input": limits.cost_per_1k_input,
            "cost_per_1k_output": limits.cost_per_1k_output
        }

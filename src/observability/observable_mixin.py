"""
Observable Mixin

Mixin that adds observability to agents.
Automatically emits events for key agent actions.
"""

from typing import Any, Dict, Optional, List
from datetime import datetime
import time

from src.observability.events import EventType, AgentEvent
from src.observability.emitter import emit_event, EventEmitter


class ObservableMixin:
    """
    Mixin that adds observability to agents.
    
    Automatically emits events for key agent actions.
    Mix this into agent classes to enable event tracking.
    
    Usage:
        class MyAgent(AsyncMultiStepAgent, ObservableMixin):
            def __init__(self, ...):
                super().__init__(...)
                self.init_observability()
    """
    
    def init_observability(self, parent_agent: Optional[str] = None):
        """
        Initialize observability for this agent.
        
        Args:
            parent_agent: Name of parent agent if this is a managed agent
        """
        self._parent_agent_name = parent_agent
        self._step_start_time: Optional[float] = None
        self._tool_start_time: Optional[float] = None
        self._observability_enabled = True
    
    def disable_observability(self):
        """Disable event emission for this agent."""
        self._observability_enabled = False
    
    def enable_observability(self):
        """Enable event emission for this agent."""
        self._observability_enabled = True
    
    def _emit(
        self,
        event_type: EventType,
        step_number: Optional[int] = None,
        duration_ms: Optional[int] = None,
        token_count: Optional[int] = None,
        **data
    ) -> Optional[AgentEvent]:
        """
        Emit an event from this agent.
        
        Args:
            event_type: The type of event
            step_number: Current step number
            duration_ms: Duration in milliseconds
            token_count: Token count
            **data: Additional event data
            
        Returns:
            The emitted event, or None if observability is disabled
        """
        if not getattr(self, '_observability_enabled', True):
            return None
        
        return emit_event(
            event_type=event_type,
            agent_name=getattr(self, 'name', 'unknown'),
            agent_type=self.__class__.__name__,
            step_number=step_number or getattr(self, 'step_number', 0),
            parent_agent=getattr(self, '_parent_agent_name', None),
            duration_ms=duration_ms,
            token_count=token_count,
            **data
        )
    
    # =========================================================================
    # AGENT LIFECYCLE EVENTS
    # =========================================================================
    
    def emit_started(self, task: str):
        """Emit agent started event."""
        self._step_start_time = time.time()
        return self._emit(EventType.AGENT_STARTED, task=task)
    
    def emit_completed(self, success: bool = True, result: Optional[Any] = None):
        """Emit agent completed event."""
        duration_ms = None
        if self._step_start_time:
            duration_ms = int((time.time() - self._step_start_time) * 1000)
        
        event_type = EventType.AGENT_COMPLETED if success else EventType.AGENT_ERROR
        return self._emit(
            event_type,
            duration_ms=duration_ms,
            success=success,
            result_preview=str(result)[:200] if result else None
        )
    
    def emit_error(self, error: str, error_type: Optional[str] = None):
        """Emit agent error event."""
        return self._emit(
            EventType.AGENT_ERROR,
            error=error,
            error_type=error_type
        )
    
    # =========================================================================
    # THINKING/REASONING EVENTS
    # =========================================================================
    
    def emit_thinking(self, thought: str):
        """Emit thinking/reasoning event."""
        return self._emit(EventType.AGENT_THINKING, thought=thought)
    
    def emit_reasoning(self, reasoning: str, conclusion: Optional[str] = None):
        """Emit reasoning event with optional conclusion."""
        return self._emit(
            EventType.AGENT_REASONING,
            reasoning=reasoning,
            conclusion=conclusion
        )
    
    # =========================================================================
    # TOOL EVENTS
    # =========================================================================
    
    def emit_tool_called(self, tool_name: str, arguments: Dict[str, Any]):
        """Emit tool called event."""
        self._tool_start_time = time.time()
        return self._emit(
            EventType.TOOL_CALLED,
            tool_name=tool_name,
            arguments=arguments
        )
    
    def emit_tool_started(self, tool_name: str):
        """Emit tool started event."""
        self._tool_start_time = time.time()
        return self._emit(EventType.TOOL_STARTED, tool_name=tool_name)
    
    def emit_tool_completed(
        self,
        tool_name: str,
        result: Any = None,
        duration_ms: Optional[int] = None
    ):
        """Emit tool completed event."""
        if duration_ms is None and self._tool_start_time:
            duration_ms = int((time.time() - self._tool_start_time) * 1000)
        
        return self._emit(
            EventType.TOOL_COMPLETED,
            tool_name=tool_name,
            result_preview=str(result)[:200] if result else None,
            duration_ms=duration_ms
        )
    
    def emit_tool_error(
        self,
        tool_name: str,
        error: str,
        duration_ms: Optional[int] = None
    ):
        """Emit tool error event."""
        if duration_ms is None and self._tool_start_time:
            duration_ms = int((time.time() - self._tool_start_time) * 1000)
        
        return self._emit(
            EventType.TOOL_ERROR,
            tool_name=tool_name,
            error=error,
            duration_ms=duration_ms
        )
    
    # =========================================================================
    # PLANNING EVENTS
    # =========================================================================
    
    def emit_plan_created(self, steps: List[Dict[str, Any]]):
        """Emit plan created event."""
        return self._emit(
            EventType.PLAN_CREATED,
            steps=steps,
            step_count=len(steps)
        )
    
    def emit_plan_updated(self, change_description: str, steps: Optional[List] = None):
        """Emit plan updated event."""
        return self._emit(
            EventType.PLAN_UPDATED,
            change_description=change_description,
            steps=steps
        )
    
    def emit_plan_step_started(self, step_description: str, step_index: int = 0):
        """Emit plan step started event."""
        return self._emit(
            EventType.PLAN_STEP_STARTED,
            step_number=step_index,
            step_description=step_description
        )
    
    def emit_plan_step_completed(self, step_description: str, step_index: int = 0):
        """Emit plan step completed event."""
        return self._emit(
            EventType.PLAN_STEP_COMPLETED,
            step_number=step_index,
            step_description=step_description
        )
    
    # =========================================================================
    # MANAGED AGENT EVENTS
    # =========================================================================
    
    def emit_delegation(self, target_agent: str, task: str):
        """Emit managed agent delegation event."""
        return self._emit(
            EventType.MANAGED_AGENT_DELEGATED,
            target_agent=target_agent,
            task=task
        )
    
    def emit_delegation_response(self, source_agent: str, summary: str):
        """Emit managed agent response event."""
        return self._emit(
            EventType.MANAGED_AGENT_RESPONSE,
            source_agent=source_agent,
            summary=summary
        )
    
    # =========================================================================
    # CONTEXT EVENTS
    # =========================================================================
    
    def emit_context_warning(self, usage_percent: float, tokens_used: int, limit: int):
        """Emit context budget warning event."""
        return self._emit(
            EventType.CONTEXT_BUDGET_WARNING,
            usage_percent=usage_percent,
            tokens_used=tokens_used,
            limit=limit
        )
    
    def emit_context_truncated(self, tokens_saved: int, strategy: str):
        """Emit context truncated event."""
        return self._emit(
            EventType.CONTEXT_TRUNCATED,
            tokens_saved=tokens_saved,
            strategy=strategy
        )
    
    # =========================================================================
    # CANVAS EVENTS
    # =========================================================================
    
    def emit_canvas_added(self, title: str, entry_id: str, tags: List[str]):
        """Emit canvas entry added event."""
        return self._emit(
            EventType.CANVAS_ENTRY_ADDED,
            title=title,
            entry_id=entry_id,
            tags=tags
        )
    
    def emit_canvas_retrieved(self, count: int, query: Optional[str] = None):
        """Emit canvas retrieved event."""
        return self._emit(
            EventType.CANVAS_RETRIEVED,
            count=count,
            query=query
        )
    
    # =========================================================================
    # FINAL ANSWER EVENTS
    # =========================================================================
    
    def emit_final_answer(self, answer_preview: str):
        """Emit final answer event."""
        return self._emit(
            EventType.FINAL_ANSWER_GENERATED,
            answer_preview=answer_preview[:200]
        )
    
    # =========================================================================
    # ASSET-SPECIFIC EVENTS
    # =========================================================================
    
    def emit_asset_loaded(self, asset_id: str, asset_name: Optional[str], total_pages: int):
        """Emit asset loaded event."""
        return self._emit(
            EventType.ASSET_LOADED,
            asset_id=asset_id,
            asset_name=asset_name,
            total_pages=total_pages
        )
    
    def emit_page_read(self, page_id: str, document_name: Optional[str] = None):
        """Emit page read event."""
        return self._emit(
            EventType.PAGE_READ,
            page_id=page_id,
            document_name=document_name
        )
    
    def emit_citation_tracked(self, fact_id: str, source_count: int):
        """Emit citation tracked event."""
        return self._emit(
            EventType.CITATION_TRACKED,
            fact_id=fact_id,
            source_count=source_count
        )
    
    def emit_extraction_complete(self, items_extracted: int, categories: Dict[str, int]):
        """Emit extraction complete event."""
        return self._emit(
            EventType.EXTRACTION_COMPLETE,
            items_extracted=items_extracted,
            categories=categories
        )

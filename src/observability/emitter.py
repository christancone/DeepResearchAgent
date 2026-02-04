"""
Event Emitter

Central event emitter for agent observability.
Supports multiple subscribers and both sync/async handlers.
"""

from typing import Callable, List, Dict, Optional, Awaitable
from collections import defaultdict
import asyncio
from datetime import datetime
import uuid

from src.observability.events import AgentEvent, EventType

# Type for event handlers
EventHandler = Callable[[AgentEvent], None]
AsyncEventHandler = Callable[[AgentEvent], Awaitable[None]]


class EventEmitter:
    """
    Central event emitter for agent observability.
    
    Supports multiple subscribers and both sync/async handlers.
    Singleton pattern ensures all agents use the same emitter.
    """
    
    _instance: Optional['EventEmitter'] = None
    
    def __init__(self):
        """Initialize the event emitter."""
        self._handlers: Dict[EventType, List[EventHandler]] = defaultdict(list)
        self._async_handlers: Dict[EventType, List[AsyncEventHandler]] = defaultdict(list)
        self._all_handlers: List[EventHandler] = []
        self._async_all_handlers: List[AsyncEventHandler] = []
        self._trace_id: str = ""
        self._event_history: List[AgentEvent] = []
        self._max_history: int = 1000
        self._paused: bool = False
    
    @classmethod
    def get_instance(cls) -> 'EventEmitter':
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
    
    def start_trace(self, trace_id: Optional[str] = None) -> str:
        """
        Start a new trace for this execution.
        
        Args:
            trace_id: Optional custom trace ID
            
        Returns:
            The trace ID being used
        """
        self._trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        self._event_history = []
        return self._trace_id
    
    @property
    def trace_id(self) -> str:
        """Get current trace ID."""
        return self._trace_id
    
    def pause(self):
        """Pause event emission."""
        self._paused = True
    
    def resume(self):
        """Resume event emission."""
        self._paused = False
    
    def subscribe(
        self, 
        event_type: Optional[EventType], 
        handler: EventHandler
    ) -> Callable[[], None]:
        """
        Subscribe to events.
        
        Args:
            event_type: Specific event type, or None for all events
            handler: Sync callback function
            
        Returns:
            Unsubscribe function
        """
        if event_type is None:
            self._all_handlers.append(handler)
            return lambda: self._all_handlers.remove(handler) if handler in self._all_handlers else None
        else:
            self._handlers[event_type].append(handler)
            return lambda: self._handlers[event_type].remove(handler) if handler in self._handlers[event_type] else None
    
    def subscribe_async(
        self,
        event_type: Optional[EventType],
        handler: AsyncEventHandler
    ) -> Callable[[], None]:
        """
        Subscribe with async handler.
        
        Args:
            event_type: Specific event type, or None for all events
            handler: Async callback function
            
        Returns:
            Unsubscribe function
        """
        if event_type is None:
            self._async_all_handlers.append(handler)
            return lambda: self._async_all_handlers.remove(handler) if handler in self._async_all_handlers else None
        else:
            self._async_handlers[event_type].append(handler)
            return lambda: self._async_handlers[event_type].remove(handler) if handler in self._async_handlers[event_type] else None
    
    def unsubscribe_all(self):
        """Remove all subscribers."""
        self._handlers.clear()
        self._async_handlers.clear()
        self._all_handlers.clear()
        self._async_all_handlers.clear()
    
    def emit(self, event: AgentEvent):
        """
        Emit an event to all subscribers.
        
        Args:
            event: The event to emit
        """
        if self._paused:
            return
        
        # Add trace context
        event.trace_id = self._trace_id
        if not event.span_id:
            event.span_id = f"span_{uuid.uuid4().hex[:12]}"
        
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]
        
        # Call sync handlers for all events
        for handler in self._all_handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")
        
        # Call sync handlers for specific event type
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")
    
    async def emit_async(self, event: AgentEvent):
        """
        Emit event and await async handlers.
        
        Args:
            event: The event to emit
        """
        # Also call sync handlers
        self.emit(event)
        
        if self._paused:
            return
        
        # Collect async handlers
        tasks = []
        
        for handler in self._async_all_handlers:
            tasks.append(self._safe_async_call(handler, event))
        
        for handler in self._async_handlers.get(event.event_type, []):
            tasks.append(self._safe_async_call(handler, event))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_async_call(self, handler: AsyncEventHandler, event: AgentEvent):
        """Safely call an async handler."""
        try:
            await handler(event)
        except Exception as e:
            print(f"Error in async event handler: {e}")
    
    def get_history(
        self,
        event_types: Optional[List[EventType]] = None,
        agent_name: Optional[str] = None,
        limit: int = 100
    ) -> List[AgentEvent]:
        """
        Get event history with optional filtering.
        
        Args:
            event_types: Filter by specific event types
            agent_name: Filter by agent name
            limit: Maximum events to return
            
        Returns:
            List of matching events
        """
        events = self._event_history
        
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        if agent_name:
            events = [e for e in events if e.agent_name == agent_name]
        
        return events[-limit:]
    
    def get_trace_summary(self) -> Dict:
        """
        Get a summary of the current trace.
        
        Returns:
            Summary dictionary with statistics
        """
        if not self._event_history:
            return {"trace_id": self._trace_id, "events": 0}
        
        events_by_type = defaultdict(int)
        events_by_agent = defaultdict(int)
        total_duration = 0
        total_tokens = 0
        
        for event in self._event_history:
            events_by_type[event.event_type.value] += 1
            if event.agent_name:
                events_by_agent[event.agent_name] += 1
            if event.duration_ms:
                total_duration += event.duration_ms
            if event.token_count:
                total_tokens += event.token_count
        
        start_time = self._event_history[0].timestamp
        end_time = self._event_history[-1].timestamp
        
        return {
            "trace_id": self._trace_id,
            "total_events": len(self._event_history),
            "events_by_type": dict(events_by_type),
            "events_by_agent": dict(events_by_agent),
            "total_duration_ms": total_duration,
            "total_tokens": total_tokens,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "elapsed_seconds": (end_time - start_time).total_seconds()
        }
    
    def clear_history(self):
        """Clear event history."""
        self._event_history = []


def emit_event(
    event_type: EventType,
    agent_name: str = "",
    agent_type: str = "",
    step_number: int = 0,
    parent_agent: Optional[str] = None,
    duration_ms: Optional[int] = None,
    token_count: Optional[int] = None,
    **data
) -> AgentEvent:
    """
    Convenience function to emit an event.
    
    Args:
        event_type: The type of event
        agent_name: Name of the agent emitting
        agent_type: Type of agent
        step_number: Current step number
        parent_agent: Parent agent name (for managed agents)
        duration_ms: Duration in milliseconds
        token_count: Token count
        **data: Additional event data
        
    Returns:
        The emitted event
    """
    event = AgentEvent(
        event_type=event_type,
        agent_name=agent_name,
        agent_type=agent_type,
        step_number=step_number,
        parent_agent=parent_agent,
        duration_ms=duration_ms,
        token_count=token_count,
        data=data
    )
    EventEmitter.get_instance().emit(event)
    return event


async def emit_event_async(
    event_type: EventType,
    agent_name: str = "",
    agent_type: str = "",
    step_number: int = 0,
    parent_agent: Optional[str] = None,
    duration_ms: Optional[int] = None,
    token_count: Optional[int] = None,
    **data
) -> AgentEvent:
    """
    Convenience function to emit an event asynchronously.
    
    Same as emit_event but awaits async handlers.
    """
    event = AgentEvent(
        event_type=event_type,
        agent_name=agent_name,
        agent_type=agent_type,
        step_number=step_number,
        parent_agent=parent_agent,
        duration_ms=duration_ms,
        token_count=token_count,
        data=data
    )
    await EventEmitter.get_instance().emit_async(event)
    return event

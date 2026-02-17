"""
Observable Event Types

Defines all event types for agent observability and monitoring.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum
import json


class EventType(Enum):
    """All observable events in the agent system."""
    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    
    # Thinking & reasoning
    AGENT_THINKING = "agent.thinking"
    AGENT_REASONING = "agent.reasoning"
    
    # Tool usage
    TOOL_CALLED = "tool.called"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_ERROR = "tool.error"
    
    # Planning
    PLAN_CREATED = "plan.created"
    PLAN_UPDATED = "plan.updated"
    PLAN_STEP_STARTED = "plan.step.started"
    PLAN_STEP_COMPLETED = "plan.step.completed"
    
    # Managed agents
    MANAGED_AGENT_DELEGATED = "managed_agent.delegated"
    MANAGED_AGENT_RESPONSE = "managed_agent.response"
    
    # Memory & context
    CONTEXT_BUDGET_WARNING = "context.budget.warning"
    CONTEXT_TRUNCATED = "context.truncated"
    CANVAS_ENTRY_ADDED = "canvas.entry.added"
    CANVAS_RETRIEVED = "canvas.retrieved"
    
    # Final answer
    FINAL_ANSWER_GENERATED = "final_answer.generated"
    
    # Asset-specific events
    ASSET_LOADED = "asset.loaded"
    PAGE_READ = "page.read"
    CITATION_TRACKED = "citation.tracked"
    EXTRACTION_COMPLETE = "extraction.complete"


@dataclass
class AgentEvent:
    """A single observable event from the agent system."""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_name: str = ""
    agent_type: str = ""
    step_number: int = 0
    
    # Event-specific data
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Context
    parent_agent: Optional[str] = None  # For managed agents
    trace_id: str = ""  # For distributed tracing
    span_id: str = ""
    
    # Metrics
    duration_ms: Optional[int] = None
    token_count: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "step_number": self.step_number,
            "data": self.data,
            "parent_agent": self.parent_agent,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "duration_ms": self.duration_ms,
            "token_count": self.token_count
        }
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    def to_human_readable(self) -> str:
        """Format event for human-readable console output."""
        icon = EVENT_ICONS.get(self.event_type, "•")
        
        if self.event_type == EventType.AGENT_STARTED:
            task = self.data.get('task', '')
            task_preview = task[:100] + "..." if len(task) > 100 else task
            return f"{icon} [{self.agent_name}] Started: {task_preview}"
        
        elif self.event_type == EventType.AGENT_COMPLETED:
            return f"{icon} [{self.agent_name}] Completed successfully"
        
        elif self.event_type == EventType.AGENT_ERROR:
            error = self.data.get('error', 'Unknown error')
            return f"{icon} [{self.agent_name}] Error: {error[:100]}"
        
        elif self.event_type == EventType.AGENT_THINKING:
            thought = self.data.get('thought', '')
            thought_preview = thought[:200] + "..." if len(thought) > 200 else thought
            return f"{icon} [{self.agent_name}] Thinking: {thought_preview}"
        
        elif self.event_type == EventType.TOOL_CALLED:
            tool = self.data.get('tool_name', 'unknown')
            args = self.data.get('arguments', {})
            args_str = json.dumps(args) if isinstance(args, dict) else str(args)
            args_preview = args_str[:100] + "..." if len(args_str) > 100 else args_str
            return f"{icon} [{self.agent_name}] Calling: {tool}({args_preview})"
        
        elif self.event_type == EventType.TOOL_COMPLETED:
            tool = self.data.get('tool_name', 'unknown')
            duration = self.duration_ms or 0
            return f"{icon} [{self.agent_name}] Tool done: {tool} ({duration}ms)"
        
        elif self.event_type == EventType.TOOL_ERROR:
            tool = self.data.get('tool_name', 'unknown')
            error = self.data.get('error', 'Unknown error')
            return f"{icon} [{self.agent_name}] Tool error: {tool} - {error[:50]}"
        
        elif self.event_type == EventType.PLAN_CREATED:
            steps = self.data.get('steps', [])
            return f"{icon} [{self.agent_name}] Created plan with {len(steps)} steps"
        
        elif self.event_type == EventType.PLAN_UPDATED:
            change = self.data.get('change_description', 'updated')
            return f"{icon} [{self.agent_name}] Plan: {change}"
        
        elif self.event_type == EventType.PLAN_STEP_STARTED:
            step_desc = self.data.get('step_description', f'Step {self.step_number}')
            return f"{icon} [{self.agent_name}] Starting: {step_desc}"
        
        elif self.event_type == EventType.PLAN_STEP_COMPLETED:
            step_desc = self.data.get('step_description', f'Step {self.step_number}')
            return f"{icon} [{self.agent_name}] Done: {step_desc}"
        
        elif self.event_type == EventType.MANAGED_AGENT_DELEGATED:
            target = self.data.get('target_agent', 'unknown')
            task = self.data.get('task', '')[:80]
            return f"{icon} [{self.agent_name}] → [{target}]: {task}..."
        
        elif self.event_type == EventType.MANAGED_AGENT_RESPONSE:
            source = self.data.get('source_agent', 'unknown')
            summary = self.data.get('summary', '')[:100]
            return f"{icon} [{source}] → [{self.agent_name}]: {summary}..."
        
        elif self.event_type == EventType.FINAL_ANSWER_GENERATED:
            return f"{icon} [{self.agent_name}] Final answer generated"
        
        elif self.event_type == EventType.CONTEXT_BUDGET_WARNING:
            usage = self.data.get('usage_percent', 0)
            return f"{icon} [{self.agent_name}] Context at {usage:.1f}% capacity"
        
        elif self.event_type == EventType.CONTEXT_TRUNCATED:
            tokens_saved = self.data.get('tokens_saved', 0)
            return f"{icon} [{self.agent_name}] Context truncated, saved {tokens_saved} tokens"
        
        elif self.event_type == EventType.CANVAS_ENTRY_ADDED:
            title = self.data.get('title', 'Untitled')
            return f"{icon} [{self.agent_name}] Canvas: Added '{title[:50]}'"
        
        elif self.event_type == EventType.CANVAS_RETRIEVED:
            count = self.data.get('count', 0)
            return f"{icon} [{self.agent_name}] Canvas: Retrieved {count} entries"
        
        elif self.event_type == EventType.ASSET_LOADED:
            asset_id = self.data.get('asset_id', 'unknown')
            pages = self.data.get('total_pages', 0)
            return f"{icon} [{self.agent_name}] Asset loaded: {asset_id} ({pages} pages)"
        
        elif self.event_type == EventType.PAGE_READ:
            page_id = self.data.get('page_id', 'unknown')
            return f"{icon} [{self.agent_name}] Read page: {page_id}"
        
        elif self.event_type == EventType.CITATION_TRACKED:
            fact_id = self.data.get('fact_id', 'unknown')
            return f"{icon} [{self.agent_name}] Citation tracked: {fact_id}"
        
        elif self.event_type == EventType.EXTRACTION_COMPLETE:
            count = self.data.get('items_extracted', 0)
            return f"{icon} [{self.agent_name}] Extraction complete: {count} items"
        
        else:
            return f"{icon} [{self.agent_name}] {self.event_type.value}"


# Icons for console output
EVENT_ICONS: Dict[EventType, str] = {
    EventType.AGENT_STARTED: "🚀",
    EventType.AGENT_COMPLETED: "✅",
    EventType.AGENT_ERROR: "❌",
    EventType.AGENT_THINKING: "🤔",
    EventType.AGENT_REASONING: "💭",
    EventType.TOOL_CALLED: "🔧",
    EventType.TOOL_STARTED: "⏳",
    EventType.TOOL_COMPLETED: "✓",
    EventType.TOOL_ERROR: "⚠️",
    EventType.PLAN_CREATED: "📋",
    EventType.PLAN_UPDATED: "📝",
    EventType.PLAN_STEP_STARTED: "▶️",
    EventType.PLAN_STEP_COMPLETED: "☑️",
    EventType.MANAGED_AGENT_DELEGATED: "📤",
    EventType.MANAGED_AGENT_RESPONSE: "📥",
    EventType.CONTEXT_BUDGET_WARNING: "⚠️",
    EventType.CONTEXT_TRUNCATED: "✂️",
    EventType.CANVAS_ENTRY_ADDED: "📌",
    EventType.CANVAS_RETRIEVED: "🔍",
    EventType.FINAL_ANSWER_GENERATED: "🎯",
    EventType.ASSET_LOADED: "📁",
    EventType.PAGE_READ: "📄",
    EventType.CITATION_TRACKED: "🔗",
    EventType.EXTRACTION_COMPLETE: "✨",
}

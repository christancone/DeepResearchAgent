"""
Smart Asset Orchestrator Mixin

Provides intelligent task routing based on task analysis.
Can be mixed into PlanningAgent for smarter orchestration.
"""

from typing import Dict, Any, List, Optional, Tuple
import re
from dataclasses import dataclass
from enum import Enum


class TaskCategory(Enum):
    """Categories of tasks for routing."""
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    ANALYSIS = "analysis"
    SCRAPING = "scraping"
    SYNTHESIS = "synthesis"
    UNKNOWN = "unknown"


@dataclass
class RoutingDecision:
    """Result of task routing analysis."""
    primary_agent: str
    secondary_agents: List[str]
    category: TaskCategory
    confidence: float
    reasoning: str
    suggested_phases: List[Dict[str, Any]]


class SmartOrchestratorMixin:
    """
    Mixin that provides intelligent task routing based on task analysis.
    Can be mixed into PlanningAgent for smarter orchestration.
    """
    
    # Pattern matching for task classification
    TASK_PATTERNS: Dict[str, List[str]] = {
        "asset_extractor_agent": [
            r"find\s+.*\s+in\s+(the\s+)?dossier",
            r"extract\s+.*\s+from\s+pages?",
            r"list\s+all\s+(LLPs?|components?|parts?)",
            r"what\s+.*\s+in\s+(the\s+)?records?",
            r"get\s+.*\s+from\s+(the\s+)?dossier",
            r"read\s+.*\s+pages?",
            r"search\s+(the\s+)?dossier",
            r"identify\s+.*\s+(components?|parts?|items?)",
        ],
        "regulatory_researcher_agent": [
            r"validate\s+AD\s*[-#]?\s*\d+",
            r"check\s+(SB|AD)\s+compliance",
            r"FAA|EASA|regulatory",
            r"airworthiness\s+directive",
            r"service\s+bulletin",
            r"verify\s+.*\s+(AD|SB)",
            r"lookup\s+.*\s+(regulation|requirement)",
            r"current\s+status\s+of\s+(AD|SB)",
        ],
        "document_analyzer_agent": [
            r"analyze\s+.*\s+(trend|pattern|history)",
            r"cross-?reference",
            r"compare\s+.*\s+documents?",
            r"summarize\s+maintenance\s+history",
            r"find\s+.*\s+(inconsistencies?|contradictions?)",
            r"detect\s+.*\s+(gaps?|missing)",
            r"timeline\s+of\s+.*\s+events?",
            r"correlate\s+.*\s+data",
        ],
        "regulatory_scraper_agent": [
            r"scrape\s+.*\s+(FAA|EASA)",
            r"get\s+current\s+AD\s+list",
            r"download\s+.*\s+from\s+website",
            r"access\s+.*\s+(database|portal)",
            r"navigate\s+to\s+.*\s+website",
        ]
    }
    
    # Keywords that indicate task category
    CATEGORY_KEYWORDS: Dict[TaskCategory, List[str]] = {
        TaskCategory.EXTRACTION: [
            "extract", "find", "list", "get", "identify", "search", "read"
        ],
        TaskCategory.VALIDATION: [
            "validate", "verify", "check", "confirm", "compliance"
        ],
        TaskCategory.ANALYSIS: [
            "analyze", "compare", "cross-reference", "detect", "identify", "summarize"
        ],
        TaskCategory.SCRAPING: [
            "scrape", "download", "access", "navigate", "fetch"
        ],
        TaskCategory.SYNTHESIS: [
            "synthesize", "compile", "produce", "generate", "create report"
        ]
    }
    
    def suggest_agent(self, task: str) -> str:
        """
        Suggest the best agent for a given task.
        
        Args:
            task: The task description
            
        Returns:
            Name of the suggested agent
        """
        task_lower = task.lower()
        
        # Score each agent based on pattern matches
        scores: Dict[str, int] = {}
        for agent, patterns in self.TASK_PATTERNS.items():
            score = sum(1 for p in patterns if re.search(p, task_lower, re.IGNORECASE))
            if score > 0:
                scores[agent] = score
        
        # Return highest scoring agent or default
        if scores:
            return max(scores, key=scores.get)
        
        return "asset_extractor_agent"  # Default for dossier-related tasks
    
    def classify_task(self, task: str) -> TaskCategory:
        """
        Classify task into a category.
        
        Args:
            task: The task description
            
        Returns:
            TaskCategory enum value
        """
        task_lower = task.lower()
        
        scores: Dict[TaskCategory, int] = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[category] = score
        
        if scores:
            return max(scores, key=scores.get)
        
        return TaskCategory.UNKNOWN
    
    def route_task(self, task: str, asset_metadata: Optional[Dict] = None) -> RoutingDecision:
        """
        Make a routing decision for a task.
        
        Args:
            task: The task description
            asset_metadata: Optional asset context (total_pages, etc.)
            
        Returns:
            RoutingDecision with agent assignments and phases
        """
        primary_agent = self.suggest_agent(task)
        category = self.classify_task(task)
        
        # Determine secondary agents based on task complexity
        secondary_agents = []
        task_lower = task.lower()
        
        # If validation keywords present, add regulatory researcher
        if re.search(r"(validate|verify|check)\s+.*(AD|SB|compliance)", task_lower, re.IGNORECASE):
            if primary_agent != "regulatory_researcher_agent":
                secondary_agents.append("regulatory_researcher_agent")
        
        # If analysis keywords present, add document analyzer
        if re.search(r"(analyze|cross-?reference|compare|trend)", task_lower, re.IGNORECASE):
            if primary_agent != "document_analyzer_agent":
                secondary_agents.append("document_analyzer_agent")
        
        # Calculate confidence based on pattern match strength
        task_lower = task.lower()
        max_matches = 0
        for agent, patterns in self.TASK_PATTERNS.items():
            matches = sum(1 for p in patterns if re.search(p, task_lower, re.IGNORECASE))
            max_matches = max(max_matches, matches)
        
        confidence = min(0.9, 0.5 + (max_matches * 0.1))
        
        # Build reasoning
        reasoning = f"Task classified as {category.value}. "
        reasoning += f"Primary agent: {primary_agent} selected based on pattern matching. "
        if secondary_agents:
            reasoning += f"Secondary agents: {', '.join(secondary_agents)} for additional support."
        
        # Generate suggested phases
        phases = self.plan_research_phases(task, asset_metadata or {})
        
        return RoutingDecision(
            primary_agent=primary_agent,
            secondary_agents=secondary_agents,
            category=category,
            confidence=confidence,
            reasoning=reasoning,
            suggested_phases=phases
        )
    
    def plan_research_phases(
        self, 
        task: str, 
        asset_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate a research plan based on task and asset size.
        
        Args:
            task: The task description
            asset_metadata: Asset information (total_pages, etc.)
            
        Returns:
            List of research phases with agent assignments
        """
        total_pages = asset_metadata.get("total_pages", 0)
        task_lower = task.lower()
        
        phases = []
        
        # Phase 1: Discovery (always needed)
        phases.append({
            "phase": "discovery",
            "phase_number": 1,
            "agent": "asset_extractor_agent",
            "task": "Get asset overview and document structure",
            "description": "Understand what's in the dossier before deep extraction"
        })
        
        # Phase 2: Main extraction
        main_agent = self.suggest_agent(task)
        phases.append({
            "phase": "extraction",
            "phase_number": 2,
            "agent": main_agent,
            "task": task,
            "description": "Primary extraction/analysis task"
        })
        
        # Phase 3: Validation (if regulatory terms detected)
        if re.search(r"(AD|SB|compliance|regulatory|airworthiness)", task_lower, re.IGNORECASE):
            phases.append({
                "phase": "validation",
                "phase_number": 3,
                "agent": "regulatory_researcher_agent",
                "task": "Validate regulatory references against FAA/EASA databases",
                "description": "Cross-check extracted ADs/SBs with official sources"
            })
        
        # Phase 4: Analysis (for large dossiers or complex tasks)
        needs_analysis = (
            total_pages > 500 or
            re.search(r"(trend|pattern|history|cross-?reference|compare)", task_lower, re.IGNORECASE)
        )
        if needs_analysis:
            phases.append({
                "phase": "analysis",
                "phase_number": len(phases) + 1,
                "agent": "document_analyzer_agent",
                "task": "Analyze patterns and cross-reference findings",
                "description": "Deep analysis for complex document sets"
            })
        
        # Final phase: Synthesis
        phases.append({
            "phase": "synthesis",
            "phase_number": len(phases) + 1,
            "agent": "asset_extractor_agent",
            "task": "Compile final structured output with all citations",
            "description": "Combine all findings into final report"
        })
        
        return phases
    
    def estimate_complexity(
        self, 
        task: str, 
        asset_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Estimate task complexity for resource planning.
        
        Args:
            task: The task description
            asset_metadata: Asset information
            
        Returns:
            Complexity assessment
        """
        total_pages = asset_metadata.get("total_pages", 0)
        total_documents = asset_metadata.get("total_documents", 0)
        
        # Base complexity from asset size
        if total_pages > 5000:
            size_complexity = "very_high"
        elif total_pages > 1000:
            size_complexity = "high"
        elif total_pages > 500:
            size_complexity = "medium"
        else:
            size_complexity = "low"
        
        # Task complexity from keywords
        task_lower = task.lower()
        complex_keywords = [
            "comprehensive", "complete", "full", "all", "every",
            "cross-reference", "validate", "analyze", "trend"
        ]
        keyword_count = sum(1 for kw in complex_keywords if kw in task_lower)
        
        if keyword_count >= 3:
            task_complexity = "high"
        elif keyword_count >= 1:
            task_complexity = "medium"
        else:
            task_complexity = "low"
        
        # Estimate number of agents needed
        routing = self.route_task(task, asset_metadata)
        agents_needed = 1 + len(routing.secondary_agents)
        
        # Estimate phases
        phases = routing.suggested_phases
        
        return {
            "size_complexity": size_complexity,
            "task_complexity": task_complexity,
            "total_pages": total_pages,
            "total_documents": total_documents,
            "agents_needed": agents_needed,
            "phases_needed": len(phases),
            "suggested_depth": "comprehensive" if size_complexity in ["high", "very_high"] else "standard",
            "routing_decision": routing
        }
    
    def get_agent_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """
        Return description of available agents and their capabilities.
        
        Returns:
            Dictionary mapping agent names to their capabilities
        """
        return {
            "asset_extractor_agent": {
                "description": "Extracts structured data from dossier pages",
                "capabilities": [
                    "Reading and extracting data from pages",
                    "Component identification (LLPs, rotables, modules)",
                    "Maintenance event extraction",
                    "Citation tracking for all facts"
                ],
                "best_for": [
                    "Finding specific data in the dossier",
                    "Listing components and their status",
                    "Extracting maintenance history"
                ]
            },
            "regulatory_researcher_agent": {
                "description": "Validates regulatory items against official databases",
                "capabilities": [
                    "FAA AD/SB lookup and validation",
                    "EASA AD lookup",
                    "TCDS and STC research",
                    "Historical document search via Wayback Machine"
                ],
                "best_for": [
                    "Validating AD/SB compliance",
                    "Finding current regulatory requirements",
                    "Researching superseded documents"
                ]
            },
            "document_analyzer_agent": {
                "description": "Performs deep analysis on complex documents",
                "capabilities": [
                    "Cross-referencing data across documents",
                    "Contradiction detection",
                    "Gap identification",
                    "Trend and pattern analysis"
                ],
                "best_for": [
                    "Complex analysis tasks",
                    "Finding inconsistencies",
                    "Building maintenance timelines"
                ]
            },
            "regulatory_scraper_agent": {
                "description": "Accesses regulatory websites for data extraction",
                "capabilities": [
                    "Web navigation and data extraction",
                    "FAA/EASA portal access",
                    "Screenshot capture"
                ],
                "best_for": [
                    "When API access is unavailable",
                    "Accessing current AD lists",
                    "Downloading specific documents"
                ]
            }
        }

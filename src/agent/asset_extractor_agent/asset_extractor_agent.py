"""
Asset Extractor Agent

Specialized agent for extracting structured data from asset dossiers.
Extends GeneralAgent with citation tracking and batch processing capabilities.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import yaml

from src.agent.general_agent import GeneralAgent
from src.registry import AGENT
from src.models import Model
from src.base.async_multistep_agent import PromptTemplates, populate_template
from src.memory import AgentMemory
from src.schemas.asset_research_output import (
    SourceCitation,
    CitedFact,
    ComponentInfo,
    MaintenanceEvent,
    ComplianceItem,
)
from src.utils import assemble_project_path


@AGENT.register_module(name="asset_extractor_agent", force=True)
class AssetExtractorAgent(GeneralAgent):
    """
    Specialized agent for extracting structured data from asset dossiers.
    
    Extends GeneralAgent with:
    - Citation tracking for every extracted fact
    - Batch processing of multiple pages/documents
    - Structured output generation
    - Integration with the working memory canvas
    """
    
    def __init__(
        self,
        config,
        tools: list[Any],
        model: Model,
        prompt_templates: PromptTemplates | None = None,
        planning_interval: int | None = None,
        stream_outputs: bool = False,
        max_tool_threads: int | None = None,
        **kwargs,
    ):
        """
        Initialize the Asset Extractor Agent.
        
        Args:
            config: Agent configuration
            tools: List of tools available to the agent
            model: LLM model to use
            prompt_templates: Optional custom prompt templates
            planning_interval: Interval for planning steps
            stream_outputs: Whether to stream outputs
            max_tool_threads: Maximum parallel tool threads
        """
        # Initialize parent class
        super().__init__(
            config=config,
            tools=tools,
            model=model,
            prompt_templates=prompt_templates,
            planning_interval=planning_interval,
            stream_outputs=stream_outputs,
            max_tool_threads=max_tool_threads,
            **kwargs,
        )
        
        # Citation tracking
        self.citation_tracker: Dict[str, Dict[str, Any]] = {}
        
        # Extraction buffer for batch processing
        self.extraction_buffer: List[Dict[str, Any]] = []
        
        # Asset context
        self.asset_id: Optional[str] = None
        self.asset_context: Dict[str, Any] = {}
        
        # Structured outputs
        self.extracted_components: List[ComponentInfo] = []
        self.extracted_events: List[MaintenanceEvent] = []
        self.extracted_compliance: List[ComplianceItem] = []
        self.extracted_findings: List[CitedFact] = []
    
    def set_asset_context(
        self,
        asset_id: str,
        asset_name: Optional[str] = None,
        total_pages: Optional[int] = None,
        document_types: Optional[List[str]] = None,
        **extra_context
    ):
        """
        Set the asset context for this extraction session.
        
        Args:
            asset_id: The asset ID being analyzed
            asset_name: Name of the asset
            total_pages: Total pages in the dossier
            document_types: Types of documents in the dossier
            **extra_context: Additional context information
        """
        self.asset_id = asset_id
        self.asset_context = {
            "asset_id": asset_id,
            "asset_name": asset_name,
            "total_pages": total_pages,
            "document_types": document_types or [],
            **extra_context
        }
    
    def track_citation(
        self,
        fact_id: str,
        page_ids: List[str],
        document_ids: Optional[List[str]] = None,
        excerpts: Optional[List[str]] = None,
        confidence: str = "medium"
    ) -> Dict[str, Any]:
        """
        Track source pages for an extracted fact.
        
        Args:
            fact_id: Unique identifier for the fact
            page_ids: List of source page IDs
            document_ids: Optional list of document IDs
            excerpts: Optional relevant text excerpts
            confidence: Confidence level (high, medium, low)
            
        Returns:
            Citation record
        """
        citation = {
            "fact_id": fact_id,
            "source_pages": page_ids,
            "document_ids": document_ids or [],
            "excerpts": excerpts or [],
            "confidence": confidence,
            "extracted_at": datetime.utcnow().isoformat(),
            "asset_id": self.asset_id
        }
        
        self.citation_tracker[fact_id] = citation
        return citation
    
    def create_source_citation(
        self,
        page_id: str,
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        page_index: Optional[int] = None,
        excerpt: Optional[str] = None,
        confidence: str = "medium"
    ) -> SourceCitation:
        """
        Create a SourceCitation object.
        
        Args:
            page_id: Page ID
            document_id: Document ID
            document_name: Document name
            page_index: Page number
            excerpt: Relevant text excerpt
            confidence: Confidence level
            
        Returns:
            SourceCitation instance
        """
        return SourceCitation(
            page_id=page_id,
            document_id=document_id,
            document_name=document_name,
            page_index=page_index,
            excerpt=excerpt,
            confidence=confidence
        )
    
    def create_cited_fact(
        self,
        value: Any,
        source_pages: List[SourceCitation],
        confidence: str = "medium",
        validation_status: str = "unverified",
        notes: Optional[str] = None
    ) -> CitedFact:
        """
        Create a CitedFact with full tracking.
        
        Args:
            value: The actual fact/value
            source_pages: Source citations
            confidence: Confidence level
            validation_status: verified, unverified, contradicted
            notes: Additional notes
            
        Returns:
            CitedFact instance
        """
        return CitedFact(
            value=value,
            source_pages=source_pages,
            confidence=confidence,
            validation_status=validation_status,
            notes=notes
        )
    
    def add_component(
        self,
        part_number: Optional[str] = None,
        serial_number: Optional[str] = None,
        description: Optional[str] = None,
        component_type: Optional[str] = None,
        source_pages: Optional[List[SourceCitation]] = None,
        confidence: str = "medium",
        **kwargs
    ) -> ComponentInfo:
        """
        Add an extracted component to the results.
        
        Args:
            part_number: Component part number
            serial_number: Serial number
            description: Component description
            component_type: Type (LLP, rotable, module)
            source_pages: Source citations
            confidence: Confidence level
            **kwargs: Additional component fields
            
        Returns:
            ComponentInfo instance
        """
        component = ComponentInfo(
            part_number=part_number,
            serial_number=serial_number,
            description=description,
            component_type=component_type,
            source_pages=source_pages or [],
            confidence=confidence,
            **kwargs
        )
        self.extracted_components.append(component)
        return component
    
    def add_maintenance_event(
        self,
        event_type: Optional[str] = None,
        date: Optional[str] = None,
        description: Optional[str] = None,
        source_pages: Optional[List[SourceCitation]] = None,
        confidence: str = "medium",
        **kwargs
    ) -> MaintenanceEvent:
        """
        Add an extracted maintenance event to the results.
        """
        event = MaintenanceEvent(
            event_type=event_type,
            date=date,
            description=description,
            source_pages=source_pages or [],
            confidence=confidence,
            **kwargs
        )
        self.extracted_events.append(event)
        return event
    
    def add_compliance_item(
        self,
        reference: str,
        title: Optional[str] = None,
        status: str = "unknown",
        source_pages: Optional[List[SourceCitation]] = None,
        confidence: str = "medium",
        **kwargs
    ) -> ComplianceItem:
        """
        Add an extracted compliance item to the results.
        """
        item = ComplianceItem(
            reference=reference,
            title=title,
            status=status,
            source_pages=source_pages or [],
            confidence=confidence,
            **kwargs
        )
        self.extracted_compliance.append(item)
        return item
    
    def add_finding(
        self,
        value: Any,
        source_pages: List[SourceCitation],
        confidence: str = "medium",
        notes: Optional[str] = None
    ) -> CitedFact:
        """
        Add a key finding to the results.
        """
        finding = self.create_cited_fact(
            value=value,
            source_pages=source_pages,
            confidence=confidence,
            notes=notes
        )
        self.extracted_findings.append(finding)
        return finding
    
    def get_citations_summary(self) -> Dict[str, Any]:
        """Return summary of all tracked citations."""
        return {
            "total_facts": len(self.citation_tracker),
            "by_confidence": {
                "high": len([c for c in self.citation_tracker.values() if c["confidence"] == "high"]),
                "medium": len([c for c in self.citation_tracker.values() if c["confidence"] == "medium"]),
                "low": len([c for c in self.citation_tracker.values() if c["confidence"] == "low"]),
            },
            "unique_pages": len(set(
                page 
                for c in self.citation_tracker.values() 
                for page in c.get("source_pages", [])
            )),
            "citations": self.citation_tracker
        }
    
    def get_extraction_results(self) -> Dict[str, Any]:
        """
        Get all extraction results with citations.
        
        Returns:
            Dictionary with all extracted data and citation summary
        """
        return {
            "asset_context": self.asset_context,
            "components": [c.dict() for c in self.extracted_components],
            "maintenance_events": [e.dict() for e in self.extracted_events],
            "compliance_items": [i.dict() for i in self.extracted_compliance],
            "key_findings": [f.dict() for f in self.extracted_findings],
            "citations_summary": self.get_citations_summary(),
            "extraction_metadata": {
                "extracted_at": datetime.utcnow().isoformat(),
                "agent_name": self.name,
                "total_components": len(self.extracted_components),
                "total_events": len(self.extracted_events),
                "total_compliance_items": len(self.extracted_compliance),
                "total_findings": len(self.extracted_findings),
            }
        }
    
    async def extract_with_citations(self, extraction_task: str) -> Dict[str, Any]:
        """
        Run extraction and return results with citation metadata.
        
        Args:
            extraction_task: The extraction task description
            
        Returns:
            Dictionary with extraction result and all citations
        """
        result = await self.run(extraction_task)
        
        return {
            "extraction_result": result,
            "structured_output": self.get_extraction_results(),
            "citations": self.get_citations_summary()
        }
    
    def reset_extraction_state(self):
        """Reset all extraction state for a new session."""
        self.citation_tracker = {}
        self.extraction_buffer = []
        self.extracted_components = []
        self.extracted_events = []
        self.extracted_compliance = []
        self.extracted_findings = []
        self.asset_context = {}
        self.asset_id = None
    
    def to_canvas_entries(self) -> List[Dict[str, Any]]:
        """
        Convert extraction results to canvas entries for storage.
        
        Returns:
            List of dictionaries suitable for canvas.add_entry()
        """
        entries = []
        
        # Components
        for comp in self.extracted_components:
            entries.append({
                "title": f"Component: {comp.part_number or comp.serial_number or 'Unknown'}",
                "tags": ["component", comp.component_type or "unknown", self.asset_id or ""],
                "content": json.dumps(comp.dict()),
                "summary": f"{comp.component_type}: {comp.description or comp.part_number}",
                "citations": [c.dict() for c in comp.source_pages],
                "confidence": comp.confidence,
                "category": "components"
            })
        
        # Maintenance events
        for event in self.extracted_events:
            entries.append({
                "title": f"Maintenance: {event.event_type} - {event.date or 'Unknown date'}",
                "tags": ["maintenance", event.event_type or "unknown", self.asset_id or ""],
                "content": json.dumps(event.dict()),
                "summary": event.description or f"{event.event_type} on {event.date}",
                "citations": [c.dict() for c in event.source_pages],
                "confidence": event.confidence,
                "category": "maintenance"
            })
        
        # Compliance items
        for item in self.extracted_compliance:
            entries.append({
                "title": f"Compliance: {item.reference}",
                "tags": ["compliance", item.issuing_authority or "unknown", item.status, self.asset_id or ""],
                "content": json.dumps(item.dict()),
                "summary": f"{item.reference}: {item.status}",
                "citations": [c.dict() for c in item.source_pages],
                "confidence": item.confidence,
                "category": "compliance"
            })
        
        # Key findings
        for finding in self.extracted_findings:
            entries.append({
                "title": f"Finding: {str(finding.value)[:50]}",
                "tags": ["finding", finding.confidence, self.asset_id or ""],
                "content": json.dumps(finding.dict()),
                "summary": str(finding.value)[:200],
                "citations": [c.dict() for c in finding.source_pages],
                "confidence": finding.confidence,
                "category": "findings"
            })
        
        return entries

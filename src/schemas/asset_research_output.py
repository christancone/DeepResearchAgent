"""
Asset Research Output Schema

Pydantic models for structured output from the Asset Research Agent.
Every extracted fact includes source citations for traceability.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal, TypeVar, Generic, Union
from datetime import datetime


T = TypeVar('T')


# ============================================================================
# CITATION TYPES
# ============================================================================

class SourceCitation(BaseModel):
    """Citation to a source document page in the asset dossier."""
    page_id: str = Field(..., description="Unique identifier of the source page")
    document_id: Optional[str] = Field(None, description="ID of the parent document")
    document_name: Optional[str] = Field(None, description="Name of the source document")
    page_index: Optional[int] = Field(None, description="Page number within the document")
    excerpt: Optional[str] = Field(None, description="Relevant text snippet from the page")
    confidence: Literal["high", "medium", "low"] = Field("medium", description="Confidence in this citation")
    
    class Config:
        extra = "allow"


class WebCitation(BaseModel):
    """Citation to an external web source."""
    url: str = Field(..., description="URL of the web source")
    title: Optional[str] = Field(None, description="Title of the web page")
    accessed_at: datetime = Field(default_factory=datetime.utcnow, description="When the URL was accessed")
    archived_url: Optional[str] = Field(None, description="Wayback Machine URL if available")
    source_type: Literal["faa", "easa", "oem", "regulatory", "other"] = Field("other", description="Type of source")
    
    class Config:
        extra = "allow"


class CitedFact(BaseModel, Generic[T]):
    """
    A fact with full citation tracking.
    
    Every extracted fact should be wrapped in this model to ensure traceability.
    """
    value: Any = Field(..., description="The actual fact/value")
    source_pages: List[SourceCitation] = Field(default_factory=list, description="Citations to dossier pages")
    web_sources: Optional[List[WebCitation]] = Field(None, description="Citations to web sources")
    validation_status: Literal["verified", "unverified", "contradicted"] = Field(
        "unverified", 
        description="Whether the fact has been validated"
    )
    confidence: Literal["high", "medium", "low"] = Field("medium", description="Overall confidence in this fact")
    notes: Optional[str] = Field(None, description="Additional notes about this fact")
    
    class Config:
        extra = "allow"


# ============================================================================
# RESEARCH METADATA
# ============================================================================

class ResearchMetadata(BaseModel):
    """Metadata about the research process."""
    asset_id: str = Field(..., description="ID of the asset that was analyzed")
    asset_name: Optional[str] = Field(None, description="Name of the asset")
    prompt: str = Field(..., description="The analysis prompt/question")
    total_pages_analyzed: int = Field(0, description="Number of pages actually read")
    total_pages_in_asset: int = Field(0, description="Total pages in the dossier")
    total_documents: Optional[int] = Field(None, description="Total documents in the dossier")
    research_depth: Literal["quick", "standard", "comprehensive"] = Field("standard")
    processing_time_ms: int = Field(0, description="Processing time in milliseconds")
    agent_version: str = Field("1.0.0", description="Version of the research agent")
    agents_used: List[str] = Field(default_factory=list, description="Agents that participated")
    tools_invoked: List[Dict[str, Any]] = Field(default_factory=list, description="Tools used with counts")
    
    class Config:
        extra = "allow"


class ConfidenceSummary(BaseModel):
    """Summary of confidence levels across all findings."""
    high_confidence_facts: int = Field(0, description="Facts with high confidence")
    medium_confidence_facts: int = Field(0, description="Facts with medium confidence")
    low_confidence_facts: int = Field(0, description="Facts with low confidence")
    web_validated_facts: int = Field(0, description="Facts validated against web sources")
    contradicted_facts: int = Field(0, description="Facts with contradictions found")
    
    class Config:
        extra = "allow"


# ============================================================================
# DOMAIN-SPECIFIC TYPES
# ============================================================================

class ComponentInfo(BaseModel):
    """Information about a component (LLP, rotable, module, etc.)."""
    part_number: Optional[str] = Field(None, description="Part number")
    serial_number: Optional[str] = Field(None, description="Serial number")
    description: Optional[str] = Field(None, description="Component description")
    component_type: Optional[str] = Field(None, description="Type: LLP, rotable, module, etc.")
    position: Optional[str] = Field(None, description="Position/location")
    
    # Life tracking
    cycles_since_new: Optional[int] = Field(None, description="Total cycles since new")
    hours_since_new: Optional[float] = Field(None, description="Total hours since new")
    cycles_since_overhaul: Optional[int] = Field(None, description="Cycles since last overhaul")
    hours_since_overhaul: Optional[float] = Field(None, description="Hours since last overhaul")
    cycle_limit: Optional[int] = Field(None, description="Cycle limit for LLPs")
    cycles_remaining: Optional[int] = Field(None, description="Remaining cycles")
    
    # Status
    condition: Optional[str] = Field(None, description="Current condition")
    last_inspection_date: Optional[str] = Field(None, description="Date of last inspection")
    
    # Citations
    source_pages: List[SourceCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = Field("medium")
    
    class Config:
        extra = "allow"


class MaintenanceEvent(BaseModel):
    """A maintenance event from the aircraft history."""
    event_type: Optional[str] = Field(None, description="Type: inspection, overhaul, repair, etc.")
    date: Optional[str] = Field(None, description="Date of the event")
    description: Optional[str] = Field(None, description="Description of work performed")
    work_order: Optional[str] = Field(None, description="Work order number")
    facility: Optional[str] = Field(None, description="Facility that performed the work")
    
    # Component info
    component_serial: Optional[str] = Field(None, description="Component serial number if applicable")
    hours_at_event: Optional[float] = Field(None, description="Aircraft/component hours at event")
    cycles_at_event: Optional[int] = Field(None, description="Aircraft/component cycles at event")
    
    # Citations
    source_pages: List[SourceCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = Field("medium")
    
    class Config:
        extra = "allow"


class ComplianceItem(BaseModel):
    """An AD, SB, or other compliance requirement."""
    reference: str = Field(..., description="AD/SB/requirement reference number")
    title: Optional[str] = Field(None, description="Title of the requirement")
    issuing_authority: Optional[str] = Field(None, description="FAA, EASA, OEM, etc.")
    status: Literal["compliant", "non_compliant", "not_applicable", "unknown"] = Field("unknown")
    compliance_date: Optional[str] = Field(None, description="Date of compliance")
    compliance_method: Optional[str] = Field(None, description="How compliance was achieved")
    next_due: Optional[str] = Field(None, description="Next compliance due date/interval")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    # Web validation
    faa_validation: Optional[WebCitation] = Field(None, description="FAA validation source")
    easa_validation: Optional[WebCitation] = Field(None, description="EASA validation source")
    
    # Citations
    source_pages: List[SourceCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = Field("medium")
    
    class Config:
        extra = "allow"


class GapInfo(BaseModel):
    """Information about a gap or missing data in the dossier."""
    gap_type: str = Field(..., description="Type of gap: missing_logbook, incomplete_records, etc.")
    description: str = Field(..., description="Description of what's missing")
    severity: Literal["critical", "major", "minor"] = Field("major")
    affected_components: Optional[List[str]] = Field(None, description="Components affected by this gap")
    affected_period: Optional[str] = Field(None, description="Time period affected")
    recommendation: Optional[str] = Field(None, description="Recommended action")
    
    # Citations
    source_pages: List[SourceCitation] = Field(default_factory=list)
    
    class Config:
        extra = "allow"


class ContradictionInfo(BaseModel):
    """Information about a contradiction found in the dossier."""
    description: str = Field(..., description="Description of the contradiction")
    sources_a: List[SourceCitation] = Field(default_factory=list, description="First set of sources")
    sources_b: List[SourceCitation] = Field(default_factory=list, description="Contradicting sources")
    resolution: Optional[str] = Field(None, description="How the contradiction was resolved")
    preferred_value: Optional[Any] = Field(None, description="The value considered correct")
    
    class Config:
        extra = "allow"


# ============================================================================
# MAIN OUTPUT SCHEMA
# ============================================================================

class AssetResearchOutput(BaseModel):
    """
    Complete research output from the Asset Research Agent.
    
    This schema extends the SummaryJson format with full citation tracking
    and validation status for every extracted fact.
    """
    
    # =========================================================================
    # METADATA
    # =========================================================================
    research_metadata: ResearchMetadata = Field(..., description="Information about the research process")
    
    # =========================================================================
    # ASSET IDENTIFICATION
    # =========================================================================
    asset_identification: Optional[Dict[str, Any]] = Field(
        None, 
        description="Aircraft/asset identification details (serial number, type, etc.)"
    )
    
    # =========================================================================
    # EXECUTIVE SUMMARY
    # =========================================================================
    executive_summary: Optional[Dict[str, Any]] = Field(
        None,
        description="High-level summary of the asset's status"
    )
    
    # =========================================================================
    # COMPONENT INVENTORY
    # =========================================================================
    components: List[ComponentInfo] = Field(
        default_factory=list,
        description="List of components (LLPs, rotables, modules)"
    )
    
    # =========================================================================
    # MAINTENANCE HISTORY
    # =========================================================================
    maintenance_events: List[MaintenanceEvent] = Field(
        default_factory=list,
        description="Maintenance history timeline"
    )
    
    # =========================================================================
    # COMPLIANCE STATUS
    # =========================================================================
    compliance_items: List[ComplianceItem] = Field(
        default_factory=list,
        description="AD/SB compliance status"
    )
    
    # =========================================================================
    # UTILIZATION METRICS
    # =========================================================================
    utilization_metrics: Optional[Dict[str, Any]] = Field(
        None,
        description="Hours, cycles, and utilization data"
    )
    
    # =========================================================================
    # FINDINGS
    # =========================================================================
    key_findings: List[CitedFact] = Field(
        default_factory=list,
        description="Key findings from the analysis"
    )
    
    gaps: List[GapInfo] = Field(
        default_factory=list,
        description="Gaps and missing information"
    )
    
    contradictions: List[ContradictionInfo] = Field(
        default_factory=list,
        description="Contradictions found in the dossier"
    )
    
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommendations based on the analysis"
    )
    
    # =========================================================================
    # CONFIDENCE SUMMARY
    # =========================================================================
    confidence_summary: ConfidenceSummary = Field(
        default_factory=ConfidenceSummary,
        description="Summary of confidence levels"
    )
    
    # =========================================================================
    # RISK ASSESSMENT
    # =========================================================================
    risk_assessment: Optional[Dict[str, Any]] = Field(
        None,
        description="Overall risk assessment"
    )
    
    # =========================================================================
    # RAW DATA (for UI compatibility)
    # =========================================================================
    raw_summary_json: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw SummaryJson for backward compatibility"
    )
    
    class Config:
        extra = "allow"  # Allow additional fields for flexibility
    
    def to_summary_json(self) -> Dict[str, Any]:
        """
        Convert to SummaryJson format for UI compatibility.
        
        Returns a dictionary matching the existing SummaryJson TypeScript interface.
        """
        return {
            "asset_id": self.research_metadata.asset_id,
            "asset_name": self.research_metadata.asset_name,
            "metadata": {
                "updated_at": datetime.utcnow().isoformat(),
                "total_components": len(self.components),
                "source_pages_count": self.research_metadata.total_pages_analyzed,
            },
            "components": [c.dict() for c in self.components],
            "key_findings": [f.dict() for f in self.key_findings],
            "configuration": self.asset_identification,
            "risk_assessment": self.risk_assessment,
            "executive_summary": self.executive_summary,
            "utilization_metrics": self.utilization_metrics,
            "asset_identification": self.asset_identification,
        }
    
    @classmethod
    def create_minimal(
        cls,
        asset_id: str,
        prompt: str,
        asset_name: Optional[str] = None
    ) -> "AssetResearchOutput":
        """Create a minimal output structure for initialization."""
        return cls(
            research_metadata=ResearchMetadata(
                asset_id=asset_id,
                asset_name=asset_name,
                prompt=prompt,
                research_depth="standard"
            ),
            confidence_summary=ConfidenceSummary()
        )

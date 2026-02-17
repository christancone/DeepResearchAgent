# Agent Prompts and JSON Schema Documentation

This document describes the prompts and JSON structure requirements for the Asset Research Agent.

## 1. Prompts Fed to the Agent

### 1.1 Orchestrator Agent (`src/agent/asset_research_prompts/orchestrator.yaml`)

The orchestrator coordinates multiple specialized agents to analyze aircraft maintenance dossiers.

#### System Prompt
```
You are the Asset Dossier Research Orchestrator. Your job is to analyze 
aircraft maintenance dossiers by coordinating specialized agents.

## Available Managed Agents
{{managed_agents}}

## Agent Selection Guide
| Task Type | Use This Agent |
|-----------|----------------|
| Extract data from dossier pages | asset_extractor_agent |
| Validate ADs/SBs against FAA/EASA | regulatory_researcher_agent (deep_researcher) |
| Analyze complex documents, cross-reference | document_analyzer_agent (deep_analyzer) |
| Scrape regulatory websites when APIs fail | regulatory_scraper_agent (browser_use) |

## Research Phases
1. **Discovery**: Use asset_extractor_agent to understand dossier structure
2. **Extraction**: Extract requested data with full citations
3. **Validation**: Use regulatory_researcher_agent to validate external references
4. **Analysis**: Use document_analyzer_agent for complex cross-referencing
5. **Synthesis**: Combine all findings into structured output

## Citation Requirements
EVERY extracted fact MUST include:
- source_pages: List of page IDs where the fact was found
- confidence: "high" | "medium" | "low"
- validation_status: "verified" | "unverified" | "contradicted"

## Available Tools
{{tools}}

## Working Memory
Use the canvas_tool to:
1. Track findings across all agents
2. Avoid duplicate extraction
3. Build up the final report incrementally

## Quality Standards
- Every fact must be traceable to a source page
- Regulatory references must be validated against official databases
- Contradictions must be reported with both sources
- Gaps in documentation must be explicitly noted
```

#### User Prompt
```
You are the Asset Research Orchestrator coordinating a multi-agent analysis.
Delegate tasks to specialized agents and synthesize their findings.

Use planning_tool to track your research progress.
```

#### Task Instruction (with template variables)
```
## Asset Research Task

Asset ID: {{asset_id}}

Research Request: {{task}}

## Expected Deliverable

Produce a comprehensive structured report with:
1. All requested information extracted with citations
2. Regulatory items validated against FAA/EASA databases
3. Confidence levels for each finding
4. Identified gaps and contradictions
5. Final JSON output compatible with AssetResearchOutput schema
```

#### Managed Agent Task Template
```
You are working as a specialized agent for the Asset Dossier Research Orchestrator.

Asset Context:
- Asset ID: {{asset_id}}
- Total Pages: {{total_pages}}
- Document Types: {{document_types}}

Your Task: {{task}}

Requirements:
- Include source page IDs for every extracted fact
- Note confidence level for each finding
- Report any gaps or contradictions found
```

#### Final Answer Prompt
```
Based on your research, provide the final structured output in JSON format.
Ensure all findings include source citations and confidence levels.
```

### 1.2 Document Analyzer Agent (`src/agent/asset_research_prompts/document_analyzer.yaml`)

Specialized for cross-referencing and pattern detection.

#### System Prompt (Key Points)
- Cross-referencing information across multiple documents
- Identifying patterns and trends in maintenance history
- Detecting inconsistencies and contradictions
- Timeline reconstruction from scattered records

#### Output Format Required
```
Analysis: [Type of analysis]
Finding: [What you found]
Sources: [All page IDs referenced]
Confidence: [high/medium/low]
Recommendation: [What action if any is needed]
```

### 1.3 Regulatory Researcher Agent (`src/agent/asset_research_prompts/regulatory_researcher.yaml`)

Validates ADs, SBs, and regulatory requirements.

#### Key Requirements
- Use deep_researcher_tool for comprehensive multi-level research
- Cite official regulatory databases (FAA, EASA)
- Provide full reference numbers, titles, compliance requirements
- Include source URLs with access timestamps

## 2. JSON Structure Schema

Note: Runtime output is now legacy-compatible at the root level for downstream consumers.  
Primary root keys are:
- `asset_id`, `metadata`, `asset_name`
- `asset_identification`, `executive_summary`, `utilization_metrics`
- `components`, `configuration`, `risk_assessment`
- `key_findings`, `important_points`

Compatibility behavior:
- Legacy `source_pages` fields are page-index integer arrays.
- Companion `source_citations` fields preserve enriched citation metadata (`pageId`, `documentId`, `documentName`, `enhancedS3Key`) when available.
- For high page-count dossiers, adaptive completeness targets are applied to avoid sparse output.

### 2.1 Main Output Schema: `AssetResearchOutput`

Defined in `src/schemas/asset_research_output.py` using Pydantic models.

```python
class AssetResearchOutput(BaseModel):
    """Complete research output from the Asset Research Agent."""
    
    # METADATA
    research_metadata: ResearchMetadata
    
    # ASSET IDENTIFICATION
    asset_identification: Optional[Dict[str, Any]]
    
    # EXECUTIVE SUMMARY
    executive_summary: Optional[Dict[str, Any]]
    
    # COMPONENT INVENTORY
    components: List[ComponentInfo]
    
    # MAINTENANCE HISTORY
    maintenance_events: List[MaintenanceEvent]
    
    # COMPLIANCE STATUS
    compliance_items: List[ComplianceItem]
    
    # UTILIZATION METRICS
    utilization_metrics: Optional[Dict[str, Any]]
    
    # FINDINGS
    key_findings: List[CitedFact]
    gaps: List[GapInfo]
    contradictions: List[ContradictionInfo]
    recommendations: List[str]
    
    # CONFIDENCE SUMMARY
    confidence_summary: ConfidenceSummary
    
    # RISK ASSESSMENT
    risk_assessment: Optional[Dict[str, Any]]
    
    # RAW DATA (for UI compatibility)
    raw_summary_json: Optional[Dict[str, Any]]
```

### 2.2 Key Sub-Schemas

#### ResearchMetadata
```python
class ResearchMetadata(BaseModel):
    asset_id: str
    asset_name: Optional[str]
    prompt: str
    total_pages_analyzed: int
    total_pages_in_asset: int
    total_documents: Optional[int]
    research_depth: Literal["quick", "standard", "comprehensive"]
    processing_time_ms: int
    agent_version: str = "1.0.0"
    agents_used: List[str]
    tools_invoked: List[Dict[str, Any]]
```

#### SourceCitation
```python
class SourceCitation(BaseModel):
    page_id: str  # Required: Unique identifier of the source page
    document_id: Optional[str]
    document_name: Optional[str]
    page_index: Optional[int]
    excerpt: Optional[str]  # Relevant text snippet
    confidence: Literal["high", "medium", "low"] = "medium"
```

#### WebCitation
```python
class WebCitation(BaseModel):
    url: str
    title: Optional[str]
    accessed_at: datetime
    archived_url: Optional[str]  # Wayback Machine URL
    source_type: Literal["faa", "easa", "oem", "regulatory", "other"] = "other"
```

#### CitedFact (Generic)
```python
class CitedFact(BaseModel, Generic[T]):
    value: Any  # The actual fact/value
    source_pages: List[SourceCitation]
    web_sources: Optional[List[WebCitation]]
    validation_status: Literal["verified", "unverified", "contradicted"] = "unverified"
    confidence: Literal["high", "medium", "low"] = "medium"
    notes: Optional[str]
```

#### ComponentInfo
```python
class ComponentInfo(BaseModel):
    part_number: Optional[str]
    serial_number: Optional[str]
    description: Optional[str]
    component_type: Optional[str]  # LLP, rotable, module, etc.
    position: Optional[str]
    
    # Life tracking
    cycles_since_new: Optional[int]
    hours_since_new: Optional[float]
    cycles_since_overhaul: Optional[int]
    hours_since_overhaul: Optional[float]
    cycle_limit: Optional[int]
    cycles_remaining: Optional[int]
    
    # Status
    condition: Optional[str]
    last_inspection_date: Optional[str]
    
    # Citations
    source_pages: List[SourceCitation]
    confidence: Literal["high", "medium", "low"] = "medium"
```

#### MaintenanceEvent
```python
class MaintenanceEvent(BaseModel):
    event_type: Optional[str]  # inspection, overhaul, repair, etc.
    date: Optional[str]
    description: Optional[str]
    work_order: Optional[str]
    facility: Optional[str]
    
    # Component info
    component_serial: Optional[str]
    hours_at_event: Optional[float]
    cycles_at_event: Optional[int]
    
    # Citations
    source_pages: List[SourceCitation]
    confidence: Literal["high", "medium", "low"] = "medium"
```

#### ComplianceItem
```python
class ComplianceItem(BaseModel):
    reference: str  # Required: AD/SB/requirement reference number
    title: Optional[str]
    issuing_authority: Optional[str]  # FAA, EASA, OEM, etc.
    status: Literal["compliant", "non_compliant", "not_applicable", "unknown"] = "unknown"
    compliance_date: Optional[str]
    compliance_method: Optional[str]
    next_due: Optional[str]
    notes: Optional[str]
    
    # Web validation
    faa_validation: Optional[WebCitation]
    easa_validation: Optional[WebCitation]
    
    # Citations
    source_pages: List[SourceCitation]
    confidence: Literal["high", "medium", "low"] = "medium"
```

#### GapInfo
```python
class GapInfo(BaseModel):
    gap_type: str  # Required: missing_logbook, incomplete_records, etc.
    description: str  # Required
    severity: Literal["critical", "major", "minor"] = "major"
    affected_components: Optional[List[str]]
    affected_period: Optional[str]
    recommendation: Optional[str]
    source_pages: List[SourceCitation]
```

#### ContradictionInfo
```python
class ContradictionInfo(BaseModel):
    description: str  # Required
    sources_a: List[SourceCitation]  # First set of sources
    sources_b: List[SourceCitation]  # Contradicting sources
    resolution: Optional[str]
    preferred_value: Optional[Any]
```

#### ConfidenceSummary
```python
class ConfidenceSummary(BaseModel):
    high_confidence_facts: int = 0
    medium_confidence_facts: int = 0
    low_confidence_facts: int = 0
    web_validated_facts: int = 0
    contradicted_facts: int = 0
```

## 3. Example Output Structure

### 3.1 Actual Output Format

The agent outputs a JSON structure that wraps the `AssetResearchOutput`:

```json
{
  "research_metadata": {
    "asset_id": "f9ff6e18-4725-4c3e-8f96-6fdf79b71cdb",
    "asset_name": "Test Asset f9ff6e18-4725-4c3e-8f96-6fdf79b71cdb",
    "prompt": "Produce a comprehensive analysis of this asset dossier",
    "total_pages_analyzed": 0,
    "total_pages_in_asset": 0,
    "research_depth": "comprehensive",
    "processing_time_ms": 279537,
    "agent_version": "1.0.0",
    "trace_id": "trace_c17d4ef5dccb4e32",
    "database_connected": false,
    "agents_used": []
  },
  "result": "{...JSON string of AssetResearchOutput...}",
  "canvas_stats": {
    "total_entries": 3,
    "total_tokens": 302,
    "average_tokens_per_entry": 100,
    "unique_tags": 8,
    "top_tags": {
      "gap_analysis": 2,
      "metadata": 1
    },
    "entries_by_confidence": {
      "high": 1,
      "medium": 0,
      "low": 2
    }
  }
}
```

### 3.2 Parsed Result Structure

The `result` field contains a JSON string that should be parsed to get the actual `AssetResearchOutput`:

```json
{
  "asset_id": "f9ff6e18-4725-4c3e-8f96-6fdf79b71cdb",
  "asset_name": "Test Asset f9ff6e18-4725-4c3e-8f96-6fdf79b71cdb",
  "document_types": ["Unknown"],
  "total_documents": 0,
  "total_pages": 0,
  "extracted_facts": [],
  "findings": [
    {
      "title": "Dossier Structure & Content Availability Report",
      "summary": "...",
      "content": "...",
      "confidence": "low",
      "validation_status": "unverified",
      "source_pages": []
    }
  ],
  "regulatory_validation_results": [],
  "identified_gaps": [
    {
      "description": "...",
      "confidence": "high"
    }
  ],
  "contradictions": [],
  "overall_confidence": "low",
  "notes": "..."
}
```

## 4. Key Requirements Summary

### 4.1 Citation Requirements
- **Every fact MUST include**: `source_pages` (list of page IDs)
- **Confidence levels**: "high", "medium", or "low"
- **Validation status**: "verified", "unverified", or "contradicted"

### 4.2 Output Format Requirements
1. Output must be valid JSON
2. Must include legacy-compatible root schema fields
3. All findings must include source citations
4. Regulatory items must be validated against FAA/EASA databases
5. Gaps and contradictions must be explicitly reported
6. Large dossiers must produce richer coverage (not minimal findings-only output)

### 4.3 Template Variables Available
- `{{asset_id}}`: The asset UUID
- `{{asset_name}}`: Name of the asset
- `{{total_pages}}`: Total pages in the dossier
- `{{total_documents}}`: Total documents in the dossier
- `{{document_types}}`: List of document types
- `{{task}}`: The research request/prompt
- `{{tools}}`: Available tools list
- `{{managed_agents}}`: Available managed agents list

## 5. Files Reference

- **Prompts**: `src/agent/asset_research_prompts/*.yaml`
- **Schema**: `src/schemas/asset_research_output.py`
- **Example Runner**: `examples/run_asset_research.py`
- **Output Examples**: `workdir/asset_research_*/output.json`

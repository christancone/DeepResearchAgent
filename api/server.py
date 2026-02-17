"""
Asset Research Agent API Server

Production-ready FastAPI service that exposes the asset research agent.
Frontend only needs to send asset_id.

Usage:
    uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path
import sys

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Default prompt and depth - configurable per deployment
DEFAULT_PROMPT = "Produce a comprehensive analysis of this asset dossier"
DEFAULT_DEPTH = "standard"


class ResearchRequest(BaseModel):
    """Request body - asset_id is the only required field from frontend."""

    asset_id: str = Field(..., description="Asset ID to analyze")
    prompt: str = Field(
        default=DEFAULT_PROMPT,
        description="Analysis prompt (optional, has default)",
    )
    depth: str = Field(
        default=DEFAULT_DEPTH,
        description="Research depth: quick | standard | comprehensive",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: no heavy init at startup; agent is created per request."""
    yield
    # Shutdown cleanup if needed


app = FastAPI(
    title="Asset Research Agent API",
    description="Analyzes aircraft maintenance dossiers. Send asset_id to run research.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check for load balancers and k8s probes."""
    return {"status": "ok"}


@app.post("/api/research")
async def run_research(req: ResearchRequest):
    """
    Run asset dossier research.

    Request body:
        { "asset_id": "d9d68f1c-85d5-4996-9b7f-6187134fd10c" }

    Optional overrides:
        { "asset_id": "...", "prompt": "...", "depth": "comprehensive" }

    Returns the full research output JSON (can take several minutes).
    """
    if req.depth not in ("quick", "standard", "comprehensive"):
        raise HTTPException(
            status_code=400,
            detail="depth must be one of: quick, standard, comprehensive",
        )

    try:
        from examples.run_asset_research import run_asset_research_programmatic

        output = await run_asset_research_programmatic(
            asset_id=req.asset_id,
            prompt=req.prompt,
            depth=req.depth,
        )
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

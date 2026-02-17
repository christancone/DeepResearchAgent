from src.tools.tools import Tool, ToolResult, AsyncTool, make_tool_instance
from src.tools.deep_analyzer import DeepAnalyzerTool
from src.tools.deep_researcher import DeepResearcherTool
from src.tools.python_interpreter import PythonInterpreterTool
from src.tools.planning import PlanningTool
from src.tools.file_reader import FileReaderTool
from src.tools.canvas_tool import CanvasTool, create_canvas_tool
from src.tools.asset_dossier import (
    SupabaseAsyncClient,
    AssetMetadataTool,
    AssetRAGSearchTool,
    AssetPageReadTool,
    DocumentTreeTool,
    AssetBatchSummaryTool,
)

# Lazy imports for optional tools (to avoid dependency issues)
AutoBrowserUseTool = None
ImageGeneratorTool = None
VideoGeneratorTool = None
OAIDeepResearchTool = None

def _lazy_import_browser():
    """Lazy import browser tool to avoid requiring browser-use package."""
    global AutoBrowserUseTool
    if AutoBrowserUseTool is None:
        try:
            from src.tools.auto_browser import AutoBrowserUseTool as _AutoBrowserUseTool
            AutoBrowserUseTool = _AutoBrowserUseTool
        except ImportError:
            pass
    return AutoBrowserUseTool

def _lazy_import_image_generator():
    """Lazy import image generator tool."""
    global ImageGeneratorTool
    if ImageGeneratorTool is None:
        try:
            from src.tools.image_generator import ImageGeneratorTool as _ImageGeneratorTool
            ImageGeneratorTool = _ImageGeneratorTool
        except ImportError:
            pass
    return ImageGeneratorTool

def _lazy_import_video_generator():
    """Lazy import video generator tool."""
    global VideoGeneratorTool
    if VideoGeneratorTool is None:
        try:
            from src.tools.video_generator import VideoGeneratorTool as _VideoGeneratorTool
            VideoGeneratorTool = _VideoGeneratorTool
        except ImportError:
            pass
    return VideoGeneratorTool

def _lazy_import_oai_deep_research():
    """Lazy import OAI deep research tool."""
    global OAIDeepResearchTool
    if OAIDeepResearchTool is None:
        try:
            from src.tools.oai_deep_research import OAIDeepResearchTool as _OAIDeepResearchTool
            OAIDeepResearchTool = _OAIDeepResearchTool
        except ImportError:
            pass
    return OAIDeepResearchTool


__all__ = [
    "Tool",
    "ToolResult",
    "AsyncTool",
    "DeepAnalyzerTool",
    "DeepResearcherTool",
    "PythonInterpreterTool",
    "AutoBrowserUseTool",
    "PlanningTool",
    "ImageGeneratorTool",
    "VideoGeneratorTool",
    "make_tool_instance",
    "FileReaderTool",
    "OAIDeepResearchTool",
    "CanvasTool",
    "create_canvas_tool",
    # Asset dossier tools
    "SupabaseAsyncClient",
    "AssetMetadataTool",
    "AssetRAGSearchTool",
    "AssetPageReadTool",
    "DocumentTreeTool",
    "AssetBatchSummaryTool",
    # Lazy import helpers
    "_lazy_import_browser",
    "_lazy_import_image_generator",
    "_lazy_import_video_generator",
    "_lazy_import_oai_deep_research",
]
import os
import sys
import inspect
from typing import get_origin
from collections.abc import Callable as CollectionsCallable

from fastmcp import FastMCP
from dotenv import load_dotenv
import asyncio
from pathlib import Path

root = str(Path(__file__).resolve().parents[2])
sys.path.append(root)

from src.utils import assemble_project_path
from src.logger import logger

# Load environment variables
load_dotenv(override=True)

# Initialize FastMCP
mcp = FastMCP("LocalMCP")
_mcp_tools_namespace = {}

def _check_script_requires(script_info: dict) -> list[str]:
    """Return list of missing module names from metadata.requires. Empty if all present."""
    metadata = script_info.get("metadata") or {}
    requires = str(metadata.get("requires", "") or "").strip()
    if requires.lower() in {"none", "null", "n/a", "na", "# no external libraries needed"}:
        return []
    if not requires:
        return []
    missing = []
    none_markers = {"none", "null", "n/a", "na", "(none)", "no external libraries needed"}
    for part in (s.strip() for s in requires.split(",")):
        if not part:
            continue
        # Ignore pseudo requirement comments from generated tool metadata.
        if part.startswith("#"):
            continue
        normalized_part = part.strip().strip(".;").lower()
        if normalized_part in none_markers:
            continue
        # Map common display names to import names
        mod = part.split()[0] if part else part
        if mod == "cv2":
            mod = "cv2"
        elif mod == "CoolProp.CoolProp":
            mod = "CoolProp"
        elif "." in mod:
            mod = mod.split(".", 1)[0]
        try:
            __import__(mod)
        except ImportError:
            missing.append(part)
    return missing


def _sanitize_script_content(script_content: str) -> str:
    """Extract a single executable Python block; strip trailing markdown/artifacts."""
    if not script_content or not script_content.strip():
        return ""
    text = script_content.strip()
    if text.startswith("```python"):
        text = text[9:].lstrip("\n")
    elif text.startswith("```"):
        text = text[3:].lstrip("\n")
    # Keep only the first code block: up to the first closing ```
    if "```" in text:
        text = text.split("```")[0]
    # Remove common accidental trailing markers from malformed registry payloads.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip()


def _has_callable_annotations(func) -> bool:
    """Return True when function annotations include callable-typed fields."""
    try:
        signature = inspect.signature(func)
    except Exception:
        return False

    annotations = [p.annotation for p in signature.parameters.values()]
    annotations.append(signature.return_annotation)
    for ann in annotations:
        if ann is inspect.Signature.empty:
            continue
        ann_str = str(ann)
        if "Callable" in ann_str:
            return True
        origin = get_origin(ann)
        if origin in (CollectionsCallable,):
            return True
    return False


async def register_tool_from_script(script_info) -> bool:
    """
    Register a tool from a script content. Returns True if registered, False if skipped/failed.
    """
    name = script_info.get("name", "UnnamedTool")
    description = script_info.get("description", "No description provided.")
    raw_content = script_info.get("script_content", "")

    missing_deps = _check_script_requires(script_info)
    if missing_deps:
        logger.warning(
            f"Tool '{name}' requires missing dependencies: {', '.join(missing_deps)}. Skipping registration."
        )
        return False

    script_content = _sanitize_script_content(raw_content)
    if not script_content:
        logger.warning(f"Tool '{name}' has no executable script content after sanitization. Skipping.")
        return False

    try:
        exec(script_content, _mcp_tools_namespace)
    except SyntaxError as e:
        logger.warning(f"Tool '{name}' script has syntax error (line {e.lineno}): {e}. Skipping registration.")
        return False
    except Exception as e:
        logger.warning(f"Error executing script for tool '{name}': {e}. Skipping registration.")
        return False

    tool_function = _mcp_tools_namespace.get(name)
    if tool_function is None:
        logger.warning(f"Tool function '{name}' not found in script namespace. Skipping registration.")
        return False

    if _has_callable_annotations(tool_function):
        logger.warning(
            f"Tool '{name}' uses callable annotations not representable in JSON schema. "
            "Skipping registration to avoid MCP schema generation failure."
        )
        return False

    try:
        mcp.tool(tool_function, name=name, description=description)
        logger.info(f"Tool '{name}' registered successfully.")
        return True
    except Exception as e:
        logger.warning(f"Failed to register tool '{name}': {e}. Skipping registration.")
        return False

async def register_tools(script_info_path):
    """
    Register tools from a JSON file containing script information.
    Continues on per-tool failure and logs a startup summary.
    """
    import json

    try:
        with open(script_info_path, "r", encoding="utf-8") as f:
            script_info_list = json.load(f)
    except FileNotFoundError:
        logger.info(f"Script info file not found: {script_info_path}")
        return
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from script info file: {script_info_path}: {e}")
        return

    ok = 0
    failed = 0
    failed_names = []
    for script_info in script_info_list:
        if await register_tool_from_script(script_info):
            ok += 1
        else:
            failed += 1
            failed_names.append(script_info.get("name", "unknown"))

    if failed:
        logger.info(
            f"MCP tool registration: {ok} succeeded, {failed} skipped "
            f"(missing deps or script errors): {', '.join(failed_names[:20])}"
        )
    else:
        logger.info("All tools from registry registered successfully.")

    mcp_tools = await mcp.get_tools()
    logger.info(f"Registered tools: {', '.join(tool for tool in mcp_tools) or 'none'}")

if __name__ == "__main__":
    script_info_path = assemble_project_path(os.path.join("src", "mcp", "local", "mcp_tools_registry.json"))
    asyncio.run(register_tools(script_info_path))
    mcp.run()
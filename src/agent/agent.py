from typing import List, Dict, Any

from src.registry import AGENT, TOOL
from src.models import model_manager
from src.tools import make_tool_instance
from src.mcp.mcpadapt import MCPAdapt, AsyncToolAdapter
from src.logger import logger

AUTHORIZED_IMPORTS = [
    "pandas",
    "requests",
    "numpy"
]

async def build_agent(config,
                      agent_config,
                      default_tools = None,
                      default_mcp_tools=None,
                      default_managed_agents=None):
    """
    Build an agent based on the provided configuration.

    Args:
        config (dict): Configuration dictionary containing tool and model settings.
        agent_config (dict): Configuration dictionary containing agent settings.

    Returns:
        Agent instance.
    """
    tools = []
    mcp_tools = []
    managed_agent_tools = []

    # Build Tools
    if default_tools is None:
        logger.info("| No default tools provided. Skipping tool initialization.")
    else:
        used_tools = agent_config.get("tools", [])
        for tool_name in used_tools:
            if tool_name not in default_tools:
                logger.warning(f"Tool '{tool_name}' is not registered. Skipping.")
            config_name = f"{tool_name}_config"  # e.g., "python_interpreter_tool" -> "python_interpreter_tool_config"
            if config_name in config:
                # If the tool has a specific config, use it
                tool_config = config[config_name]
            else:
                # Otherwise, use the default tool instance
                tool_config = dict(type=tool_name)
            tool = TOOL.build(tool_config)
            tools.append(tool)
        logger.info(f"| Tools initialized: {', '.join([tool.name for tool in tools])}")

    # Build MCP Tools
    if default_mcp_tools is None:
        logger.info("| No MCP tools provided. Skipping MCP tool initialization.")
    else:
        used_mcp_tools = agent_config.get("mcp_tools", [])
        for tools_name in used_mcp_tools:
            if tools_name not in default_mcp_tools:
                logger.warning(f"MCP tool '{tools_name}' is not available. Skipping.")
            else:
                mcp_tool = default_mcp_tools[tools_name]
                mcp_tools.append(mcp_tool)
        logger.info(f"| MCP Tools initialized: {', '.join([tool.name for tool in mcp_tools])}")

    # Load Managed Agents
    if default_managed_agents is None:
        logger.info("| No managed agents provided. Skipping managed agent initialization.")
    else:
        used_managed_agents = agent_config.get("managed_agents", [])
        if isinstance(default_managed_agents, dict):
            # Dual-resolution strategy: allow config managed_agents to reference either
            # registry keys (e.g. deep_researcher_agent) or configured names
            # (e.g. regulatory_researcher_agent).
            by_key = default_managed_agents
            by_name = {agent.name: agent for agent in default_managed_agents.values()}
            seen_names = set()
            for requested in used_managed_agents:
                managed_agent = by_key.get(requested) or by_name.get(requested)
                if managed_agent is None:
                    logger.warning(
                        f"Managed agent '{requested}' could not be resolved. "
                        f"Available keys: {', '.join(sorted(by_key.keys()))}. "
                        f"Available names: {', '.join(sorted(by_name.keys()))}."
                    )
                    continue
                if managed_agent.name in seen_names:
                    continue
                seen_names.add(managed_agent.name)
                managed_agent_tools.append(make_tool_instance(managed_agent))
        else:
            for managed_agent in default_managed_agents:
                if managed_agent.name not in used_managed_agents:
                    logger.warning(f"Managed agent '{managed_agent.name}' is not registered. Skipping.")
                else:
                    managed_agent_tool = make_tool_instance(managed_agent)
                    managed_agent_tools.append(managed_agent_tool)
        logger.info(f"| Managed agents initialized: {', '.join([agent.name for agent in managed_agent_tools])}")

    # Load Model
    model = model_manager.registed_models[agent_config["model_id"]]

    # Build Agent
    combined_tools = tools + mcp_tools + managed_agent_tools
    agent_config = dict(
        type=agent_config.type,
        config=agent_config,
        model=model,
        tools=combined_tools,
        max_steps=agent_config.max_steps,
        name=agent_config.name,
        description=agent_config.description,
        provide_run_summary=agent_config.provide_run_summary
    )
    agent = AGENT.build(agent_config)

    return agent


async def create_agent(config):

    # Load MCP tools
    mcpadapt = MCPAdapt(config.mcp_tools_config, AsyncToolAdapter())
    mcpadapt_tools = await mcpadapt.tools()
    
    if config.use_hierarchical_agent:

        logger.info("| Creating a hierarchical agent.")
        agent_config = config.agent_config

        managed_agents: dict[str, Any] = {}
        used_managed_agents = agent_config.get("managed_agents", [])
        unresolved = []
        resolved_pairs = []
        # Index configured agent configs by key and configured name for alias resolution.
        config_agent_key_to_cfg = {}
        config_agent_name_to_key = {}
        for key, value in config.items():
            if isinstance(key, str) and key.endswith("_agent_config") and isinstance(value, dict):
                agent_key = key[: -len("_config")]
                config_agent_key_to_cfg[agent_key] = value
                configured_name = value.get("name")
                if isinstance(configured_name, str) and configured_name:
                    config_agent_name_to_key[configured_name] = agent_key

        for requested in used_managed_agents:
            resolved_agent_key = requested
            if resolved_agent_key not in AGENT:
                alias_key = config_agent_name_to_key.get(requested)
                if alias_key and alias_key in AGENT:
                    resolved_agent_key = alias_key
                else:
                    unresolved.append(requested)
                    continue

            managed_agent_config_name = f"{resolved_agent_key}_config"
            managed_agent_config = config.get(managed_agent_config_name, None)
            if managed_agent_config is None:
                unresolved.append(requested)
                logger.warning(
                    f"Managed agent '{requested}' resolved to '{resolved_agent_key}' but config "
                    f"'{managed_agent_config_name}' was not found."
                )
                continue
            managed_agent = await build_agent(
                config,
                managed_agent_config,
                default_tools=TOOL,
                default_mcp_tools=mcpadapt_tools,
            )
            managed_agents[resolved_agent_key] = managed_agent
            resolved_pairs.append(f"{requested}->{resolved_agent_key}({managed_agent.name})")

        logger.info(f"| Managed agent resolution: {', '.join(resolved_pairs) or 'none'}")
        resolved_names = [a.name for a in managed_agents.values()]
        logger.info(f"| Managed agents initialized: {', '.join(resolved_names) or 'none'}")
        if unresolved:
            logger.warning(
                "| Unresolved managed_agents: "
                f"{', '.join(unresolved)}. "
                "Use AGENT registry keys or configured agent names."
            )

        # Build the main agent
        agent = await build_agent(
            config,
            agent_config,
            default_tools=TOOL,
            default_mcp_tools=mcpadapt_tools,
            default_managed_agents=managed_agents
        )

        return agent
    
    else:

        logger.info("| Creating a single agent.")

        agent_config = config.agent_config

        # Build agent
        agent = await build_agent(config,
            agent_config,
            default_tools=TOOL,
            default_mcp_tools=mcpadapt_tools
        )

        return agent
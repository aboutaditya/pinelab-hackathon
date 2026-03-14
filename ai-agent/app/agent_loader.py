"""
YAML Agent Loader.

Reads agent YAML definitions from the agents/ directory and constructs
structured agent configs used by the orchestrator at startup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """MCP server connection details from agent YAML."""

    name: str
    url: str


@dataclass
class MemoryConfig:
    """Memory / state management configuration."""

    provider: str = "redis"
    strategy: str = "message_id_chain"
    ttl_seconds: int = 86400


@dataclass
class AgentConfig:
    """Parsed agent configuration from YAML."""

    id: str
    route: str
    model: str
    system_prompt: str
    api_key_env: str = ""
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


def load_agent_configs(config_dir: str) -> dict[str, AgentConfig]:
    """
    Load all agent YAML configs from the given directory.

    Returns:
        dict mapping agent_id -> AgentConfig
    """
    config_path = Path(config_dir)
    if not config_path.exists():
        logger.warning("Agent config directory not found: %s", config_dir)
        return {}

    agents: dict[str, AgentConfig] = {}

    for yml_file in config_path.glob("*.yml"):
        try:
            with open(yml_file) as f:
                raw = yaml.safe_load(f)

            agent_raw = raw.get("agent", raw)

            mcp_servers = [
                MCPServerConfig(name=s["name"], url=s["url"])
                for s in agent_raw.get("mcp_servers", [])
            ]

            memory_raw = agent_raw.get("memory", {})
            memory = MemoryConfig(
                provider=memory_raw.get("provider", "redis"),
                strategy=memory_raw.get("strategy", "message_id_chain"),
                ttl_seconds=memory_raw.get("ttl_seconds", 86400),
            )

            config = AgentConfig(
                id=agent_raw["id"],
                route=agent_raw.get("route", ""),
                model=agent_raw.get("model", "gemini-3.1-pro"),
                api_key_env=agent_raw.get("api_key_env", ""),
                system_prompt=agent_raw.get("system_prompt", ""),
                mcp_servers=mcp_servers,
                tools=agent_raw.get("tools", []),
                memory=memory,
            )

            agents[config.id] = config
            logger.info("Loaded agent: %s (model=%s, tools=%d)", config.id, config.model, len(config.tools))

        except Exception as e:
            logger.error("Failed to load agent config %s: %s", yml_file, e)

    return agents

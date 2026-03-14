"""
Configuration management for the orchestrator.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    # Redis
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # MCP Bridge
    mcp_bridge_url: str = os.environ.get("MCP_BRIDGE_URL", "http://localhost:8001")

    # AWS (Bedrock)
    aws_region: str = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    # Agent config
    agent_config_dir: str = os.environ.get("AGENT_CONFIG_DIR", "agents")

    # State TTL
    state_ttl_seconds: int = int(os.environ.get("STATE_TTL_SECONDS", "86400"))


settings = Settings()

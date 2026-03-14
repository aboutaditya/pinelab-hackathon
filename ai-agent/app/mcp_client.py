"""
MCP Client — communicates with the MCP Bridge to list and execute tools.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for the MCP Bridge service."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.mcp_bridge_url).rstrip("/")

    async def is_connected(self) -> bool:
        """Check if MCP Bridge is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch available tools from the MCP Bridge."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/mcp/tools")
            resp.raise_for_status()
            return resp.json()

    async def get_openai_tool_schemas(self) -> list[dict[str, Any]]:
        """Fetch tools in OpenAI function-calling format."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/mcp/tools/openai-schema")
            resp.raise_for_status()
            return resp.json()

    async def execute_tool(
        self, tool_name: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute a tool via the MCP Bridge.

        Args:
            tool_name: Name of the tool to call
            parameters: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        logger.info("Executing MCP tool: %s(%s)", tool_name, parameters)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/mcp/execute",
                json={
                    "tool_name": tool_name,
                    "parameters": parameters,
                },
            )
            resp.raise_for_status()
            result = resp.json()

        logger.info(
            "Tool %s result: success=%s",
            tool_name,
            result.get("success", "unknown"),
        )
        return result

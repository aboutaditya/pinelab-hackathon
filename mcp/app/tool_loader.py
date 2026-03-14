"""
YAML-based MCP Tool Loader.

Reads mcp_config.yml and converts each tool definition into a
structured schema that the orchestrator can use to build LLM tool
definitions and execute proxied calls.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ToolParameter:
    """A single parameter for an MCP tool."""

    name: str
    type: str
    description: str
    required: bool = False
    location: str = "query"  # path | query | body


@dataclass
class MCPTool:
    """Parsed MCP tool from YAML config."""

    name: str
    description: str
    endpoint: str
    method: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible function calling schema."""
        properties = {}
        required = []

        for p in self.parameters:
            properties[p.name] = {
                "type": p.type if p.type != "number" else "number",
                "description": p.description,
            }
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def build_url(self, base_url: str, params: dict[str, Any]) -> str:
        """Build the full URL with path parameters substituted."""
        url = f"{base_url}{self.endpoint}"
        for p in self.parameters:
            if p.location == "path" and p.name in params:
                url = url.replace(f"{{{p.name}}}", str(params[p.name]))
        return url

    def extract_query_params(self, params: dict[str, Any]) -> dict[str, str]:
        """Extract query string parameters."""
        query_names = {p.name for p in self.parameters if p.location == "query"}
        return {k: str(v) for k, v in params.items() if k in query_names and v is not None}

    def extract_body_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Extract body (JSON) parameters."""
        body_names = {p.name for p in self.parameters if p.location == "body"}
        return {k: v for k, v in params.items() if k in body_names and v is not None}


def load_tools(config_path: str | None = None) -> dict[str, MCPTool]:
    """
    Load MCP tools from a YAML config file.

    Returns:
        dict mapping tool name -> MCPTool
    """
    if config_path is None:
        config_path = os.environ.get(
            "MCP_CONFIG_PATH",
            str(Path(__file__).parent.parent / "mcp_config.yml"),
        )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    tools: dict[str, MCPTool] = {}

    for tool_def in config.get("tools", []):
        params = [
            ToolParameter(
                name=p["name"],
                type=p.get("type", "string"),
                description=p.get("description", ""),
                required=p.get("required", False),
                location=p.get("location", "query"),
            )
            for p in tool_def.get("parameters", [])
        ]

        tool = MCPTool(
            name=tool_def["name"],
            description=tool_def["description"],
            endpoint=tool_def["endpoint"],
            method=tool_def.get("method", "GET").upper(),
            parameters=params,
        )
        tools[tool.name] = tool

    return tools

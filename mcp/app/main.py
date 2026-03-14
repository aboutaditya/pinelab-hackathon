"""
MCP Bridge Service — FastAPI application.

This service:
1. Loads MCP tool definitions from mcp_config.yml
2. Exposes an MCP-compatible endpoint for tool listing and execution
3. Proxies tool calls to the Django backend
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .proxy import BackendProxy
from .tool_loader import load_tools

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App Init ──────────────────────────────────────────────────────
app = FastAPI(
    title="Pine Labs MCP Bridge",
    description="Model Context Protocol bridge — translates YAML tool definitions to executable actions",
    version="1.0.0",
)

# Load tools from YAML at startup
TOOLS = load_tools()
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:8002")
proxy = BackendProxy(base_url=BACKEND_BASE_URL)

logger.info("Loaded %d MCP tools: %s", len(TOOLS), list(TOOLS.keys()))


# ── Schemas ───────────────────────────────────────────────────────


class ToolCallRequest(BaseModel):
    """Request to execute an MCP tool."""

    tool_name: str
    parameters: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    """Response from an MCP tool execution."""

    tool_name: str
    success: bool
    result: Any


class ToolSchema(BaseModel):
    """Schema describing an available MCP tool."""

    name: str
    description: str
    method: str
    parameters: list[dict[str, Any]]


# ── Endpoints ─────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mcp", "tools_loaded": len(TOOLS)}


@app.get("/mcp/tools", response_model=list[ToolSchema])
async def list_tools():
    """
    List all available MCP tools with their schemas.
    Used by the orchestrator to build LLM tool definitions.
    """
    result = []
    for tool in TOOLS.values():
        result.append(
            ToolSchema(
                name=tool.name,
                description=tool.description,
                method=tool.method,
                parameters=[
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                        "location": p.location,
                    }
                    for p in tool.parameters
                ],
            )
        )
    return result


@app.get("/mcp/tools/openai-schema")
async def list_tools_openai_schema():
    """
    Return tools in OpenAI function-calling schema format.
    Used directly by the orchestrator for Gemini/OpenAI tool definitions.
    """
    return [tool.to_openai_schema() for tool in TOOLS.values()]


@app.post("/mcp/execute", response_model=ToolCallResponse)
async def execute_tool(request: ToolCallRequest):
    """
    Execute an MCP tool by proxying the request to the Django backend.

    The orchestrator calls this endpoint when the LLM selects a tool.
    """
    tool = TOOLS.get(request.tool_name)
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{request.tool_name}' not found. Available: {list(TOOLS.keys())}",
        )

    logger.info("Executing tool: %s with params: %s", request.tool_name, request.parameters)

    result = await proxy.execute_tool(tool, request.parameters)

    is_error = isinstance(result, dict) and result.get("error") is True
    return ToolCallResponse(
        tool_name=request.tool_name,
        success=not is_error,
        result=result,
    )


@app.post("/mcp")
async def mcp_endpoint(request: ToolCallRequest):
    """
    MCP-compatible endpoint (matches the agent YAML config URL).
    Alias for /mcp/execute.
    """
    return await execute_tool(request)

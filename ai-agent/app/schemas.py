"""
Pydantic schemas for the orchestrator API.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat request from the user."""

    message: str = Field(..., description="User's message text")
    parent_id: Optional[str] = Field(
        None,
        description="ID of the parent message for conversation threading. "
        "null for the first message in a conversation.",
    )
    phone_number: Optional[str] = Field(
        None,
        description="Optional phone number provided as context",
    )


class ChatResponse(BaseModel):
    """Response from the orchestrator."""

    message_id: str = Field(..., description="Unique ID for this response message")
    parent_id: Optional[str] = Field(
        None, description="ID of the parent message"
    )
    role: str = Field("assistant", description="Message role")
    content: str = Field(..., description="Response content")
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool calls made during this turn",
    )
    agent_id: str = Field(..., description="Agent that handled the request")


class AgentInfo(BaseModel):
    """Information about a registered agent."""

    id: str
    model: str
    tools: list[str]
    memory_provider: str
    memory_strategy: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    agents_loaded: int
    redis_connected: bool
    mcp_bridge_connected: bool

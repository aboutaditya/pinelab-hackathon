"""
LangGraph-based agent execution graph.

Implements a ReAct-style agent loop:
  1. LLM decides to call a tool or respond
  2. If tool call → execute via MCP Bridge → feed result back
  3. If response → return to user
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_aws import ChatBedrockConverse
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from .agent_loader import AgentConfig
from .config import settings
from .mcp_client import MCPClient

logger = logging.getLogger(__name__)


# ── State Definition ─────────────────────────────────────────────


class AgentState(TypedDict):
    """State passed through the LangGraph nodes."""

    messages: list[BaseMessage]
    tool_schemas: list[dict[str, Any]]
    agent_config: dict[str, Any]
    tool_calls_made: list[dict[str, Any]]
    final_response: str
    iteration: int
    max_iterations: int
    authenticated_phone_number: Optional[str]


# ── Node Functions ───────────────────────────────────────────────


async def call_llm(state: AgentState) -> AgentState:
    """
    Call the LLM with conversation history and tool definitions.
    The LLM will either respond directly or request tool calls.
    """
    import os

    agent_cfg = state["agent_config"]
    model_name = agent_cfg.get("model", "anthropic.claude-3-haiku-20240307-v1:0")

    llm = ChatBedrockConverse(
        model_id=model_name,
        temperature=0.1,
    )

    # Bind tools if available
    tool_schemas = state.get("tool_schemas", [])
    if tool_schemas:
        # Convert to langchain tool format
        tools = []
        for schema in tool_schemas:
            func_def = schema.get("function", schema)
            tools.append({
                "type": "function",
                "function": {
                    "name": func_def["name"],
                    "description": func_def["description"],
                    "parameters": func_def.get("parameters", {}),
                },
            })
        llm = llm.bind_tools(tools)

    messages = state["messages"]
    logger.info(
        "Calling LLM (%s) with %d messages, iteration %d",
        model_name,
        len(messages),
        state["iteration"],
    )

    response = await llm.ainvoke(messages)

    # Add AI response to messages
    updated_messages = list(messages) + [response]

    return {
        **state,
        "messages": updated_messages,
        "iteration": state["iteration"] + 1,
    }


async def execute_tools(state: AgentState) -> AgentState:
    """
    Execute any tool calls from the LLM response via the MCP Bridge.
    """
    messages = state["messages"]
    last_message = messages[-1]
    tool_calls_made = list(state.get("tool_calls_made", []))

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state

    mcp = MCPClient()
    updated_messages = list(messages)

    authenticated_phone = state.get("authenticated_phone_number")
    tool_schemas = state.get("tool_schemas", [])

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = dict(tool_call.get("args", {}))
        tool_call_id = tool_call.get("id", tool_name)

        # Enforce: only allow data for the logged-in merchant
        if authenticated_phone:
            for schema in tool_schemas:
                func = schema.get("function", schema)
                if func.get("name") == tool_name:
                    params_schema = func.get("parameters") or {}
                    props = params_schema.get("properties") or {}
                    if "phone_number" in props:
                        tool_args["phone_number"] = authenticated_phone
                        logger.info("Scoped tool %s to authenticated phone", tool_name)
                    break

        logger.info("Executing tool: %s(%s)", tool_name, tool_args)

        try:
            result = await mcp.execute_tool(tool_name, tool_args)
            tool_result = result.get("result", result)
            result_str = json.dumps(tool_result, indent=2, default=str)

            tool_calls_made.append({
                "tool": tool_name,
                "args": tool_args,
                "result_preview": result_str[:500],
                "success": result.get("success", True),
            })

        except Exception as e:
            logger.error("Tool execution failed: %s — %s", tool_name, e)
            result_str = json.dumps({"error": str(e)})
            tool_calls_made.append({
                "tool": tool_name,
                "args": tool_args,
                "error": str(e),
                "success": False,
            })

        # Add tool result as a ToolMessage
        updated_messages.append(
            ToolMessage(
                content=result_str,
                tool_call_id=tool_call_id,
            )
        )

    return {
        **state,
        "messages": updated_messages,
        "tool_calls_made": tool_calls_made,
    }


def should_continue(state: AgentState) -> str:
    """
    Routing function: decide whether to continue tool calling or end.
    """
    messages = state["messages"]
    last_message = messages[-1]

    # If we've hit max iterations, stop
    if state["iteration"] >= state["max_iterations"]:
        logger.warning("Max iterations reached (%d)", state["max_iterations"])
        return "end"

    # If the last message is an AI message with tool calls, execute them
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "execute_tools"

    # Otherwise, the LLM has given a final response
    return "end"


def extract_response(state: AgentState) -> AgentState:
    """Extract the final text response from the last AI message."""
    messages = state["messages"]

    # Find the last AI message
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return {
                **state,
                "final_response": msg.content,
            }

    return {
        **state,
        "final_response": "I apologize, but I was unable to generate a response. Please try again.",
    }


# ── Graph Builder ────────────────────────────────────────────────


def build_agent_graph() -> StateGraph:
    """
    Build the LangGraph ReAct agent graph.

    Flow:
        call_llm → [should_continue] → execute_tools → call_llm → ...
                                      → end → extract_response
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("call_llm", call_llm)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("extract_response", extract_response)

    # Set entry point
    graph.set_entry_point("call_llm")

    # Add conditional edges from call_llm
    graph.add_conditional_edges(
        "call_llm",
        should_continue,
        {
            "execute_tools": "execute_tools",
            "end": "extract_response",
        },
    )

    # After tool execution, call LLM again
    graph.add_edge("execute_tools", "call_llm")

    # extract_response is the final node
    graph.add_edge("extract_response", END)

    return graph


async def run_agent(
    agent_config: AgentConfig,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    max_iterations: int = 10,
    authenticated_phone_number: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Run the agent graph for a single turn.

    Args:
        agent_config: The agent's YAML configuration
        user_message: The current user message
        conversation_history: Previous messages from Redis
        tool_schemas: Available MCP tools in OpenAI schema format
        max_iterations: Max tool-call loops
        authenticated_phone_number: Logged-in merchant phone; tool calls are scoped to this only.

    Returns:
        (response_text, tool_calls_made)
    """
    # Build message history
    messages: list[BaseMessage] = [
        SystemMessage(content=agent_config.system_prompt)
    ]

    # Add conversation history from Redis
    for msg in conversation_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    # Add current user message
    messages.append(HumanMessage(content=user_message))

    # Build and run the graph
    graph = build_agent_graph()
    compiled = graph.compile()

    initial_state: AgentState = {
        "messages": messages,
        "tool_schemas": tool_schemas,
        "agent_config": {
            "model": agent_config.model,
            "id": agent_config.id,
            "api_key_env": agent_config.api_key_env,
        },
        "tool_calls_made": [],
        "final_response": "",
        "iteration": 0,
        "max_iterations": max_iterations,
        "authenticated_phone_number": authenticated_phone_number,
    }

    # Execute the graph
    final_state = await compiled.ainvoke(initial_state)

    return (
        final_state.get("final_response", ""),
        final_state.get("tool_calls_made", []),
    )

"""
Pine Labs Orchestrator — FastAPI application.

The "Brain" that:
1. Loads agent YAML definitions at startup
2. Manages conversation state via Redis (message ID chain)
3. Routes chat requests through the LangGraph agent
4. Executes MCP tool calls via the bridge service
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agent_loader import AgentConfig, load_agent_configs
from .config import settings
from .graph import run_agent
from .mcp_client import MCPClient
from .schemas import AgentInfo, ChatRequest, ChatResponse, HealthResponse
from .state_manager import StateManager

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────────────
AGENT_REGISTRY: dict[str, AgentConfig] = {}
state_manager = StateManager()
mcp_client = MCPClient()


# ── Lifespan ──────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # ── Startup ──
    logger.info("🚀 Starting Pine Labs Orchestrator...")

    # 1. Load agent configs
    agents = load_agent_configs(settings.agent_config_dir)
    AGENT_REGISTRY.update(agents)
    logger.info("Loaded %d agents: %s", len(agents), list(agents.keys()))

    # 2. Connect to Redis
    try:
        await state_manager.connect()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error("⚠️ Redis connection failed: %s (will retry on requests)", e)

    # 3. Check MCP Bridge
    if await mcp_client.is_connected():
        logger.info("✅ MCP Bridge connected")
    else:
        logger.warning("⚠️ MCP Bridge not reachable (will retry on requests)")

    yield

    # ── Shutdown ──
    await state_manager.disconnect()
    logger.info("Orchestrator shut down.")


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Pine Labs Reconciliation Agent — Orchestrator",
    description="Multi-agent orchestrator for autonomous settlement reconciliation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check with status of all dependencies."""
    return HealthResponse(
        status="healthy",
        service="ai-agent",
        agents_loaded=len(AGENT_REGISTRY),
        redis_connected=await state_manager.is_connected(),
        mcp_bridge_connected=await mcp_client.is_connected(),
    )


@app.get("/api/v1/agents", response_model=list[AgentInfo])
async def list_agents():
    """List all registered agents."""
    return [
        AgentInfo(
            id=agent.id,
            model=agent.model,
            tools=agent.tools,
            memory_provider=agent.memory.provider,
            memory_strategy=agent.memory.strategy,
        )
        for agent in AGENT_REGISTRY.values()
    ]


@app.post("/chat/{agent_route:path}", response_model=ChatResponse)
async def chat(agent_route: str, request: ChatRequest):
    """
    Main chat endpoint (routed by agent route).

    Implements the Message ID flow:
    1. If parent_id is provided, load conversation context from Redis
    2. Run the agent graph with context + user message
    3. Store both user and assistant messages in Redis
    4. Return response with new message_id
    """
    # 1. Validate agent by route
    # Strip any leading/trailing slashes for safety
    clean_route = agent_route.strip("/")
    agent_config = next((a for a in AGENT_REGISTRY.values() if a.route == clean_route), None)
    
    if not agent_config:
        available_routes = [a.route for a in AGENT_REGISTRY.values() if a.route]
        raise HTTPException(
            status_code=404,
            detail=f"Agent with route '{clean_route}' not found. Available routes: {available_routes}",
        )

    # 2. Load conversation context from Redis
    conversation_history = []
    if request.parent_id:
        try:
            conversation_history = await state_manager.load_conversation_context(
                request.parent_id
            )
        except Exception as e:
            logger.error("Failed to load context for parent_id=%s: %s", request.parent_id, e)

    # 3. Store user message in Redis (do not inject phone/merchant id into visible prompt)
    user_message_content = request.message
    if request.phone_number:
        user_message_content = "[System Context: You are assisting the logged-in merchant. Do not mention or ask for phone number or merchant ID.]\n\n" + user_message_content

    try:
        user_msg_id = await state_manager.store_message(
            role="user",
            content=user_message_content,
            parent_id=request.parent_id,
            agent_id=agent_config.id,
        )
    except Exception as e:
        logger.error("Failed to store user message: %s", e)
        user_msg_id = None

    # 4. Fetch MCP tool schemas
    try:
        tool_schemas = await mcp_client.get_openai_tool_schemas()
    except Exception as e:
        logger.error("Failed to fetch tool schemas: %s", e)
        tool_schemas = []

    # 5. Run the agent graph
    try:
        response_text, tool_calls = await run_agent(
            agent_config=agent_config,
            user_message=user_message_content,
            conversation_history=conversation_history,
            tool_schemas=tool_schemas,
            authenticated_phone_number=request.phone_number,
        )
    except Exception as e:
        logger.error("Agent execution failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )

    # 6. Store assistant response in Redis
    try:
        assistant_msg_id = await state_manager.store_message(
            role="assistant",
            content=response_text,
            parent_id=user_msg_id,
            tool_calls=tool_calls,
            agent_id=agent_config.id,
        )
    except Exception as e:
        logger.error("Failed to store assistant message: %s", e)
        assistant_msg_id = "error-storing-message"

    # 7. Return response
    return ChatResponse(
        message_id=assistant_msg_id,
        parent_id=user_msg_id,
        role="assistant",
        content=response_text,
        tool_calls=tool_calls,
        agent_id=agent_config.id,
    )


@app.get("/api/v1/conversation/{message_id}")
async def get_conversation(message_id: str):
    """
    Retrieve the full conversation thread ending at a specific message.
    Useful for debugging and inspecting conversation history.
    """
    messages = await state_manager.load_conversation_context(message_id)
    if not messages:
        raise HTTPException(
            status_code=404,
            detail=f"No conversation found for message_id '{message_id}'",
        )
    return {
        "message_count": len(messages),
        "messages": messages,
    }

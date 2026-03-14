"""
Redis-based conversation state manager.

Implements the "Message ID Chain" pattern:
- Each message is stored as a unique node: msg:{uuid}
- Each node has { role, content, parent_id, tool_calls, timestamp }
- Context is reconstructed by traversing parent_id links backwards
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

import redis.asyncio as redis

from .config import settings

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages conversation state in Redis using the message ID chain pattern.
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        """Initialize Redis connection."""
        self._redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        # Test connection
        await self._redis.ping()
        logger.info("Connected to Redis at %s", settings.redis_url)

    async def disconnect(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    async def is_connected(self) -> bool:
        """Check if Redis is reachable."""
        try:
            if self._redis:
                await self._redis.ping()
                return True
        except Exception:
            pass
        return False

    def _key(self, message_id: str) -> str:
        """Redis key for a message node."""
        return f"msg:{message_id}"

    async def store_message(
        self,
        role: str,
        content: str,
        parent_id: Optional[str] = None,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        agent_id: str = "",
    ) -> str:
        """
        Store a new message in the chain.

        Returns:
            The generated message_id (UUID)
        """
        message_id = str(uuid.uuid4())

        payload = {
            "message_id": message_id,
            "role": role,
            "content": content,
            "parent_id": parent_id or "",
            "tool_calls": json.dumps(tool_calls or []),
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        key = self._key(message_id)
        await self._redis.hset(key, mapping=payload)
        await self._redis.expire(key, settings.state_ttl_seconds)

        logger.debug("Stored message %s (parent=%s)", message_id, parent_id)
        return message_id

    async def get_message(self, message_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a single message by ID."""
        data = await self._redis.hgetall(self._key(message_id))
        if not data:
            return None

        data["tool_calls"] = json.loads(data.get("tool_calls", "[]"))
        return data

    async def load_conversation_context(
        self, parent_id: Optional[str], max_depth: int = 50
    ) -> list[dict[str, Any]]:
        """
        Reconstruct conversation history by traversing the message chain.

        Walks backwards from parent_id to the root, then reverses
        to get chronological order.

        Args:
            parent_id: The ID to start traversal from
            max_depth: Maximum messages to load (prevents infinite loops)

        Returns:
            List of messages in chronological order
        """
        if not parent_id:
            return []

        messages = []
        current_id = parent_id
        depth = 0

        while current_id and depth < max_depth:
            msg = await self.get_message(current_id)
            if not msg:
                logger.warning("Message %s not found in chain", current_id)
                break

            messages.append(msg)
            current_id = msg.get("parent_id", "")
            depth += 1

        # Reverse to get chronological order
        messages.reverse()

        logger.info(
            "Loaded %d messages in conversation context (from parent_id=%s)",
            len(messages),
            parent_id,
        )
        return messages

    async def get_conversation_summary(
        self, parent_id: Optional[str]
    ) -> dict[str, Any]:
        """Get a summary of the conversation chain."""
        messages = await self.load_conversation_context(parent_id)
        return {
            "message_count": len(messages),
            "roles": [m["role"] for m in messages],
            "agent_ids": list({m.get("agent_id", "") for m in messages if m.get("agent_id")}),
        }

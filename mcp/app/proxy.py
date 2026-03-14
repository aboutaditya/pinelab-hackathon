"""
HTTP proxy that forwards MCP tool calls to the Django backend.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .tool_loader import MCPTool

logger = logging.getLogger(__name__)


class BackendProxy:
    """Asynchronous proxy to the Django transaction backend."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def execute_tool(
        self, tool: MCPTool, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute an MCP tool by proxying the request to the Django backend.

        Args:
            tool: The MCPTool definition
            params: Parameters provided by the LLM

        Returns:
            JSON response from the backend
        """
        url = tool.build_url(self.base_url, params)
        query_params = tool.extract_query_params(params)
        body_params = tool.extract_body_params(params)

        logger.info(
            "Proxying %s %s | query=%s | body=%s",
            tool.method,
            url,
            query_params,
            body_params,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                if tool.method == "GET":
                    response = await client.get(url, params=query_params)
                elif tool.method == "POST":
                    response = await client.post(
                        url, json=body_params, params=query_params
                    )
                elif tool.method == "PATCH":
                    response = await client.patch(
                        url, json=body_params, params=query_params
                    )
                elif tool.method == "DELETE":
                    response = await client.delete(url, params=query_params)
                else:
                    return {
                        "error": f"Unsupported HTTP method: {tool.method}"
                    }

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "Backend returned %s for %s %s: %s",
                    e.response.status_code,
                    tool.method,
                    url,
                    e.response.text,
                )
                try:
                    error_body = e.response.json()
                except Exception:
                    error_body = {"detail": e.response.text}
                return {
                    "error": True,
                    "status_code": e.response.status_code,
                    **error_body,
                }
            except httpx.RequestError as e:
                logger.error("Request failed for %s %s: %s", tool.method, url, e)
                return {"error": True, "detail": str(e)}

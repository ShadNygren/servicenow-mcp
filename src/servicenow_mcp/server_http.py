"""ServiceNow MCP server — Streamable HTTP transport.

Streamable HTTP is the MCP spec's HTTP transport. A single endpoint at
``/mcp`` handles both request/response and server-pushed streaming
over chunked HTTP. (This replaced the older SSE transport's
``/sse`` + ``/messages/`` pair when SSE was retired in v0.7.)

The HTTP transport is gated by SecurityMiddleware
(:mod:`servicenow_mcp.transport_security`):

  - Loopback bind by default; non-loopback requires --allow-remote AND
    MCP_AUTH_TOKEN.
  - Bearer-token gate validated with hmac.compare_digest.
  - Host header allowlist  -> 421 (DNS-rebinding defense).
  - Origin header allowlist -> 403 (browser CSRF defense).
  - Pure ASGI middleware — keeps streaming responses unbuffered.
  - GET /health bypasses the bearer-token check (Host check still
    applies) so platform liveness probes work.

Reference implementation pattern from ``ibeketov/servicenow-mcp``
(server_http.py, MIT-licensed). Original copyright preserved in NOTICE.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from typing import Set

import uvicorn
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from servicenow_mcp.event_store import InMemoryEventStore
from servicenow_mcp.server import ServiceNowMCP
from servicenow_mcp.transport_security import (
    SecurityMiddleware,
    build_allowed_hosts,
    build_allowed_origins,
    is_loopback_host,
    resolve_auth_token,
)
from servicenow_mcp.utils.config import (
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    ServerConfig,
)

logger = logging.getLogger(__name__)


def create_starlette_app(
    mcp_server: Server,
    *,
    auth_token: str,
    allowed_hosts: Set[str],
    allowed_origins: Set[str],
    debug: bool = False,
) -> Starlette:
    """Build a Starlette app exposing the MCP server via Streamable HTTP.

    SecurityMiddleware (from :mod:`servicenow_mcp.transport_security`)
    is mounted in front of every request: bearer token, Host allowlist,
    Origin allowlist. ``/health`` is bypassed for the bearer check
    (Host allowlist still applies) so platform liveness probes work.
    """
    event_store = InMemoryEventStore()

    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=event_store,
        json_response=False,  # Default to SSE-style streaming responses (per MCP spec).
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    async def health_check(request: Request) -> PlainTextResponse:
        """Liveness probe — bypasses bearer auth (see SecurityMiddleware)."""
        return PlainTextResponse("OK", status_code=200)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Manage the StreamableHTTPSessionManager lifecycle."""
        async with session_manager.run():
            logger.info("Streamable HTTP session manager started")
            try:
                yield
            finally:
                logger.info("Streamable HTTP session manager shutting down")

    return Starlette(
        debug=debug,
        routes=[
            Route("/health", endpoint=health_check),
            Mount("/mcp", app=handle_streamable_http),
        ],
        middleware=[
            Middleware(
                SecurityMiddleware,
                token=auth_token,
                allowed_hosts=allowed_hosts,
                allowed_origins=allowed_origins,
            ),
        ],
        lifespan=lifespan,
    )


class ServiceNowHttpMCP(ServiceNowMCP):
    """ServiceNow MCP server using Streamable HTTP transport."""

    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        *,
        auth_token: str,
        allowed_hosts: Set[str],
        allowed_origins: Set[str],
    ) -> None:
        """Run the server with Streamable HTTP via Starlette + Uvicorn.

        Distinct name from base ``ServiceNowMCP.start()`` (which returns the
        underlying low-level Server) because this method *runs* the uvicorn
        process — different shape, different return type.

        Args:
            host: Bind address. Defaults to loopback.
            port: Listening port.
            auth_token: Bearer token MCP clients must present.
            allowed_hosts: Allowlist for Host header (DNS-rebinding defense).
            allowed_origins: Allowlist for Origin header (CSRF defense).
        """
        starlette_app = create_starlette_app(
            self.mcp_server,
            auth_token=auth_token,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
            debug=False,
        )
        logger.info("Starting Streamable HTTP server on %s:%d", host, port)
        uvicorn.run(starlette_app, host=host, port=port)


def create_servicenow_mcp(
    instance_url: str,
    username: str,
    password: str,
) -> ServiceNowHttpMCP:
    """Factory: a basic-auth Streamable HTTP MCP server."""
    auth_config = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username=username, password=password),
    )
    config = ServerConfig(instance_url=instance_url, auth=auth_config)
    return ServiceNowHttpMCP(config)


def main() -> None:
    """CLI entry point for the Streamable HTTP server."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run the ServiceNow MCP server with Streamable HTTP transport.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="Listening port")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding to a non-loopback address. Requires MCP_AUTH_TOKEN.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    allow_remote = args.allow_remote or bool(os.getenv("MCP_ALLOW_REMOTE"))
    if not allow_remote and not is_loopback_host(args.host):
        raise SystemExit(
            f"Refusing to bind to non-loopback address {args.host} without "
            "--allow-remote (or MCP_ALLOW_REMOTE=1)."
        )

    auth_token = resolve_auth_token(
        allow_remote=allow_remote, transport_name="servicenow-mcp-http"
    )
    allowed_hosts = build_allowed_hosts(host=args.host, port=args.port)
    allowed_origins = build_allowed_origins(allowed_hosts)

    instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
    username = os.getenv("SERVICENOW_USERNAME")
    password = os.getenv("SERVICENOW_PASSWORD")
    if not (instance_url and username and password):
        raise SystemExit(
            "Set SERVICENOW_INSTANCE_URL, SERVICENOW_USERNAME, SERVICENOW_PASSWORD "
            "(or use --instance-url/--username/--password)."
        )

    server = create_servicenow_mcp(instance_url, username, password)
    server.serve(
        host=args.host,
        port=args.port,
        auth_token=auth_token,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


if __name__ == "__main__":
    main()

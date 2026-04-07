"""Entry point to run the Google Scholar MCP server via HTTP."""

import os

import uvicorn


class RewriteHostMiddleware:
    """ASGI middleware that rewrites the Host header to localhost.

    Azure Container Apps proxies requests with the external FQDN as Host,
    but the MCP SDK's TrustedHostMiddleware only allows localhost.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            # Rewrite host header to localhost so TrustedHostMiddleware accepts it
            new_headers = []
            for k, v in scope.get("headers", []):
                if k == b"host":
                    new_headers.append((k, b"localhost:8080"))
                else:
                    new_headers.append((k, v))
            scope = dict(scope, headers=new_headers)
        return await self.app(scope, receive, send)


def create_app():
    """Import the MCP server and return the ASGI app with host rewrite."""
    from google_scholar_server import mcp

    # Try streamable-http first, fall back to SSE
    for method_name in ("streamable_http_app", "sse_app", "http_app"):
        factory = getattr(mcp, method_name, None)
        if factory:
            inner_app = factory()
            return RewriteHostMiddleware(inner_app)

    raise RuntimeError(
        f"FastMCP has no HTTP app factory. Available: {[m for m in dir(mcp) if 'app' in m.lower()]}"
    )


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

"""MCP: the tools of the servers a run is given, a client of geomind's own over httpx.

``gd.mcp.list_tools(server)`` lists a server's tools; in a run each tool is offered to the
agents as ``<server>__<tool>``. Imports ``types``, ``errors``, ``runtime`` and ``utils``.
"""

from geomind.mcp.client import McpClient, McpError, Server, list_tools, servers_from_text

__all__ = ["McpClient", "McpError", "Server", "list_tools", "servers_from_text"]

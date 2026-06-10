"""
Datadex — MCP Server

Exposes 4 MCP tools (datadex_search, datadex_register, datadex_summary, datadex_list_workspaces)
to Claude Code via the Model Context Protocol (stdio transport).

Usage:
    python datadex_server.py
"""

import os
import sys
import argparse
from typing import Optional

# Ensure the datadex package directory is on sys.path regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Windows terminal encoding for Unicode output
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from mcp.server.fastmcp import FastMCP

from core.query.engine import QueryEngine

# === Configuration ===
DEFAULT_WORKSPACES_DIR = os.path.join(os.path.dirname(__file__), "workspaces")
DEFAULT_WORKSPACE = os.environ.get("DATADEX_DEFAULT_WORKSPACE", "demo")
WORKSPACES_DIR = os.environ.get("DATADEX_WORKSPACES_DIR", DEFAULT_WORKSPACES_DIR)

# === Query Engine (shared state) ===
engine = QueryEngine(workspaces_dir=WORKSPACES_DIR)

# === MCP Server ===
mcp = FastMCP("datadex")


def _resolve_workspace(workspace: Optional[str]) -> str:
    """Use provided workspace or fall back to default."""
    return workspace or DEFAULT_WORKSPACE


@mcp.tool()
def datadex_search(query: str, workspace: str = None) -> str:
    """Search hardware documents for relevant sections.

    Performs semantic vector search across all ingested document chunks
    (datasheets, protocol specs, driver guides) for the given workspace.

    Args:
        query: Natural language question (e.g., "I2C configuration mode write steps")
        workspace: Workspace name (e.g., "my_project"). Defaults to DATADEX_DEFAULT_WORKSPACE.

    Returns:
        Top 5 relevant document chunks with source file citations and section headings.
    """
    ws = _resolve_workspace(workspace)
    return engine.search(query=query, workspace=ws, top_k=5)


@mcp.tool()
def datadex_register(register: str, workspace: str = None) -> str:
    """Look up a hardware register by name or address.

    Searches the structured register database for matching register entries.
    Matches by register name (e.g., "I2C_CFG", "GPIO_CTRL") or by hex address
    (e.g., "0xFC", "0x3C").

    Args:
        register: Register name or hex address (e.g., "I2C_CFG" or "0xFC")
        workspace: Product workspace name. Defaults to DATADEX_DEFAULT_WORKSPACE.

    Returns:
        Register record with address, bit fields, access type, reset value, and description.
    """
    ws = _resolve_workspace(workspace)
    return engine.lookup_register(register=register, workspace=ws)


@mcp.tool()
def datadex_summary(topic: str, workspace: str = None) -> str:
    """Get a condensed feature summary from ingested documents.

    Finds the most relevant document sections about a topic and presents them
    as a focused summary. Useful for getting a quick overview of a feature,
    protocol, or procedure without reading the full document.

    Args:
        topic: Feature or protocol name (e.g., "I2C mode write procedure", "LED blink pattern")
        workspace: Product workspace name. Defaults to DATADEX_DEFAULT_WORKSPACE.

    Returns:
        Top 3 most relevant document sections concatenated as a summary.
    """
    ws = _resolve_workspace(workspace)
    return engine.get_summary(topic=topic, workspace=ws, top_k=3)


@mcp.tool()
def datadex_list_workspaces() -> str:
    """List all available product workspaces with ingested data counts.

    Returns:
        List of workspace names, each showing how many document chunks
        and register records are indexed.
    """
    return engine.list_workspaces()


def main():
    global engine, WORKSPACES_DIR

    parser = argparse.ArgumentParser(description="Datadex MCP Server")
    parser.add_argument(
        "--workspaces-dir",
        default=WORKSPACES_DIR,
        help=f"Workspaces root directory (default: {WORKSPACES_DIR})",
    )
    args = parser.parse_args()

    WORKSPACES_DIR = args.workspaces_dir
    engine = QueryEngine(workspaces_dir=WORKSPACES_DIR)

    print(f"[Datadex] Datadex MCP Server starting...", file=sys.stderr)
    print(f"   Workspaces dir: {WORKSPACES_DIR}", file=sys.stderr)
    print(f"   Default workspace: {DEFAULT_WORKSPACE}", file=sys.stderr)
    print(f"   Transport: stdio (MCP)", file=sys.stderr)
    print(f"   Tools: datadex_search, datadex_register, datadex_summary, datadex_list_workspaces", file=sys.stderr)
    print(f"   Ready for Claude Code connection.", file=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    import sys
    main()

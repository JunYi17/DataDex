"""
Ken -- Query Engine

Combines vector search (ChromaDB) and structured lookup (SQLite)
to answer hardware documentation queries.
"""

import os
from typing import List, Optional

from ..ingestion.markdown_parser import Chunk
from ..storage.chroma_store import ChromaStore
from ..storage.sqlite_store import SQLiteStore


class QueryEngine:
    """Unified query interface combining semantic search and structured lookup."""

    def __init__(self, workspaces_dir: str):
        """Initialize the query engine.

        Args:
            workspaces_dir: Root directory containing all workspaces
        """
        self.workspaces_dir = workspaces_dir

    def _get_stores(self, workspace: str):
        """Get ChromaDB and SQLite stores for a workspace."""
        ws_dir = os.path.join(self.workspaces_dir, workspace, "data")
        chroma_dir = os.path.join(ws_dir, "chroma")
        sqlite_path = os.path.join(ws_dir, "registers.db")

        chroma = ChromaStore(persist_directory=chroma_dir)
        sqlite = SQLiteStore(db_path=sqlite_path)
        return chroma, sqlite

    def search(self, query: str, workspace: str, top_k: int = 5) -> str:
        """Semantic search across document chunks.

        Args:
            query: Natural language query
            workspace: Workspace name
            top_k: Number of results

        Returns:
            Formatted string with top matching chunks and source citations
        """
        chroma, _ = self._get_stores(workspace)
        results = chroma.search(workspace, query, top_k=top_k)

        if not results:
            return f"No results found for '{query}' in workspace '{workspace}'."

        lines = [f"Top {len(results)} results for: {query}", ""]
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            source = meta.get("source", "unknown")
            heading = meta.get("heading", "")
            source_line = f"[{source}]" + (f" - {heading}" if heading else "")

            # Truncate very long documents for display
            doc = r["document"]
            if len(doc) > 2000:
                doc = doc[:2000] + "\n... (truncated)"

            lines.append(f"--- Result {i} ---")
            lines.append(f"  {source_line}")
            lines.append("")
            lines.append(doc)
            lines.append("")

        return "\n".join(lines)

    def lookup_register(self, register: str, workspace: str) -> str:
        """Look up a register by name or address.

        Args:
            register: Register name (e.g., "I2C_CFG") or address (e.g., "0xFC")
            workspace: Workspace name

        Returns:
            Formatted string with matching register records
        """
        _, sqlite = self._get_stores(workspace)

        # Try name lookup first, then address
        results = sqlite.lookup_by_name(register, workspace)
        if not results:
            results = sqlite.lookup_by_address(register, workspace)

        if not results:
            return f"No register found for '{register}' in workspace '{workspace}'."

        lines = [f"Register results for: {register}", ""]
        for r in results:
            lines.append(f"  {r.get('name', '')}")
            lines.append(f"  |- Address:    {r.get('address', '-')}")
            if r.get('bit_field'):
                lines.append(f"  |- Bits:       {r['bit_field']}")
            if r.get('access'):
                lines.append(f"  |- Access:     {r['access']}")
            if r.get('reset_value'):
                lines.append(f"  |- Reset:      {r['reset_value']}")
            if r.get('description'):
                desc = r['description']
                if len(desc) > 300:
                    desc = desc[:300] + "..."
                lines.append(f"  |- Description: {desc}")
            lines.append(f"     (source: {r.get('source', 'unknown')})")
            lines.append("")

        return "\n".join(lines)

    def get_summary(self, topic: str, workspace: str, top_k: int = 3) -> str:
        """Get a condensed summary of a topic from ingested documents.

        Args:
            topic: Topic or feature name
            workspace: Workspace name
            top_k: Number of chunks to summarize from

        Returns:
            Concatenated summary of top matching document sections
        """
        chroma, _ = self._get_stores(workspace)
        results = chroma.search(workspace, topic, top_k=top_k)

        if not results:
            return f"No information found for '{topic}' in workspace '{workspace}'."

        lines = [f"Summary: {topic}", "=" * 40, ""]
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            source = meta.get("source", "unknown")
            heading = meta.get("heading", "")

            doc = r["document"]
            if len(doc) > 1500:
                doc = doc[:1500] + "\n... (truncated)"

            lines.append(f"--- From: {source}" + (f" - {heading}" if heading else ""))
            lines.append(doc)
            lines.append("")

        return "\n".join(lines)

    def list_workspaces(self) -> str:
        """List all available workspaces with register and chunk counts.

        Returns:
            Formatted string listing workspaces
        """
        if not os.path.exists(self.workspaces_dir):
            return "No workspaces directory found."

        workspace_names = sorted([
            d for d in os.listdir(self.workspaces_dir)
            if os.path.isdir(os.path.join(self.workspaces_dir, d))
            and not d.startswith("_")
            and not d.startswith(".")
        ])

        if not workspace_names:
            return "No workspaces found."

        lines = ["Available Workspaces", "=" * 30, ""]
        for ws in workspace_names:
            try:
                chroma, sqlite = self._get_stores(ws)
                chunk_count = chroma.count(ws)
                reg_count = sqlite.count(ws)
                lines.append(f"  {ws}")
                lines.append(f"    |- Document chunks: {chunk_count}")
                lines.append(f"    |- Register records: {reg_count}")
            except Exception:
                lines.append(f"  {ws}  (no data ingested yet)")
            lines.append("")

        return "\n".join(lines)

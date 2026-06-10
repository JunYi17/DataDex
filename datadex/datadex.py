#!/usr/bin/env python3
"""Datadex -- CLI Entry Point"""

# Fix Windows terminal encoding for Unicode output
import sys
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

"""
Command-line interface for document ingestion, workspace listing, and quick queries.

Usage:
    python datadex.py ingest --workspace 1363
    python datadex.py list
    python datadex.py query --workspace 1363 --search "I2C configuration"
    python datadex.py query --workspace 1363 --register I2C_CFG

Supported file formats:
    .md    Markdown  -- heading-split chunks (ChromaDB)
    .pdf   PDF       -- font-size heading detection, page-group fallback (ChromaDB)
    .docx  Word      -- Heading style chunks, paragraph-group fallback (ChromaDB)
    .xlsx  Excel     -- register auto-detect (SQLite + ChromaDB)
"""

import os
import sys
import argparse
import yaml

from core.ingestion.markdown_parser import MarkdownParser
from core.ingestion.excel_parser import ExcelRegisterParser
from core.ingestion.pdf_parser import PdfParser
from core.ingestion.docx_parser import DocxParser
from core.storage.chroma_store import ChromaStore
from core.storage.sqlite_store import SQLiteStore
from core.query.engine import QueryEngine


# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config():
    """Load global config.yaml if it exists."""
    config_path = os.path.join(SCRIPT_DIR, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_workspace_dir(workspace: str, workspaces_dir: str) -> str:
    """Get the path to a workspace directory."""
    return os.path.join(workspaces_dir, workspace)


def ingest_workspace(workspace: str, workspaces_dir: str, reindex: bool = False):
    """Ingest all documents in a single workspace. Returns (chunks, registers) counts."""
    ws_dir = get_workspace_dir(workspace, workspaces_dir)
    docs_dir = os.path.join(ws_dir, "docs")
    data_dir = os.path.join(ws_dir, "data")
    chroma_dir = os.path.join(data_dir, "chroma")
    sqlite_path = os.path.join(data_dir, "registers.db")

    if not os.path.exists(docs_dir):
        print(f"[X] Docs directory not found: {docs_dir}")
        print(f"   Create it and place your documents there.")
        return 0, 0

    chroma = ChromaStore(persist_directory=chroma_dir)
    sqlite = SQLiteStore(db_path=sqlite_path)

    if reindex:
        print(f"   Re-index mode: clearing existing data for '{workspace}'...")
        chroma.delete_collection(workspace)
        sqlite.clear_workspace(workspace)

    total_chunks = 0
    total_registers = 0

    md_parser = MarkdownParser()
    excel_parser = ExcelRegisterParser()
    pdf_parser = PdfParser()
    docx_parser = DocxParser()

    files = sorted(os.listdir(docs_dir))
    if not files:
        print(f"   No files found in {docs_dir}")
        return 0, 0

    print(f"[*] Scanning {len(files)} file(s) in {docs_dir}")

    for filename in files:
        filepath = os.path.join(docs_dir, filename)
        ext = os.path.splitext(filename)[1].lower()

        if not os.path.isfile(filepath):
            continue

        if filename.startswith("~$"):
            print(f"   [-] Skipping temp file: {filename}")
            continue

        try:
            if ext == ".md":
                print(f"  [MD] Parsing markdown: {filename}")
                chunks = md_parser.parse_file(filepath, workspace=workspace)
                if chunks:
                    texts = [c.text for c in chunks]
                    metadatas = [c.metadata for c in chunks]
                    chroma.add_chunks(workspace, chunks, texts, metadatas)
                    total_chunks += len(chunks)
                    print(f"       -> {len(chunks)} chunk(s) indexed")

            elif ext in (".xlsx", ".xls"):
                print(f"  [XL] Parsing Excel: {filename}")
                registers = excel_parser.parse_file(filepath, workspace=workspace)
                if registers:
                    sqlite.insert_registers(workspace, registers)
                    total_registers += len(registers)
                    print(f"       -> {len(registers)} register(s) stored")

                    reg_texts = []
                    reg_metas = []
                    for r in registers:
                        reg_text = (
                            f"Register {r.name} (address {r.address}): "
                            f"{'Bits: ' + r.bit_field + '. ' if r.bit_field else ''}"
                            f"{'Access: ' + r.access + '. ' if r.access else ''}"
                            f"{'Reset: ' + r.reset_value + '. ' if r.reset_value else ''}"
                            f"{r.description}"
                        ).strip()
                        if reg_text and len(reg_text) > 10:
                            reg_texts.append(reg_text)
                            reg_metas.append({
                                "source": filename,
                                "heading": f"Register: {r.name}",
                                "heading_chain": f"Register Map > {r.name}",
                                "chunk_index": 0,
                                "workspace": workspace,
                                "register_name": r.name,
                                "register_address": r.address,
                            })

                    if reg_texts:
                        chroma.add_chunks(workspace, [], reg_texts, reg_metas)
                        total_chunks += len(reg_texts)

            elif ext == ".pdf":
                print(f"  [PDF] Parsing PDF: {filename}")
                chunks = pdf_parser.parse_file(filepath, workspace=workspace)
                if chunks:
                    texts = [c.text for c in chunks]
                    metadatas = [c.metadata for c in chunks]
                    chroma.add_chunks(workspace, chunks, texts, metadatas)
                    total_chunks += len(chunks)
                    print(f"       -> {len(chunks)} chunk(s) indexed")

            elif ext == ".docx":
                print(f"  [DOC] Parsing Word: {filename}")
                chunks = docx_parser.parse_file(filepath, workspace=workspace)
                if chunks:
                    texts = [c.text for c in chunks]
                    metadatas = [c.metadata for c in chunks]
                    chroma.add_chunks(workspace, chunks, texts, metadatas)
                    total_chunks += len(chunks)
                    print(f"       -> {len(chunks)} chunk(s) indexed")

            else:
                print(f"   [-] Skipping unsupported: {filename}")

        except Exception as e:
            print(f"   [X] Error processing {filename}: {e}")

    print()
    print(f"[OK] '{workspace}' done — {total_chunks} chunk(s), {total_registers} register(s)")

    try:
        chunk_count = chroma.count(workspace)
        reg_count = sqlite.count(workspace)
        print(f"   Verified: {chunk_count} chunks in ChromaDB, {reg_count} registers in SQLite")
    except Exception:
        pass

    return total_chunks, total_registers


def cmd_ingest(args):
    """Ingest documents into the vector and structured stores."""
    config = load_config()
    workspaces_dir = args.workspaces_dir or config.get("workspaces_dir", os.path.join(SCRIPT_DIR, "workspaces"))

    if args.all:
        # Discover all workspace directories that have a docs/ folder
        if not os.path.isdir(workspaces_dir):
            print(f"[X] Workspaces directory not found: {workspaces_dir}")
            sys.exit(1)
        workspaces = sorted([
            d for d in os.listdir(workspaces_dir)
            if os.path.isdir(os.path.join(workspaces_dir, d))
            and os.path.isdir(os.path.join(workspaces_dir, d, "docs"))
        ])
        if not workspaces:
            print(f"[X] No workspaces with a docs/ folder found in {workspaces_dir}")
            sys.exit(1)
        print(f"[*] Ingesting all {len(workspaces)} workspace(s): {', '.join(workspaces)}")
        print()
        grand_chunks = 0
        grand_registers = 0
        for ws in workspaces:
            print(f"{'='*55}")
            print(f"  Workspace: {ws}")
            print(f"{'='*55}")
            c, r = ingest_workspace(ws, workspaces_dir, reindex=args.reindex)
            grand_chunks += c
            grand_registers += r
            print()
        print(f"{'='*55}")
        print(f"[OK] All workspaces ingested.")
        print(f"   Total chunks:    {grand_chunks}")
        print(f"   Total registers: {grand_registers}")
    else:
        ingest_workspace(args.workspace, workspaces_dir, reindex=args.reindex)


def cmd_list(args):
    """List all available workspaces."""
    config = load_config()
    workspaces_dir = args.workspaces_dir or config.get("workspaces_dir", os.path.join(SCRIPT_DIR, "workspaces"))

    engine = QueryEngine(workspaces_dir=workspaces_dir)
    print(engine.list_workspaces())


def cmd_query(args):
    """Run a quick query against a workspace (without MCP server)."""
    config = load_config()
    workspaces_dir = args.workspaces_dir or config.get("workspaces_dir", os.path.join(SCRIPT_DIR, "workspaces"))
    workspace = args.workspace or config.get("default_workspace", "1363")

    engine = QueryEngine(workspaces_dir=workspaces_dir)

    if args.search:
        print(engine.search(query=args.search, workspace=workspace, top_k=5))
    elif args.register:
        print(engine.lookup_register(register=args.register, workspace=workspace))
    else:
        print("Specify --search or --register to query.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Datadex -- Offline RAG for Hardware/Firmware Engineers"
    )
    parser.add_argument(
        "--workspaces-dir",
        help="Root workspaces directory (default: ./workspaces/)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents into Datadex")
    ws_group = ingest_parser.add_mutually_exclusive_group(required=True)
    ws_group.add_argument("--workspace", "-w", help="Workspace name")
    ws_group.add_argument("--all", "-a", action="store_true", help="Ingest all workspaces")
    ingest_parser.add_argument("--reindex", action="store_true", help="Re-index from scratch")

    # list
    subparsers.add_parser("list", help="List available workspaces")

    # query
    query_parser = subparsers.add_parser("query", help="Quick query against a workspace")
    query_parser.add_argument("--workspace", "-w", help="Workspace name")
    query_parser.add_argument("--search", "-s", help="Search query string")
    query_parser.add_argument("--register", "-r", help="Register name or address")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "query":
        cmd_query(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

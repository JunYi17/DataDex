# Datadex — Architecture Document

**Offline RAG MCP Server for Hardware/Firmware Engineers**

Version: MVP-1.1 | Date: 2026-06-09

---

## 1. System Overview

Datadex is an offline RAG (Retrieval-Augmented Generation) system that ingests hardware datasheets and register files, stores them in a searchable local database, and exposes them to Claude Code via the Model Context Protocol (MCP).

```
┌─────────────────────────────────────────────────────────────┐
│                       Claude Code                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              MCP Client (built-in)                     │ │
│  │  → datadex_search()        → datadex_summary()        │ │
│  │  → datadex_register()      → datadex_list_workspaces()│ │
│  └──────────────────────┬────────────────────────────────┘ │
└─────────────────────────┼──────────────────────────────────┘
                          │ MCP Protocol (stdio JSON-RPC)
┌─────────────────────────┼──────────────────────────────────┐
│                  ┌──────▼──────────────────────┐            │
│                  │    Datadex MCP Server        │            │
│                  │    (datadex_server.py)       │            │
│                  └──────┬──────────────────────┘            │
│                         │                                    │
│             ┌───────────┴───────────┐                        │
│             │                       │                        │
│       ┌─────▼─────┐          ┌──────▼──────────┐            │
│       │   Query    │          │    Ingest        │            │
│       │   Engine   │          │   Pipeline       │            │
│       └──┬──┬──────┘          └──┬──┬──┬──┬─────┘            │
│          │  │                    │  │  │  │                   │
│       ┌──▼──▼──┐           ┌────▼──▼──▼──▼─────┐            │
│       │ChromaDB │           │   Parsers         │            │
│       │(Vector) │           │                   │            │
│       └─────────┘           │  MarkdownParser   │            │
│       ┌─────────┐           │  PdfParser        │            │
│       │ SQLite  │           │  DocxParser       │            │
│       │(Regs)   │           │  ExcelRegisterParser         │
│       └─────────┘           └────────┬──────────┘            │
│                                      │                       │
│                               ┌──────▼──────┐               │
│                               │  Doc Files  │               │
│                               │ .md .pdf    │               │
│                               │ .docx .xlsx │               │
│                               └─────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Architecture

### 2.1 Layer Map

```
┌──────────────────────────────────────────────────────────┐
│                  Interface Layer                           │
│  MCP Server (datadex_server.py)    CLI (datadex.py)       │
├──────────────────────────────────────────────────────────┤
│                  Query Layer                               │
│  Vector Search    Structured Lookup    Summary             │
│  (ChromaDB)       (SQLite)            (Rerank)            │
├──────────────────────────────────────────────────────────┤
│                  Storage Layer                             │
│  ChromaDB (embeddings + chunks)                           │
│  SQLite   (register records)                              │
├──────────────────────────────────────────────────────────┤
│                  Ingestion Layer                           │
│  Markdown → heading-split chunks                          │
│  PDF      → font-size heading detection                   │
│  DOCX     → Heading style recognition                     │
│  Excel    → auto-detect register columns → structured row │
├──────────────────────────────────────────────────────────┤
│                  Document Layer                            │
│  .md files      .pdf files     .docx files     .xlsx      │
│  (datasheets,   (datasheets,   (specs,         (register  │
│   protocol docs) app notes)    manual)          maps)     │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow — Ingest

```
Source Files                  Parsing                         Storage
────────────               ──────────                       ────────

datasheet.md   ──→  MarkdownParser.split_by_heading()
                     ┌──────────────────────────┐            ChromaDB
                     │ Chunk 1: heading=         │ ──embed──→ (vector)
                     │   "I2C Overview"          │            Collection:
                     │ Chunk 2: heading=         │            datadex_{workspace}
                     │   "Configuration"         │
                     └──────────────────────────┘

datasheet.pdf  ──→  PdfParser.parse_file()
                     ┌──────────────────────────┐            ChromaDB
                     │ Per-block font-size      │ ──embed──→ (vector)
                     │ analysis → heading       │
                     │ detection (1.35x median) │
                     │ chain-based chunking     │
                     └──────────────────────────┘

spec.docx      ──→  DocxParser.parse_file()
                     ┌──────────────────────────┐            ChromaDB
                     │ Paragraph style →        │ ──embed──→ (vector)
                     │ Heading N recognition    │
                     │ chain-based chunking     │
                     └──────────────────────────┘

register.xlsx  ──→  ExcelRegisterParser.parse()
                     ┌──────────────────────────┐            SQLite
                     │ Register I2C_CFG         │ ────────→ registers.db
                     │   addr = 0xFC            │            Table: registers
                     │   bits = [7:0]           │
                     │   access = R/W           │
                     └──────────────────────────┘
```

### 2.3 Data Flow — Query

```
User Question                    Retrieval                        Response
─────────────                  ────────────                      ────────
"How do I do           ──→  datadex_search(query)            ──→  Top-5 chunks
 I2C Configuration           ChromaDB.similarity_search()          with source
 Mode Write?"                                                       citations
                             datadex_register("I2C_CFG")
                             SQLite: SELECT * FROM registers
                             WHERE name LIKE '%I2C%'          ─→  Register record
                                                                   (address, bits, access)

                             datadex_summary("I2C Mode Write")
                             search top-3 + deduplicate      ─→  Condensed summary
```

---

## 3. Component Specifications

### 3.1 Document Parsers

| Component | Input | Output | Method |
|---|---|---|---|
| `MarkdownParser` | `.md` file | `list[Chunk]` | Split by `##`/`###` headings. H2 resets chain, H3 appends. Each chunk = heading chain + body text |
| `PdfParser` | `.pdf` file | `list[Chunk]` | Per-block font-size analysis via PyMuPDF (fitz). Blocks with font >= 1.35× page median → headings. Heading-chain chunking; fallback to ~800-char size-capped chunks when <2 headings found |
| `DocxParser` | `.docx` file | `list[Chunk]` | Iterates paragraphs via python-docx; recognises "Heading N" / "Title" / "Subtitle" style names. Heading-chain chunking; fallback to size-capped chunks when <2 headings found |
| `ExcelRegisterParser` | `.xlsx` file | `list[Register]` | Auto-detect register columns by header name matching (alias patterns for name, address, bit_field, access, reset_value, description). One row = one register. Also indexed into ChromaDB as text chunks |

**Chunk Schema:**
```python
@dataclass
class Chunk:
    text: str          # Heading chain + body content
    metadata: dict     # {source, heading, heading_chain, page?, chunk_index, workspace}
```
- `heading_chain`: list of ancestor headings, e.g. `["I2C Overview", "Configuration Registers"]`
- `page`: present only for PDF-sourced chunks (integer page number)
- `source`: filename of the source document

**Register Schema:**
```python
@dataclass
class Register:
    name: str          # Register name (e.g., I2C_CFG)
    address: str       # Address (e.g., 0xFC)
    bit_field: str     # Bit field description (e.g., "[7:0]")
    access: str        # Access type (e.g., R/W, RO)
    reset_value: str   # Reset value (e.g., 0x00)
    description: str   # Full description
    source: str        # Source filename
```

### 3.2 Storage Layer

**ChromaDB (Vector Store):**
- Location: `workspaces/{name}/data/chroma/`
- Collection naming: `datadex_{workspace}`
- Default embedding: `all-MiniLM-L6-v2` (ChromaDB built-in, ~80 MB ONNX model, auto-downloaded on first use)
- Vector dimension: 384
- Metadata filters: `workspace`, `source`, `heading`

**SQLite (Register Store):**
- Location: `workspaces/{name}/data/registers.db`
- Table: `registers`
- Columns: `id, name, address, bit_field, access, reset_value, description, source, workspace`
- Indexes: `idx_name`, `idx_address`

### 3.3 Query Engine

```python
class QueryEngine:
    def search(query: str, workspace: str, top_k: int = 5) -> list[Chunk]:
        """Vector similarity search in ChromaDB, filtered by workspace"""

    def lookup_register(register: str, workspace: str) -> list[Register]:
        """Structured look up by register name (LIKE) or exact address"""

    def get_summary(topic: str, workspace: str) -> str:
        """Vector search top-3 chunks → concatenate into condensed summary"""

    def list_workspaces() -> list[dict]:
        """Scan workspaces directory for valid configs; return name + description + doc count"""
```

### 3.4 MCP Interface

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("datadex")

@mcp.tool()
def datadex_search(query: str, workspace: str = None) -> str:
    """Search hardware documents for relevant sections.
    Args:
        query: Natural language question (e.g., "I2C configuration mode write")
        workspace: Optional product name filter (default: DATADEX_DEFAULT_WORKSPACE)
    Returns:
        Top relevant document chunks with source citations
    """

@mcp.tool()
def datadex_register(register: str, workspace: str = None) -> str:
    """Look up a hardware register by name or address.
    Args:
        register: Register name or hex address (e.g., "I2C_CFG" or "0xFC")
        workspace: Optional product name filter
    Returns:
        Register record: address, bit fields, access type, reset value, description
    """

@mcp.tool()
def datadex_summary(topic: str, workspace: str = None) -> str:
    """Get a condensed feature summary from ingested documents.
    Args:
        topic: Feature or protocol name (e.g., "I2C mode write procedure")
        workspace: Optional product name filter
    Returns:
        Synthesized summary of top matching document sections
    """

@mcp.tool()
def datadex_list_workspaces() -> str:
    """List all available product workspaces that have been ingested.
    Returns:
        List of workspace names with descriptions
    """
```

### 3.5 CLI Entry Point

```
Usage: python datadex.py <command> [options]

Commands:
  ingest    Parse documents and store in vector + structured DB
            Options: --workspace <name> (required)
                     --docs <path>       (default: ./workspaces/{name}/docs)
                     --reindex           (force re-index existing docs)

  list      List available workspaces

  query     Quick test query (without MCP server)
            Options: --workspace <name>
                     --search <query>
                     --register <name>
```

---

## 4. Configuration

### 4.1 Config File (`config.yaml`)

```yaml
default_workspace: demo

workspaces_dir: ./workspaces/

mcp:
  server_name: datadex
  transport: stdio

storage:
  chroma_dir: ./data/chroma/   # relative to workspace
  sqlite_path: ./data/registers.db

embedding:
  model: default    # ChromaDB default (all-MiniLM-L6-v2)
  dimension: 384
```

### 4.2 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATADEX_DEFAULT_WORKSPACE` | `demo` | Default workspace when none specified |
| `DATADEX_WORKSPACES_DIR` | `./workspaces/` | Root workspace directory |

---

## 5. Directory Structure

```
datadex/
├── .venv/                         # Python virtual environment (created by setup.ps1)
├── core/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── markdown_parser.py     # Markdown split-by-heading parser
│   │   ├── pdf_parser.py          # PDF font-size heading detection parser
│   │   ├── docx_parser.py         # DOCX Heading-style parser
│   │   └── excel_parser.py        # Excel register table parser
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── chroma_store.py        # ChromaDB wrapper
│   │   └── sqlite_store.py        # SQLite register store
│   ├── query/
│   │   ├── __init__.py
│   │   └── engine.py              # Query engine (search, lookup, summary)
│   └── __init__.py
├── workspaces/
│   └── demo/                      # One directory per project/product
│       ├── config.yaml            # Workspace configuration (auto-created by setup.ps1)
│       ├── docs/                  # Source documents go here (.md, .pdf, .docx, .xlsx)
│       └── data/                  # Auto-created on ingest
│           ├── chroma/
│           └── registers.db
├── datadex_server.py              # MCP server entry point
├── datadex.py                     # CLI entry point
├── config.yaml                    # Global configuration
└── requirements.txt               # Python dependencies
```

---

## 6. Dependencies

### 6.1 Runtime

| Requirement | Version | Purpose |
|---|---|---|
| **Python** | 3.10 – 3.14 | Tested on Python 3.14.4. All dependencies ship pre-built wheels for Windows. |
| **pip** | 24.0+ | Package installer — comes with Python |
| **Claude Code** | latest | The AI assistant that queries Datadex via MCP protocol |

### 6.2 Python Packages

| Package | Version | Purpose |
|---|---|---|
| `chromadb` | >=0.6.0 | Vector database with built-in all-MiniLM-L6-v2 embedding (~80 MB auto-downloaded) |
| `openpyxl` | >=3.1.0 | Excel file parsing |
| `mcp` | >=1.0.0 | MCP server framework (FastMCP) |
| `pyyaml` | >=6.0 | YAML config parsing |
| `pymupdf` | >=1.24.0 | PDF text extraction via MuPDF (imported as `fitz`) |
| `python-docx` | >=1.1.0 | Word document parsing |

### 6.3 Auto-installed (transitive)

| Package | Brought in by | Purpose |
|---|---|---|
| `onnxruntime` | chromadb | Runs the embedding model locally |
| `numpy` | chromadb, onnxruntime | Numerical computation for vector embeddings |
| `lxml` | python-docx | XML parsing for .docx format |
| `pydantic` | mcp | Data validation for MCP messages |
| `pyarrow` | chromadb | Columnar data format for vector storage |

No external API calls. All processing is local. Embedding model is auto-downloaded by ChromaDB (~80 MB one-time).

---

## 7. Design Decisions (ADRs)

### ADR-1: ChromaDB built-in embedding vs. separate model
- **Decision:** Use ChromaDB's default `all-MiniLM-L6-v2` embedding
- **Rationale:** Zero-config, auto-downloads, small footprint (~80 MB), sufficient for domain-specific search
- **Trade-off:** Less accurate than BGE-M3 for cross-lingual or very technical queries
- **Future:** Can swap to `BGE-M3` by changing one config value

### ADR-2: SQLite + ChromaDB (hybrid) vs. ChromaDB-only
- **Decision:** Both — ChromaDB for semantic search, SQLite for structured register lookups
- **Rationale:** Register lookups by exact name/address are fundamentally different from semantic search. SQLite gives deterministic "WHERE name LIKE '%I2C%'" queries. ChromaDB handles fuzzy/descriptive queries.
- **Trade-off:** Two storage systems to maintain, but each excels at its purpose

### ADR-3: fastmcp vs. raw MCP SDK
- **Decision:** Use `mcp` package's `FastMCP` class
- **Rationale:** FastMCP provides decorator-based tool definitions (`@mcp.tool()`), automatic JSON schema generation from type hints, and clean stdio transport — minimal boilerplate

### ADR-4: Workspace directory under datadex vs. separate location
- **Decision:** Workspaces nested under `datadex/workspaces/`
- **Rationale:** Self-contained, portable — move the whole directory and everything moves. Avoids R: drive dependency for MVP.

### ADR-5: PDF heading detection via font-size heuristics vs. PDF structure
- **Decision:** Use block-level font-size analysis (PyMuPDF `get_text("dict")`) with a 1.35× median threshold
- **Rationale:** Many hardware datasheets don't use tagged PDF structure — font size is the only reliable heading signal
- **Trade-off:** Threshold may misfire on documents with very uniform font sizes; fallback chunk-by-size covers that case

### ADR-6: DOCX heading via style name vs. paragraph outline level
- **Decision:** Match paragraph style names against `^heading\s*\d` (case-insensitive), plus Title and Subtitle
- **Rationale:** python-docx exposes style names reliably; outline level is inconsistently set in many Word documents

---

## 8. Current Scope

| Feature | Status |
|---|---|
| Markdown parsing (`##`/`###` heading split) | ✅ Implemented |
| PDF parsing (font-size heading detection) | ✅ Implemented |
| DOCX parsing (Heading style recognition) | ✅ Implemented |
| Excel register parsing (auto-detect columns) | ✅ Implemented |
| Embedding model | all-MiniLM-L6-v2 (ChromaDB default) |
| Semantic search | ✅ Basic similarity search |
| Structured register query | ✅ By name/address (LIKE) |
| MCP tools | ✅ All 4 tools (search, register, summary, list_workspaces) |
| CLI | ✅ ingest, list, query |
| Multiple workspaces | ✅ Supported |
| Source citations | ✅ Chunk-level with heading chain |
| .mcp.json registration | ✅ Registered with Claude Code |
| UTF-8 Windows terminal fix | ✅ `sys.stdout.reconfigure(encoding="utf-8")` |

### Future / Planned

| Feature | Notes |
|---|---|
| Hybrid search (BM25 + vector) | Reranking for better precision |
| Custom column mapping config | For non-standard Excel layouts |
| CSV parsing | DuckDB or pandas for structured data |
| Cross-workspace search | Search across all workspaces at once |
| Page-number PDF citations | Include page numbers in search results |
| Frontmatter parsing | YAML frontmatter metadata extraction |

---

## 9. System Requirements

### Hardware
- **Disk:** ~500 MB minimum (Python + packages + model + your documents)
- **RAM:** ~256 MB idle, up to 1 GB during ingest
- **Network:** One-time download of embedding model (~80 MB); everything else runs fully offline

### OS
- **Windows** 10 / 11 (tested on Windows 11 Enterprise build 26200)
- Also compatible with Linux / macOS

### Software
- **Python** 3.10–3.14, **pip**, **Claude Code** CLI
- Git Bash recommended for terminal on Windows (or any Unix-style shell)

---

## 10. MCP Integration

Datadex communicates with Claude Code via stdio JSON-RPC using the MCP protocol.

**Registration file (`.mcp.json`)** — placed at the DataDex project root, auto-generated by `setup.ps1`:

```powershell
.\setup.ps1   # writes .mcp.json with paths correct for the current machine
```

The generated file points `command` to the `.venv` Python and `cwd` to the `datadex/` directory — no manual path editing required. Re-run `setup.ps1` any time you move the folder or change Python installations.

When Claude Code starts, it launches `datadex_server.py` as a subprocess. All tool calls (`datadex_search`, `datadex_register`, etc.) are JSON-RPC requests over stdin/stdout.

---

*Date: 2026-06-09*
*Status: Draft / Ready for Review*

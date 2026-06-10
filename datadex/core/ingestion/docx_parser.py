"""
Ken — Word Document Parser (.docx)

Parses .docx files into chunks using python-docx.
Treats paragraphs with "Heading N" style as heading boundaries (like
the MarkdownParser), and groups leftover paragraphs into size-capped
chunks when no heading styles are present.

Tables are converted to plain-text (markdown-style) and treated as
body content under the current heading — this captures data-format
figures and register tables that would otherwise be skipped.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List

from docx import Document as DocxDocument
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


@dataclass
class Chunk:
    """A single document chunk with metadata."""
    text: str
    metadata: dict = field(default_factory=dict)


# Heading style name prefixes recognised by python-docx
_HEADING_STYLES = {"heading", "title", "subtitle"}

# Fallback chunk size when no heading styles are found
_FALLBACK_CHUNK_SIZE = 800


def _table_to_text(table) -> str:
    """Convert a docx table to a plain-text markdown-style representation."""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        # Deduplicate merged cells (python-docx repeats merged cell text)
        deduped = []
        for i, c in enumerate(cells):
            if i == 0 or c != cells[i - 1]:
                deduped.append(c)
        rows.append(" | ".join(deduped))

    if not rows:
        return ""

    # Insert a separator after the first row (treat it as a header)
    if len(rows) > 1:
        sep = " | ".join(["---"] * len(rows[0].split(" | ")))
        rows.insert(1, sep)

    return "\n".join(rows)


class DocxParser:
    """Parse .docx files into heading-based chunks for vector indexing."""

    def __init__(self, min_chunk_length: int = 20):
        self.min_chunk_length = min_chunk_length

    def parse_file(self, filepath: str, workspace: str = "") -> List[Chunk]:
        """Parse a single .docx file into chunks.

        Iterates over the document body in XML order so that tables
        interleaved with paragraphs are captured in the right position.

        Args:
            filepath: Path to the .docx file
            workspace: Workspace name for metadata

        Returns:
            List of Chunk objects with text and metadata
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        source_name = os.path.basename(filepath)
        doc = DocxDocument(filepath)

        # Build a flat list of entries in document order, including tables
        entries: List[dict] = []
        body = doc.element.body

        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                # It's a paragraph — find the matching Paragraph object
                para = Paragraph(child, doc)
                text = para.text.strip()
                if not text:
                    continue
                level = self._heading_level(para)
                entries.append({"text": text, "level": level, "type": "para"})

            elif tag == "tbl":
                # It's a table — convert to text
                from docx.table import Table
                tbl = Table(child, doc)
                text = _table_to_text(tbl)
                if text and len(text.strip()) >= self.min_chunk_length:
                    entries.append({"text": text, "level": 0, "type": "table"})

        # If we have at least two headings, chunk by heading boundaries
        heading_count = sum(1 for e in entries if e["level"] > 0)
        if heading_count >= 2:
            return self._chunk_by_headings(entries, source_name, workspace)

        # Otherwise fall back to size-capped grouping
        return self._chunk_by_size(entries, source_name, workspace)

    # ── helpers ──────────────────────────────────────────────────────

    def _heading_level(self, para: Paragraph) -> int:
        """Return the heading level (1-9) or 0 for body text."""
        style = para.style
        if style is None:
            return 0
        name = style.name or ""

        m = re.match(r"^heading\s*(\d)", name, re.IGNORECASE)
        if m:
            return int(m.group(1))

        if name.lower() in _HEADING_STYLES:
            return 1

        return 0

    def _chunk_by_headings(
        self, entries: List[dict], source: str, workspace: str
    ) -> List[Chunk]:
        """Group entries under the nearest preceding heading."""
        chunks: List[Chunk] = []
        heading_chain: List[str] = []
        current_lines: List[str] = []
        current_heading = "(no heading)"

        for ent in entries:
            if ent["level"] > 0:
                # flush previous section
                if current_lines:
                    body = "\n".join(current_lines).strip()
                    if len(body) >= self.min_chunk_length:
                        chain_str = " > ".join(heading_chain) if heading_chain else current_heading
                        full_text = f"{chain_str}\n\n{body}"
                        chunks.append(Chunk(
                            text=full_text,
                            metadata={
                                "source": source,
                                "heading": current_heading,
                                "heading_chain": chain_str,
                                "chunk_index": len(chunks),
                                "workspace": workspace,
                            }
                        ))
                    current_lines = []

                ht = ent["text"][:80]
                if ent["level"] == 1 or not heading_chain:
                    heading_chain = [ht]
                else:
                    heading_chain = heading_chain[: ent["level"] - 1] + [ht]
                current_heading = ht
            else:
                current_lines.append(ent["text"])

        # flush last section
        if current_lines:
            body = "\n".join(current_lines).strip()
            if len(body) >= self.min_chunk_length:
                chain_str = " > ".join(heading_chain) if heading_chain else current_heading
                full_text = f"{chain_str}\n\n{body}"
                chunks.append(Chunk(
                    text=full_text,
                    metadata={
                        "source": source,
                        "heading": current_heading,
                        "heading_chain": chain_str,
                        "chunk_index": len(chunks),
                        "workspace": workspace,
                    }
                ))

        return chunks

    def _chunk_by_size(
        self, entries: List[dict], source: str, workspace: str
    ) -> List[Chunk]:
        """Group entries by target character size."""
        chunks: List[Chunk] = []
        group: List[str] = []

        for ent in entries:
            group.append(ent["text"])
            if sum(len(t) for t in group) >= _FALLBACK_CHUNK_SIZE:
                body = "\n".join(group).strip()
                if len(body) >= self.min_chunk_length:
                    chunks.append(Chunk(
                        text=body,
                        metadata={
                            "source": source,
                            "heading": "(body text)",
                            "heading_chain": "(body text)",
                            "chunk_index": len(chunks),
                            "workspace": workspace,
                        }
                    ))
                group = []

        if group:
            body = "\n".join(group).strip()
            if len(body) >= self.min_chunk_length:
                chunks.append(Chunk(
                    text=body,
                    metadata={
                        "source": source,
                        "heading": "(body text)",
                        "heading_chain": "(body text)",
                        "chunk_index": len(chunks),
                        "workspace": workspace,
                    }
                ))

        return chunks

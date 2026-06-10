"""
Ken — PDF Document Parser

Extracts text from PDF files using PyMuPDF (fitz).
Attempts heading detection via font size heuristics; falls back to
page-based or size-capped chunking when headings are not found.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import fitz  # PyMuPDF


@dataclass
class Chunk:
    """A single document chunk with metadata."""
    text: str
    metadata: dict = field(default_factory=dict)


# Minimum font-size ratio relative to the page's median to be considered
# a "heading".  e.g. 1.4 means 40 % larger than median body text.
_HEADING_SIZE_RATIO = 1.35

# If no headings are detected, fall back to paragraph-group chunks of
# roughly this many characters.
_FALLBACK_CHUNK_SIZE = 800


class PdfParser:
    """Parse .pdf files into chunks for vector indexing."""

    def __init__(self, min_chunk_length: int = 20):
        self.min_chunk_length = min_chunk_length

    def parse_file(self, filepath: str, workspace: str = "") -> List[Chunk]:
        """Parse a single PDF file into chunks.

        Args:
            filepath: Path to the .pdf file
            workspace: Workspace name for metadata

        Returns:
            List of Chunk objects with text and metadata
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        source_name = os.path.basename(filepath)
        doc = fitz.open(filepath)

        all_blocks: List[dict] = []   # each block: {page, text, font_size, is_heading}
        heading_count = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            page_median_size = self._estimate_body_size(blocks)

            for block in blocks:
                if block["type"] != 0:          # 0 = text block
                    continue
                text = self._extract_block_text(block).strip()
                if not text or len(text) < self.min_chunk_length:
                    continue

                # Determine max font size on this block
                max_size = page_median_size
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 0)
                        if size > max_size:
                            max_size = size

                is_heading = (
                    page_median_size > 0
                    and max_size >= page_median_size * _HEADING_SIZE_RATIO
                )
                if is_heading:
                    heading_count += 1

                all_blocks.append({
                    "page": page_num + 1,
                    "text": text,
                    "font_size": max_size,
                    "is_heading": is_heading,
                })

        doc.close()

        # If we found meaningful headings, chunk by heading boundaries
        if heading_count >= 2:
            return self._chunk_by_headings(all_blocks, source_name, workspace)

        # Otherwise fall back to size-capped paragraph grouping
        return self._chunk_by_size(all_blocks, source_name, workspace)

    # ── helpers ──────────────────────────────────────────────────────

    def _estimate_body_size(self, blocks: list) -> float:
        """Return the median font size across all text spans on a page."""
        sizes = []
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0)
                    if s > 0:
                        sizes.append(s)
        if not sizes:
            return 0
        sizes.sort()
        return sizes[len(sizes) // 2]

    def _extract_block_text(self, block: dict) -> str:
        """Concatenate all span text inside a block."""
        parts = []
        for line in block.get("lines", []):
            line_text = "".join(
                span.get("text", "") for span in line.get("spans", [])
            ).strip()
            if line_text:
                parts.append(line_text)
        return "\n".join(parts)

    def _chunk_by_headings(
        self, blocks: List[dict], source: str, workspace: str
    ) -> List[Chunk]:
        """Group blocks under the nearest preceding heading."""
        chunks: List[Chunk] = []
        current_heading = f"(page 1)"
        current_lines: List[str] = []
        heading_chain: List[str] = []

        for blk in blocks:
            if blk["is_heading"]:
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
                                "page": blk["page"],
                                "chunk_index": len(chunks),
                                "workspace": workspace,
                            }
                        ))
                    current_lines = []

                # update heading chain
                heading_text = blk["text"][:80].strip()
                heading_chain = [heading_text]
                current_heading = heading_text
            else:
                current_lines.append(blk["text"])

        # flush last
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
                        "page": blocks[-1]["page"] if blocks else 0,
                        "chunk_index": len(chunks),
                        "workspace": workspace,
                    }
                ))

        return chunks

    def _chunk_by_size(
        self, blocks: List[dict], source: str, workspace: str
    ) -> List[Chunk]:
        """Group consecutive blocks until each group reaches ~_FALLBACK_CHUNK_SIZE chars."""
        chunks: List[Chunk] = []
        group: List[str] = []
        group_start_page = 0

        for blk in blocks:
            if not group:
                group_start_page = blk["page"]
            group.append(blk["text"])

            if sum(len(t) for t in group) >= _FALLBACK_CHUNK_SIZE:
                body = "\n".join(group).strip()
                if len(body) >= self.min_chunk_length:
                    chunks.append(Chunk(
                        text=body,
                        metadata={
                            "source": source,
                            "heading": f"(page {group_start_page})",
                            "heading_chain": f"(page {group_start_page})",
                            "page": group_start_page,
                            "chunk_index": len(chunks),
                            "workspace": workspace,
                        }
                    ))
                group = []

        # flush remainder
        if group:
            body = "\n".join(group).strip()
            if len(body) >= self.min_chunk_length:
                chunks.append(Chunk(
                    text=body,
                    metadata={
                        "source": source,
                        "heading": f"(page {group_start_page})",
                        "heading_chain": f"(page {group_start_page})",
                        "page": group_start_page,
                        "chunk_index": len(chunks),
                        "workspace": workspace,
                    }
                ))

        return chunks

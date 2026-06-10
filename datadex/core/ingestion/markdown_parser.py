"""
Ken — Markdown Document Parser

Splits markdown files into chunks by heading hierarchy.
Each chunk preserves its heading chain as metadata for context.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chunk:
    """A single document chunk with metadata."""
    text: str
    metadata: dict = field(default_factory=dict)


class MarkdownParser:
    """Parse .md files into heading-based chunks for vector indexing."""

    def __init__(self, min_chunk_length: int = 20):
        self.min_chunk_length = min_chunk_length

    def parse_file(self, filepath: str, workspace: str = "") -> List[Chunk]:
        """Parse a single markdown file into chunks.

        Args:
            filepath: Path to the .md file
            workspace: Workspace name for metadata

        Returns:
            List of Chunk objects with text and metadata
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        return self._chunk_by_headings(content, filepath, workspace)

    def _chunk_by_headings(
        self, content: str, filepath: str, workspace: str
    ) -> List[Chunk]:
        """Split content by markdown headings (## or ###)."""
        source_name = os.path.basename(filepath)
        chunks = []
        heading_chain: List[str] = []
        current_section_lines: List[str] = []
        current_heading = ""

        for line in content.split("\n"):
            heading_match = re.match(r"^(#{2,3})\s+(.+)$", line)

            if heading_match:
                # Flush current section
                if current_section_lines:
                    body = "\n".join(current_section_lines).strip()
                    if len(body) >= self.min_chunk_length:
                        heading_text = " > ".join(
                            filter(None, [current_heading] if not current_heading.startswith("#") else heading_chain)
                        )
                        # Build full text with heading context
                        full_text = f"{' > '.join(heading_chain)}\n\n{body}" if heading_chain else body
                        chunks.append(Chunk(
                            text=full_text,
                            metadata={
                                "source": source_name,
                                "heading": heading_text,
                                "heading_chain": " > ".join(heading_chain),
                                "chunk_index": len(chunks),
                                "workspace": workspace,
                            }
                        ))
                    current_section_lines = []

                # Update heading chain
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()

                if level == 2:
                    # ## - reset chain to this heading
                    heading_chain = [heading_text]
                elif level == 3:
                    # ### - subheading under current ##
                    if heading_chain:
                        heading_chain = [heading_chain[0], heading_text]
                    else:
                        heading_chain = [heading_text]

                current_heading = heading_text
            else:
                if line.strip():  # skip empty leading lines
                    current_section_lines.append(line)

        # Flush last section
        if current_section_lines:
            body = "\n".join(current_section_lines).strip()
            if len(body) >= self.min_chunk_length:
                heading_text = " > ".join(heading_chain) if heading_chain else "(no heading)"
                full_text = f"{' > '.join(heading_chain)}\n\n{body}" if heading_chain else body
                chunks.append(Chunk(
                    text=full_text,
                    metadata={
                        "source": source_name,
                        "heading": heading_text,
                        "heading_chain": " > ".join(heading_chain),
                        "chunk_index": len(chunks),
                        "workspace": workspace,
                    }
                ))

        return chunks

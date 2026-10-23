import re
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """Represents a chunk of a technical runbook or post-mortem."""
    id: str
    document_id: str
    title: str
    section: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class MarkdownChunker:
    """Intelligent chunker for technical Markdown runbooks and post-mortems.
    Preserves section context, header hierarchies, and code blocks intact.
    """

    @staticmethod
    def chunk_markdown(doc_id: str, title: str, content: str, default_metadata: Dict[str, Any] = None) -> List[DocumentChunk]:
        metadata = default_metadata.copy() if default_metadata else {}

        # Extract top-level metadata from frontmatter or text if present
        service_match = re.search(r"\*\*Service\*\*:\s*`?([a-zA-Z0-9_\-]+)`?", content)
        if service_match:
            metadata["service"] = service_match.group(1)

        severity_match = re.search(r"\*\*Severity Level\*\*:\s*([a-zA-Z0-9_\-/\s]+)", content)
        if severity_match:
            metadata["severity"] = severity_match.group(1).strip()

        # Split content by top-level markdown sections (##) to keep sub-steps intact
        sections = re.split(r"\n(?=##\s+)", content)
        chunks: List[DocumentChunk] = []

        chunk_idx = 0
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue

            # Extract heading (## Heading)
            heading_match = re.match(r"^##\s+(.+)$", sec, re.MULTILINE)
            section_title = heading_match.group(1).strip() if heading_match else "Overview"

            chunk_id = f"{doc_id}_chunk_{chunk_idx}"
            chunk_metadata = metadata.copy()
            chunk_metadata["section"] = section_title

            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    document_id=doc_id,
                    title=title,
                    section=section_title,
                    content=sec,
                    metadata=chunk_metadata
                )
            )
            chunk_idx += 1

        return chunks

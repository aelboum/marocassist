"""Split an item body into retrieval chunks (search architecture section 3,
`knowledge_chunks`).

Body format: plain paragraphs separated by blank lines. A line of the form
`## Heading` starts a section; its heading is stored with every chunk of
that section. No other markup is allowed (the sanitiser refuses it).

Paragraphs are packed into chunks of at most `TARGET_CHARS`. A paragraph
longer than that is split at sentence ends. A single sentence longer than
`MAX_CHARS` (the database limit) cannot be chunked and is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

TARGET_CHARS: Final = 800
MAX_CHARS: Final = 1200
MAX_HEADING_CHARS: Final = 200

_HEADING: Final = re.compile(r"^##[ \t]+(\S.*)$")
_SENTENCE_END: Final = re.compile(r"(?<=[.!?" + chr(0x061F) + r"])\s+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading: str | None
    body: str


class ChunkingError(ValueError):
    pass


def _sections(body: str) -> list[tuple[str | None, list[str]]]:
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            sections[-1][1].append(" ".join(paragraph))
            paragraph.clear()

    for raw in body.split("\n"):
        line = raw.strip()
        heading = _HEADING.match(line)
        if heading:
            flush()
            title = heading.group(1).strip()
            if len(title) > MAX_HEADING_CHARS:
                raise ChunkingError(f"heading longer than {MAX_HEADING_CHARS} characters")
            sections.append((title, []))
        elif line.startswith("#"):
            raise ChunkingError("only '## Heading' lines are allowed as headings")
        elif not line:
            flush()
        else:
            paragraph.append(line)
    flush()
    return [(h, ps) for h, ps in sections if ps]


def _pieces(paragraph: str) -> list[str]:
    if len(paragraph) <= TARGET_CHARS:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(paragraph):
        if len(sentence) > MAX_CHARS:
            raise ChunkingError(f"a sentence is longer than {MAX_CHARS} characters")
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > TARGET_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_body(body: str) -> list[Chunk]:
    """Chunks in reading order, numbered from 0. Raises `ChunkingError`."""
    chunks: list[Chunk] = []
    for heading, paragraphs in _sections(body):
        current = ""
        for paragraph in paragraphs:
            for piece in _pieces(paragraph):
                candidate = f"{current}\n\n{piece}" if current else piece
                if current and len(candidate) > TARGET_CHARS:
                    chunks.append(Chunk(len(chunks), heading, current))
                    current = piece
                else:
                    current = candidate
        if current:
            chunks.append(Chunk(len(chunks), heading, current))
    if not chunks:
        raise ChunkingError("body has no text")
    return chunks

"""
Step 1 — Document parser
Reads a .docx file and returns clean text with structural markers.
Handles invalid XML characters that sometimes appear in .docx files.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from docx import Document
import io
import re


# Characters invalid in XML 1.0 (except tab \x09, newline \x0A, carriage return \x0D)
_INVALID_XML_CHARS = re.compile(
    r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\uFFFE\uFFFF]'
)

def _sanitise_bytes(data: bytes) -> bytes:
    """
    Strip invalid XML control characters from raw .docx bytes.
    .docx files are ZIP archives containing XML — invalid chars
    cause lxml to throw PCDATA errors during parsing.
    """
    try:
        text = data.decode("utf-8", errors="replace")
        text = _INVALID_XML_CHARS.sub("", text)
        return text.encode("utf-8")
    except Exception:
        return data


def parse_docx(file) -> dict:
    """
    Parse an uploaded .docx file.
    Returns:
        {
            "full_text": str,
            "sections":  list[dict],  # [{heading, content}]
            "tables":    list[str],   # table rows as text
        }
    """
    raw_bytes = file.read() if hasattr(file, "read") else file

    # Try parsing directly first; fall back to sanitised bytes on XML error
    doc = None
    for attempt_bytes in [raw_bytes, _sanitise_bytes(raw_bytes)]:
        try:
            doc = Document(io.BytesIO(attempt_bytes))
            break
        except Exception:
            continue

    if doc is None:
        raise ValueError(
            "Could not parse the .docx file. "
            "The file may be corrupted or password-protected. "
            "Try re-saving it from Microsoft Word."
        )

    sections     = []
    tables_text  = []
    current_heading    = "Introduction"
    current_paragraphs = []

    # Extract tables
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables_text.append("\n".join(rows))

    # Extract paragraphs
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name.lower() if para.style else ""
        is_heading = (
            "heading" in style_name
            or (para.runs and any(r.bold for r in para.runs))
        )

        if is_heading and len(text) < 120:
            if current_paragraphs:
                sections.append({
                    "heading": current_heading,
                    "content": " ".join(current_paragraphs),
                })
            current_heading    = text
            current_paragraphs = []
        else:
            current_paragraphs.append(text)

    if current_paragraphs:
        sections.append({
            "heading": current_heading,
            "content": " ".join(current_paragraphs),
        })

    # Build full text
    parts = []
    for section in sections:
        parts.append(f"## {section['heading']}\n{section['content']}")
    for i, table in enumerate(tables_text):
        parts.append(f"## Table {i+1}\n{table}")

    full_text = "\n\n".join(parts)
    full_text = _clean_text(full_text)

    return {
        "full_text": full_text,
        "sections":  sections,
        "tables":    tables_text,
    }


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and common boilerplate."""
    text = _INVALID_XML_CHARS.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"(?im)^page \d+ of \d+$", "", text)
    text = re.sub(r"(?im)^confidential.*$", "", text)
    return text.strip()
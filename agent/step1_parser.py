"""
Step 1 — Document parser
Reads a .docx file and returns clean text with structural markers.
"""

from docx import Document
import io
import re


def parse_docx(file) -> dict:
    """
    Parse an uploaded .docx file (Streamlit UploadedFile or file-like object).
    Returns:
        {
            "full_text": str,          # clean concatenated text
            "sections": list[dict],    # [{heading, content}]
            "tables": list[list[str]], # extracted table rows as text
        }
    """
    file_bytes = file.read() if hasattr(file, "read") else file
    doc = Document(io.BytesIO(file_bytes))

    sections = []
    current_heading = "Introduction"
    current_paragraphs = []

    tables_text = []

    # Extract tables first
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables_text.append("\n".join(rows))

    # Extract paragraphs with heading detection
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name.lower() if para.style else ""
        is_heading = "heading" in style_name or para.runs and any(
            r.bold for r in para.runs
        )

        if is_heading and len(text) < 120:
            if current_paragraphs:
                sections.append({
                    "heading": current_heading,
                    "content": " ".join(current_paragraphs),
                })
            current_heading = text
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
        "sections": sections,
        "tables": tables_text,
    }


def _clean_text(text: str) -> str:
    """Remove excessive whitespace, page numbers, and common boilerplate."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Remove common footer/header noise
    text = re.sub(r"(?im)^page \d+ of \d+$", "", text)
    text = re.sub(r"(?im)^confidential.*$", "", text)
    return text.strip()

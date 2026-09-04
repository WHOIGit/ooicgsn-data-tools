"""Small shared PDF-text-extraction helper used by the per-instrument parsers."""

import pdfplumber


def extract_text(filepath: str) -> str:
    """Return the full text of a PDF using pdfplumber."""
    text_parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)

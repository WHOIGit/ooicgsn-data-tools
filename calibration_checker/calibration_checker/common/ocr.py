"""
Shared OCR helper for calibration PDFs that are scanned images with no
embedded text layer (as opposed to text-based PDFs, which
``common.pdf_text.extract_text`` handles directly).

Used by any per-instrument parser that needs to fall back to OCR — CDOM's
characterisation sheets always need it; other instruments (e.g. PARAD-K)
only need it for the subset of certificates that turn out to be scanned
rather than text-based.
"""

from __future__ import annotations


def ocr_pdf_text(filepath: str, dpi: int = 500, tesseract_cmd: str | None = None,
                  psm: int = 6) -> str:
    """
    Rasterise a PDF with pdf2image and return OCR text via pytesseract.

    If Tesseract is not on your PATH, pass tesseract_cmd (or set it once
    at the call site's module level), e.g.:

        ocr_pdf_text(path, tesseract_cmd=r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
    """
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import ImageFilter, ImageEnhance

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    images = convert_from_path(filepath, dpi=dpi)
    pages = []
    for img in images:
        img = img.convert("L")
        img = img.filter(ImageFilter.SHARPEN).filter(ImageFilter.SHARPEN)
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = img.point(lambda x: 0 if x < 150 else 255, "1")
        pages.append(pytesseract.image_to_string(img, config=f"--psm {psm}"))
    return "\n".join(pages)

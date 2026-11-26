"""Tipul fisierului dupa continut (magic bytes), niciodata dupa extensie."""
from __future__ import annotations

import re

MIME_PNG = "image/png"
MIME_JPEG = "image/jpeg"
MIME_WEBP = "image/webp"
MIME_GIF = "image/gif"
MIME_TIFF = "image/tiff"
MIME_PDF = "application/pdf"
MIME_SVG = "image/svg+xml"
MIME_UNKNOWN = "application/octet-stream"

RASTER_MIMES = frozenset({MIME_PNG, MIME_JPEG, MIME_WEBP, MIME_GIF, MIME_TIFF})
SUPPORTED_MIMES = RASTER_MIMES | {MIME_PDF, MIME_SVG}

SNIFF_BYTES = 64 * 1024

_SVG_ROOT = re.compile(r"<svg[\s>]", re.IGNORECASE)
_HTML_ROOT = re.compile(r"<(?:html|body|head)[\s>]|<!doctype\s+html", re.IGNORECASE)


def decode_text(data: bytes) -> str:
    """Text din bytes, tolerant: BOM UTF-8/UTF-16, altfel UTF-8 cu inlocuire."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if data[:3] == b"\xef\xbb\xbf":
        data = data[3:]
    return data.decode("utf-8", errors="replace")


def _looks_like_svg(head: bytes) -> bool:
    if b"\x00" in head[:2048] and head[:2] not in (b"\xff\xfe", b"\xfe\xff"):
        return False
    text = decode_text(head).lstrip()
    if not text.startswith("<"):
        return False
    match = _SVG_ROOT.search(text)
    if not match:
        return False
    # un <svg> inline intr-o pagina HTML nu este un fisier SVG
    return not _HTML_ROOT.search(text[: match.start()])


def sniff_mime(head: bytes) -> str:
    """MIME dupa primii bytes. Formatele nesuportate primesc un MIME orientativ."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return MIME_PNG
    if head.startswith(b"\xff\xd8\xff"):
        return MIME_JPEG
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return MIME_GIF
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return MIME_WEBP
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return MIME_TIFF
    # antetul PDF poate fi precedat de cativa bytes; AI compatibil PDF ajunge tot aici
    if b"%PDF-" in head[:1024]:
        return MIME_PDF
    if head.startswith(b"%!PS"):
        return "application/postscript"  # EPS sau AI vechi, fara PDF
    if head.startswith(b"\xc5\xd0\xd3\xc6"):
        return "application/postscript"  # EPS binar
    if head.startswith(b"8BPS"):
        return "image/vnd.adobe.photoshop"
    if head.startswith(b"BM"):
        return "image/bmp"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
            return "image/heic"
        if brand in (b"avif", b"avis"):
            return "image/avif"
        return "video/mp4"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"  # si docx, cdr nou, afdesign etc.
    if head.startswith(b"\x1f\x8b"):
        return "application/gzip"  # si svgz: nu il despachetam
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/x-ole-storage"  # doc, cdr vechi
    if _looks_like_svg(head):
        return MIME_SVG
    return MIME_UNKNOWN

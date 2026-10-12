"""Load receipt files (images / PDFs) into normalised page images for the LLM.

Re-encoding to JPEG drops EXIF/GPS metadata, which keeps location data out of
LLM requests and caches.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PDF_EXT = ".pdf"


class UnsupportedFileError(ValueError):
    pass


@dataclass(frozen=True)
class Page:
    data: bytes
    media_type: str = "image/jpeg"


@dataclass(frozen=True)
class LoadedFile:
    name: str
    sha256: str
    pages: list[Page]
    embedded_text: str = field(default="")


def _to_page(img: Image.Image, max_side: int) -> Page:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return Page(buf.getvalue())


def load_bytes(data: bytes, filename: str, *, max_side: int = 1600, max_pdf_pages: int = 3) -> LoadedFile:
    ext = Path(filename).suffix.lower()
    sha = hashlib.sha256(data).hexdigest()

    if ext in IMAGE_EXTS:
        try:
            with Image.open(io.BytesIO(data)) as img:
                pages = [_to_page(img, max_side)]
        except OSError as e:
            raise UnsupportedFileError(f"{filename}: not a readable image ({e})") from e
        return LoadedFile(filename, sha, pages)

    if ext == PDF_EXT:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as e:  # pymupdf raises several error types
            raise UnsupportedFileError(f"{filename}: not a readable PDF ({e})") from e
        pages: list[Page] = []
        texts: list[str] = []
        with doc:
            for page in list(doc)[:max_pdf_pages]:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pages.append(_to_page(img, max_side))
                texts.append(page.get_text().strip())
        return LoadedFile(filename, sha, pages, "\n".join(t for t in texts if t))

    raise UnsupportedFileError(f"{filename}: unsupported type '{ext}'")


def load_file(path: Path, **kwargs) -> LoadedFile:
    return load_bytes(path.read_bytes(), path.name, **kwargs)

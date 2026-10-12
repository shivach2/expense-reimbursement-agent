import io

import pytest
from PIL import Image

from app.ingest import UnsupportedFileError, load_bytes


def _png(size=(3000, 1000)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_image_is_downscaled_and_reencoded_as_jpeg():
    loaded = load_bytes(_png(), "a.png", max_side=1600)
    page = loaded.pages[0]
    assert page.media_type == "image/jpeg"
    assert max(Image.open(io.BytesIO(page.data)).size) <= 1600
    assert len(loaded.sha256) == 64


def test_exif_metadata_is_stripped():
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, "JPEG", exif=exif)
    assert Image.open(io.BytesIO(buf.getvalue())).getexif()  # sanity: input has EXIF

    loaded = load_bytes(buf.getvalue(), "a.jpg")
    assert not Image.open(io.BytesIO(loaded.pages[0].data)).getexif()


def test_pdf_is_rasterised():
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(buf, "PDF")
    loaded = load_bytes(buf.getvalue(), "r.pdf")
    assert len(loaded.pages) == 1
    assert loaded.pages[0].media_type == "image/jpeg"


def test_same_bytes_same_hash():
    assert load_bytes(_png(), "a.png").sha256 == load_bytes(_png(), "b.png").sha256


def test_unsupported_extension_rejected():
    with pytest.raises(UnsupportedFileError):
        load_bytes(b"hello", "notes.txt")


def test_corrupt_image_rejected():
    with pytest.raises(UnsupportedFileError):
        load_bytes(b"not an image", "a.png")


def test_corrupt_pdf_rejected():
    with pytest.raises(UnsupportedFileError):
        load_bytes(b"not a pdf", "a.pdf")

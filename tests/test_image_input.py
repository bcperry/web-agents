"""Tests for multi-modal image input validation (spec 002).

Updated for FastAPI-based architecture — tests the validation functions
available in the new main.py.
"""

import io
import pytest
from types import SimpleNamespace
from fastapi import UploadFile

from main import (
    _validate_image_magic_bytes,
    _validate_uploaded_images,
    ALLOWED_IMAGE_MIMES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_IMAGES_PER_MESSAGE,
)


# ---------------------------------------------------------------------------
# Helpers — create UploadFile mocks
# ---------------------------------------------------------------------------

def _make_upload_file(
    mime: str = "image/png",
    filename: str = "test.png",
    data: bytes | None = None,
) -> tuple[UploadFile, bytes]:
    """Return an UploadFile and its raw bytes for testing."""
    if data is None:
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    file_obj = io.BytesIO(data)
    upload = UploadFile(filename=filename, file=file_obj, headers={"content-type": mime})
    return upload, data


_VALID_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100
_VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_VALID_GIF87_BYTES = b"GIF87a" + b"\x00" * 100
_VALID_GIF89_BYTES = b"GIF89a" + b"\x00" * 100
_VALID_WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 100


# ===========================================================================
# T006 — Test fixtures and foundational tests
# ===========================================================================


class TestValidateImageMagicBytes:
    """Test _validate_image_magic_bytes for each supported format."""

    def test_valid_jpeg(self) -> None:
        assert _validate_image_magic_bytes(_VALID_JPEG_BYTES, "image/jpeg") is True

    def test_valid_png(self) -> None:
        assert _validate_image_magic_bytes(_VALID_PNG_BYTES, "image/png") is True

    def test_valid_gif87a(self) -> None:
        assert _validate_image_magic_bytes(_VALID_GIF87_BYTES, "image/gif") is True

    def test_valid_gif89a(self) -> None:
        assert _validate_image_magic_bytes(_VALID_GIF89_BYTES, "image/gif") is True

    def test_valid_webp(self) -> None:
        assert _validate_image_magic_bytes(_VALID_WEBP_BYTES, "image/webp") is True

    def test_corrupt_jpeg_header(self) -> None:
        """Non-JPEG bytes claiming to be JPEG should fail."""
        assert _validate_image_magic_bytes(b"\x00\x00\x00", "image/jpeg") is False

    def test_corrupt_png_header(self) -> None:
        assert _validate_image_magic_bytes(b"\x00\x00\x00\x00\x00\x00\x00\x00", "image/png") is False

    def test_corrupt_gif_header(self) -> None:
        assert _validate_image_magic_bytes(b"NOTGIF", "image/gif") is False

    def test_corrupt_webp_header(self) -> None:
        assert _validate_image_magic_bytes(b"RIFF\x00\x00\x00\x00NOPE", "image/webp") is False

    def test_empty_data(self) -> None:
        assert _validate_image_magic_bytes(b"", "image/jpeg") is False
        assert _validate_image_magic_bytes(b"", "image/png") is False
        assert _validate_image_magic_bytes(b"", "image/webp") is False

    def test_unknown_mime(self) -> None:
        """Unknown MIME types should fail validation."""
        assert _validate_image_magic_bytes(b"\xff\xd8\xff", "image/tiff") is False


class TestValidateUploadedImages:
    """Test _validate_uploaded_images for count, MIME, size, and header checks."""

    def test_valid_single_image(self) -> None:
        f, data = _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES)
        error = _validate_uploaded_images([f], [data])
        assert error is None

    def test_valid_multiple_images(self) -> None:
        f1, d1 = _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES, filename="a.png")
        f2, d2 = _make_upload_file(mime="image/jpeg", data=_VALID_JPEG_BYTES, filename="b.jpg")
        error = _validate_uploaded_images([f1, f2], [d1, d2])
        assert error is None

    def test_valid_five_images(self) -> None:
        pairs = [
            _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES, filename=f"img{i}.png")
            for i in range(5)
        ]
        files = [p[0] for p in pairs]
        datas = [p[1] for p in pairs]
        error = _validate_uploaded_images(files, datas)
        assert error is None

    def test_exceeds_max_images(self) -> None:
        pairs = [
            _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES, filename=f"img{i}.png")
            for i in range(6)
        ]
        files = [p[0] for p in pairs]
        datas = [p[1] for p in pairs]
        error = _validate_uploaded_images(files, datas)
        assert error is not None
        assert "Maximum of 5 images" in error

    def test_invalid_mime_type(self) -> None:
        f, data = _make_upload_file(mime="application/pdf", filename="doc.pdf", data=b"fake")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "Only image files are accepted" in error
        assert "'doc.pdf'" in error

    def test_file_too_large(self) -> None:
        huge_data = b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_SIZE_BYTES + 1)
        f, data = _make_upload_file(mime="image/jpeg", data=huge_data, filename="big.jpg")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "exceeds the maximum file size" in error
        assert "'big.jpg'" in error

    def test_corrupt_header(self) -> None:
        corrupt_data = b"\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 100
        f, data = _make_upload_file(mime="image/png", data=corrupt_data, filename="corrupt.png")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "could not be processed" in error
        assert "'corrupt.png'" in error

    def test_empty_files_list(self) -> None:
        error = _validate_uploaded_images([], [])
        assert error is None


# ===========================================================================
# T011 — User Story 1 tests
# ===========================================================================


class TestMimeTypeValidation:
    """Test MIME type validation rejects non-image types (FR-003)."""

    @pytest.mark.parametrize(
        "bad_mime",
        [
            "application/pdf",
            "text/plain",
            "application/json",
            "video/mp4",
            "audio/mpeg",
            "application/octet-stream",
        ],
    )
    def test_rejects_non_image_mime(self, bad_mime: str) -> None:
        f, data = _make_upload_file(mime=bad_mime, data=b"fake", filename="file.bin")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "Only image files are accepted" in error


class TestSizeValidation:
    """Test size validation rejects > 400 MB (FR-007)."""

    def test_rejects_oversized_image(self) -> None:
        huge = b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_SIZE_BYTES + 1)
        f, data = _make_upload_file(mime="image/jpeg", data=huge, filename="huge.jpg")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "exceeds the maximum file size" in error

    def test_accepts_exactly_max_size(self) -> None:
        """400 MB exactly should be accepted."""
        data = b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_SIZE_BYTES - 3)
        f, d = _make_upload_file(mime="image/jpeg", data=data, filename="max.jpg")
        error = _validate_uploaded_images([f], [d])
        assert error is None


class TestMagicByteValidationCatchesCorrupt:
    """Test magic byte validation catches corrupt files (FR-009)."""

    def test_png_mime_with_jpeg_bytes(self) -> None:
        """Claiming PNG but having JPEG bytes should fail."""
        f, data = _make_upload_file(mime="image/png", data=_VALID_JPEG_BYTES, filename="mislabeled.png")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "could not be processed" in error

    def test_jpeg_mime_with_random_bytes(self) -> None:
        f, data = _make_upload_file(mime="image/jpeg", data=b"\x00\x01\x02\x03" * 30, filename="random.jpg")
        error = _validate_uploaded_images([f], [data])
        assert error is not None
        assert "could not be processed" in error


class TestContentCreation:
    """Test Content.from_data/from_text work correctly."""

    def test_single_image_produces_data_content(self) -> None:
        from agent_framework._types import Content
        content = Content.from_data(data=_VALID_PNG_BYTES, media_type="image/png")
        assert content.type == "data"

    def test_text_only_content(self) -> None:
        from agent_framework._types import Content
        text_content = Content.from_text("Hello, world!")
        contents = [text_content]
        assert len(contents) == 1
        assert contents[0].type == "text"


class TestMultiImageValidation:
    """Test multi-image validation."""

    def test_two_images_accepted(self) -> None:
        f1, d1 = _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES, filename="a.png")
        f2, d2 = _make_upload_file(mime="image/jpeg", data=_VALID_JPEG_BYTES, filename="b.jpg")
        error = _validate_uploaded_images([f1, f2], [d1, d2])
        assert error is None

    def test_five_images_accepted(self) -> None:
        pairs = [
            _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES, filename=f"img{i}.png")
            for i in range(5)
        ]
        files = [p[0] for p in pairs]
        datas = [p[1] for p in pairs]
        error = _validate_uploaded_images(files, datas)
        assert error is None

    def test_six_images_rejected(self) -> None:
        """6 images should be rejected at the validation step (FR-006)."""
        pairs = [
            _make_upload_file(mime="image/png", data=_VALID_PNG_BYTES, filename=f"img{i}.png")
            for i in range(6)
        ]
        files = [p[0] for p in pairs]
        datas = [p[1] for p in pairs]
        error = _validate_uploaded_images(files, datas)
        assert error is not None
        assert "Maximum of 5 images" in error


# ===========================================================================
# Source inspection tests — verify main.py structure
# ===========================================================================


class TestStreamAgentResponseSignature:
    """Verify _stream_agent_response accepts contents: list[Content]."""

    def test_signature_has_contents_param(self) -> None:
        import inspect
        from main import _stream_agent_response

        sig = inspect.signature(_stream_agent_response)
        assert "contents" in sig.parameters

    def test_is_async_generator(self) -> None:
        import inspect
        from main import _stream_agent_response

        assert inspect.isasyncgenfunction(_stream_agent_response)


class TestSendMessageEndpoint:
    """Verify send_message endpoint handles images and errors."""

    def test_send_message_has_validation(self) -> None:
        import inspect
        import main

        source = inspect.getsource(main.send_message)
        assert "_validate_uploaded_images" in source

    def test_send_message_builds_contents_list(self) -> None:
        import inspect
        import main

        source = inspect.getsource(main.send_message)
        assert "Content.from_text" in source

    def test_send_message_handles_image_errors(self) -> None:
        import inspect
        import main

        source = inspect.getsource(main.send_message)
        assert "could not be processed" in source

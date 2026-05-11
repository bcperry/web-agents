"""Tests for shared validation helpers."""

import io

import pytest
from fastapi import HTTPException, UploadFile

from validators import (
    ALLOWED_IMAGE_MIMES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_IMAGES_PER_MESSAGE,
    available_skill_names,
    filter_known_skill_names,
    validate_custom_name,
    validate_http_mcp_servers,
    validate_image_magic_bytes,
    validate_prompt,
    validate_temperature,
    validate_tool_names,
    validate_uploaded_images,
)


def _upload(mime: str, filename: str, data: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data), headers={"content-type": mime})


VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
VALID_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
VALID_WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16


def test_image_constants_preserved():
    assert ALLOWED_IMAGE_MIMES == {"image/jpeg", "image/png", "image/gif", "image/webp"}
    assert MAX_IMAGE_SIZE_BYTES == 400 * 1024 * 1024
    assert MAX_IMAGES_PER_MESSAGE == 5


def test_validate_image_magic_bytes_supported_types():
    assert validate_image_magic_bytes(VALID_JPEG, "image/jpeg") is True
    assert validate_image_magic_bytes(VALID_PNG, "image/png") is True
    assert validate_image_magic_bytes(b"GIF87a" + b"\x00", "image/gif") is True
    assert validate_image_magic_bytes(b"GIF89a" + b"\x00", "image/gif") is True
    assert validate_image_magic_bytes(VALID_WEBP, "image/webp") is True
    assert validate_image_magic_bytes(b"not an image", "image/png") is False


def test_validate_uploaded_images_rejects_bad_mime_size_count_and_corruption():
    assert validate_uploaded_images([_upload("image/png", "ok.png", VALID_PNG)], [VALID_PNG]) is None

    too_many = [_upload("image/png", f"{index}.png", VALID_PNG) for index in range(6)]
    assert "Maximum of 5 images" in (validate_uploaded_images(too_many, [VALID_PNG] * 6) or "")

    assert "Only image files" in (validate_uploaded_images([_upload("text/plain", "bad.txt", b"x")], [b"x"]) or "")

    huge = b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_SIZE_BYTES + 1)
    assert "maximum file size" in (validate_uploaded_images([_upload("image/jpeg", "huge.jpg", huge)], [huge]) or "")

    assert "could not be processed" in (
        validate_uploaded_images([_upload("image/png", "corrupt.png", b"nope")], [b"nope"]) or ""
    )


def test_validate_temperature_accepts_range_and_rejects_invalid_values():
    assert validate_temperature(None) is None
    assert validate_temperature("0.7") == 0.7
    assert validate_temperature(0) == 0.0
    assert validate_temperature(2) == 2.0

    with pytest.raises(HTTPException) as not_number:
        validate_temperature("warm")
    assert not_number.value.status_code == 400
    assert "must be a number" in not_number.value.detail

    with pytest.raises(HTTPException) as out_of_range:
        validate_temperature(2.1)
    assert out_of_range.value.status_code == 400
    assert "between 0.0 and 2.0" in out_of_range.value.detail


def test_validate_custom_name_and_prompt_bounds():
    assert validate_custom_name("  Agent Name  ") == "Agent Name"
    assert validate_prompt("  instructions  ", max_chars=20) == "instructions"

    with pytest.raises(HTTPException):
        validate_custom_name("")
    with pytest.raises(HTTPException):
        validate_custom_name("x" * 101)
    with pytest.raises(HTTPException):
        validate_prompt("", max_chars=20)
    with pytest.raises(HTTPException):
        validate_prompt("x" * 21, max_chars=20)


def test_validate_tool_and_skill_names():
    known_tools = {"get_user_profile", "save_user_profile"}
    assert validate_tool_names(["get_user_profile"], known_tools) == ["get_user_profile"]

    with pytest.raises(HTTPException) as bad_tools:
        validate_tool_names(["missing_tool"], known_tools)
    assert bad_tools.value.detail == "Unknown tools: missing_tool"

    with pytest.raises(HTTPException):
        validate_tool_names("get_user_profile", known_tools)  # type: ignore[arg-type]

    kept, dropped = filter_known_skill_names(["table-usage", "unknown"], {"table-usage"})
    assert kept == ["table-usage"]
    assert dropped == ["unknown"]
    with pytest.raises(HTTPException):
        filter_known_skill_names("table-usage", {"table-usage"})  # type: ignore[arg-type]


def test_available_skill_names_reads_skill_provider(tmp_path, make_skill):
    make_skill(tmp_path, "alpha", "Alpha")
    assert available_skill_names(tmp_path) == {"alpha"}
    assert available_skill_names(tmp_path / "missing") == set()


def test_validate_http_mcp_servers_accepts_only_request_http_servers():
    raw = [{"name": "docs", "transport": "http", "url": "https://example.test/mcp"}]
    assert validate_http_mcp_servers(raw, override=False) == raw

    with pytest.raises(HTTPException) as bad_container:
        validate_http_mcp_servers({}, override=False)  # type: ignore[arg-type]
    assert bad_container.value.detail == "mcp_servers must be a list"

    with pytest.raises(HTTPException) as bad_transport:
        validate_http_mcp_servers([{"name": "local", "transport": "stdio"}], override=False)
    assert "Custom agents only support 'http' MCP servers" in bad_transport.value.detail

    with pytest.raises(HTTPException) as missing_url:
        validate_http_mcp_servers([{"name": "docs", "transport": "http"}], override=True)
    assert "requires a 'url'" in missing_url.value.detail
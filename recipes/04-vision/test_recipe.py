"""Tests for recipe 04."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

from common.client import CookbookClient
from recipes._fixtures import FakeTextBlock, FakeUsage, build_response

from .recipe import (
    DEFAULT_IMAGE_B64,
    InvoiceExtraction,
    build_image_block,
    encode_image,
    extract_invoice,
)


def _client(*responses: object) -> CookbookClient:
    raw = MagicMock()
    raw.messages.create.side_effect = list(responses)
    return CookbookClient.with_raw_client(raw)


SAMPLE_PAYLOAD = {
    "vendor_name": "ACME Supply Company",
    "invoice_number": "INV-2026-04217",
    "issue_date": "2026-04-15",
    "due_date": "2026-05-15",
    "total_usd": 153.01,
    "currency": "USD",
    "line_items": [
        {"sku": "A-440", "description": "Stainless fasteners", "qty": 24, "unit_price": 0.75, "total": 18.00},
        {"sku": "B-112", "description": "Neoprene gaskets", "qty": 12, "unit_price": 2.10, "total": 25.20},
        {"sku": "C-099", "description": "Industrial adhesive", "qty": 2, "unit_price": 42.00, "total": 84.00},
    ],
}


def test_build_image_block_shape() -> None:
    block = build_image_block(DEFAULT_IMAGE_B64, "image/png")
    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/png"
    assert block["source"]["data"] == DEFAULT_IMAGE_B64


def test_encode_image_infers_media_type(tmp_path: Path) -> None:
    jpg = tmp_path / "x.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xe0fake")
    b64, media = encode_image(jpg)
    assert media == "image/jpeg"
    assert base64.b64decode(b64) == b"\xff\xd8\xff\xe0fake"


def test_invoice_model_accepts_valid_payload() -> None:
    parsed = InvoiceExtraction.model_validate(SAMPLE_PAYLOAD)
    assert parsed.vendor_name == "ACME Supply Company"
    assert parsed.total_usd == 153.01
    assert len(parsed.line_items) == 3


def test_extract_invoice_parses_happy_path() -> None:
    response = build_response(
        content=[FakeTextBlock(json.dumps(SAMPLE_PAYLOAD))],
        usage=FakeUsage(800, 220),
        stop_reason="end_turn",
    )
    client = _client(response)
    result = extract_invoice(client=client, image_b64=DEFAULT_IMAGE_B64)
    assert result["ok"] is True
    assert result["parsed"]["invoice_number"] == "INV-2026-04217"
    assert len(result["parsed"]["line_items"]) == 3


def test_extract_invoice_tolerates_json_code_fence() -> None:
    fenced = "```json\n" + json.dumps(SAMPLE_PAYLOAD) + "\n```"
    response = build_response(
        content=[FakeTextBlock(fenced)],
        usage=FakeUsage(800, 220),
        stop_reason="end_turn",
    )
    client = _client(response)
    result = extract_invoice(client=client, image_b64=DEFAULT_IMAGE_B64)
    assert result["ok"] is True


def test_extract_invoice_returns_structured_error_on_bad_json() -> None:
    response = build_response(
        content=[FakeTextBlock("This is not JSON at all")],
        usage=FakeUsage(100, 10),
        stop_reason="end_turn",
    )
    client = _client(response)
    result = extract_invoice(client=client, image_b64=DEFAULT_IMAGE_B64)
    assert result["ok"] is False
    assert "json_decode_error" in result["error"]


def test_extract_invoice_returns_schema_error_on_bad_shape() -> None:
    bad = {"vendor_name": "ACME"}  # missing required keys
    response = build_response(
        content=[FakeTextBlock(json.dumps(bad))],
        usage=FakeUsage(100, 10),
        stop_reason="end_turn",
    )
    client = _client(response)
    result = extract_invoice(client=client, image_b64=DEFAULT_IMAGE_B64)
    assert result["ok"] is False
    assert "schema_validation_error" in result["error"]
    assert "raw_json" in result

"""Recipe 04: vision-driven structured extraction.

The use case is invoice processing: hand Claude an image of an invoice and
get back a strictly-typed JSON payload (vendor, total, line items, etc.).

Two sub-patterns combine here:

1. **Image content blocks.** Claude accepts ``image`` blocks with a ``source``
   of ``type: "base64"``. We build them from either a real image path or the
   placeholder PNG shipped in ``samples/``.
2. **Structured output via Pydantic.** We give Claude a JSON-only response
   contract, parse the response with Pydantic, and surface validation errors
   as actionable diagnostics rather than letting them crash the caller.

The recipe is written so swapping the placeholder PNG for a real invoice
image requires zero code changes — pass ``--image path/to/invoice.png``.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from common.client import CookbookClient
from common.logging import get_logger, setup_logging

logger = get_logger(__name__)

SAMPLES = Path(__file__).parent / "samples"
DEFAULT_IMAGE_B64 = (SAMPLES / "minimal_pixel.png.b64").read_text(encoding="utf-8").strip()
DEFAULT_MEDIA_TYPE = "image/png"


SYSTEM_PROMPT = (
    "You extract structured invoice data from document images. Respond with "
    "a single JSON object matching the schema provided. Do not add "
    "commentary, markdown fences, or keys outside the schema. If a field is "
    "not visible in the image, set it to null."
)

RESPONSE_SCHEMA_DOC = (
    "Return a JSON object with exactly these keys:\n"
    '  "vendor_name": string,\n'
    '  "invoice_number": string,\n'
    '  "issue_date": string (YYYY-MM-DD or null),\n'
    '  "due_date":   string (YYYY-MM-DD or null),\n'
    '  "total_usd":  number,\n'
    '  "currency":   string (ISO 4217, e.g. "USD"),\n'
    '  "line_items": array of {"sku": string, "description": string, "qty": number, "unit_price": number, "total": number}\n'
)


# ---------------------------------------------------------------------------
# Pydantic response model
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    sku: str
    description: str
    qty: float = Field(..., ge=0)
    unit_price: float = Field(..., ge=0)
    total: float = Field(..., ge=0)


class InvoiceExtraction(BaseModel):
    vendor_name: str
    invoice_number: str
    issue_date: str | None = None
    due_date: str | None = None
    total_usd: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    line_items: list[LineItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

MediaType = Literal["image/png", "image/jpeg", "image/gif", "image/webp"]


def encode_image(path: Path) -> tuple[str, MediaType]:
    """Read ``path``, base64-encode, and infer a media type from its suffix."""
    suffix = path.suffix.lower()
    media: MediaType = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix, "image/png")  # type: ignore[assignment]
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return data, media


def build_image_block(b64: str, media_type: MediaType) -> dict[str, Any]:
    """Return an Anthropic ``image`` content block."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64,
        },
    }


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------


def _strip_json_fence(text: str) -> str:
    """Strip an optional ```json fence so lenient Claude outputs still parse."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # remove the opening fence line and any language tag
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def extract_invoice(
    *,
    client: CookbookClient,
    image_b64: str = DEFAULT_IMAGE_B64,
    media_type: MediaType = DEFAULT_MEDIA_TYPE,
    caption: str = "Extract fields from this invoice image.",
) -> dict[str, Any]:
    """Send ``image_b64`` to Claude and return a validated extraction.

    The result dictionary always contains ``raw_text``. On successful parse it
    also contains ``parsed`` (the :class:`InvoiceExtraction` serialized).
    On validation failure it contains ``error`` so callers can inspect what
    went wrong without re-parsing.
    """

    user_content = [
        build_image_block(image_b64, media_type),
        {
            "type": "text",
            "text": f"{caption}\n\n{RESPONSE_SCHEMA_DOC}",
        },
    ]
    response = client.create_message(
        messages=[{"role": "user", "content": user_content}],
        system=SYSTEM_PROMPT,
        max_tokens=1024,
        temperature=0.0,
    )
    raw_text = _strip_json_fence(response.text)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": f"json_decode_error: {exc}",
            "raw_text": response.text,
            "usage": client.ledger.summary(),
        }

    try:
        extraction = InvoiceExtraction.model_validate(payload)
    except ValidationError as exc:
        return {
            "ok": False,
            "error": f"schema_validation_error: {exc.errors()}",
            "raw_text": response.text,
            "raw_json": payload,
            "usage": client.ledger.summary(),
        }

    return {
        "ok": True,
        "parsed": extraction.model_dump(),
        "raw_text": response.text,
        "usage": client.ledger.summary(),
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 04 — vision invoice extraction")
    parser.add_argument("--image", type=Path, default=None, help="Path to a real image; default uses the shipped placeholder.")
    parser.add_argument(
        "--media-type",
        default=DEFAULT_MEDIA_TYPE,
        choices=["image/png", "image/jpeg", "image/gif", "image/webp"],
    )
    parser.add_argument("--caption", default="Extract fields from this invoice image.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()

    if args.image is not None:
        b64, media_type = encode_image(args.image)
    else:
        b64, media_type = DEFAULT_IMAGE_B64, DEFAULT_MEDIA_TYPE

    result = extract_invoice(
        client=client,
        image_b64=b64,
        media_type=media_type,  # type: ignore[arg-type]
        caption=args.caption,
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())

# Vision

Claude can accept images alongside text. Images are supplied as content blocks
of type `image` with either a `base64` source (for uploaded bytes) or a `url`
source (for hosted files). Supported formats include PNG, JPEG, GIF, and
WebP. Each image is tokenized; larger images consume more input tokens.

Vision is suitable for document OCR, chart interpretation, UI screenshot
analysis, and structured extraction from forms. For very large documents,
paginate into multiple images and process each batch within the per-request
token budget.

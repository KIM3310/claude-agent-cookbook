# Sample images

These are placeholders used so the recipe can be run and tested without
shipping large binary assets.

- `sample_invoice.txt` — a plain-text representation of an invoice. The
  recipe encodes it as base64 and treats the bytes as a "document" only so
  that `recipe.py` exercises the full base64-upload code path.
- `minimal_pixel.png.b64` — a 1x1 pixel white PNG encoded as base64. This is
  enough to exercise the `image/png` content-block shape.

For production use, swap in real PNG/JPEG files. The `build_image_block`
helper in `recipe.py` accepts any bytes plus a media type.

## How to test with a real image

```bash
python recipes/04-vision/recipe.py \
    --image ~/Downloads/my_invoice.png \
    --media-type image/png
```

The recipe base64-encodes the bytes and includes them as an `image`
content block in the user turn.

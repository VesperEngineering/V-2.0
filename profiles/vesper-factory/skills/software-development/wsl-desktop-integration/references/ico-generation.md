# Multi-Resolution ICO Generation from Python

PIL's `Image.save(..., format="ICO", append_images=...)` **does not produce valid multi-image ICOs**. It only writes the first image. Windows needs multiple resolutions (16, 32, 48, 256 px) for crisp icons at different sizes.

## Working Method: Manual ICO Construction with PNG Payloads

Modern Windows supports PNG-compressed images inside ICO files. This is the simplest reliable method.

```python
import struct
import io
from PIL import Image, ImageDraw

def make_icon(path):
    sizes = [16, 32, 48, 256]
    images = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw a simple white diamond (monochrome/minimalist)
        pad = int(size * 0.2)
        diamond = [
            (size // 2, pad),
            (size - pad, size // 2),
            (size // 2, size - pad),
            (pad, size // 2),
        ]
        draw.polygon(diamond, fill=(220, 220, 220, 255))
        images.append(img)

    # Build ICO directory + PNG payloads
    entries = []
    payload = b""
    offset = 6 + 16 * len(images)
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
        w, h = img.size
        entries.append((w if w < 256 else 0, h if h < 256 else 0, 0, 0, 1, 32, len(png), offset))
        payload += png
        offset += len(png)

    header = struct.pack("<HHH", 0, 1, len(images))
    dir_bytes = b"".join(struct.pack("<BBBBHHII", *e) for e in entries)

    with open(path, "wb") as f:
        f.write(header + dir_bytes + payload)
    print(f"Saved {path} with {len(images)} sizes")
```

## Verification

```python
import struct

with open(r"C:\Users\<user>\Desktop\v20\assets\dashboard.ico", "rb") as f:
    data = f.read()

count = struct.unpack("<HHH", data[:6])[2]
print(f"Images in ICO: {count}")

sizes = []
offset = 6
for i in range(count):
    w, h = data[offset], data[offset + 1]
    sizes.append(w if w else 256)
    offset += 16

print(f"Sizes found: {sizes}")  # [16, 32, 48, 256]
```

## Notes

- `w == 0` or `h == 0` in the ICO directory means 256 pixels.
- Keep shapes simple for small sizes — complex detail is invisible at 16×16.
- The user prefers **monochrome, minimalist** icons — stick to 1-2 colors, geometric shapes.

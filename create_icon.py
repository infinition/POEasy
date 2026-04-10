"""Generate a proper multi-size .ico file for POEasy using Pillow."""

import struct
import os
import sys

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poeasy.ico")

# Minimal BMP-based ICO builder (no Pillow dependency)
# Creates a simple lightning bolt icon at multiple sizes

def create_icon_bmp(size: int) -> bytes:
    """Create a 32-bit BGRA bitmap of a lightning bolt on dark circle."""
    pixels = bytearray(size * size * 4)

    cx, cy = size / 2, size / 2
    r = size / 2 - 2

    # Lightning bolt points (normalized 0-1)
    bolt_points = [
        (0.57, 0.12), (0.33, 0.49), (0.51, 0.49),
        (0.43, 0.88), (0.68, 0.46), (0.50, 0.46),
    ]

    def point_in_polygon(px, py, polygon):
        """Ray casting algorithm."""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    # Scale bolt to pixel coords
    bolt_px = [(int(x * size), int(y * size)) for x, y in bolt_points]
    # Two triangles for lightning bolt
    tri1 = [bolt_px[0], bolt_px[1], bolt_px[5]]
    tri2 = [bolt_px[2], bolt_px[3], bolt_px[4]]

    for y in range(size):
        for x in range(size):
            off = (y * size + x) * 4
            dx, dy = x - cx, y - cy
            dist = (dx * dx + dy * dy) ** 0.5

            if dist <= r:
                # Inside circle
                # Check if in bolt
                if point_in_polygon(x, y, tri1) or point_in_polygon(x, y, tri2):
                    # Gold bolt
                    pixels[off:off+4] = bytes([0, 185, 255, 255])  # BGRA: gold
                else:
                    # Dark bg with slight gradient
                    v = int(30 + 15 * (1 - dist / r))
                    pixels[off:off+4] = bytes([v + 10, v, v, 255])

                # Green border ring
                if abs(dist - r) < 2.5:
                    pixels[off:off+4] = bytes([67, 160, 46, 255])  # BGRA: green
            else:
                pixels[off:off+4] = bytes([0, 0, 0, 0])  # Transparent

    return bytes(pixels)


def build_ico(sizes=(16, 32, 48, 64, 128, 256)) -> bytes:
    """Build a .ico file with multiple image sizes."""
    entries = []
    image_data_list = []

    for s in sizes:
        bgra = create_icon_bmp(s)

        # DIB header (BITMAPINFOHEADER) — height is 2*size for ICO (includes AND mask)
        dib = struct.pack('<IiiHHIIiiII',
            40,       # header size
            s,        # width
            s * 2,    # height (doubled for ICO format)
            1,        # planes
            32,       # bpp
            0,        # compression
            len(bgra),# image size
            0, 0,     # ppm
            0, 0,     # colors
        )

        # Flip rows vertically (BMP is bottom-up)
        row_size = s * 4
        flipped = bytearray()
        for row in range(s - 1, -1, -1):
            flipped.extend(bgra[row * row_size:(row + 1) * row_size])

        # AND mask (all zeros = fully opaque since we use 32-bit alpha)
        and_mask_row = ((s + 31) // 32) * 4
        and_mask = bytes(and_mask_row * s)

        img_bytes = dib + bytes(flipped) + and_mask
        image_data_list.append(img_bytes)
        entries.append((s, img_bytes))

    # ICO header
    num = len(entries)
    ico_header = struct.pack('<HHH', 0, 1, num)

    # Directory entries (16 bytes each)
    dir_data = bytearray()
    offset = 6 + num * 16  # after header + directory

    for (s, img_bytes) in entries:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        dir_data.extend(struct.pack('<BBBBHHII',
            w,             # width (0 = 256)
            h,             # height (0 = 256)
            0,             # color palette
            0,             # reserved
            1,             # color planes
            32,            # bits per pixel
            len(img_bytes),# size of image data
            offset,        # offset to image data
        ))
        offset += len(img_bytes)

    result = ico_header + bytes(dir_data)
    for (s, img_bytes) in entries:
        result += img_bytes

    return result


def main():
    ico_data = build_ico()
    with open(OUTPUT, 'wb') as f:
        f.write(ico_data)
    print(f"Icon saved: {OUTPUT} ({len(ico_data)} bytes)")


if __name__ == "__main__":
    main()

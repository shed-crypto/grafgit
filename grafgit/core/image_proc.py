"""Image converter module for converting arbitrary images to 7-pixel height grid data."""

from typing import List, Tuple
from PIL import Image


def get_image_info(image_path: str) -> Tuple[int, int]:
    """Returns (width, height) of an image."""
    with Image.open(image_path) as img:
        return img.size


def convert_image_to_grid(
    image_path: str,
    invert: bool = False,
    sensitivity: float = 1.0,
    target_height: int = 7,
    max_width: int = 53
) -> List[List[int]]:
    """Loads an image, scales it to target_height (1..7), and maps to levels 0..4.

    Args:
        image_path: Path to PNG/JPG/BMP image.
        invert: Inverts dark and bright pixels.
        sensitivity: Contrast/threshold multiplier (0.2x to 3.0x).
        target_height: Height of the output grid in pixels (1 to 7).
        max_width: Maximum allowed width in columns.

    Returns:
        List of columns, where each column has target_height integers (levels 0..4).
    """
    img = Image.open(image_path)
    target_height = max(1, min(7, target_height))

    # Detect transparency channel
    alpha_mask = None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img_rgba = img.convert("RGBA")
        alpha_mask = img_rgba.split()[3]
        gray = img_rgba.convert("L")
    else:
        gray = img.convert("L")

    # Calculate proportional target width
    orig_w, orig_h = gray.size
    aspect = orig_w / max(1, orig_h)
    target_w = max(1, min(max_width, int(round(target_height * aspect))))

    resized_gray = gray.resize((target_w, target_height), Image.Resampling.LANCZOS)
    resized_alpha = (
        alpha_mask.resize((target_w, target_height), Image.Resampling.BILINEAR)
        if alpha_mask is not None
        else None
    )

    grid_cols: List[List[int]] = []

    for x in range(target_w):
        col: List[int] = []
        for y in range(target_height):
            # Check transparency first: if transparent, pixel is empty (0)
            if resized_alpha is not None and resized_alpha.getpixel((x, y)) < 64:
                col.append(0)
                continue

            pixel_val = resized_gray.getpixel((x, y))

            if invert:
                pixel_val = 255 - pixel_val

            # Apply sensitivity multiplier
            adjusted = min(255, max(0, int(pixel_val * sensitivity)))

            # Quantize luminance into 5 discrete levels (0..4)
            if adjusted < 40:
                level = 0
            elif adjusted < 90:
                level = 1
            elif adjusted < 145:
                level = 2
            elif adjusted < 205:
                level = 3
            else:
                level = 4

            col.append(level)
        grid_cols.append(col)

    return grid_cols

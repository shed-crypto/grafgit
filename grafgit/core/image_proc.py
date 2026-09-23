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
    max_width: int = 53,
    autocrop: bool = False
) -> List[List[int]]:
    """Loads an image, scales it to target_height (1..7), and maps to levels 0..4.

    Args:
        image_path: Path to PNG/JPG/BMP image.
        invert: Inverts dark and bright pixels.
        sensitivity: Contrast/threshold multiplier (0.2x to 3.0x).
        target_height: Height of the output grid in pixels (1 to 7).
        max_width: Maximum allowed width in columns.
        autocrop: If True, crops empty/black/transparent borders to fit subject.

    Returns:
        List of columns, where each column has target_height integers (levels 0..4).
    """
    img = Image.open(image_path)
    target_height = max(1, min(35, target_height))
    max_width = max(1, min(150, max_width))

    # Detect transparency channel
    alpha_mask = None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img_rgba = img.convert("RGBA")
        alpha_mask = img_rgba.split()[3]
        gray = img_rgba.convert("L")
    else:
        gray = img.convert("L")

    # Autocrop empty/black/transparent margins if requested
    if autocrop:
        # Step 1: Crop transparent margins if alpha channel has transparency
        if alpha_mask is not None:
            min_a, _ = alpha_mask.getextrema()
            if min_a < 200:
                mask = alpha_mask.point(lambda p: 255 if p > 30 else 0)
                bbox = mask.getbbox()
                if bbox and (bbox[2] - bbox[0] >= 3) and (bbox[3] - bbox[1] >= 3):
                    gray = gray.crop(bbox)
                    alpha_mask = alpha_mask.crop(bbox)

        # Step 2: Also crop solid background margins (e.g. black or white borders)
        w, h = gray.size
        if w > 4 and h > 4:
            corners = [
                gray.getpixel((0, 0)),
                gray.getpixel((w - 1, 0)),
                gray.getpixel((0, h - 1)),
                gray.getpixel((w - 1, h - 1))
            ]
            avg_corner = sum(corners) / 4
            if max(abs(c - avg_corner) for c in corners) < 35:
                if avg_corner < 128:
                    # Dark background (like Space Invader on black):
                    thresh = max(25, int(avg_corner + 15))
                    mask = gray.point(lambda p: 255 if p > thresh else 0)
                else:
                    # Light background: content is darker
                    thresh = min(230, int(avg_corner - 15))
                    mask = gray.point(lambda p: 255 if p < thresh else 0)
                bbox = mask.getbbox()
                if bbox and (bbox[2] - bbox[0] >= 3) and (bbox[3] - bbox[1] >= 3):
                    gray = gray.crop(bbox)
                    if alpha_mask is not None:
                        alpha_mask = alpha_mask.crop(bbox)

    # Calculate proportional target width
    orig_w, orig_h = gray.size
    aspect = orig_w / max(1, orig_h)
    target_w = max(1, min(max_width, int(round(target_height * aspect))))

    # For pixel art and clean downscaling without blur or ringing, use BOX filter
    resample_method = (
        Image.Resampling.NEAREST
        if (orig_w <= 48 or orig_h <= 32)
        else Image.Resampling.BOX
    )

    resized_gray = gray.resize((target_w, target_height), resample_method)
    resized_alpha = (
        alpha_mask.resize((target_w, target_height), resample_method)
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

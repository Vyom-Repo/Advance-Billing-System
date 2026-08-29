"""
apps/common/validators.py

Reusable file and image upload validators for resource protection and security boundaries.
"""

from django.core.exceptions import ValidationError
from PIL import Image

MAX_IMAGE_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_PIXEL_DIMENSIONS = (5000, 5000)
ALLOWED_IMAGE_FORMATS = ("PNG", "JPEG", "WEBP", "MPO")


def validate_image_file_size(file_obj):
    """
    Validates that the uploaded file size does not exceed MAX_IMAGE_UPLOAD_SIZE_BYTES (5 MB).
    Checked BEFORE reading content or opening image files.
    """
    if file_obj and hasattr(file_obj, "size") and file_obj.size > MAX_IMAGE_UPLOAD_SIZE_BYTES:
        size_mb = file_obj.size / (1024 * 1024)
        raise ValidationError(
            f"File is too large ({size_mb:.1f} MB). Maximum allowed size is 5 MB."
        )


def validate_image_dimensions_and_format(file_obj):
    """
    Validates image header format and pixel dimensions using Pillow without
    decompressing full raster image data into RAM.
    """
    if not file_obj:
        return

    # First perform size check
    validate_image_file_size(file_obj)

    image = None
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        image = Image.open(file_obj)
        image_format = (image.format or "").upper()
        
        # Verify allowed formats
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(
                f"Unsupported image format ({image_format or 'Unknown'}). Please upload a valid PNG, JPEG, or WebP image."
            )

        width, height = image.size
        max_w, max_h = MAX_IMAGE_PIXEL_DIMENSIONS

        if width > max_w or height > max_h:
            raise ValidationError(
                f"Image dimensions ({width}×{height} px) exceed the maximum allowed limit of {max_w}×{max_h} px."
            )

    except ValidationError:
        raise
    except Exception:
        raise ValidationError("The uploaded image file is corrupt or invalid.")
    finally:
        if hasattr(file_obj, "seek"):
            try:
                file_obj.seek(0)
            except Exception:
                pass

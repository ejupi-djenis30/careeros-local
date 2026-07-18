from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.core.config import settings
from backend.resumes.renderers.base import render_docx, render_pdf
from backend.resumes.renderers.photo_layout import (
    render_two_column_docx,
    render_two_column_pdf,
)


class PhotoValidationError(ValueError):
    pass


def normalize_photo(data: bytes) -> tuple[bytes, int, int]:
    if not data:
        raise PhotoValidationError("The photo is empty")
    if len(data) > settings.MAX_UPLOAD_FILE_SIZE:
        raise PhotoValidationError("The photo exceeds the configured size limit")

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = settings.RESUME_PHOTO_MAX_PIXELS
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.width * image.height > settings.RESUME_PHOTO_MAX_PIXELS:
                raise PhotoValidationError("The photo has too many pixels")
            if "A" in image.getbands() or image.mode == "P":
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            edge = settings.RESUME_PHOTO_EDGE_PX
            normalized = ImageOps.fit(
                image,
                (edge, edge),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.42),
            )
            output = BytesIO()
            normalized.save(output, format="JPEG", quality=90, optimize=True, progressive=False)
            result = output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoValidationError("The uploaded file is not a valid safe image") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    with Image.open(BytesIO(result)) as check:
        if check.getexif():
            raise PhotoValidationError("Photo metadata removal failed")
        return result, check.width, check.height


def render_photo_pdf(snapshot: dict, photo: bytes | None) -> bytes:
    if (snapshot.get("resume", {}).get("canvas_document") or {}).get("style", {}).get(
        "columns"
    ) == 2:
        return render_two_column_pdf(snapshot, photo)
    return render_pdf(snapshot, photo=photo)


def render_photo_docx(snapshot: dict, photo: bytes | None) -> bytes:
    if (snapshot.get("resume", {}).get("canvas_document") or {}).get("style", {}).get(
        "columns"
    ) == 2:
        return render_two_column_docx(snapshot, photo)
    return render_docx(snapshot, photo=photo)

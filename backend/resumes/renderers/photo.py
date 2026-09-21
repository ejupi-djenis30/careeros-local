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

    try:
        with Image.open(BytesIO(data)) as source:
            # Check dimensions before decoding pixels. Mutating Pillow's global
            # MAX_IMAGE_PIXELS here made concurrent uploads temporarily inherit
            # another request's limit (or the library default).
            if source.width <= 0 or source.height <= 0:
                raise PhotoValidationError("The photo dimensions are invalid")
            if source.width * source.height > settings.RESUME_PHOTO_MAX_PIXELS:
                raise PhotoValidationError("The photo has too many pixels")
            source.load()
            image = ImageOps.exif_transpose(source)
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

    with Image.open(BytesIO(result)) as check:
        if check.getexif():
            raise PhotoValidationError("Photo metadata removal failed")
        return result, check.width, check.height


def render_photo_pdf(snapshot: dict, photo: bytes | None) -> bytes:
    from backend.resumes.renderers.semantic_layout import render_swiss_pdf
    from backend.resumes.templates import resolve_template_defaults

    resume = snapshot.get("resume", {})
    preset, _ = resolve_template_defaults(
        template_id=resume.get("template_id"),
        template_kind=resume.get("template_kind"),
    )
    if resume.get("template_id"):
        return render_swiss_pdf(snapshot, photo, operational=preset.layout == "swiss-operational")
    if (resume.get("canvas_document") or {}).get("style", {}).get("columns") == 2:
        return render_two_column_pdf(snapshot, photo)
    return render_pdf(snapshot, photo=photo)


def render_photo_docx(snapshot: dict, photo: bytes | None) -> bytes:
    from backend.resumes.renderers.semantic_layout import render_swiss_docx
    from backend.resumes.templates import resolve_template_defaults

    resume = snapshot.get("resume", {})
    preset, _ = resolve_template_defaults(
        template_id=resume.get("template_id"),
        template_kind=resume.get("template_kind"),
    )
    if resume.get("template_id"):
        return render_swiss_docx(snapshot, photo, operational=preset.layout == "swiss-operational")
    if (resume.get("canvas_document") or {}).get("style", {}).get("columns") == 2:
        return render_two_column_docx(snapshot, photo)
    return render_docx(snapshot, photo=photo)

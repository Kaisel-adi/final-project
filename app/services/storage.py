import os
import uuid
import logging
from pathlib import Path
from typing import cast
from werkzeug.utils import secure_filename
from flask import current_app

logger = logging.getLogger(__name__)


def save_image(file_obj) -> str:
    """
    Saves an uploaded image either to Cloudinary (if configured)
    or to local static/uploads storage (for development/offline use).
    Returns the public URL / path to the saved image.
    """
    if not file_obj or not file_obj.filename:
        raise ValueError("No file provided for upload.")

    filename = secure_filename(file_obj.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp", "mp4", "webm", "mov"})
    if ext not in allowed:
        raise ValueError(f"File type .{ext} not allowed. Supported: {', '.join(allowed)}")

    is_video = ext in {"mp4", "webm", "mov"}
    use_cloudinary = current_app.config.get("USE_CLOUDINARY", False)
    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME")

    if use_cloudinary and cloud_name:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=current_app.config.get("CLOUDINARY_API_KEY"),
            api_secret=current_app.config.get("CLOUDINARY_API_SECRET")
        )
        try:
            upload_kwargs: dict[str, object] = {
                "folder": "gcir_reports",
                "resource_type": "video" if is_video else "image"
            }
            if not is_video:
                upload_kwargs["transformation"] = [
                    {"width": 1200, "height": 1200, "crop": "limit", "quality": "auto"}
                ]
            upload_result = cloudinary.uploader.upload(file_obj, **upload_kwargs)
            return upload_result.get("secure_url", upload_result.get("url"))
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}. Falling back to local storage.")

    # Local fallback
    unique_filename = f"{uuid.uuid4().hex[:12]}_{filename}"
    upload_folder = cast(str, current_app.config.get("UPLOAD_FOLDER") or "static/uploads")
    upload_dir = Path(upload_folder)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / unique_filename

    # Optimize and auto-orient images if not a video
    optimized = False
    if not is_video:
        try:
            from PIL import Image, ImageOps
            file_obj.seek(0)
            with Image.open(file_obj) as img:
                img = ImageOps.exif_transpose(img)
                save_format = "JPEG" if ext in {"jpg", "jpeg"} else ("PNG" if ext == "png" else "WEBP")
                if save_format in {"JPEG", "WEBP"} and img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
                
                max_dim = 1600
                if max(img.width, img.height) > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                
                if save_format == "JPEG":
                    img.save(destination, format="JPEG", quality=82, optimize=True)
                elif save_format == "WEBP":
                    img.save(destination, format="WEBP", quality=80)
                else:
                    img.save(destination, optimize=True)
                optimized = True
        except Exception as img_err:
            logger.debug(f"Pillow image optimization skipped/failed: {img_err}. Saving raw file.")

    if not optimized:
        file_obj.seek(0)
        file_obj.save(destination)

    return f"/static/uploads/{unique_filename}"


save_media = save_image


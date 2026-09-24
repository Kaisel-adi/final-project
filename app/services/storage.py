import os
import uuid
import logging
from pathlib import Path
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
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp"})
    if ext not in allowed:
        raise ValueError(f"File type .{ext} not allowed. Supported: {', '.join(allowed)}")

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
            upload_result = cloudinary.uploader.upload(
                file_obj,
                folder="gcir_reports",
                transformation=[{"width": 1200, "height": 1200, "crop": "limit", "quality": "auto"}]
            )
            return upload_result.get("secure_url", upload_result.get("url"))
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}. Falling back to local storage.")

    # Local fallback
    unique_filename = f"{uuid.uuid4().hex[:12]}_{filename}"
    upload_dir = Path(current_app.config.get("UPLOAD_FOLDER"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / unique_filename
    file_obj.seek(0)
    file_obj.save(destination)
    return f"/static/uploads/{unique_filename}"

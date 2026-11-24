import os

from django.conf import settings
from django.core.exceptions import ValidationError

DOC_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".doc", ".docx", ".txt", ".zip", ".ppt", ".pptx", ".xls", ".xlsx", ".odt"}
VIEW_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAGIC = {".pdf": [b"%PDF"], ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
         ".gif": [b"GIF8"], ".webp": [b"RIFF"], ".zip": [b"PK"], ".docx": [b"PK"], ".xlsx": [b"PK"], ".pptx": [b"PK"]}


def check_upload(f, allowed=DOC_EXT, max_mb=None):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in allowed:
        raise ValidationError("Bu fayl turi qabul qilinmaydi: " + (ext or "noma’lum"))
    if f.size > (max_mb or settings.MAX_UPLOAD_MB) * 1024 * 1024:
        raise ValidationError(f"Fayl hajmi {(max_mb or settings.MAX_UPLOAD_MB)} MB dan oshmasligi kerak")
    sigs = MAGIC.get(ext)
    if sigs:
        head = f.read(12)
        f.seek(0)
        if not any(head.startswith(s) for s in sigs):
            raise ValidationError("Fayl mazmuni kengaytmasiga mos emas")
    return ext

import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def get_private_storage():
    """Yopiq saqlash joyi: MEDIA_URL yo'q, URL berilmaydi — fayllarni faqat himoyalangan view'lar beradi."""
    return FileSystemStorage(location=str(settings.PRIVATE_ROOT), base_url=None)


def _p(prefix, filename):
    ext = os.path.splitext(filename)[1].lower()[:8]
    return f"{prefix}/{uuid.uuid4().hex}{ext}"


def material_path(i, f): return _p("materials", f)
def taskfile_path(i, f): return _p("taskfiles", f)
def submission_path(i, f): return _p("submissions", f)
def video_src_path(i, f): return _p("video_src", f)
def testfile_path(i, f): return _p("testfiles", f)
def solution_path(i, f): return _p("solutions", f)
def guidefile_path(i, f): return _p("guidefiles", f)
def editor_path(i, f): return _p("editor", f)
def article_path(i, f): return _p("articles", f)

"""Himoyalangan fayl xizmati.

Talaba hech qachon asl faylni olmaydi: PDF/rasm server tomonida sahifalarga ajratilib, har bir sahifaga
foydalanuvchining ismi va ID si suv belgisi sifatida yoziladi va PNG ko'rinishida beriladi.
Asl fayl yuklab olish faqat o'qituvchilar uchun (/f/<kind>/<pk>/download/)."""
import io
import math
import os
import subprocess
import tempfile

import pymupdf
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from PIL import Image, ImageDraw, ImageFont

from apps.core.validators import IMG_EXT, VIEW_EXT

NOSTORE = {"Cache-Control": "private, no-store, max-age=0", "X-Content-Type-Options": "nosniff", "Pragma": "no-cache"}


def resolve(request, kind, pk):
    """-> (FieldFile, nom). Ruxsat bo'lmasa PermissionDenied."""
    from apps.courses.models import GuideFileModel, LessonMaterialModel, SubmissionModel, TaskFileModel
    from apps.courses.services import lock_reason, student_in_scope
    from apps.exams.models import AttemptModel, QuestionModel, TestModel
    from apps.exams.services import has_paid_access
    u = request.user
    if kind == "mat":
        m = get_object_or_404(LessonMaterialModel, pk=pk, kind="file")
        if lock_reason(u, m.lesson):
            raise PermissionDenied
        return m.file, m.filename or m.title
    if kind == "tf":
        f = get_object_or_404(TaskFileModel, pk=pk)
        if lock_reason(u, f.task.lesson):
            raise PermissionDenied
        return f.file, f.name
    if kind == "sub":
        s = get_object_or_404(SubmissionModel, pk=pk)
        if not u.is_authenticated:
            raise PermissionDenied
        if u.is_student and s.student_id != u.pk:
            raise PermissionDenied
        if u.is_assistant and not student_in_scope(u, s.student):
            raise PermissionDenied
        return s.file, s.filename
    if kind == "test":
        t = get_object_or_404(TestModel, pk=pk, mode="file")
        if not (u.is_authenticated and u.is_teacher):
            if not t.file or not has_paid_access(t, u) or (not u.is_authenticated and not t.allow_guest):
                raise PermissionDenied
            if t.live_status != "active" and not (u.is_authenticated and AttemptModel.objects.filter(test=t, user=u).exists()):
                raise PermissionDenied
        return t.file, t.file_name or t.title
    if kind == "gf":
        g = get_object_or_404(GuideFileModel, pk=pk)
        if not u.is_authenticated or (not g.guide.is_active and not u.is_teacher):
            raise PermissionDenied
        return g.file, g.name
    if kind == "sol":
        q = get_object_or_404(QuestionModel, pk=pk)
        if not q.solution_image:
            raise Http404
        if not u.is_authenticated or not (u.is_teacher or AttemptModel.objects.filter(test=q.test, user=u).exists()):
            raise PermissionDenied
        return q.solution_image, "yechim"
    raise Http404


def _limit(request):
    key = "pgs:%s" % (request.user.pk if request.user.is_authenticated else request.META.get("REMOTE_ADDR"))
    cache.add(key, 0, 600)
    try:
        n = cache.incr(key)
    except ValueError:
        n = 1
    if n > 500:
        raise PermissionDenied


def wm_text(request):
    u = request.user
    return f"{u.full_name} · {u.uid}" if u.is_authenticated else "MEHMON · " + (request.META.get("REMOTE_ADDR") or "")


def watermark(img, text):
    img = img.convert("RGBA")
    W, H = img.size
    size = max(14, W // 34)
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    d = int(math.hypot(W, H)) + 40
    layer = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    w = int(dr.textlength(text, font=font)) + size * 2
    h = size * 4
    for y in range(0, d, h):
        for x in range(-(w // 2) * ((y // h) % 2), d, w):
            dr.text((x, y), text, font=font, fill=(90, 90, 110, 46))
    layer = layer.rotate(25, resample=Image.BICUBIC)
    ox, oy = (d - W) // 2, (d - H) // 2
    img.alpha_composite(layer.crop((ox, oy, ox + W, oy + H)))
    return img.convert("RGB")


def _ext(name):
    return os.path.splitext(name or "")[1].lower()


def _open_doc(ff):
    path = ff.path
    if path.lower().endswith(".pdf"):
        return "pdf", pymupdf.open(path)
    if _ext(path) in IMG_EXT:
        return "img", None
    return "other", None


def page_count(ff):
    t, doc = _open_doc(ff)
    if t == "pdf":
        n = doc.page_count
        doc.close()
        return n
    return 1 if t == "img" else 0


def info_response(request, kind, pk):
    ff, name = resolve(request, kind, pk)
    return JsonResponse({"pages": page_count(ff), "name": name}, headers=NOSTORE)


def page_response(request, kind, pk, n):
    ff, name = resolve(request, kind, pk)
    _limit(request)
    t, doc = _open_doc(ff)
    if t == "pdf":
        if n < 1 or n > doc.page_count:
            raise Http404
        pix = doc[n - 1].get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()
    elif t == "img":
        if n != 1:
            raise Http404
        img = Image.open(ff.path)
        img.load()
        if img.width > 1800:
            img = img.resize((1800, int(img.height * 1800 / img.width)))
    else:
        raise Http404
    img = watermark(img, wm_text(request))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False)
    return HttpResponse(buf.getvalue(), content_type="image/png", headers=NOSTORE)


def download_response(request, kind, pk):
    u = request.user
    if not (u.is_authenticated and u.is_teacher):
        raise PermissionDenied  # talabalar uchun yuklab olish yo'q
    ff, name = resolve(request, kind, pk)
    r = FileResponse(open(ff.path, "rb"), as_attachment=True, filename=name if _ext(name) else name + _ext(ff.name))
    r["X-Content-Type-Options"] = "nosniff"
    return r


def office_to_pdf(django_file):
    """Word/PowerPoint faylini PDF ga aylantirishga urinadi (LibreOffice bo'lsa). Aks holda None."""
    try:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in" + _ext(django_file.name))
            with open(src, "wb") as f:
                for c in django_file.chunks():
                    f.write(c)
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", d, src], capture_output=True, timeout=120)
            out = os.path.join(d, "in.pdf")
            if os.path.exists(out):
                return open(out, "rb").read()
    except Exception:
        pass
    return None

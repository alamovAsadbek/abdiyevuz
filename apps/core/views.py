import io
import json
import re

from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from PIL import Image

from . import protected as P
from .helpers import clean_html
from .models import ArticleModel, EditorImageModel, SiteSettingsModel
from .perms import login_required, main_required, perm_required, teacher_required
from .validators import IMG_EXT, check_upload


def err403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def err404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def _can_read(request):
    return request.user.is_authenticated or SiteSettingsModel.get().articles_public


def _manage_articles(user):
    return user.is_authenticated and user.is_teacher and user.can("articles")


def home(request):
    """Sayt ochilganda birinchi — maqolalar (yangiliklar) lentasi."""
    from django.core.paginator import Paginator
    ok = _can_read(request)
    mg = _manage_articles(request.user)
    arts, q = None, request.GET.get("q", "").strip()
    if ok:
        qs = ArticleModel.objects.all() if mg else ArticleModel.objects.filter(is_active=True)
        if q:
            qs = qs.filter(title__icontains=q)
        arts = Paginator(qs.select_related("author"), 9).get_page(request.GET.get("page") or 1)
    return render(request, "public/home.html", {"arts": arts, "ok": ok, "mg": mg, "q": q})


def article_detail(request, pk):
    if not _can_read(request):
        return redirect(f"{reverse('login')}?next={request.path}")
    a = get_object_or_404(ArticleModel, pk=pk)
    mg = _manage_articles(request.user)
    if not a.is_active and not mg:
        raise Http404
    if not mg:
        ArticleModel.objects.filter(pk=pk).update(views=a.views + 1)
        a.views += 1
    return render(request, "public/article.html", {"a": a, "mg": mg})


def article_cover(request, pk):
    if not _can_read(request):
        raise PermissionDenied
    a = get_object_or_404(ArticleModel, pk=pk)
    if not a.cover or (not a.is_active and not _manage_articles(request.user)):
        raise Http404
    r = FileResponse(open(a.cover.path, "rb"), content_type="image/jpeg")
    r["X-Content-Type-Options"] = "nosniff"
    r["Cache-Control"] = "public, max-age=3600"
    return r


def _save_article(request, a=None):
    P = request.POST
    title, body = P.get("title", "").strip(), clean_html(P.get("body", ""))
    if not title:
        return None, "Sarlavhani kiriting"
    if not re.sub(r"<[^>]+>", "", body).strip() and "<img" not in body:
        return None, "Maqola matnini yozing"
    f = request.FILES.get("cover")
    data = None
    if f:
        try:
            check_upload(f, IMG_EXT, 8)
            im = Image.open(f)
            im.load()
            im = im.convert("RGB")
            if im.width > 1400:
                im = im.resize((1400, int(im.height * 1400 / im.width)))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85, optimize=True)
            data = buf.getvalue()
        except ValidationError as e:
            return None, e.messages[0]
        except Exception:
            return None, "Rasm o‘qilmadi"
    a = a or ArticleModel(author=request.user)
    a.title, a.summary, a.body = title[:220], P.get("summary", "").strip()[:300], body
    a.is_active = bool(P.get("is_active"))
    a.save()
    if data:
        if a.cover:
            a.cover.delete(save=False)
        a.cover.save("cover.jpg", ContentFile(data), save=True)
    elif P.get("remove_cover") and a.cover:
        a.cover.delete(save=True)
    return a, None


@perm_required("articles")
def article_new(request):
    if request.method == "POST":
        a, err = _save_article(request)
        if not err:
            messages.success(request, "Maqola saqlandi")
            return redirect("article_detail", pk=a.pk)
        messages.error(request, err)
    return render(request, "staff/articles/form.html", {"a": None, "active": True, "body_json": json.dumps("")})


@perm_required("articles")
def article_edit(request, pk):
    a = get_object_or_404(ArticleModel, pk=pk)
    if request.method == "POST":
        _, err = _save_article(request, a)
        if not err:
            messages.success(request, "Maqola saqlandi")
            return redirect("article_detail", pk=pk)
        messages.error(request, err)
    return render(request, "staff/articles/form.html", {"a": a, "active": a.is_active, "body_json": json.dumps(a.body)})


@perm_required("articles")
@require_POST
def article_toggle(request, pk):
    a = get_object_or_404(ArticleModel, pk=pk)
    a.is_active = not a.is_active
    a.save(update_fields=["is_active"])
    messages.success(request, "Maqola aktiv qilindi" if a.is_active else "Maqola noaktiv qilindi")
    return redirect(request.POST.get("next") or "home")


@perm_required("articles")
@require_POST
def article_delete(request, pk):
    a = get_object_or_404(ArticleModel, pk=pk)
    a.cover.delete(save=False) if a.cover else None
    a.delete()
    messages.success(request, "Maqola o‘chirildi")
    return redirect("home")


@main_required
@require_POST
def site_settings(request):
    s = SiteSettingsModel.get()
    s.articles_public = bool(request.POST.get("articles_public"))
    s.registration_open = bool(request.POST.get("registration_open"))
    s.save()
    messages.success(request, "Umumiy sozlamalar saqlandi")
    return redirect("settings")


def file_info(request, kind, pk):
    return P.info_response(request, kind, pk)


def file_page(request, kind, pk, n):
    return P.page_response(request, kind, pk, n)


@login_required
def file_download(request, kind, pk):
    return P.download_response(request, kind, pk)


@teacher_required
@require_POST
def editor_upload(request):
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "error": "Fayl yo‘q"}, status=400)
    try:
        check_upload(f, IMG_EXT, 5)
        im = Image.open(f)
        im.load()
        im = im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im
        if im.width > 1600:
            im = im.resize((1600, int(im.height * 1600 / im.width)))
        buf = io.BytesIO()
        im.save(buf, "PNG")
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": e.messages[0]}, status=400)
    except Exception:
        return JsonResponse({"ok": False, "error": "Rasm o‘qilmadi"}, status=400)
    from django.core.files.base import ContentFile
    obj = EditorImageModel(owner=request.user)
    obj.file.save("img.png", ContentFile(buf.getvalue()), save=True)
    return JsonResponse({"ok": True, "url": f"/editor/img/{obj.pk}/"})


def editor_img(request, pk):
    obj = get_object_or_404(EditorImageModel, pk=pk)
    r = FileResponse(open(obj.file.path, "rb"), content_type="image/png")
    r["X-Content-Type-Options"] = "nosniff"
    r["Cache-Control"] = "private, max-age=3600"
    return r

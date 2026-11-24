from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


def is_ajax(request):
    return request.headers.get("X-Requested-With") == "fetch" or "application/json" in request.headers.get("Accept", "")


def deny(request, msg="Sizda bu bo‘limga ruxsat yo‘q", to="dashboard"):
    if is_ajax(request):
        return JsonResponse({"ok": False, "error": msg}, status=403)
    messages.error(request, msg)
    return redirect(to)


def login_required(view):
    @wraps(view)
    def w(request, *a, **kw):
        if not request.user.is_authenticated:
            if is_ajax(request):
                return JsonResponse({"ok": False, "error": "Tizimga kiring"}, status=401)
            return redirect(f"{reverse('login')}?next={request.get_full_path()}")
        return view(request, *a, **kw)
    return w


def teacher_required(view):
    @wraps(view)
    @login_required
    def w(request, *a, **kw):
        if not request.user.is_teacher:
            return deny(request)
        return view(request, *a, **kw)
    return w


def main_required(view):
    @wraps(view)
    @login_required
    def w(request, *a, **kw):
        if not request.user.is_main:
            return deny(request)
        return view(request, *a, **kw)
    return w


def student_required(view):
    @wraps(view)
    @login_required
    def w(request, *a, **kw):
        if not request.user.is_student:
            return deny(request)
        return view(request, *a, **kw)
    return w


def perm_required(code):
    """Backend ruxsat tekshiruvi: asosiy o'qituvchi — hammasi; yordamchi — faqat berilgan ruxsatlar."""
    def deco(view):
        @wraps(view)
        @login_required
        def w(request, *a, **kw):
            if not (request.user.is_teacher and request.user.can(code)):
                return deny(request)
            return view(request, *a, **kw)
        return w
    return deco


def post_only(view):
    @wraps(view)
    def w(request, *a, **kw):
        if request.method != "POST":
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(["POST"])
        return view(request, *a, **kw)
    return w

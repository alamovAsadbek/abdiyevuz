from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from . import jwt_auth as J

CSP = ("default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ws: wss:; "
       "frame-src https://www.youtube.com https://player.vimeo.com https://rutube.ru; worker-src blob:; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def _user_from_access(token):
    p = J.decode(token, "access")
    if not p:
        return None
    U = get_user_model()
    u = U.objects.filter(pk=p["sub"], is_active=True, is_blocked=False).first()
    return u


class JWTAuthMiddleware:
    """Har bir so'rovda JWT (HttpOnly cookie yoki Authorization: Bearer) tekshiriladi.
    Access muddati tugasa refresh token orqali avtomatik yangilanadi (rotatsiya bilan)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user, new = None, None
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.COOKIES.get(J.ACCESS_COOKIE)
        if token:
            user = _user_from_access(token)
        if not user and request.COOKIES.get(J.REFRESH_COOKIE):
            r = J.rotate(request.COOKIES[J.REFRESH_COOKIE], request)
            if r:
                user, a, rf = r
                new = (a, rf)
        request.user = user or AnonymousUser()
        response = self.get_response(request)
        if new and not getattr(request, "_jwt_skip", False):
            J.set_cookies(response, *new)
        elif not user and request.COOKIES.get(J.REFRESH_COOKIE) and J.ACCESS_COOKIE not in response.cookies:
            J.clear_cookies(response)
        if user and (not user.last_seen or timezone.now() - user.last_seen > timedelta(seconds=60)):
            type(user).objects.filter(pk=user.pk).update(last_seen=timezone.now())
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        r = self.get_response(request)
        if not request.path.startswith("/admin/"):
            r.setdefault("Content-Security-Policy", CSP)
        r.setdefault("Permissions-Policy", "camera=(self), microphone=(self), display-capture=(self), geolocation=(), payment=()")
        r.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            r.setdefault("Cache-Control", "no-store, private")
        return r


class SectionAccessMiddleware:
    """Bo'lim × amal ruxsatini url nomi bo'yicha MARKAZIY tekshiradi (apps.accounts.permissions.ROUTES).
    Ruxsat yo'q bo'lsa — view umuman ishga tushmaydi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from apps.accounts import permissions as PM
        u = getattr(request, "user", None)
        if u is None or not u.is_authenticated or u.is_main:
            return None
        name = getattr(request.resolver_match, "url_name", "") or ""
        rule = PM.ROUTES.get(name)
        if not rule:
            return None
        code, action = rule
        if request.method == "GET" and name in PM.GET_AS_VIEW:
            action = "view"
        if u.can(code, action):
            return None
        from django.shortcuts import redirect
        from .perms import deny
        if name == "home":            # maqolalar yopiq bo'lsa — bosh sahifa o'rniga panel
            return redirect("dashboard")
        request._audit_denied = (code, action)
        sec = PM.SECTION_MAP.get(code)
        what = f"«{sec[1]}» bo‘limida «{PM.ACTION_LABELS.get(action, action)}»" if sec else "bu amalga"
        return deny(request, f"Sizda {what} ruxsati yo‘q")


class AuditMiddleware:
    """Tizim jurnali: kirgan foydalanuvchining har bir o'zgartiruvchi (POST) so'rovi, ruxsatsiz urinishlar
    va fayl yuklab olishlar yoziladi. Natija (bajarildi / xato / ruxsat yo'q) javob va flash xabardan aniqlanadi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def process_view(self, request, view_func, view_args, view_kwargs):
        from apps.security import services as S
        name = getattr(request.resolver_match, "url_name", "") or ""
        if name in S.SKIP or name in ("login", "register"):
            return None
        if request.method == "POST" or name in S.LOG_GET:
            request._audit = {"name": name, "kw": dict(view_kwargs), "obj": S.resolve_obj(name, view_kwargs),
                              "target": S.target_from(name, view_kwargs, request.POST if request.method == "POST" else None)}
        return None

    def __call__(self, request):
        import time
        t0 = time.monotonic()
        response = self.get_response(request)
        info = getattr(request, "_audit", None)
        denied = getattr(request, "_audit_denied", None)
        u = getattr(request, "user", None)
        if (info or denied) and u is not None and u.is_authenticated:
            try:
                self._write(request, response, info, denied, int((time.monotonic() - t0) * 1000))
            except Exception:
                import logging
                logging.getLogger("km.audit").exception("audit middleware")
        return response

    def _write(self, request, response, info, denied, ms):
        from apps.security import services as S
        name = getattr(request.resolver_match, "url_name", "") or ""
        st = response.status_code
        msg, result = "", "ok"
        q = getattr(getattr(request, "_messages", None), "_queued_messages", []) or []
        errs = [str(m.message) for m in q if m.level >= 40]
        oks = [str(m.message) for m in q if m.level < 40]
        if denied or st == 403:
            result = "denied"
        elif st >= 400 or errs:
            result = "fail"
        msg = (errs or oks or [""])[0]
        if denied:
            from apps.accounts import permissions as PM
            sec = PM.SECTION_MAP.get(denied[0])
            label = f"Ruxsatsiz urinish: {sec[1] if sec else denied[0]} → {PM.ACTION_LABELS.get(denied[1], denied[1])}"
            S.audit(request, name or "denied", label=label, category="security", result="denied", status=st, duration_ms=ms,
                    data={"section": denied[0], "action": denied[1], "url_name": name},
                    obj=S.resolve_obj(name, request.resolver_match.kwargs if request.resolver_match else {}))
            return
        data = S.safe_data(request.POST) if request.method == "POST" else {}
        if not data and request.method == "POST" and request.body and len(request.body) < 4000 and "json" in request.content_type:
            import json
            try:
                data = {"json": json.loads(request.body)}
            except Exception:
                data = {}
        S.audit(request, name, result=result, status=st, duration_ms=ms, obj=info["obj"], target=info["target"], data=data, message=msg)

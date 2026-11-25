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
    """Har bir so'rovda url nomi bo'yicha bo'lim × amal ruxsatini tekshiradi (asosiy o'qituvchi va mehmonlar bundan mustasno).
    «Ko'rish» berilmagan bo'lim sahifalari ochilmaydi; yozish amallari faqat berilgan bo'lsa bajariladi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated) or u.is_main:
            return None
        from apps.accounts.permissions import route_need
        need = route_need(getattr(request.resolver_match, "url_name", "") or "", request.method)
        if not need or not need[0]:
            return None
        sec, act = need
        if u.is_student and act != "view":
            return None  # talaba yozish amallari view'larning o'zida rol bo'yicha tekshiriladi
        if not u.can(sec, act):
            from .perms import deny
            return deny(request, "Sizda bu amal uchun ruxsat yo‘q" if act != "view" else "Bu bo‘lim siz uchun yopiq")
        return None

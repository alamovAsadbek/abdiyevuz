import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

ACCESS_COOKIE = "km_access"
REFRESH_COOKIE = "km_refresh"
GRACE = timedelta(seconds=25)  # parallel so'rovlar uchun eski refresh token qisqa vaqt yashaydi


def client_ip(request):
    if settings.TRUST_PROXY:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _enc(payload):
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode(token, typ):
    try:
        p = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
    except jwt.PyJWTError:
        return None
    return p if p.get("typ") == typ else None


def make_access(user):
    now = timezone.now()
    return _enc({"sub": str(user.pk), "typ": "access", "role": user.role, "iat": now,
                 "exp": now + timedelta(minutes=settings.JWT_ACCESS_MINUTES), "jti": uuid.uuid4().hex})


def issue_refresh(user, request):
    from apps.accounts.models import RefreshTokenModel
    now = timezone.now()
    jti = uuid.uuid4().hex
    exp = now + timedelta(days=settings.JWT_REFRESH_DAYS)
    RefreshTokenModel.objects.create(user=user, jti=jti, expires_at=exp, ip=client_ip(request),
                                     user_agent=request.META.get("HTTP_USER_AGENT", "")[:300])
    return _enc({"sub": str(user.pk), "typ": "refresh", "iat": now, "exp": exp, "jti": jti})


def issue_pair(user, request):
    return make_access(user), issue_refresh(user, request)


def rotate(token, request):
    from apps.accounts.models import RefreshTokenModel
    p = decode(token, "refresh")
    if not p:
        return None
    now = timezone.now()
    row = RefreshTokenModel.objects.select_related("user").filter(jti=p["jti"], revoked=False, expires_at__gt=now).first()
    if not row or row.user.is_blocked or not row.user.is_active:
        return None
    row.expires_at = min(row.expires_at, now + GRACE)
    row.save(update_fields=["expires_at"])
    return row.user, make_access(row.user), issue_refresh(row.user, request)


def revoke(token):
    from apps.accounts.models import RefreshTokenModel
    p = decode(token or "", "refresh")
    if p:
        RefreshTokenModel.objects.filter(jti=p["jti"]).update(revoked=True)


def revoke_all(user):
    user.refresh_tokens.update(revoked=True)


def set_cookies(resp, access, refresh):
    kw = dict(httponly=True, secure=settings.COOKIE_SECURE, samesite="Lax", path="/")
    resp.set_cookie(ACCESS_COOKIE, access, max_age=settings.JWT_ACCESS_MINUTES * 60, **kw)
    resp.set_cookie(REFRESH_COOKIE, refresh, max_age=settings.JWT_REFRESH_DAYS * 86400, **kw)


def clear_cookies(resp):
    resp.delete_cookie(ACCESS_COOKIE, path="/")
    resp.delete_cookie(REFRESH_COOKIE, path="/")

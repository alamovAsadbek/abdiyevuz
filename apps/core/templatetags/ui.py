from django import template
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()
MONTHS = None


@register.simple_tag
def icon(name):
    return mark_safe(f'<i data-feather="{escape(name)}"></i>')


@register.simple_tag
def tag(text, cls=""):
    return format_html('<span class="tag {}">{}</span>', cls, text)


@register.filter
def money(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "Bepul"
    return f"{n:,}".replace(",", " ") + " so‘m" if n else "Bepul"


@register.filter
def dtm(v):
    if not v:
        return "—"
    v = timezone.localtime(v) if timezone.is_aware(v) else v
    return v.strftime("%d.%m.%Y %H:%M")


@register.filter
def dfmt(v):
    if not v:
        return "—"
    v = timezone.localtime(v) if hasattr(v, "hour") and timezone.is_aware(v) else v
    return v.strftime("%d.%m.%Y")


@register.filter
def dtl(v):
    """<input type=datetime-local> uchun qiymat."""
    if not v:
        return ""
    return timezone.localtime(v).strftime("%Y-%m-%dT%H:%M")


@register.filter
def ago(v):
    if not v:
        return "—"
    m = int((timezone.now() - v).total_seconds() // 60)
    if m < 1:
        return "hozirgina"
    if m < 60:
        return f"{m} daqiqa oldin"
    if m < 1440:
        return f"{m // 60} soat oldin"
    return f"{m // 1440} kun oldin"


@register.filter
def getitem(d, k):
    try:
        return d.get(k)
    except Exception:
        return None


@register.filter
def letter(i):
    return "ABCDEFGH"[int(i)] if 0 <= int(i) < 8 else "?"


@register.filter
def add_one(i):
    return int(i) + 1


@register.filter
def has(seq, v):
    return v in (seq or [])


@register.filter
def pct(a, b):
    return round(a / b * 100) if b else 0


@register.filter
def index(seq, i):
    try:
        return seq[int(i)]
    except Exception:
        return ""


@register.filter
def initials(name):
    return "".join(w[0] for w in str(name).split()[:2]).upper() or "?"


@register.simple_tag
def cell(c):
    if isinstance(c, dict):
        return format_html('<span class="tag {}">{}</span>', c.get("cls", ""), c.get("tag", ""))
    if hasattr(c, "hour"):
        return dtm(c)
    if hasattr(c, "year"):
        return dfmt(c)
    return c if c not in (None, "") else "—"


@register.filter
def split(s, sep=","):
    return [x for x in str(s).split(sep) if x]


@register.filter
def can(user, code):
    return bool(user.is_authenticated and user.is_teacher and user.can(code))


@register.filter
def dur(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return "—"
    if not sec:
        return "—"
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return (f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")

import json
from urllib.parse import urlencode

import nh3
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_datetime

ALLOWED_TAGS = {"p", "br", "b", "strong", "i", "em", "u", "sub", "sup", "span", "div", "ul", "ol", "li", "img", "h3", "h4", "table", "tr", "td", "th", "thead", "tbody", "a", "hr"}
ALLOWED_ATTRS = {"img": {"src", "alt"}, "a": {"href"}}


def clean_html(html):
    """Rich-text maydonlar XSS dan tozalanadi (img faqat bizning himoyalangan manzildan)."""
    html = nh3.clean(html or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, url_schemes={"http", "https", "mailto"},
                     link_rel="noopener noreferrer", strip_comments=True)
    return html


def T(text, cls=""):
    return {"tag": text, "cls": cls}


def A(icon, title, url="", post="", confirm="", cls=""):
    return {"icon": icon, "title": title, "url": url, "post": post, "confirm": confirm, "cls": cls}


def parse_local(value):
    """<input type=datetime-local> qiymatini aware datetime ga aylantiradi."""
    if not value:
        return None
    d = parse_datetime(value)
    if d and timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def jload(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default


def to_int(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def make_list(request, rows, headers, filters=(), add=None, show_mode=True, search=True, force_mode=None):
    q = request.GET.get("q", "").strip().lower()
    fv = {k: request.GET.get("f_" + k, "") for k, _, _ in filters}

    def ok(r):
        if q and q not in (r["title"] + " " + str(r.get("search", ""))).lower():
            return False
        for k, v in fv.items():
            if v:
                rv = r.get("f", {}).get(k)
                if isinstance(rv, (list, tuple, set)):
                    if v not in rv:
                        return False
                elif rv != v:
                    return False
        return True

    rows = [r for r in rows if ok(r)]
    mode = force_mode or request.GET.get("mode") or request.COOKIES.get("km_mode") or "cards"
    mode = mode if mode in ("cards", "table") else "cards"
    ps = to_int(request.GET.get("ps"), 10)
    ps = ps if ps in (10, 20, 50) else 10
    pg = Paginator(rows, ps).get_page(request.GET.get("page") or 1)
    keep = {k: v for k, v in request.GET.items() if k not in ("page",) and v}
    base = request.path + "?" + (urlencode(keep) + "&" if keep else "")
    keep2 = {k: v for k, v in keep.items() if k != "mode"}
    mbase = request.path + "?" + (urlencode(keep2) + "&" if keep2 else "")
    keep3 = {k: v for k, v in keep.items() if k not in ("ps",)}
    pbase = request.path + "?" + (urlencode(keep3) + "&" if keep3 else "")
    st = {0, pg.paginator.num_pages - 1, pg.number - 2, pg.number - 1, pg.number}
    pages, last = [], -1
    for i in sorted(x for x in st if 0 <= x < pg.paginator.num_pages):
        if i - last > 1:
            pages.append({"gap": True})
        pages.append({"n": i + 1, "on": i + 1 == pg.number})
        last = i
    fl = [{"key": k, "label": l, "value": fv[k], "options": list(o), "current": fv[k] or f"{l}: hammasi"} for k, l, o in filters]
    return {"rows": pg.object_list, "headers": headers, "filters": fl, "q": request.GET.get("q", ""), "mode": mode,
            "add": add, "page": pg, "pages": pages, "ps": ps, "total": len(rows), "base": base, "mbase": mbase, "pbase": pbase,
            "has_actions": any(r.get("actions") for r in pg.object_list), "show_mode": show_mode, "search": search,
            "offset": pg.start_index() - 1 if len(rows) else 0, "ps_opts": [10, 20, 50]}

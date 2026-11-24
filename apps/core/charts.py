"""Original dizayndagi SVG diagrammalar (Python versiyasi). Barcha qiymatlar haqiqiy ma'lumotdan."""
from django.utils.html import escape
from django.utils.safestring import mark_safe


def ring(v):
    v = max(0, min(100, int(v)))
    return mark_safe(f'<div class="rw"><svg class="rg" viewBox="0 0 44 44"><circle class="tr" cx="22" cy="22" r="18"/>'
                     f'<circle class="fg" cx="22" cy="22" r="18" style="--o:{113 - 1.13 * v}"/></svg><b>{v}%</b></div>')


def _sm(p):
    return "".join(f"C{(p[i-1][0]+q[0])/2} {p[i-1][1]} {(p[i-1][0]+q[0])/2} {q[1]} {q[0]} {q[1]}" if i else f"M{q[0]} {q[1]}" for i, q in enumerate(p))


def line(a, b=None):
    b = b or [0] * len(a)
    if len(a) < 2:
        return mark_safe('<span class="m">Grafik uchun ma’lumot yetarli emas</span>')
    w, h = 400, 150
    mx = (max(list(a) + list(b)) or 1) * 1.1
    pt = lambda d: [(i * w / (len(d) - 1), h - v / mx * h) for i, v in enumerate(d)]
    A, B = pt(a), pt(b)
    return mark_safe(f'<svg viewBox="0 0 {w} {h}" class="lc" preserveAspectRatio="none"><defs><linearGradient id="gd" x1="0" y1="0" x2="0" y2="1">'
                     f'<stop offset="0" stop-color="#6b5bd2" stop-opacity=".3"/><stop offset="1" stop-color="#6b5bd2" stop-opacity="0"/></linearGradient></defs>'
                     f'<path class="ar" d="{_sm(A)}L{w} {h}L0 {h}Z"/><path class="l2" pathLength="1" d="{_sm(B)}"/><path class="l1" pathLength="1" d="{_sm(A)}"/></svg>')


def beaker(v):
    v = max(0, min(100, int(v)))
    bub = "".join(f'<circle class="bb" cx="{x}" cy="118" r="{3+i}" style="animation-delay:{i*.9}s"/>' for i, x in enumerate((45, 62, 78)))
    return mark_safe(f'<svg class="bk" viewBox="0 0 120 140"><defs><clipPath id="bc"><path d="M25 14H95V110Q95 128 77 128H43Q25 128 25 110Z"/></clipPath>'
                     f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a99cff"/><stop offset="1" stop-color="#6b5bd2"/></linearGradient></defs>'
                     f'<g clip-path="url(#bc)"><g class="lq" style="--y:{126 - v}px"><path class="wv" d="M-60 0q15-8 30 0t30 0 30 0 30 0 30 0 30 0 30 0 30 0V130H-60Z"/></g>{bub}</g>'
                     f'<path d="M25 14H95V110Q95 128 77 128H43Q25 128 25 110Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round" opacity=".5"/>'
                     f'<path d="M20 14H100" stroke="currentColor" stroke-width="4" stroke-linecap="round" opacity=".5"/></svg>')


def donut(parts):
    parts = [p for p in parts if p[1] > 0]
    tot = sum(p[1] for p in parts)
    if not tot:
        return mark_safe('<span class="m">Ma’lumot yo‘q</span>')
    acc, circles, leg = 0, "", ""
    for name, n, col in parts:
        v = n / tot * 100
        circles += f'<circle cx="18" cy="18" r="15.915" stroke="{col}" stroke-dasharray="{v} {100-v}" stroke-dashoffset="{-acc}"/>'
        acc += v
        leg += f'<div class="row" style="gap:8px"><i style="width:10px;height:10px;border-radius:50%;background:{col}"></i>{escape(name)} <b>{n}</b></div>'
    return mark_safe(f'<div class="row mt" style="gap:18px;flex-wrap:nowrap"><svg class="dn" viewBox="0 0 36 36">{circles}</svg><div>{leg}</div></div>')


def phbar(v):
    v = max(0, min(100, int(v)))
    return mark_safe(f'<div class="phb" style="--l:{v}%"><b>pH {v / 100 * 14:.1f}</b></div><div class="row m" style="justify-content:space-between;font-size:12px">'
                     f'<span>Kislotali</span><span>Neytral</span><span>Ishqoriy</span></div>')


def tiles(items):
    """items: [(symbol, title, number, percent)] — Mendeleyev jadvali uslubidagi mavzu kartalari."""
    if not items:
        return mark_safe('<span class="m">Hali ma’lumot yo‘q</span>')
    out = "".join(f'<div class="el {"hi" if e[3] > 66 else ""}" style="--a:{e[3]};animation-delay:{i*.06}s"><small>{e[2]}</small><b>{escape(e[0])}</b>'
                  f'<span>{escape(e[1])}</span><em>{e[3]}%</em></div>' for i, e in enumerate(items))
    return mark_safe(f'<div class="pt4 mt">{out}</div>')

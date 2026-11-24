import json
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserModel
from apps.core.helpers import A, T, jload, make_list
from apps.core.perms import deny, login_required, perm_required, post_only
from apps.courses.services import scoped_students
from . import services as S
from .models import CATS, KINDS, SEVERITY, AuditLogModel, SecurityIncidentModel

PERIOD = {"Bugun": 1, "7 kun": 7, "30 kun": 30}
ROLE_NAMES = dict(UserModel.ROLES)


def protected_user(user):
    """Bu foydalanuvchiga ekran himoyasi qo'llanadimi (asosiy o'qituvchiga hech qachon)."""
    if not user.is_authenticated or user.is_main:
        return False
    from apps.core.models import SiteSettingsModel
    s = SiteSettingsModel.get()
    return bool(s.protect_students if user.is_student else s.protect_assistants)


# ---------------------------------------------------------------- brauzerdan kelgan hodisa
@login_required
@post_only
def incident(request):
    u = request.user
    if u.is_main:
        return JsonResponse({"ok": True, "skip": True})
    d = jload(request.body, {}) or {}
    kind = str(d.get("kind", ""))[:20]
    if kind not in KINDS:
        return JsonResponse({"ok": False}, status=400)
    if not S.rate_ok(u.pk):
        return JsonResponse({"ok": True, "limited": True})
    url = str(d.get("url", ""))[:400]
    if not url.startswith("/"):
        url = ""
    meta = {k: str(v)[:120] for k, v in (d.get("meta") or {}).items() if k in ("key", "detail", "tz", "lang", "vis", "w", "h")} if isinstance(d.get("meta"), dict) else {}
    rec, new = S.record_incident(request, kind, url=url, title=str(d.get("title", "")), content=str(d.get("content", "")),
                                 screen=str(d.get("screen", "")), meta=meta)
    return JsonResponse({"ok": True, "id": rec.pk, "new": new})


# ---------------------------------------------------------------- hodisalar ro'yxati
def _scope(request):
    qs = SecurityIncidentModel.objects.select_related("user", "reviewed_by")
    if request.user.is_assistant:
        qs = qs.filter(user__in=scoped_students(request.user))
    return qs


@perm_required("security")
def incidents(request):
    qs = _scope(request)
    now = timezone.now()
    day0 = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    g = request.GET
    if g.get("f_per") in PERIOD:
        qs = qs.filter(last_at__gte=now - timedelta(days=PERIOD[g["f_per"]]))
    if g.get("uid"):
        qs = qs.filter(user_id=g.get("uid"))
    base = _scope(request)
    st = {"today": base.filter(last_at__gte=day0).count(), "week": base.filter(last_at__gte=now - timedelta(days=7)).count(),
          "high": base.filter(severity="high", reviewed=False).count(), "open": base.filter(reviewed=False).count(),
          "users": base.filter(last_at__gte=now - timedelta(days=30)).values("user").distinct().count()}
    top = (base.filter(last_at__gte=now - timedelta(days=30)).values("user", "user__full_name", "user__uid")
           .annotate(n=Count("id"), r=Sum("count")).order_by("-n")[:5])
    by_kind = [(KINDS.get(r["kind"], (r["kind"],))[0], r["n"]) for r in
               base.filter(last_at__gte=now - timedelta(days=30)).values("kind").annotate(n=Count("id")).order_by("-n")[:6]]
    mx = max([n for _, n in by_kind] or [1])
    can_edit = request.user.can("security", "edit")
    rows = []
    for r in qs[:2000]:
        sv = T(r.sev_label, r.sev_tag)
        stt = T("Ko‘rib chiqilgan", "f") if r.reviewed else T("Yangi", "x")
        acts = []
        if can_edit and not r.reviewed:
            acts.append(A("check", "Ko‘rib chiqildi", post=reverse("security_review", args=[r.pk])))
        rows.append({"title": r.user.full_name, "sub": r.label, "avatar": True, "url": reverse("security_detail", args=[r.pk]),
                     "tags": [sv, stt] + ([T(f"×{r.count}")] if r.count > 1 else []),
                     "cells": [r.user.full_name, r.user.get_role_display(), r.label, sv, r.content or r.page_title or r.url or "—", r.count, r.last_at, stt],
                     "actions": acts, "search": f"{r.user.username} {r.user.uid} {r.url} {r.page_title}",
                     "f": {"kd": r.label, "sv": r.sev_label, "st": "Ko‘rib chiqilgan" if r.reviewed else "Yangi", "rl": r.user.get_role_display(),
                           "per": g.get("f_per", "")}})
    L = make_list(request, rows, ["Foydalanuvchi", "Rol", "Hodisa", "Daraja", "Sahifa / kontent", "Takror", "Oxirgi marta", "Holat"],
                  [("kd", "Hodisa", [v[0] for v in KINDS.values()]), ("sv", "Daraja", [x[1] for x in SEVERITY]),
                   ("st", "Holat", ["Yangi", "Ko‘rib chiqilgan"]), ("rl", "Rol", ["Talaba", "Yordamchi o‘qituvchi"]),
                   ("per", "Davr", list(PERIOD))], force_mode=None)
    filt_user = UserModel.objects.filter(pk=g.get("uid")).first() if g.get("uid") else None
    return render(request, "security/list.html", {"L": L, "st": st, "top": top, "by_kind": [(k, n, round(n / mx * 100)) for k, n in by_kind],
                                                  "filt_user": filt_user, "can_edit": can_edit})


@perm_required("security")
def incident_detail(request, pk):
    r = get_object_or_404(_scope(request), pk=pk)
    u = r.user
    other = SecurityIncidentModel.objects.filter(user=u).exclude(pk=r.pk)[:30]
    tot = SecurityIncidentModel.objects.filter(user=u)
    summary = [(KINDS.get(x["kind"], (x["kind"],))[0], x["n"], x["c"]) for x in tot.values("kind").annotate(n=Count("id"), c=Sum("count")).order_by("-n")]
    logs = AuditLogModel.objects.filter(actor=u)[:15]
    logins = u.logins.all()[:5]
    return render(request, "security/detail.html", {
        "r": r, "u": u, "other": other, "summary": summary, "n_total": tot.count(), "n_high": tot.filter(severity="high").count(),
        "logs": logs, "logins": logins, "can_edit": request.user.can("security", "edit"),
        "can_block": request.user.can("users", "edit") and (request.user.is_main or u.is_student),
        "meta": json.dumps(r.meta, ensure_ascii=False, indent=1) if r.meta else ""})


@perm_required("security", "edit")
@post_only
def incident_review(request, pk):
    r = get_object_or_404(_scope(request), pk=pk)
    act = request.POST.get("act", "review")
    note = request.POST.get("note", "").strip()[:2000]
    if note:
        r.note = note
    if act == "reopen":
        r.reviewed, r.reviewed_by, r.reviewed_at = False, None, None
        messages.success(request, "Hodisa qayta ochildi")
    else:
        r.reviewed, r.reviewed_by, r.reviewed_at = True, request.user, timezone.now()
        messages.success(request, "Hodisa ko‘rib chiqildi deb belgilandi")
    r.save()
    if act == "warn":
        from apps.notifications.services import notify
        notify([r.user], "⚠ Ogohlantirish: saytdagi ma’lumotlarni skrinshot qilish / yozib olish taqiqlangan. Takrorlansa hisobingiz bloklanadi.", "")
        messages.success(request, f"{r.user.full_name} ga ogohlantirish yuborildi")
    if act == "block" and request.user.can("users", "edit") and not r.user.is_main:
        from apps.core import jwt_auth as J
        from apps.core.models import log_event
        r.user.is_blocked = True
        r.user.save(update_fields=["is_blocked"])
        J.revoke_all(r.user)
        log_event("user_block", request.user, user=r.user, note="Xavfsizlik hodisasi #%d" % r.pk)
        messages.success(request, f"{r.user.full_name} bloklandi")
    if request.POST.get("all"):
        n = _scope(request).filter(user=r.user, reviewed=False).update(reviewed=True, reviewed_by=request.user, reviewed_at=timezone.now())
        if n:
            messages.success(request, f"Yana {n} ta hodisa ko‘rib chiqildi")
    return redirect(request.POST.get("next") or reverse("security_detail", args=[pk]))


# ---------------------------------------------------------------- tizim jurnali
def _log_scope(request):
    qs = AuditLogModel.objects.select_related("actor", "target_user")
    if request.user.is_assistant:
        ids = list(scoped_students(request.user).values_list("pk", flat=True)) + [request.user.pk]
        qs = qs.filter(Q(actor_id__in=ids) | Q(target_user_id__in=ids))
    return qs


@perm_required("logs")
def logs(request):
    qs = _log_scope(request)
    g = request.GET
    now = timezone.now()
    if g.get("f_per") in PERIOD:
        qs = qs.filter(created__gte=now - timedelta(days=PERIOD[g["f_per"]]))
    cmap = {v: k for k, v in CATS}
    if g.get("f_cat") in cmap:
        qs = qs.filter(category=cmap[g["f_cat"]])
    rmap = {"Bajarildi": "ok", "Xato": "fail", "Ruxsat yo‘q": "denied"}
    if g.get("f_res") in rmap:
        qs = qs.filter(result=rmap[g["f_res"]])
    rlmap = {v: k for k, v in UserModel.ROLES}
    if g.get("f_rl") in rlmap:
        qs = qs.filter(actor_role=rlmap[g["f_rl"]])
    if g.get("uid"):
        qs = qs.filter(Q(actor_id=g["uid"]) | Q(target_user_id=g["uid"]))
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(actor_name__icontains=q) | Q(label__icontains=q) | Q(obj_label__icontains=q) | Q(path__icontains=q) | Q(ip__icontains=q))
    day0 = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    base = _log_scope(request)
    st = {"today": base.filter(created__gte=day0).count(), "fail": base.filter(created__gte=now - timedelta(days=7), result="fail").count(),
          "denied": base.filter(created__gte=now - timedelta(days=7), result="denied").count(),
          "logins": base.filter(created__gte=day0, action="login").count()}
    rows = []
    for r in qs[:3000]:
        rt = T(*r.result_tag)
        rows.append({"title": r.label, "sub": f"{r.actor_name} · {timezone.localtime(r.created):%d.%m.%Y %H:%M:%S}", "url": reverse("log_detail", args=[r.pk]),
                     "tags": [T(r.cat_label), rt], "search": f"{r.actor_name} {r.obj_label} {r.path} {r.ip or ''}",
                     "cells": [r.created, r.actor_name, ROLE_NAMES.get(r.actor_role, "Mehmon"), r.label,
                               (f"{r.obj_type}: " if r.obj_type else "") + (r.obj_label or r.obj_id or "—"),
                               r.target_user.full_name if r.target_user else "—", rt, r.ip or "—"],
                     "f": {"cat": r.cat_label, "res": r.result_tag[0], "rl": ROLE_NAMES.get(r.actor_role, "Mehmon"), "per": g.get("f_per", "")}})
    L = make_list(request, rows, ["Vaqt", "Kim", "Rol", "Amal", "Obyekt", "Kim haqida", "Natija", "IP"],
                  [("cat", "Bo‘lim", [v for _, v in CATS]), ("res", "Natija", list(rmap)), ("rl", "Rol", [v for _, v in UserModel.ROLES]),
                   ("per", "Davr", list(PERIOD))], force_mode="table")
    filt_user = UserModel.objects.filter(pk=g.get("uid")).first() if g.get("uid") else None
    return render(request, "security/logs.html", {"L": L, "st": st, "filt_user": filt_user})


@perm_required("logs")
def log_detail(request, pk):
    r = get_object_or_404(_log_scope(request), pk=pk)
    near = _log_scope(request).filter(actor=r.actor, created__gte=r.created - timedelta(minutes=30),
                                      created__lte=r.created + timedelta(minutes=30)).exclude(pk=r.pk)[:20] if r.actor else []
    return render(request, "security/log_detail.html", {"r": r, "near": near, "role": ROLE_NAMES.get(r.actor_role, "Mehmon"),
                                                        "data": json.dumps(r.data, ensure_ascii=False, indent=2) if r.data else ""})

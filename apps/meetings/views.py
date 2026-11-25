import json

from django.conf import settings
from django.db.models import Count
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserModel
from apps.core.helpers import A, T, jload, make_list, parse_local, to_int
from apps.core.perms import deny, login_required, post_only
from apps.courses.services import scoped_students
from . import access, services as S
from .models import MPERMS, MeetingMemberModel, MeetingModel, MeetingRecordingModel

ACT = {"scheduled": ("Rejalashtirilgan", ""), "live": ("Jonli", "f"), "ended": ("Yakunlangan", "x")}
ACT_ICONS = {"start": "play", "end": "end", "kick": "chiqarildi", "invite": "taklif"}


def can_create(u):
    return u.is_authenticated and u.is_teacher and u.can("meetings", "add")


def _get(request, pk):
    m = get_object_or_404(MeetingModel.objects.select_related("host"), pk=pk)
    return m


def _kind_tag(m):
    return T("Ochiq", "") if m.is_public else T("Yopiq", "x")


def _when(m):
    return m.start_at or m.created


def _candidates(user, meeting):
    qs = UserModel.objects.on_site().filter(is_active=True, is_blocked=False).exclude(pk=meeting.host_id)
    if user.is_assistant:
        qs = qs.filter(pk__in=scoped_students(user).values_list("pk", flat=True))
    return qs.order_by("full_name")


def _picker_json(qs, off=()):
    return json.dumps([{"id": u.pk, "t": u.full_name or u.username, "s": f"@{u.username} · {u.uid}", "off": u.pk in off} for u in qs], ensure_ascii=False)


def fmt_dur(sec):
    sec = int(sec or 0)
    h, m = sec // 3600, sec // 60 % 60
    return (f"{h} soat " if h else "") + f"{m} daqiqa" if (h or m) else f"{sec} soniya"


@login_required
def meetings(request):
    u = request.user
    order = {"live": 0, "scheduled": 1, "ended": 2}
    qs = sorted(access.visible_meetings(u, ended=True).select_related("host").annotate(np=Count("sessions__user", distinct=True)),
                key=lambda m: (order[m.status], -(m.ended_at or m.start_at or m.created).timestamp()))
    rows = []
    for m in qs:
        lbl, cls = ACT[m.status]
        owner = access.is_owner(m, u)
        acts = []
        if owner and not m.is_ended:
            acts.append(A("edit-2", "Tahrirlash", url=reverse("meeting_edit", args=[m.pk])))
        if owner:
            acts.append(A("trash-2", "O‘chirish", post=reverse("meeting_delete", args=[m.pk]), confirm="Meeting o‘chirilsinmi? Barcha tarix va yozuvlar ham o‘chadi.", cls="dg"))
        dur = "—"
        if m.started_at:
            dur = fmt_dur(((m.ended_at or timezone.now()) - m.started_at).total_seconds())
        rows.append({"title": m.title, "sub": (m.description or "")[:70] or f"Boshlovchi: {m.host.full_name}", "url": reverse("meeting_detail", args=[m.pk]),
                     "tags": [T(lbl, cls), _kind_tag(m)],
                     "cells": [m.title, T(lbl, cls), _kind_tag(m), m.started_at or m.start_at, m.ended_at, dur, m.np, m.host.full_name], "actions": acts,
                     "search": m.host.full_name, "f": {"st": lbl, "kind": "Ochiq" if m.is_public else "Yopiq", "host": m.host.full_name}})
    add = []
    if can_create(u):
        add.append({"icon": "plus", "label": "Yangi meeting", "url": reverse("meeting_new")})
    hosts = sorted({r["f"]["host"] for r in rows})
    L = make_list(request, rows, ["Nomi", "Holat", "Turi", "Boshlangan / rejalangan", "Tugagan", "Davomiyligi", "Qatnashgan", "Boshlovchi"],
                  [("st", "Holat", ["Jonli", "Rejalashtirilgan", "Yakunlangan"]), ("kind", "Turi", ["Ochiq", "Yopiq"]), ("host", "Boshlovchi", hosts)],
                  add, force_mode=request.GET.get("mode") or "table")
    return render(request, "meetings/list.html", {"L": L})


def _save(request, m=None):
    d = request.POST
    title = d.get("title", "").strip()[:200]
    if not title:
        messages.error(request, "Meeting nomini kiriting")
        return None
    kind = d.get("kind") if d.get("kind") in ("public", "private") else "private"
    fields = dict(title=title, description=d.get("description", "").strip()[:2000], kind=kind, start_at=parse_local(d.get("start_at")),
                  chat_on=bool(d.get("chat_on")), mic_default=bool(d.get("mic_default")), cam_default=bool(d.get("cam_default")),
                  screen_default=bool(d.get("screen_default")))
    if m:
        for k, v in fields.items():
            setattr(m, k, v)
        m.save()
    else:
        m = MeetingModel.objects.create(host=request.user, **fields)
        MeetingMemberModel.objects.get_or_create(meeting=m, user=request.user, defaults={"invited": True})
    return m


KINDS = [("private", "Yopiq"), ("public", "Ochiq")]


def _form_ctx(request, m):
    if request.method == "POST":
        d = request.POST
        F = {k: d.get(k, "") for k in ("title", "description", "start_at", "kind")}
        F.update({k: bool(d.get(k)) for k in ("chat_on", "mic_default", "cam_default", "screen_default")})
    elif m:
        F = {"title": m.title, "description": m.description, "kind": m.kind, "chat_on": m.chat_on, "mic_default": m.mic_default,
             "cam_default": m.cam_default, "screen_default": m.screen_default,
             "start_at": timezone.localtime(m.start_at).strftime("%Y-%m-%dT%H:%M") if m.start_at else ""}
    else:
        F = {"title": "", "description": "", "start_at": "", "kind": "private", "chat_on": True, "mic_default": True, "cam_default": True, "screen_default": False}
    return {"m": m, "F": F, "kinds": KINDS}


@login_required
def meeting_new(request):
    if not can_create(request.user):
        return deny(request, "Meeting tashkil qilish uchun ruxsatingiz yo‘q", "meetings")
    if request.method == "POST":
        m = _save(request)
        if m:
            messages.success(request, "Meeting yaratildi. Endi qatnashchilarni taklif qiling")
            return redirect("meeting_detail", pk=m.pk)
    return render(request, "meetings/form.html", _form_ctx(request, None))


@login_required
def meeting_edit(request, pk):
    m = _get(request, pk)
    if not access.is_owner(m, request.user) or m.is_ended:
        return deny(request, to="meetings")
    if request.method == "POST":
        if _save(request, m):
            messages.success(request, "Saqlandi")
            return redirect("meeting_detail", pk=m.pk)
    return render(request, "meetings/form.html", _form_ctx(request, m))


@login_required
@post_only
def meeting_delete(request, pk):
    m = _get(request, pk)
    if not access.is_owner(m, request.user):
        return deny(request, to="meetings")
    if m.is_live:
        S.end_meeting(m, request.user)
    m.delete()
    messages.success(request, "Meeting o‘chirildi")
    return redirect("meetings")


@login_required
@post_only
def meeting_start(request, pk):
    m = _get(request, pk)
    if not access.is_moderator(m, request.user) or m.is_ended:
        return deny(request, to="meetings")
    S.start_meeting(m, request.user)
    return redirect("meeting_room", pk=m.pk)


@login_required
@post_only
def meeting_end(request, pk):
    m = _get(request, pk)
    if not access.can_perm(m, request.user, "end"):
        return deny(request, to="meetings")
    S.end_meeting(m, request.user)
    messages.success(request, "Meeting yakunlandi")
    return redirect("meeting_detail", pk=m.pk)


@login_required
def meeting_by_code(request, code):
    m = get_object_or_404(MeetingModel, code=code.lower())
    return redirect("meeting_detail", pk=m.pk)


@login_required
def meeting_detail(request, pk):
    u = request.user
    m = _get(request, pk)
    if not access.can_view(m, u):
        return deny(request, "Bu meetingni ko‘rishga ruxsatingiz yo‘q", "meetings")
    me = access.member_of(m, u)
    owner = access.is_owner(m, u)
    mod = access.is_moderator(m, u, me)
    perms = {c: access.can_perm(m, u, c, me) for c in ("kick", "mute", "comments", "invite", "grant", "end")}
    ok, why = access.can_join(m, u)
    mem = []
    if mod or m.is_public:
        for x in MeetingMemberModel.objects.filter(meeting=m).select_related("user").order_by("role", "user__full_name"):
            if x.user_id == m.host_id:
                continue
            if not mod and not (x.invited or x.role == "cohost"):
                continue
            mem.append({"x": x, "role": S.role_of(m, x.user, x), "perms": set(x.mperms or []), "caps": access.effective(m, x.user, x)})
    ctx = {"m": m, "me": me, "owner": owner, "mod": mod, "perms": perms, "can_join": ok, "why": why, "members": mem if mod else [],
           "n_members": len(mem), "mperms": MPERMS, "tag": ACT[m.status], "host_is_me": m.host_id == u.pk,
           "events": list(m.events.select_related("actor", "target")[:200]) if owner else [],
           "can_edit": owner and not m.is_ended, "link": request.build_absolute_uri(reverse("meeting_code", args=[m.code]))}
    if perms["invite"] and not m.is_ended:
        have = set(MeetingMemberModel.objects.filter(meeting=m, invited=True).values_list("user_id", flat=True))
        ctx["invite_json"] = _picker_json(_candidates(u, m), have)
    if owner and not m.is_ended:
        ass = UserModel.objects.on_site().filter(role="assistant", is_active=True, is_blocked=False).exclude(pk=m.host_id)
        have = set(MeetingMemberModel.objects.filter(meeting=m, role="cohost").values_list("user_id", flat=True))
        ctx["cohost_json"] = _picker_json(ass, have)
    ctx.update(_history(m, u, mod, owner, request))
    return render(request, "meetings/detail.html", ctx)


ROLE_UZ = {"host": "Boshlovchi", "cohost": "Yordamchi", "member": "Qatnashchi"}


def _history(m, u, mod, owner, request):
    """Detail sahifasi uchun to'liq tarix: sessiyalar, qatnashchilar statistikasi, izohlar, yozuvlar."""
    now = timezone.now()
    tabs = [(0, "Umumiy")]
    if mod:
        tabs += [(1, "Qatnashchilar"), (2, "Kirish-chiqish"), (3, "Izohlar")]
    if owner:
        tabs += [(4, "Yozuvlar"), (5, "Tarix")]
    tab = to_int(request.GET.get("tab"), 0)
    tab = tab if tab in [t[0] for t in tabs] else 0
    out = {"tabs": tabs, "tab": tab, "dur": fmt_dur(((m.ended_at or now) - m.started_at).total_seconds()) if m.started_at else "—"}
    if not mod:
        return out
    sess = list(m.sessions.select_related("user").order_by("joined_at"))
    for x in sess:
        x.sec = int(((x.left_at or now) - x.joined_at).total_seconds())
        x.dur = fmt_dur(x.sec)
        x.role_uz = ROLE_UZ.get(x.role, x.role)
        x.open = x.left_at is None
    out["sessions"] = sess
    stats = {}
    for x in sess:
        st = stats.setdefault(x.user_id, {"user": x.user, "first": x.joined_at, "last": x.left_at, "sec": 0, "n": 0, "role": x.role_uz, "open": False})
        st["sec"] += x.sec
        st["n"] += 1
        st["last"] = x.left_at
        st["open"] = st["open"] or x.open
    cc = dict(m.comments.filter(is_deleted=False).values_list("user_id").annotate(n=Count("id")))
    for st in stats.values():
        st["dur"] = fmt_dur(st["sec"])
        st["comments"] = cc.get(st["user"].pk, 0)
    out["stats"] = sorted(stats.values(), key=lambda s: s["first"])
    cm = list(m.comments.select_related("user", "deleted_by").order_by("created", "id"))
    for c in cm:
        c.role_uz = ROLE_UZ[S.role_of(m, c.user)]
    out["comments"] = cm
    if owner:
        recs = list(m.recordings.all())
        for r in recs:
            r.dur = fmt_dur(r.seconds)
            r.mb = round(r.size / 1048576, 1)
        out["recs"] = recs
    return out


@login_required
def meeting_room(request, pk):
    m = _get(request, pk)
    ok, why = access.can_join(m, request.user)
    if not ok:
        return deny(request, why, "meetings")
    return render(request, "meetings/room.html", {"m": m, "ice_obj": settings.MEETING_ICE_SERVERS})


@login_required
@post_only
def meeting_invite(request, pk):
    m = _get(request, pk)
    if m.is_ended or not access.can_perm(m, request.user, "invite"):
        return JsonResponse({"ok": False, "error": "Ruxsat yo‘q"}, status=403)
    ids = [to_int(x) for x in jload(request.body, {}).get("uids", [])]
    users = _candidates(request.user, m).filter(pk__in=ids)
    n = S.invite(m, request.user, users)
    return JsonResponse({"ok": True, "n": n})


@login_required
@post_only
def meeting_cohost_add(request, pk):
    m = _get(request, pk)
    if m.is_ended or not access.is_owner(m, request.user):
        return JsonResponse({"ok": False, "error": "Ruxsat yo‘q"}, status=403)
    ids = [to_int(x) for x in jload(request.body, {}).get("uids", [])]
    n = 0
    for u in UserModel.objects.on_site().filter(pk__in=ids, role="assistant", is_active=True, is_blocked=False).exclude(pk=m.host_id):
        x, _ = MeetingMemberModel.objects.get_or_create(meeting=m, user=u, defaults={"invited": True})
        x.role, x.invited, x.banned = "cohost", True, False
        x.mperms = x.mperms or ["kick", "mute", "comments", "invite"]
        x.save()
        S.log(m, request.user, "cohost", u)
        from apps.notifications.services import notify
        notify([u], f"Siz “{m.title}” meetingiga yordamchi etib biriktirildingiz", f"/meetings/{m.pk}/")
        n += 1
    return JsonResponse({"ok": True, "n": n})


@login_required
@post_only
def member_action(request, pk, uid):
    """Qatnashchi ustidan amallar (oddiy POST forma). Barcha huquqlar shu yerda tekshiriladi."""
    m = _get(request, pk)
    u = request.user
    back = redirect("meeting_detail", pk=m.pk)
    x = MeetingMemberModel.objects.filter(meeting=m, user_id=uid).select_related("user").first()
    if not x or uid == m.host_id or x.user.is_main or uid == u.pk:
        messages.error(request, "Bu amalni bajarib bo‘lmaydi")
        return back
    act = request.POST.get("action")
    owner = access.is_owner(m, u)
    target_mod = access.is_moderator(m, x.user, x)
    if act in ("cohost_off", "perms"):
        if not owner or x.role != "cohost":
            return deny(request, to="meetings")
        if act == "cohost_off":
            x.role, x.mperms = "member", []
            S.log(m, u, "cohost_off", x.user)
        else:
            x.mperms = access.clean_perms(request.POST.getlist("mperms"))
            S.log(m, u, "perms", x.user, ",".join(x.mperms))
        x.save()
        S.to_user(m.pk, x.user_id, {"type": "refresh_caps"})
    elif act == "caps":
        if not access.can_perm(m, u, "grant") or (target_mod and not owner):
            return deny(request, to="meetings")
        for k in ("mic", "cam", "chat", "screen"):
            v = request.POST.get(k)
            setattr(x, "can_" + k, None if v in (None, "", "default") else v == "1")
        x.save()
        S.log(m, u, "grant", x.user, "mic/cam/chat/screen")
        S.to_user(m.pk, x.user_id, {"type": "caps", "caps": access.effective(m, x.user, x)})
    elif act in ("ban", "unban"):
        if not access.can_perm(m, u, "kick") or (target_mod and not owner):
            return deny(request, to="meetings")
        x.banned = act == "ban"
        x.online = x.online and not x.banned
        x.save()
        S.log(m, u, act, x.user)
        if x.banned:
            S._send(S.ugrp(m.pk, x.user_id), {"type": "kicked"})
            S.broadcast(m.pk, {"type": "peer_left", "uid": x.user_id, "kicked": True})
    elif act == "remove":
        if not access.can_perm(m, u, "invite") or (target_mod and not owner):
            return deny(request, to="meetings")
        x.delete()
        S.log(m, u, "remove", None, x.user.username)
    else:
        messages.error(request, "Noma’lum amal")
        return back
    messages.success(request, "Bajarildi")
    return back


# ---------------------------------------------------------------- yozib olish (faqat egasi / asosiy o'qituvchi)
def _rec_guard(request, pk):
    m = _get(request, pk)
    if not access.is_owner(m, request.user):
        return m, None
    return m, True


@login_required
@post_only
def rec_start(request, pk):
    m, ok = _rec_guard(request, pk)
    if not ok or not m.is_live:
        return JsonResponse({"ok": False, "error": "Ruxsat yo‘q yoki meeting jonli emas"}, status=403)
    r = S.rec_start(m, request.user)
    return JsonResponse({"ok": bool(r), "id": r.pk if r else None, "error": "" if r else "Yozuv allaqachon ketmoqda"}, status=200 if r else 409)


@login_required
@post_only
def rec_chunk(request, pk, rid):
    m, ok = _rec_guard(request, pk)
    r = MeetingRecordingModel.objects.filter(pk=rid, meeting=m, active=True, started_by=request.user).first()
    if not ok or not r:
        return JsonResponse({"ok": False}, status=403)
    f = S.rec_dir() / r.path
    if f.stat().st_size + len(request.body) > settings.MEETING_REC_MAX_MB * 1024 * 1024:
        S.rec_finish(r, request.user)
        return JsonResponse({"ok": False, "error": "Yozuv hajmi chegarasiga yetdi"}, status=413)
    with open(f, "ab") as fh:
        fh.write(request.body)
    return JsonResponse({"ok": True})


@login_required
@post_only
def rec_stop(request, pk):
    m, ok = _rec_guard(request, pk)
    if not ok:
        return JsonResponse({"ok": False}, status=403)
    for r in MeetingRecordingModel.objects.filter(meeting=m, active=True):
        S.rec_finish(r, request.user)
    return JsonResponse({"ok": True})


@login_required
def rec_file(request, pk, rid):
    """Yozuvni ko'rish/yuklab olish — faqat egasi va asosiy o'qituvchi (Range qo'llab-quvvatlanadi)."""
    m, ok = _rec_guard(request, pk)
    r = MeetingRecordingModel.objects.filter(pk=rid, meeting=m).first()
    if not ok or not r:
        raise Http404
    f = S.rec_dir() / r.path
    if not f.exists():
        raise Http404
    size, start, end = f.stat().st_size, 0, None
    rng = request.headers.get("Range", "")
    if rng.startswith("bytes="):
        a, _, b = rng[6:].partition("-")
        start = to_int(a, 0)
        end = to_int(b, size - 1) if b else size - 1
        end = min(end, size - 1)
        with open(f, "rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        resp = HttpResponse(data, status=206, content_type="video/webm")
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
    else:
        resp = FileResponse(open(f, "rb"), content_type="video/webm")
    resp["Accept-Ranges"] = "bytes"
    resp["Cache-Control"] = "private, no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    if request.GET.get("dl"):
        resp["Content-Disposition"] = f'attachment; filename="meeting_{m.pk}_{r.pk}.webm"'
    return resp

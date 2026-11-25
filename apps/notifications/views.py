import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GroupModel, UserModel
from apps.core.helpers import A, T, clean_html, jload, make_list, to_int
from apps.core.perms import deny, login_required, perm_required, post_only
from apps.courses.services import my_groups, scoped_students
from .models import MessageDeliveryModel, MessageModel, NotificationModel
from .services import deliver, recipients, retry_failed, unread_count


@login_required
def notifications(request):
    u = request.user
    rows = []
    for d in MessageDeliveryModel.objects.filter(user=u, channel="app", ok=True).select_related("message__author"):
        m = d.message
        tt = T("O‘qilgan") if d.is_read else T("O‘qilmagan", "x")
        rows.append({"title": m.title, "sub": m.short, "url": reverse("notification_open", args=["m", d.pk]), "tags": [tt] + ([T("Muhim", "x")] if m.important else []),
                     "cells": [m.title, m.author.full_name if m.author else "—", m.created, tt], "sort": m.created,
                     "f": {"st": "O‘qilgan" if d.is_read else "O‘qilmagan", "pr": "Muhim" if m.important else "Oddiy"}})
    for n in NotificationModel.objects.filter(user=u):
        tt = T("O‘qilgan") if n.is_read else T("O‘qilmagan", "x")
        rows.append({"title": n.text, "sub": n.created.strftime("%d.%m.%Y %H:%M"), "url": reverse("notification_open", args=["n", n.pk]), "tags": [tt],
                     "cells": [n.text, "Tizim", n.created, tt], "sort": n.created,
                     "f": {"st": "O‘qilgan" if n.is_read else "O‘qilmagan", "pr": "Oddiy"}})
    rows.sort(key=lambda r: r["sort"], reverse=True)
    add = [{"icon": "check-circle", "label": "Hammasini o‘qilgan deb belgilash", "post": reverse("read_all"), "cls": "s"}]
    return render(request, "shared/notifications.html", {"L": make_list(request, rows, ["Xabarnoma", "Yuboruvchi", "Sana", "Holat"],
                  [("st", "Holat", ["O‘qilmagan", "O‘qilgan"]), ("pr", "Muhimlik", ["Oddiy", "Muhim"])], add)})


@login_required
def notification_open(request, kind, pk):
    u = request.user
    if kind == "m":
        d = get_object_or_404(MessageDeliveryModel.objects.select_related("message__author"), pk=pk, user=u)
        if not d.is_read:
            d.is_read, d.read_at = True, timezone.now()
            d.save(update_fields=["is_read", "read_at"])
        return render(request, "shared/notification_open.html", {"m": d.message})
    n = get_object_or_404(NotificationModel, pk=pk, user=u)
    NotificationModel.objects.filter(pk=pk).update(is_read=True)
    if n.link and n.link.startswith("/") and not n.link.startswith("//"):
        return redirect(n.link)
    return redirect("notifications")


@login_required
@post_only
def read_all(request):
    NotificationModel.objects.filter(user=request.user, is_read=False).update(is_read=True)
    MessageDeliveryModel.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
    messages.success(request, "Hammasi o‘qilgan deb belgilandi")
    return redirect("notifications")


def _stats(m):
    d = m.deliveries
    return {"n": d.values("user").distinct().count(), "ok": d.filter(ok=True).count(), "bad": d.filter(ok=False).count(), "rd": d.filter(is_read=True).count()}


@perm_required("notify")
def messages_list(request):
    u = request.user
    qs = MessageModel.objects.select_related("author")
    if u.is_assistant:
        qs = qs.filter(author=u)
    rows = []
    for m in qs:
        s = _stats(m)
        rt = T(f"{s['ok']} / {s['ok'] + s['bad']}", "x" if s["bad"] else "f")
        rows.append({"title": m.title, "sub": m.short, "url": reverse("message_detail", args=[m.pk]), "tags": [T(MessageModel.AUD[m.audience]), rt],
                     "cells": [m.title, MessageModel.AUD[m.audience], MessageModel.CH[m.channel], m.author.full_name if m.author else "—", m.created, rt],
                     "actions": [A("edit-2", "Tahrirlash", url=reverse("message_edit", args=[m.pk])),
                                 A("refresh-cw", "Xatoliklarni qayta yuborish", post=reverse("message_resend", args=[m.pk])),
                                 A("trash-2", "O‘chirish", post=reverse("message_delete", args=[m.pk]), confirm="Xabarnoma o‘chirilsinmi?", cls="x")],
                     "f": {"au": MessageModel.AUD[m.audience], "ch": MessageModel.CH[m.channel], "st": "Xatolik bor" if s["bad"] else "Hammasi yetkazilgan"}})
    return render(request, "staff/messages/list.html", {"L": make_list(request, rows, ["Sarlavha", "Auditoriya", "Kanal", "Yuboruvchi", "Sana", "Natija"],
                  [("au", "Auditoriya", list(MessageModel.AUD.values())), ("ch", "Kanal", list(MessageModel.CH.values())), ("st", "Natija", ["Xatolik bor", "Hammasi yetkazilgan"])],
                  [{"icon": "plus", "label": "Xabarnoma yuborish", "url": reverse("message_new")}])})


def _aud_types(u):
    return ["mygroups", "group", "users"] if u.is_assistant else ["all", "students", "staff", "nobuy", "buyers", "inactive", "online", "group", "users"]


@perm_required("notify")
def message_new(request):
    u = request.user
    types = _aud_types(u)
    if request.method == "POST":
        P = request.POST
        title, body = P.get("title", "").strip(), clean_html(P.get("body", ""))
        aud, ch = P.get("audience"), P.get("channel", "app")
        gids, uids = [to_int(x) for x in P.getlist("groups")], [to_int(x) for x in P.getlist("users")]
        err = None
        if not title:
            err = "Sarlavhani kiriting"
        elif not body.strip():
            err = "Xabar matnini yozing"
        elif aud not in types or ch not in MessageModel.CH:
            err = "Auditoriya yoki kanal noto‘g‘ri"
        elif aud == "group" and not gids:
            err = "Kamida bitta guruhni tanlang"
        elif aud == "users" and not uids:
            err = "Kamida bitta foydalanuvchini tanlang"
        if not err:
            groups = list(my_groups(u).filter(pk__in=gids))
            users = list(UserModel.objects.on_site().filter(pk__in=uids))
            rcp = list(recipients(aud, u, groups, users).distinct())
            if not rcp:
                err = "Qabul qiluvchi topilmadi"
        if err:
            messages.error(request, err)
        else:
            m = MessageModel.objects.create(title=title[:200], short=P.get("short", "")[:200], body=body, audience=aud, channel=ch,
                                            important=P.get("priority") == "important", author=u)
            m.groups.set(groups)
            m.users.set([x for x in users if x in rcp])
            deliver(m, rcp)
            s = _stats(m)
            messages.success(request, f"Yuborildi: {s['ok']} ta yetkazildi" + (f", {s['bad']} ta xatolik" if s["bad"] else ""))
            return redirect("message_detail", pk=m.pk)
    pre = request.GET.get("uid")
    return render(request, "staff/messages/form.html", {"m": None, "channel_opts": [("app", "Sayt ichida"), ("sms", "SMS"), ("both", "Ikkalasi")],
        "prio_opts": [("normal", "Oddiy"), ("important", "Muhim")], "types": [(k, MessageModel.AUD[k]) for k in types], "pre": pre,
        "groups_json": json.dumps([{"id": g.pk, "t": g.name, "s": f"{g.kind_label} · {g.members.filter(show_on_site=True).count()} talaba"} for g in my_groups(u)], ensure_ascii=False),
        "users_json": json.dumps([{"id": s.pk, "t": s.full_name, "s": f"{s.uid} · {s.get_role_display()}"} for s in (scoped_students(u) if u.is_assistant else UserModel.objects.on_site().exclude(pk=u.pk))], ensure_ascii=False)})


def _msg(request, pk):
    qs = MessageModel.objects.all()
    if request.user.is_assistant:
        qs = qs.filter(author=request.user)
    return get_object_or_404(qs, pk=pk)


@perm_required("notify")
def message_detail(request, pk):
    m = _msg(request, pk)
    tab = request.GET.get("tab", "body")
    ds = m.deliveries.select_related("user")
    return render(request, "staff/messages/detail.html", {"m": m, "s": _stats(m), "tab": tab if tab in ("body", "rcp", "err") else "body",
        "tabs": [("body", "Xabar matni"), ("rcp", "Qabul qiluvchilar"), ("err", "Xatoliklar")], "rows": ds if tab == "rcp" else ds.filter(ok=False) if tab == "err" else [],
        "aud": MessageModel.AUD[m.audience], "ch": MessageModel.CH[m.channel]})


@perm_required("notify")
def message_edit(request, pk):
    m = _msg(request, pk)
    if request.method == "POST":
        body = clean_html(request.POST.get("body", ""))
        if not request.POST.get("title", "").strip() or not body.strip():
            messages.error(request, "Sarlavha va matnni kiriting")
        else:
            m.title, m.short, m.body = request.POST["title"].strip()[:200], request.POST.get("short", "")[:200], body
            m.save()
            messages.success(request, "Xabarnoma saqlandi")
            return redirect("message_detail", pk=pk)
    return render(request, "staff/messages/form.html", {"m": m, "body_json": json.dumps(m.body)})


@perm_required("notify")
@post_only
def message_resend(request, pk):
    n = retry_failed(_msg(request, pk))
    messages.success(request, f"{n} ta qayta yuborildi") if n else messages.info(request, "Qayta yuborib bo‘ladigan xatolik yo‘q")
    return redirect(request.POST.get("next") or reverse("message_detail", args=[pk]))


@perm_required("notify")
@post_only
def message_delete(request, pk):
    _msg(request, pk).delete()
    messages.success(request, "Xabarnoma o‘chirildi")
    return redirect("messages")


@perm_required("notify")
def recipients_count(request):
    u = request.user
    aud = request.GET.get("a")
    if aud not in _aud_types(u):
        return JsonResponse({"n": 0})
    groups = list(my_groups(u).filter(pk__in=[to_int(x) for x in request.GET.getlist("g")]))
    users = list(UserModel.objects.on_site().filter(pk__in=[to_int(x) for x in request.GET.getlist("u")]))
    return JsonResponse({"n": recipients(aud, u, groups, users).distinct().count()})

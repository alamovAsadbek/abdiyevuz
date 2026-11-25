import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.core import jwt_auth as J
from apps.core.helpers import A, T, make_list, to_int
from apps.core.models import EVENTS, log_event
from apps.core.perms import deny, login_required, main_required, perm_required, post_only
from apps.courses.services import my_groups, scoped_students, student_in_scope
from apps.notifications.services import notify
from . import permissions as PM
from .models import GroupModel, LoginHistoryModel, UserModel
from .utils import UN_RE, device_of, gen_password, norm_phone, phone_ok, slugify_name, unique_username

ROLE_OPTS = [(UserModel.STUDENT, "Talaba"), (UserModel.ASSISTANT, "Yordamchi o‘qituvchi"), (UserModel.MAIN, "Asosiy o‘qituvchi")]


def _record(user, request, ok, reason=""):
    P = request.POST
    LoginHistoryModel.objects.create(
        user=user, ok=ok, reason=reason, ip=J.client_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        device=device_of(request.META.get("HTTP_USER_AGENT", "")), language=P.get("lang", "")[:20], tz=P.get("tz", "")[:50],
        screen=P.get("scr", "")[:20])


def _safe_next(request):
    n = request.GET.get("next") or request.POST.get("next") or ""
    return n if n.startswith("/") and not n.startswith("//") else ""


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    ctx = {"next": _safe_next(request)}
    if request.method == "POST":
        un = request.POST.get("username", "").strip().lower()
        pw = request.POST.get("password", "")
        ip = J.client_ip(request) or "?"
        key = f"lf:{ip}:{un}"
        if cache.get(key, 0) >= settings.LOGIN_MAX_FAILS:
            ctx["error"] = f"Juda ko‘p urinish. {settings.LOGIN_LOCK_MINUTES} daqiqadan keyin qayta urinib ko‘ring"
        else:
            target = UserModel.objects.filter(username=un).first()
            user = authenticate(request, username=un, password=pw)
            if user and user.is_blocked:
                _record(user, request, False, "Hisob bloklangan")
                ctx["error"] = "Hisobingiz bloklangan"
            elif user:
                cache.delete(key)
                _record(user, request, True)
                UserModel.objects.filter(pk=user.pk).update(last_login=timezone.now(), last_seen=timezone.now())
                resp = redirect(_safe_next(request) or "dashboard")
                J.set_cookies(resp, *J.issue_pair(user, request))
                messages.success(request, "Xush kelibsiz, " + (user.full_name.split() or [user.username])[0])
                return resp
            else:
                cache.set(key, cache.get(key, 0) + 1, settings.LOGIN_LOCK_MINUTES * 60)
                if target:
                    _record(target, request, False, "Noto‘g‘ri parol")
                ctx["error"] = "Foydalanuvchi nomi yoki parol noto‘g‘ri"
        ctx["username"] = un
    return render(request, "auth/login.html", ctx)


def register_view(request):
    from apps.core.models import SiteSettingsModel
    if request.user.is_authenticated:
        return redirect("dashboard")
    if not SiteSettingsModel.get().registration_open:
        messages.error(request, "Hozircha ro‘yxatdan o‘tish yopiq")
        return redirect("login")
    ctx = {}
    if request.method == "POST":
        P = request.POST
        name, un, pw, pw2 = P.get("full_name", "").strip(), P.get("username", "").strip().lower(), P.get("password", ""), P.get("password2", "")
        phone = P.get("phone", "").strip()
        ctx.update(full_name=name, username=un, phone=phone)
        ipk = "reg:" + (J.client_ip(request) or "?")
        err = None
        if cache.get(ipk, 0) >= 10:
            err = "Juda ko‘p ro‘yxatdan o‘tish urinishi. Keyinroq urinib ko‘ring"
        elif not name:
            err = "Ism familiyani kiriting"
        elif not UN_RE.match(un):
            err = "Foydalanuvchi nomi kamida 3 ta lotin harf/raqam bo‘lsin"
        elif UserModel.objects.filter(username=un).exists():
            err = "Bu foydalanuvchi nomi band, boshqasini tanlang"
        elif not phone_ok(phone):
            err = "Telefon raqami to‘liq emas"
        elif pw != pw2:
            err = "Parollar bir-biriga mos emas"
        else:
            try:
                validate_password(pw)
            except ValidationError as e:
                err = e.messages[0]
        if err:
            ctx["error"] = err
        else:
            cache.set(ipk, cache.get(ipk, 0) + 1, 3600)
            u = UserModel.objects.create_user(username=un, password=pw, full_name=name, phone=norm_phone(phone))
            _record(u, request, True)
            resp = redirect("dashboard")
            J.set_cookies(resp, *J.issue_pair(u, request))
            messages.success(request, "Ro‘yxatdan o‘tdingiz")
            return resp
    return render(request, "auth/register.html", ctx)


@require_POST
def logout_view(request):
    request._jwt_skip = True
    J.revoke(request.COOKIES.get(J.REFRESH_COOKIE))
    resp = redirect("home")
    J.clear_cookies(resp)
    return resp


def ping(request):
    """Cookie'larni yangilash (WebSocket ulanishdan oldin chaqiriladi)."""
    return JsonResponse({"ok": request.user.is_authenticated})


@login_required
def profile(request):
    u = request.user
    if request.method == "POST":
        P = request.POST
        name, un, phone = P.get("full_name", "").strip(), P.get("username", "").strip().lower(), P.get("phone", "").strip()
        p0, p1, p2 = P.get("p0", ""), P.get("p1", ""), P.get("p2", "")
        err = None
        if not name:
            err = "Ism familiyani kiriting"
        elif not UN_RE.match(un):
            err = "Foydalanuvchi nomi kamida 3 ta lotin harf/raqam bo‘lsin"
        elif UserModel.objects.filter(username=un).exclude(pk=u.pk).exists():
            err = "Bu foydalanuvchi nomi band"
        elif not phone_ok(phone):
            err = "Telefon raqami to‘liq emas"
        elif p0 or p1 or p2:
            if not u.check_password(p0):
                err = "Joriy parol noto‘g‘ri"
            elif p1 != p2:
                err = "Parollar bir-biriga mos emas"
            else:
                try:
                    validate_password(p1, u)
                except ValidationError as e:
                    err = e.messages[0]
        if err:
            messages.error(request, err)
        else:
            u.full_name, u.username, u.phone = name, un, norm_phone(phone)
            resp = redirect("profile")
            if p1:
                u.set_password(p1)
                J.revoke_all(u)
                u.save()
                J.set_cookies(resp, *J.issue_pair(u, request))
            else:
                u.save()
            messages.success(request, "Profil yangilandi")
            return resp
    return render(request, "shared/profile.html", {})


@login_required
def settings_view(request):
    ctx = {"theme_opts": [("light", "Yorug‘"), ("dark", "Qorong‘i")], "mode_opts": [("cards", "Kartalar"), ("table", "Jadval")],
           "act_opts": [("top", "Tepada"), ("float", "Suzuvchi panel")]}
    if request.user.is_main:
        role = request.GET.get("role") if request.GET.get("role") in ("assistant", "student") else "assistant"
        ctx.update(role_tab=role, role_tabs=[("assistant", "Yordamchi o‘qituvchi"), ("student", "Talaba")],
                   role_rows=PM.matrix(role, PM.role_defaults(role)))
    return render(request, "shared/settings.html", ctx)


@main_required
@post_only
def role_perms(request):
    """Rol standartini saqlash: shaxsiy ruxsati yo'q barcha yordamchi / talabalarga darhol amal qiladi."""
    from apps.core.models import SiteSettingsModel
    role = request.POST.get("role")
    if role not in ("assistant", "student"):
        return deny(request, "Noto‘g‘ri rol", "settings")
    s = SiteSettingsModel.get()
    data = dict(s.role_perms or {})
    if request.POST.get("reset") == "1":
        data.pop(role, None)
        messages.success(request, "Tizim standarti tiklandi")
    else:
        data[role] = PM.from_post(role, request.POST)
        messages.success(request, "Rol standarti saqlandi")
    s.role_perms = data
    s.save(update_fields=["role_perms"])
    return redirect(reverse("settings") + f"?role={role}#roles")


# ---------------------------------------------------------------- users (staff)
def _user_scope(request):
    qs = UserModel.objects.on_site().exclude(pk=request.user.pk)
    if request.user.is_assistant:
        qs = scoped_students(request.user).exclude(pk=request.user.pk)
    return qs


def _get_user(request, pk):
    u = get_object_or_404(_user_scope(request), pk=pk)
    return u


@perm_required("users")
def users(request):
    me = request.user
    can_act = me.can_view("activity")
    P = me.acts("users")
    rows = []
    for u in _user_scope(request).prefetch_related("member_groups").order_by("-id"):
        gs = [g.name for g in u.member_groups.all()]
        st = T("Bloklangan", "x") if u.is_blocked else T("Faol", "f")
        acts = []
        if me.can("gift", "use") and u.is_student:
            acts.append(A("gift", "Kurs berish", url=reverse("user_detail", args=[u.pk]) + "?tab=kurs&gift=1"))
        if me.is_main and not u.is_main:
            acts.append(A("key", "Ruxsatlar", url=reverse("user_detail", args=[u.pk]) + "?tab=perm"))
        if P["edit"] and not u.is_main:
            acts += [A("edit-2", "Tahrirlash", url=reverse("user_detail", args=[u.pk]) + "?tab=info"),
                     A("slash", "Bloklash", post=reverse("user_block", args=[u.pk]), confirm="Blokdan chiqarilsinmi?" if u.is_blocked else "Foydalanuvchi bloklansinmi?")]
        if P["delete"] and not u.is_main:
            acts.append(A("trash-2", "O‘chirish", post=reverse("user_delete", args=[u.pk]), confirm=f"{u.full_name} o‘chirilsinmi?", cls="x"))
        cells = [u.full_name, "@" + u.username, u.uid, u.get_role_display(), ", ".join(gs) or "—", st]
        if can_act:
            cells.append(T("Onlayn", "f") if u.online else T("Oxirgi: " + ("%s" % u.last_seen.strftime("%d.%m %H:%M") if u.last_seen else "kirmagan")))
        rows.append({"title": u.full_name, "sub": u.get_role_display(), "avatar": True, "url": reverse("user_detail", args=[u.pk]),
                     "tags": [st], "cells": cells, "actions": acts, "search": f"{u.username} {u.uid} {u.phone}",
                     "f": {"role": u.get_role_display(), "grp": gs or ["—"], "st": "Bloklangan" if u.is_blocked else "Faol", "on": "Onlayn" if u.online else "Oflayn"}})
    headers = ["Foydalanuvchi", "Foydalanuvchi nomi", "Maxsus ID", "Rol", "Guruh", "Holat"] + (["Faollik"] if can_act else [])
    filters = [("role", "Rol", ["Talaba", "Yordamchi o‘qituvchi", "Asosiy o‘qituvchi"]),
               ("grp", "Guruh", [g.name for g in my_groups(request.user)] + ["—"]), ("st", "Holat", ["Faol", "Bloklangan"])]
    if can_act:
        filters.append(("on", "Faollik", ["Onlayn", "Oflayn"]))
    add = [{"icon": "users", "label": "Ko‘plab qo‘shish", "url": reverse("user_bulk"), "cls": "s"},
           {"icon": "user-plus", "label": "Qo‘shish", "url": reverse("user_new")}] if P["add"] else None
    return render(request, "staff/users/list.html", {"L": make_list(request, rows, headers, filters, add)})


def _role_options(request):
    return ROLE_OPTS if request.user.is_main else [ROLE_OPTS[0]]


def _validate_user(request, existing=None):
    P = request.POST
    d = {"full_name": P.get("full_name", "").strip(), "username": P.get("username", "").strip().lower(),
         "phone": P.get("phone", "").strip(), "role": P.get("role", "student"), "password": P.get("password", "")}
    err = None
    if d["role"] not in dict(ROLE_OPTS) or (not request.user.is_main and d["role"] != "student"):
        d["role"] = existing.role if existing else "student"
        if not request.user.is_main and P.get("role") not in (None, "student", ""):
            err = "Sizda bu rolni berish huquqi yo‘q"
    if not d["full_name"]:
        err = "Ism familiyani kiriting"
    elif not UN_RE.match(d["username"]):
        err = "Foydalanuvchi nomi kamida 3 ta lotin harf/raqam bo‘lsin"
    elif UserModel.objects.filter(username=d["username"]).exclude(pk=getattr(existing, "pk", None)).exists():
        err = "Bu foydalanuvchi nomi band, boshqasini yozing"
    elif not phone_ok(d["phone"]):
        err = "Telefon raqami to‘liq emas"
    elif not existing and not d["password"]:
        err = "Parol kerak"
    elif d["password"]:
        try:
            validate_password(d["password"])
        except ValidationError as e:
            err = e.messages[0]
    return d, err


@perm_required("users")
def user_new(request):
    ctx = {"role_options": _role_options(request), "pw": gen_password(), "group_options": [("", "Guruhsiz")] + [(g.pk, g.name) for g in my_groups(request.user)],
           "pm_assistant": PM.matrix("assistant", PM.role_defaults("assistant")), "pm_student": PM.matrix("student", PM.role_defaults("student"))}
    if request.method == "POST":
        d, err = _validate_user(request)
        gid = request.POST.get("group")
        grp = my_groups(request.user).filter(pk=gid).first() if gid else None
        if not err and request.user.is_assistant and not grp:
            err = "Guruhni tanlang (yordamchi faqat o‘z guruhiga talaba qo‘sha oladi)"
        if err:
            messages.error(request, err)
            ctx.update(d=d, pw=d["password"])
        else:
            n = UserModel.objects.create_user(username=d["username"], password=d["password"], full_name=d["full_name"],
                                              phone=norm_phone(d["phone"]), role=d["role"])
            if request.user.is_main and not n.is_main and request.POST.get("custom_perms") == "1":
                n.set_grants(PM.from_post(n.role, request.POST, "pa" if n.is_assistant else "ps"))
                n.save(update_fields=["perms"])
            if grp and n.is_student:
                grp.members.add(n)
                log_event("group_add", request.user, user=n, group=grp, note=grp.name)
            messages.success(request, f"Foydalanuvchi qo‘shildi. Login: {n.username} · Parol: {d['password']} — hozir nusxalab oling")
            request.session["new_cred"] = {"name": n.full_name, "uid": n.uid, "un": n.username, "pw": d["password"]}
            return redirect("users")
    return render(request, "staff/users/form.html", ctx)


@perm_required("users")
def user_bulk(request):
    ctx = {"group_options": [("", "Guruhsiz")] + [(g.pk, g.name) for g in my_groups(request.user)]}
    if request.method == "POST":
        grp = my_groups(request.user).filter(pk=request.POST.get("group") or 0).first()
        if request.user.is_assistant and not grp:
            messages.error(request, "Guruhni tanlang")
            return render(request, "staff/users/bulk.html", ctx)
        out = []
        for ln in request.POST.get("lines", "").splitlines()[:300]:
            p = [x.strip() for x in ln.replace(";", ",").replace("\t", ",").split(",")]
            if not p or not p[0]:
                continue
            ph = norm_phone(p[1]) if len(p) > 1 else ""
            un, pw = unique_username(slugify_name(p[0])), gen_password(10)
            u = UserModel.objects.create_user(username=un, password=pw, full_name=p[0], phone=ph)
            if grp:
                grp.members.add(u)
                log_event("group_add", request.user, user=u, group=grp, note=grp.name)
            out.append({"name": p[0], "un": un, "pw": pw, "ph": ph, "bad": len(p) > 1 and p[1] and not ph})
        if not out:
            messages.error(request, "Talabalar ro‘yxatini kiriting")
        else:
            ctx["result"] = out
            messages.success(request, f"{len(out)} ta talaba qo‘shildi")
    return render(request, "staff/users/bulk.html", ctx)


@perm_required("users")
def user_detail(request, pk):
    from apps.courses.models import CourseAccessModel, CourseModel, SubmissionModel
    from apps.courses.services import completed_count
    from apps.core.models import EventModel
    from apps.exams.models import AttemptModel
    from apps.notifications.models import MessageDeliveryModel
    u = _get_user(request, pk)
    me = request.user
    keys = ["kurs", "guruh", "test", "vazifa", "info"] + (["xabar"] if me.can_view("notify") else []) + (["faol"] if me.can_view("activity") else []) + ["tarix"]
    if not u.is_student:
        keys = [k for k in keys if k not in ("kurs", "test", "vazifa")]
    if me.is_main and not u.is_main:
        keys.append("perm")
    names = {"kurs": "Kurslari", "guruh": "Guruhlari", "test": "Testlari", "vazifa": "Vazifalar", "info": "Ma‘lumotlar", "perm": "Ruxsatlar",
             "xabar": "Xabarnomalar", "faol": "Faollik", "tarix": "Tarix"}
    tab = request.GET.get("tab") if request.GET.get("tab") in keys else keys[0]
    ctx = {"u": u, "tabs": [(k, names[k]) for k in keys], "tab": tab, "role_options": _role_options(request), "P": me.acts("users"),
           "can_gift": me.can("gift", "use") and u.is_student}
    if tab == "kurs":
        rows = []
        for a in CourseAccessModel.objects.filter(user=u).select_related("course", "module", "granted_by"):
            if a.course.is_hidden:
                continue
            done, tot = completed_count(u, a.course)
            rows.append({"a": a, "pct": round(done / tot * 100) if tot else 0})
        ctx["accesses"] = rows
    elif tab == "guruh":
        ctx["ugroups"] = u.member_groups.all()
        ctx["free_groups"] = json.dumps([{"id": g.pk, "t": g.name, "s": g.kind_label} for g in my_groups(me).exclude(members=u)], ensure_ascii=False)
    elif tab == "test":
        ctx["attempts"] = AttemptModel.objects.filter(user=u).select_related("test")
    elif tab == "vazifa":
        ctx["subs"] = SubmissionModel.objects.filter(student=u).select_related("task__lesson__module__course")
    elif tab == "xabar":
        ctx["deliveries"] = MessageDeliveryModel.objects.filter(user=u).select_related("message")[:50]
    elif tab == "faol":
        logs = u.logins.all()
        ctx.update(logs=logs[:60], ok_count=logs.filter(ok=True).count(), last_login=logs.filter(ok=True).first())
    elif tab == "tarix":
        ctx["events"] = EventModel.objects.filter(Q(user=u) | Q(actor=u)).select_related("course", "user", "actor", "group")[:100]
    elif tab == "perm":
        ctx.update(_perm_ctx(u))
    return render(request, "staff/users/detail.html", ctx)


@perm_required("users")
@post_only
def user_edit(request, pk):
    u = _get_user(request, pk)
    d, err = _validate_user(request, u)
    if u.is_main or (not request.user.is_main and u.role != "student"):
        err = "Bu foydalanuvchini tahrirlab bo‘lmaydi"
    if err:
        messages.error(request, err)
    else:
        u.full_name, u.username, u.phone = d["full_name"], d["username"], norm_phone(d["phone"])
        if request.user.is_main:
            u.role = d["role"]
        if d["password"]:
            u.set_password(d["password"])
            J.revoke_all(u)
        u.save()
        messages.success(request, "Ma‘lumotlar saqlandi")
    return redirect(reverse("user_detail", args=[pk]) + "?tab=info")


@perm_required("users")
@post_only
def user_block(request, pk):
    u = _get_user(request, pk)
    if u.is_main:
        return deny(request, "Asosiy o‘qituvchini bloklab bo‘lmaydi", "users")
    u.is_blocked = not u.is_blocked
    u.save(update_fields=["is_blocked"])
    if u.is_blocked:
        J.revoke_all(u)
    log_event("user_block" if u.is_blocked else "user_unblock", request.user, user=u)
    messages.success(request, "Foydalanuvchi bloklandi" if u.is_blocked else "Blokdan chiqarildi")
    return redirect(request.POST.get("next") or "users")


@perm_required("users")
@post_only
def user_delete(request, pk):
    u = _get_user(request, pk)
    if u.is_main:
        return deny(request, "Asosiy o‘qituvchini o‘chirib bo‘lmaydi", "users")
    u.delete()
    messages.success(request, "Foydalanuvchi o‘chirildi")
    return redirect("users")


def _perm_ctx(u):
    """Ruxsatlar matritsasi (rolga mos bo'limlar va amallar)."""
    return {"pm_rows": PM.matrix(u.role, u.grants), "pm_custom": u.has_custom_grants, "pm_student": u.is_student,
            "pm_actions": [(a, PM.ACTION_LABELS[a], PM.ACTION_HINTS[a]) for a in (PM.CRUD if u.is_assistant else [PM.VIEW])]}


@main_required
@post_only
def user_perm(request, pk):
    """Asosiy o'qituvchi istalgan yordamchi yoki talabaga bo'lim × amal ruxsatlarini beradi (rolga mos)."""
    u = get_object_or_404(UserModel.objects.on_site().exclude(role=UserModel.MAIN), pk=pk)
    if request.POST.get("reset") == "1":
        u.reset_grants()
        msg = "Ruxsatlar rol standartiga qaytarildi"
        log_event("user_perm", request.user, user=u, note="standart")
    else:
        u.set_grants(PM.from_post(u.role, request.POST))
        msg = "Ruxsatlar saqlandi"
        log_event("user_perm", request.user, user=u, note=", ".join(f"{k}:{'/'.join(v)}" for k, v in u.grants.items())[:300])
    u.save(update_fields=["perms"])
    notify([u], "Sizning ruxsatlaringiz yangilandi", "/dashboard/")
    messages.success(request, msg)
    return redirect(reverse("user_detail", args=[pk]) + "?tab=perm")

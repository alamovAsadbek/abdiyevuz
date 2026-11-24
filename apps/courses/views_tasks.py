import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserModel
from apps.core.helpers import A, T, clean_html, jload, make_list, parse_local, to_int
from apps.core.models import log_event
from apps.core.perms import deny, login_required, perm_required, post_only, student_required
from apps.core.validators import check_upload
from apps.notifications.services import notify
from .models import (CourseAccessModel, CourseModel, LessonModel, LessonProgressModel, ModuleModel, PurchaseRequestModel,
                     SubmissionModel, TaskFileModel, TaskModel)
from .services import (can_access, enrolled, lock_reason, scoped_students, student_in_scope)


def _task_scope(request, lesson_qs=None):
    return TaskModel.objects.select_related("lesson__module__course__group")


def _need_task_perm(request, t):
    if not (request.user.is_teacher and request.user.can("tasks")):
        return deny(request)
    return None


# ---------------------------------------------------------------- task CRUD
def _save_task(request, lesson, task=None):
    P = request.POST
    title = P.get("title", "").strip()
    if not title:
        return None, "Vazifa nomini kiriting"
    t = task or TaskModel(lesson=lesson)
    t.title, t.description = title[:200], P.get("description", "")
    t.max_score = max(1, to_int(P.get("max_score"), 10))
    t.deadline = parse_local(P.get("deadline"))
    t.is_closed = bool(t.deadline and t.deadline <= timezone.now())
    t.save()
    try:
        for f in request.FILES.getlist("files"):
            check_upload(f)
        for f in request.FILES.getlist("files"):
            x = TaskFileModel(task=t, name=f.name)
            x.file.save(f.name, f, save=True)
    except ValidationError as e:
        return t, e.messages[0]
    return t, None


@perm_required("tasks")
def task_new(request, lid=None):
    lessons = LessonModel.objects.select_related("module__course").filter(module__course__group__isnull=True)
    lesson = get_object_or_404(LessonModel, pk=lid) if lid else None
    if request.method == "POST":
        l = lesson or get_object_or_404(LessonModel, pk=to_int(request.POST.get("lesson")))
        t, err = _save_task(request, l)
        if err:
            messages.error(request, err)
        else:
            messages.success(request, "Vazifa qo‘shildi")
            return redirect(reverse("lesson_detail", args=[l.pk]) + "?tab=task")
    opts = [(l.pk, f"{l.module.course.title} · {l.title}") for l in lessons] if not lesson else []
    return render(request, "staff/tasks/form.html", {"lesson": lesson, "lesson_options": opts})


@perm_required("tasks")
@post_only
def task_edit(request, pk):
    t = get_object_or_404(TaskModel, pk=pk)
    _, err = _save_task(request, t.lesson, t)
    messages.error(request, err) if err else messages.success(request, "Vazifa saqlandi")
    return redirect(reverse("task_detail", args=[pk]) + "?tab=set")


@perm_required("tasks")
@post_only
def task_toggle(request, pk):
    t = get_object_or_404(TaskModel, pk=pk)
    t.is_active = not t.is_active
    t.save(update_fields=["is_active"])
    messages.success(request, "Vazifa aktiv qilindi" if t.is_active else "Vazifa noaktiv qilindi")
    return redirect(reverse("task_detail", args=[pk]) + "?tab=set")


@perm_required("tasks")
@post_only
def task_delete(request, pk):
    t = get_object_or_404(TaskModel, pk=pk)
    lid = t.lesson_id
    t.delete()
    messages.success(request, "Vazifa o‘chirildi")
    return redirect(request.POST.get("next") or reverse("lesson_detail", args=[lid]) + "?tab=task")


def _status_tag(s):
    if not s:
        return T("Topshirilmagan", "x")
    return {"pending": T("Tekshirilmoqda"), "accepted": T("Qabul qilindi", "f"), "returned": T("Qayta topshiring", "x")}[s.status]


@login_required
def tasks(request):
    u = request.user
    rows = []
    if u.is_student:
        subs = {s.task_id: s for s in SubmissionModel.objects.filter(student=u)}
        for t in TaskModel.objects.filter(is_active=True).select_related("lesson__module__course__group"):
            if lock_reason(u, t.lesson) and t.pk not in subs:
                continue
            if not can_access(u, t.lesson.module.course, t.lesson.module):
                continue
            s = subs.get(t.pk)
            tt = _status_tag(s)
            if not s and not t.is_open:
                tt = T("Muddati o‘tgan", "x")
            rows.append({"title": t.title, "sub": t.lesson.title, "url": reverse("lesson_detail", args=[t.lesson_id]) + "?tab=task", "tags": [tt],
                         "cells": [t.title, f"{t.lesson.module.course.title} · {t.lesson.title}", f"{t.max_score} ball", t.deadline or "—", tt,
                                   f"{s.score} / {t.max_score}" if s and s.status == "accepted" else "—"], "f": {"st": tt["tag"]}})
        L = make_list(request, rows, ["Vazifa", "Kurs / dars", "Eng yuqori ball", "Muddat", "Holat", "Mening ballim"],
                      [("st", "Holat", ["Topshirilmagan", "Tekshirilmoqda", "Qabul qilindi", "Qayta topshiring", "Muddati o‘tgan"])], show_mode=False)
        return render(request, "student/tasks.html", {"L": L})
    if not u.can("tasks"):
        return deny(request)
    for t in TaskModel.objects.select_related("lesson__module__course").order_by("-id"):
        en = enrolled(t.lesson, u)
        if u.is_assistant and not en.exists():
            continue
        sb = t.submissions.filter(student__in=en)
        pend = sb.filter(status="pending").count()
        h = "Tekshirilmagan bor" if pend else "Hammasi tekshirilgan" if sb.exists() else "Hech kim topshirmagan"
        tt = T(h, "x" if pend else "f" if sb.exists() else "")
        st = T("Yopilgan", "x") if not t.is_open else T("Ochiq", "f")
        acts = [A("trash-2", "O‘chirish", post=reverse("task_delete", args=[t.pk]), confirm="Vazifa o‘chirilsinmi?", cls="x")] if True else []
        rows.append({"title": t.title, "sub": t.lesson.title, "url": reverse("task_detail", args=[t.pk]), "tags": [tt, st],
                     "cells": [t.title, f"{t.lesson.module.course.title} · {t.lesson.module.title}", t.lesson.title, f"{t.max_score} ball", t.deadline or "—", f"{sb.count()} / {max(en.count(), sb.count())}", tt],
                     "actions": acts, "f": {"crs": t.lesson.module.course.title, "hl": h}})
    L = make_list(request, rows, ["Vazifa", "Kurs / modul", "Dars", "Ball", "Muddat", "Topshirgan", "Holat"],
                  [("crs", "Kurs", [c.title for c in CourseModel.objects.all()]), ("hl", "Holat", ["Tekshirilmagan bor", "Hammasi tekshirilgan", "Hech kim topshirmagan"])],
                  [{"icon": "plus", "label": "Vazifa qo‘shish", "url": reverse("task_new_global")}])
    return render(request, "staff/tasks/list.html", {"L": L})


@perm_required("tasks")
def task_detail(request, pk):
    t = get_object_or_404(TaskModel.objects.select_related("lesson__module__course"), pk=pk)
    u = request.user
    en = list(enrolled(t.lesson, u))
    subs = {s.student_id: s for s in t.submissions.filter(student__in=en).select_related("student")}
    tab = request.GET.get("tab", "sub")
    sub = [{"u": x, "s": subs[x.pk]} for x in en if x.pk in subs]
    non = [x for x in en if x.pk not in subs]
    ctx = {"t": t, "tab": tab if tab in ("sub", "non", "info", "set") else "sub", "sub": sub, "non": non, "n": len(en),
           "pending": sum(1 for x in sub if x["s"].status == "pending"), "ok": sum(1 for x in sub if x["s"].status == "accepted"),
           "tabs": [("sub", "Topshirganlar"), ("non", "Topshirmaganlar"), ("info", "Ma‘lumot"), ("set", "Sozlamalar")]}
    return render(request, "staff/tasks/detail.html", ctx)


# ---------------------------------------------------------------- submissions
def _notify_reviewers(student, text, link):
    ids = {u.pk for u in UserModel.objects.filter(role="main")}
    ids |= {a.pk for g in student.member_groups.all() for a in g.assistants.all() if a.can("tasks")}
    notify(list(ids), text, link)


@student_required
@post_only
def submission_upload(request, tid):
    t = get_object_or_404(TaskModel.objects.select_related("lesson__module__course"), pk=tid, is_active=True)
    u = request.user
    back = redirect(reverse("lesson_detail", args=[t.lesson_id]) + "?tab=task")
    if lock_reason(u, t.lesson):
        return deny(request, "Bu darsga kirish huquqingiz yo‘q")
    if not t.is_open:
        messages.error(request, "Vazifa muddati tugagan — yuklash yopilgan")
        return back
    f = request.FILES.get("file")
    old = SubmissionModel.objects.filter(task=t, student=u).first()
    if old and old.status == "accepted":
        messages.error(request, "Qabul qilingan vazifani qayta yuklab bo‘lmaydi")
        return back
    try:
        if not f:
            raise ValidationError("Fayl tanlanmadi")
        check_upload(f)
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return back
    if old:
        old.file.delete(save=False)
        s = old
    else:
        s = SubmissionModel(task=t, student=u)
    s.filename, s.status, s.score, s.comment, s.graded_at, s.submitted_at = f.name[:200], "pending", None, "", None, timezone.now()
    s.file.save(f.name, f, save=False)
    s.save()
    LessonProgressModel.objects.get_or_create(user=u, lesson=t.lesson)
    _notify_reviewers(u, f"{u.full_name} “{t.title}” vazifasini yubordi", f"/staff/submissions/{s.pk}/")
    messages.success(request, "Vazifa yuborildi — o‘qituvchi tekshiradi")
    return back


@perm_required("tasks")
@post_only
def submission_upload_for(request, tid, uid):
    t = get_object_or_404(TaskModel, pk=tid)
    st = get_object_or_404(scoped_students(request.user), pk=uid)
    f = request.FILES.get("file")
    try:
        if not f:
            raise ValidationError("Fayl tanlanmadi")
        check_upload(f)
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect("task_detail", pk=tid)
    s = SubmissionModel.objects.filter(task=t, student=st).first() or SubmissionModel(task=t, student=st)
    if s.pk:
        s.file.delete(save=False)
    s.filename, s.status, s.score, s.submitted_at = f.name[:200], "pending", None, timezone.now()
    s.file.save(f.name, f, save=False)
    s.save()
    messages.success(request, f"Vazifa {st.full_name} nomidan yuklandi")
    return redirect("task_detail", pk=tid)


@perm_required("tasks")
@post_only
def task_remind(request, tid, uid):
    t = get_object_or_404(TaskModel, pk=tid)
    st = get_object_or_404(scoped_students(request.user), pk=uid)
    notify([st], f"Eslatma: “{t.title}” vazifasini topshiring", f"/lessons/{t.lesson_id}/?tab=task")
    messages.success(request, f"{st.full_name} ga eslatma yuborildi")
    return redirect(request.POST.get("next") or "tasks")


@perm_required("tasks")
def submission_review(request, pk):
    s = get_object_or_404(SubmissionModel.objects.select_related("task__lesson__module__course", "student"), pk=pk)
    if not student_in_scope(request.user, s.student):
        return deny(request)
    t = s.task
    if request.method == "POST":
        act, P = request.POST.get("act"), request.POST
        st = s.student
        if act == "reset":
            st.points = max(0, st.points - s.points_given)
            s.points_given, s.status, s.score, s.graded_at = 0, "pending", None, None
            st.save(update_fields=["points"])
            s.save()
            notify([st], f"“{t.title}” vazifasi bahosi bekor qilindi, qayta tekshiriladi", f"/lessons/{t.lesson_id}/?tab=task")
            messages.success(request, "Baholash bekor qilindi")
            return redirect("submission_review", pk=pk)
        comment = P.get("comment", "").strip()
        sc = to_int(P.get("score"), -1)
        if act == "accept" and not 0 <= sc <= t.max_score:
            messages.error(request, f"Ball 0 dan {t.max_score} gacha bo‘lishi kerak")
            return redirect("submission_review", pk=pk)
        if act == "return" and not comment:
            messages.error(request, "Qayta topshirish sababini izohda yozing")
            return redirect("submission_review", pk=pk)
        st.points = max(0, st.points - s.points_given)
        if act == "accept":
            s.status, s.score, s.points_given = "accepted", sc, sc
            st.points += sc
        else:
            s.status, s.score, s.points_given = "returned", None, 0
        s.comment, s.graded_at, s.reviewer = comment, timezone.now(), request.user
        s.save()
        st.save(update_fields=["points"])
        notify([st], f"“{t.title}” vazifangiz tekshirildi: {sc}/{t.max_score} ball" if act == "accept" else f"“{t.title}” vazifasi qayta topshirish uchun qaytarildi",
               f"/lessons/{t.lesson_id}/?tab=task")
        messages.success(request, "Natija e’lon qilindi" if act == "accept" else "Vazifa qaytarildi")
        return redirect("task_detail", pk=t.pk)
    return render(request, "staff/tasks/review.html", {"s": s, "t": t, "is_img": s.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))})


# ---------------------------------------------------------------- gifts / access
def _course_json(c):
    return {"id": c.pk, "title": c.title, "modular": c.is_modular, "price": c.min_price() if c.is_modular else c.price,
            "paid": c.is_paid, "lessons": c.lesson_count,
            "modules": [{"id": m.pk, "title": m.title, "price": m.price, "lessons": m.lessons.count(), "active": m.is_active} for m in c.modules.all()]}


@perm_required("gift")
def gift_data(request):
    """Kurs berish oynasi uchun JSON: kurslar (BARCHA modullari bilan) va talabalar."""
    out = {"courses": [_course_json(c) for c in CourseModel.objects.filter(group__isnull=True)]}
    uid, cid = to_int(request.GET.get("uid")), to_int(request.GET.get("course"))
    if uid:
        owned = set(CourseAccessModel.objects.filter(user_id=uid, module__isnull=True).values_list("course_id", flat=True))
        out["courses"] = [c for c in out["courses"] if c["id"] not in owned]
        mod_owned = {}
        for a in CourseAccessModel.objects.filter(user_id=uid, module__isnull=False):
            mod_owned.setdefault(a.course_id, []).append(a.module_id)
        for c in out["courses"]:
            for m in c["modules"]:
                m["owned"] = m["id"] in mod_owned.get(c["id"], [])
    if cid:
        whole = set(CourseAccessModel.objects.filter(course_id=cid, module__isnull=True).values_list("user_id", flat=True))
        out["students"] = [{"id": s.pk, "t": s.full_name, "s": s.uid + (" · " + s.phone if s.phone else ""), "off": s.pk in whole,
                            "tg": "Kursga ega" if s.pk in whole else ""} for s in scoped_students(request.user)]
    return JsonResponse(out)


@perm_required("gift")
@post_only
def gift_do(request):
    d = jload(request.body, {})
    c = get_object_or_404(CourseModel, pk=to_int(d.get("course")), group__isnull=True)
    users = list(scoped_students(request.user).filter(pk__in=[to_int(x) for x in d.get("uids", [])]))
    if not users:
        return JsonResponse({"ok": False, "error": "Talaba tanlanmadi"}, status=400)
    all_ids = list(c.modules.values_list("pk", flat=True))
    mods = d.get("modules", "all")
    chosen = all_ids if mods == "all" or not c.is_modular else [m for m in (to_int(x) for x in mods) if m in all_ids]
    if c.is_modular and not chosen:
        return JsonResponse({"ok": False, "error": "Kamida bitta modul tanlang"}, status=400)
    whole = (not c.is_modular) or set(chosen) >= set(all_ids)
    names = ["Barcha modullar"] if whole else [m.title for m in c.modules.filter(pk__in=chosen)]
    for u in users:
        if whole:
            CourseAccessModel.objects.get_or_create(user=u, course=c, module=None, defaults={"granted_by": request.user})
        else:
            for m in chosen:
                CourseAccessModel.objects.get_or_create(user=u, course=c, module_id=m, defaults={"granted_by": request.user})
        log_event("give", request.user, user=u, course=c, mods=", ".join(names)[:300])
        notify([u], f"Sizga ochib berildi: {c.title}" + ("" if whole else " — " + ", ".join(names)), f"/courses/{c.pk}/")
    return JsonResponse({"ok": True, "n": len(users)})


@perm_required("gift")
@post_only
def revoke(request):
    P = request.POST
    c = get_object_or_404(CourseModel, pk=to_int(P.get("course")))
    u = get_object_or_404(scoped_students(request.user), pk=to_int(P.get("uid")))
    qs = CourseAccessModel.objects.filter(user=u, course=c)
    if P.get("module"):
        qs = qs.filter(module_id=to_int(P["module"]))
    n = qs.count()
    mods = [a.module.title if a.module else "Barcha modullar" for a in qs.select_related("module")]
    qs.delete()
    if n:
        log_event("revoke", request.user, user=u, course=c, mods=", ".join(mods)[:300])
        notify([u], "Kursga kirish huquqi olib tashlandi: " + c.title)
    messages.success(request, "Kirish huquqi olib tashlandi")
    return redirect(request.POST.get("next") or reverse("user_detail", args=[u.pk]) + "?tab=kurs")


@student_required
@post_only
def buy_request(request):
    """To'lov tizimi ulanmaguncha: talaba so'rov yuboradi, o'qituvchi kursni ochib beradi."""
    P, u = request.POST, request.user
    c = get_object_or_404(CourseModel, pk=to_int(P.get("course")), group__isnull=True, is_active=True)
    m = ModuleModel.objects.filter(pk=to_int(P.get("module")), course=c).first() if P.get("module") else None
    if PurchaseRequestModel.objects.filter(user=u, course=c, module=m, done=False).exists():
        messages.info(request, "So‘rovingiz allaqachon yuborilgan")
    else:
        PurchaseRequestModel.objects.create(user=u, course=c, module=m)
        log_event("buy", u, user=u, course=c, mods=m.title if m else "Barcha modullar")
        from apps.notifications.services import notify_staff
        notify_staff("gift", f"{u.full_name} “{c.title}{' · ' + m.title if m else ''}” ni sotib olmoqchi", f"/staff/users/{u.pk}/?tab=kurs&gift=1")
        messages.success(request, "So‘rov yuborildi — o‘qituvchi siz bilan bog‘lanadi")
    return redirect(request.POST.get("next") or "courses")

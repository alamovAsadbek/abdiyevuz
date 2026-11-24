import json
from datetime import timedelta

from django.contrib import messages
from django.db.models import Avg, Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core import charts
from apps.core.helpers import A, T, jload, make_list, to_int
from apps.core.models import EventModel, log_event
from apps.core.perms import deny, login_required, main_required, perm_required, post_only
from apps.courses.models import (CourseAccessModel, LessonModel, LessonProgressModel, SubmissionModel, TaskModel)
from apps.courses.services import (completed_count, enrolled, lock_reason, my_groups, scoped_students, student_in_scope)
from apps.exams.models import AttemptModel, TestModel
from apps.notifications.services import notify
from .models import GroupModel, UserModel


def _grp(request, pk):
    u = request.user
    qs = GroupModel.objects.all()
    if u.is_student:
        qs = qs.filter(is_active=True, members=u)
    elif u.is_assistant:
        qs = qs.filter(assistants=u)
    return get_object_or_404(qs, pk=pk)


@login_required
def groups(request):
    u = request.user
    qs = GroupModel.objects.all() if u.is_main else u.assist_groups.all() if u.is_assistant else u.member_groups.filter(is_active=True)
    can = u.is_teacher and u.can("groups")
    rows = []
    for g in qs.annotate(mc=Count("members", distinct=True)):
        st = T("Aktiv", "f") if g.is_active else T("Noaktiv", "x")
        acts = []
        if can:
            acts = [A("edit-2", "Tahrirlash", url=reverse("group_detail", args=[g.pk]) + "?tab=set"),
                    A("pause" if g.is_active else "play", "Aktiv/Noaktiv", post=reverse("group_toggle", args=[g.pk]), confirm="Guruh holati o‘zgartirilsinmi?"),
                    A("trash-2", "O‘chirish", post=reverse("group_delete", args=[g.pk]), confirm=f"“{g.name}” guruhi o‘chirilsinmi?", cls="x")]
        nv = g.course.modules.first().lessons.count() if hasattr(g, "course") and g.course.modules.exists() else 0
        rows.append({"title": g.name, "sub": g.kind_label, "url": reverse("group_detail", args=[g.pk]), "tags": [T(g.kind_label), st],
                     "cells": [g.name, T(g.kind_label, "" if g.kind == "online" else "f"), f"{g.mc} ta", f"{nv} ta", st], "actions": acts,
                     "f": {"ty": g.kind_label, "st": "Aktiv" if g.is_active else "Noaktiv"}})
    add = [{"icon": "plus", "label": "Yangi guruh", "url": reverse("group_new")}] if can else None
    return render(request, "shared/groups/list.html", {"L": make_list(request, rows, ["Guruh nomi", "Turi", "Talabalar", "Videolar", "Status"],
                                                                    [("ty", "Turi", ["Onlayn", "Oflayn"]), ("st", "Status", ["Aktiv", "Noaktiv"])], add)})


@perm_required("groups")
def group_new(request):
    if request.method == "POST":
        n = request.POST.get("name", "").strip()
        if not n:
            messages.error(request, "Guruh nomini kiriting")
        else:
            g = GroupModel.objects.create(name=n, kind="offline" if request.POST.get("kind") == "offline" else "online",
                                          description=request.POST.get("description", ""), is_active=bool(request.POST.get("is_active")))
            if request.user.is_assistant:
                g.assistants.add(request.user)
            messages.success(request, "Guruh yaratildi")
            return redirect("groups")
    return render(request, "shared/groups/form.html", {"g": None, "kinds": [("online", "Onlayn"), ("offline", "Oflayn")]})


@login_required
def group_detail(request, pk):
    g = _grp(request, pk)
    u = request.user
    course = g.course
    module = course.first_module()
    lessons = list(module.lessons.prefetch_related("tasks"))
    ctx = {"g": g, "course": course, "module": module, "can": u.is_teacher and u.can("groups"),
           "kinds": [("online", "Onlayn"), ("offline", "Oflayn")]}
    if u.is_student:
        seen = set(LessonProgressModel.objects.filter(user=u, lesson__in=lessons).values_list("lesson_id", flat=True))
        subs = set(SubmissionModel.objects.filter(student=u, task__lesson__in=lessons).values_list("task_id", flat=True))
        ctx["lessons"] = [{"l": l, "lock": lock_reason(u, l), "seen": l.pk in seen,
                           "done": l.pk in seen and all(t.pk in subs or not t.blocks_next for t in l.tasks.all())} for l in lessons]
        return render(request, "student/group_detail.html", ctx)
    keys = ["vid", "mem", "set"] + (["tch"] if u.is_main else []) + ["stat"]
    names = {"vid": "Videodarslar", "mem": "Talabalar", "set": "Sozlamalar", "tch": "O‘qituvchilar", "stat": "Statistika"}
    tab = request.GET.get("tab") if request.GET.get("tab") in keys else "vid"
    ctx.update(tabs=[(k, names[k]) for k in keys], tab=tab)
    members = g.members.all()
    if tab == "vid":
        ctx["lessons"] = [{"l": l, "seen": LessonProgressModel.objects.filter(lesson=l, user__in=members).count()} for l in lessons]
    elif tab == "mem":
        ctx["members"] = members
        ctx["free"] = json.dumps([{"id": s.pk, "t": s.full_name, "s": s.uid + (" · " + s.phone if s.phone else ""),
                                   "off": g.members.filter(pk=s.pk).exists(),
                                   "tg": ", ".join(x.name for x in s.member_groups.exclude(pk=g.pk))}
                                  for s in scoped_students(u)], ensure_ascii=False)
    elif tab == "tch":
        ctx["assistants"] = g.assistants.all()
        ctx["all_ass"] = json.dumps([{"id": a.pk, "t": a.full_name, "s": a.uid, "off": g.assistants.filter(pk=a.pk).exists()}
                                     for a in UserModel.objects.filter(role="assistant")], ensure_ascii=False)
    elif tab == "stat":
        ms = list(members)
        rows = []
        for i, l in enumerate(lessons):
            seen = LessonProgressModel.objects.filter(lesson=l, user__in=ms).values("user").distinct().count()
            tks = list(l.tasks.all())
            sub = sum(1 for s in ms if tks and all(t.submissions.filter(student=s).exists() for t in tks))
            rows.append({"l": l, "seen": seen, "sub": sub, "has_tasks": bool(tks)})
        ctx["lrows"] = rows
        ctx["n"] = len(ms)
        ctx["srows"] = [{"u": s, "seen": LessonProgressModel.objects.filter(user=s, lesson__in=lessons).count(),
                         "sub": SubmissionModel.objects.filter(student=s, task__lesson__in=lessons).count(),
                         "pts": sum(x.points_given for x in SubmissionModel.objects.filter(student=s, task__lesson__in=lessons))} for s in ms]
        ctx["nl"] = len(lessons)
    return render(request, "shared/groups/detail.html", ctx)


@perm_required("groups")
@post_only
def group_edit(request, pk):
    g = _grp(request, pk)
    n = request.POST.get("name", "").strip()
    if not n:
        messages.error(request, "Guruh nomini kiriting")
    else:
        g.name, g.description = n, request.POST.get("description", "")
        g.kind = "offline" if request.POST.get("kind") == "offline" else "online"
        g.is_active = bool(request.POST.get("is_active"))
        g.save()
        messages.success(request, "Guruh saqlandi")
    return redirect(reverse("group_detail", args=[pk]) + "?tab=set")


@perm_required("groups")
@post_only
def group_toggle(request, pk):
    g = _grp(request, pk)
    g.is_active = not g.is_active
    g.save(update_fields=["is_active"])
    messages.success(request, "Guruh aktiv qilindi" if g.is_active else "Guruh noaktiv qilindi")
    return redirect(request.POST.get("next") or "groups")


@perm_required("groups")
@post_only
def group_delete(request, pk):
    _grp(request, pk).delete()
    messages.success(request, "Guruh o‘chirildi")
    return redirect("groups")


@perm_required("groups")
@post_only
def group_members(request, pk):
    """JSON: {"add": [ids]} yoki {"remove": id} — guruhga talaba qo'shish/chiqarish."""
    g = _grp(request, pk)
    d = jload(request.body, None) or {"remove": request.POST.get("remove")}
    ajax = request.headers.get("X-Requested-With") == "fetch"
    st = scoped_students(request.user)
    for i in d.get("add", []):
        s = st.filter(pk=to_int(i)).first()
        if s and not g.members.filter(pk=s.pk).exists():
            g.members.add(s)
            log_event("group_add", request.user, user=s, group=g, note=g.name)
            notify([s], f"Siz “{g.name}” guruhiga qo‘shildingiz", f"/groups/{g.pk}/")
    if d.get("remove"):
        s = st.filter(pk=to_int(d["remove"])).first()
        if s:
            g.members.remove(s)
            log_event("group_remove", request.user, user=s, group=g, note=g.name)
    if not ajax:
        return redirect(reverse("group_detail", args=[pk]) + "?tab=mem")
    return JsonResponse({"ok": True})


@perm_required("groups")
@post_only
def user_groups(request, pk):
    """Foydalanuvchi sahifasidan: guruhga qo'shish/chiqarish."""
    from .views import _get_user
    s = _get_user(request, pk)
    d = jload(request.body, None) or {"remove": request.POST.get("remove")}
    ajax = request.headers.get("X-Requested-With") == "fetch"
    for i in d.get("add", []):
        g = my_groups(request.user).filter(pk=to_int(i)).first()
        if g and s.is_student and not g.members.filter(pk=s.pk).exists():
            g.members.add(s)
            log_event("group_add", request.user, user=s, group=g, note=g.name)
    if d.get("remove"):
        g = my_groups(request.user).filter(pk=to_int(d["remove"])).first()
        if g:
            g.members.remove(s)
            log_event("group_remove", request.user, user=s, group=g, note=g.name)
    if not ajax:
        return redirect(reverse("user_detail", args=[pk]) + "?tab=guruh")
    return JsonResponse({"ok": True})


@main_required
@post_only
def group_assistants(request, pk):
    g = get_object_or_404(GroupModel, pk=pk)
    d = jload(request.body, {})
    for i in d.get("add", []):
        a = UserModel.objects.filter(pk=to_int(i), role="assistant").first()
        if a:
            g.assistants.add(a)
    if d.get("remove"):
        g.assistants.remove(to_int(d["remove"]))
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- dashboards
def _day_counts(qs, field, days=7):
    now = timezone.localtime()
    out = []
    for i in range(days - 1, -1, -1):
        d0 = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        out.append(qs.filter(**{field + "__gte": d0, field + "__lt": d0 + timedelta(days=1)}).count())
    return out


def _test_tiles(attempts):
    best = {}
    for a in attempts:
        best.setdefault(a.test.title, []).append(a.percent)
    return [(t[:2].title(), t[:14], i + 1, round(sum(v) / len(v))) for i, (t, v) in enumerate(list(best.items())[:8])]


@login_required
def dashboard(request):
    u = request.user
    if u.is_student:
        return _dash_student(request)
    return _dash_staff(request)


def _meet_ctx(u):
    from apps.meetings.access import visible_meetings
    qs = list(visible_meetings(u).select_related("host"))
    return {"meet_live": [m for m in qs if m.status == "live"], "meet_soon": [m for m in qs if m.status == "scheduled"][:4]}


def _dash_student(request):
    from apps.courses.models import CourseModel
    u = request.user
    prog = LessonProgressModel.objects.filter(user=u).select_related("lesson__module__course").order_by("-last_seen")
    last = prog.first()
    att = list(AttemptModel.objects.filter(user=u).select_related("test").order_by("-created"))
    avg = round(sum(a.percent for a in att) / len(att)) if att else 0
    course_ids = set(CourseAccessModel.objects.filter(user=u).values_list("course_id", flat=True))
    ctx = {"cont": None, "avg": avg, "ph": charts.phbar(avg), "tiles": charts.tiles(_test_tiles(att)),
           "bars": [a.percent for a in att[:5]][::-1], "n_courses": len(course_ids), "n_done": prog.count(), "n_att": len(att)}
    if last:
        c = last.lesson.module.course
        done, tot = completed_count(u, c)
        ctx["cont"] = {"p": last, "pct": round(done / tot * 100) if tot else 0, "course": c}
        ctx["beaker"] = charts.beaker(ctx["cont"]["pct"])
        ctx["beaker_pct"] = ctx["cont"]["pct"]
    else:
        ctx["beaker"], ctx["beaker_pct"] = charts.beaker(0), 0
    gl = []
    for g in u.member_groups.filter(is_active=True):
        for l in LessonModel.objects.filter(module__course__group=g).order_by("-created")[:4]:
            gl.append({"l": l, "g": g, "lock": lock_reason(u, l), "seen": LessonProgressModel.objects.filter(user=u, lesson=l).exists()})
    ctx["group_lessons"] = gl[:4]
    from apps.courses.views import student_open_tasks
    ctx["tasks"] = student_open_tasks(u)[:6] if u.can_view("tasks") else []
    if not u.can_view("groups"):
        ctx["group_lessons"] = []
    if u.can_view("meetings"):
        ctx.update(_meet_ctx(u))
    return render(request, "student/dashboard.html", ctx)


def _dash_staff(request):
    u = request.user
    st = scoped_students(u)
    sids = list(st.values_list("pk", flat=True))
    atts = AttemptModel.objects.filter(user_id__in=sids)
    subs = SubmissionModel.objects.filter(student_id__in=sids)
    pend = subs.filter(status="pending").select_related("student", "task__lesson").order_by("submitted_at")
    avg = atts.aggregate(a=Avg(F("score") * 100.0 / F("total")))["a"] or 0
    done = [completed_count(s, c)[0] / max(1, completed_count(s, c)[1]) for s in st[:30] for c in
            [x.course for x in CourseAccessModel.objects.filter(user=s).select_related("course")[:1]]]
    comp = round(sum(done) / len(done) * 100) if done else 0
    top = st.order_by("-points")[:3]
    from apps.courses.models import CourseModel
    ctx = {"n_students": st.count(), "n_courses": CourseModel.objects.filter(group__isnull=True).count(), "n_tests": TestModel.objects.count(),
           "n_access": CourseAccessModel.objects.filter(user_id__in=sids).count(), "n_pending": pend.count(), "pending": pend[:6],
           "line": charts.line(_day_counts(atts, "created"), _day_counts(subs, "submitted_at")), "beaker": charts.beaker(comp), "comp": comp,
           "donut": charts.donut([("Faol", st.filter(is_blocked=False, last_seen__isnull=False).count(), "#6b5bd2"),
                                  ("Yangi", st.filter(is_blocked=False, last_seen__isnull=True).count(), "#ff9db5"),
                                  ("Bloklangan", st.filter(is_blocked=True).count(), "#f4d44d")]),
           "ph": charts.phbar(round(avg)), "avg": round(avg), "tiles": charts.tiles(_test_tiles(atts.select_related("test")[:200])), "top": top,
           "groups": [(g, g.members.count()) for g in my_groups(u)[:4]],
           "events": EventModel.objects.filter(Q(user_id__in=sids) | Q(actor=u)).select_related("user", "course")[:5],
           "last_attempts": atts.select_related("user", "test")[:5]}
    if u.can_view("meetings"):
        ctx.update(_meet_ctx(u))
    return render(request, "staff/dashboard.html", ctx)


# ---------------------------------------------------------------- statistics
PERIOD = {"Bugun": 1, "7 kun": 7, "30 kun": 30}


@login_required
def stats(request):
    """Statistika rolga qarab: talaba — faqat o‘zi; yordamchi — o‘z guruhlari talabalari; asosiy o‘qituvchi — butun sayt."""
    if request.user.is_student:
        return _stats_student(request)
    return _stats_staff(request)


def _period(g):
    per = g.get("f_per", "")
    return timezone.now() - timedelta(days=PERIOD[per]) if per in PERIOD else None


def _stats_student(request):
    u, g = request.user, request.GET
    since = _period(g)
    tabs = [("sum", "Umumiy"), ("tests", "Test natijalarim"), ("tasks", "Vazifalarim"), ("courses", "Kurslarim")]
    tab = g.get("tab") if g.get("tab") in dict(tabs) else "sum"
    atts = AttemptModel.objects.filter(user=u).select_related("test")
    subs = SubmissionModel.objects.filter(student=u).select_related("task__lesson__module__course")
    if g.get("f_crs"):
        subs = subs.filter(task__lesson__module__course__title=g["f_crs"])
    if since:
        atts, subs = atts.filter(created__gte=since), subs.filter(submitted_at__gte=since)
    my_courses = [a.course for a in CourseAccessModel.objects.filter(user=u).select_related("course") if not a.course.is_hidden]
    my_courses = list({c.pk: c for c in my_courses}.values())
    filters = [("crs", "Kurs", [c.title for c in my_courses]), ("per", "Davr", list(PERIOD))]
    ctx = {"tab": tab, "tabs": tabs, "student": True}
    at = list(atts)
    avg = round(sum(a.percent for a in at) / len(at)) if at else 0
    if tab == "sum":
        ps = {k: subs.filter(status=k).count() for k in ("accepted", "pending", "returned")}
        best = max([a.percent for a in at] or [0])
        week = _day_counts(LessonProgressModel.objects.filter(user=u), "last_seen")
        mx = max(week or [1]) or 1
        ctx.update(points=u.points, n_att=len(at), avg=avg, best=best, n_sub=subs.count(), n_ok=ps["accepted"], n_pending=ps["pending"],
                   n_returned=ps["returned"], n_views=LessonProgressModel.objects.filter(user=u).count(), n_courses=len(my_courses),
                   donut=charts.donut([("Qabul qilindi", ps["accepted"], "#2fb67c"), ("Tekshirilmoqda", ps["pending"], "#6b5bd2"),
                                       ("Qayta topshiring", ps["returned"], "#f4d44d")]),
                   line=charts.line([a.percent for a in sorted(at, key=lambda x: x.created)][-10:], [70] * min(10, len(at))),
                   tiles=charts.tiles(_test_tiles(at[:300])), ph=charts.phbar(avg),
                   week_bars=[{"v": v, "h": round(v / mx * 100)} for v in week])
        return render(request, "shared/stats.html", ctx)
    if tab == "tests":
        rows = []
        for a in at:
            tt = T(f"{a.percent}%", "f" if a.percent >= 70 else "x")
            rows.append({"title": a.test.title, "sub": timezone.localtime(a.created).strftime("%d.%m.%Y %H:%M"), "url": reverse("attempt_detail", args=[a.pk]), "tags": [tt],
                         "cells": [a.test.title, a.created, f"{a.score} / {a.total}", tt, a.score * 10],
                         "f": {"res": "O‘tdi (70% va yuqori)" if a.percent >= 70 else "O‘tmadi", "per": g.get("f_per", "")}})
        ctx["L"] = make_list(request, rows, ["Test", "Sana", "To‘g‘ri javoblar", "Natija", "Ball"],
                             [("res", "Natija", ["O‘tdi (70% va yuqori)", "O‘tmadi"]), ("per", "Davr", list(PERIOD))])
    elif tab == "tasks":
        rows = []
        for sb in subs.order_by("-submitted_at"):
            lab = dict(SubmissionModel.STATUS)[sb.status]
            tt = T(lab, "f" if sb.status == "accepted" else "" if sb.status == "pending" else "x")
            rows.append({"title": sb.task.title, "sub": sb.task.lesson.title, "url": reverse("lesson_detail", args=[sb.task.lesson_id]) + "?tab=task", "tags": [tt],
                         "cells": [sb.task.title, sb.task.lesson.title, sb.submitted_at, sb.graded_at or "—", f"{sb.score}/{sb.task.max_score}" if sb.score is not None else "—", tt],
                         "f": {"st": lab, "crs": g.get("f_crs", ""), "per": g.get("f_per", "")}})
        ctx["L"] = make_list(request, rows, ["Vazifa", "Dars", "Topshirgan sana", "Baholangan sana", "Ball", "Holat"],
                             filters + [("st", "Holat", [x[1] for x in SubmissionModel.STATUS])])
    else:
        rows = []
        for c in my_courses:
            done, tot = completed_count(u, c)
            pct = round(done / tot * 100) if tot else 0
            rows.append({"title": c.title, "sub": f"{done} / {tot} dars", "url": reverse("course_detail", args=[c.pk]), "tags": [T(f"{pct}%", "f" if pct == 100 else "")],
                         "cells": [c.title, f"{done} / {tot}", T(f"{pct}%", "f" if pct == 100 else ""),
                                   SubmissionModel.objects.filter(student=u, task__lesson__module__course=c).count()], "f": {}})
        ctx["L"] = make_list(request, rows, ["Kurs", "Ko‘rilgan darslar", "Jarayon", "Topshirgan vazifalar"], [])
    return render(request, "shared/stats.html", ctx)


def _stats_staff(request):
    from apps.courses.models import CourseModel
    from apps.security.models import SecurityIncidentModel
    u, g = request.user, request.GET
    since = _period(g)
    main = u.is_main
    tabs = [("sum", "Umumiy"), ("users", "Foydalanuvchilar" if main else "Talabalarim"), ("tests", "Test natijalari"), ("tasks", "Vazifalar")]
    tab = g.get("tab") if g.get("tab") in dict(tabs) else "sum"
    users = list(UserModel.objects.all()) if main else list(scoped_students(u))
    if g.get("f_role"):
        users = [x for x in users if x.get_role_display() == g["f_role"]]
    if g.get("f_grp"):
        users = [x for x in users if x.member_groups.filter(name=g["f_grp"]).exists()]
    if g.get("f_crs"):
        users = [x for x in users if CourseAccessModel.objects.filter(user=x, course__title=g["f_crs"]).exists()]
    ids = [x.pk for x in users]
    stu = [x for x in users if x.is_student]
    atts = AttemptModel.objects.filter(user_id__in=ids).select_related("test", "user")
    subs = SubmissionModel.objects.filter(student_id__in=ids).select_related("task__lesson", "student")
    if since:
        atts, subs = atts.filter(created__gte=since), subs.filter(submitted_at__gte=since)
    filters = ([("role", "Rol", [r[1] for r in UserModel.ROLES])] if main else []) + [("grp", "Guruh", [x.name for x in my_groups(u)])]
    filters += [("crs", "Kurs", [c.title for c in CourseModel.objects.filter(group__isnull=True)]), ("per", "Davr", list(PERIOD))]
    ctx = {"tab": tab, "tabs": tabs, "main": main, "student": False}
    fv = {k: g.get("f_" + k, "") for k in ("role", "grp", "crs", "per")}
    if tab == "sum":
        at = list(atts)
        avg = round(sum(a.percent for a in at) / len(at)) if at else 0
        ps = {k: subs.filter(status=k).count() for k in ("accepted", "pending", "returned")}
        day0 = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        ctx.update(n_students=len(stu), points=sum(x.points for x in stu), n_att=len(at), avg=avg, n_sub=subs.count(),
                   n_pending=ps["pending"], n_returned=ps["returned"],
                   views=sum(LessonProgressModel.objects.filter(user_id__in=[x.pk for x in stu]).values_list("views", flat=True)),
                   active_today=sum(1 for x in stu if x.last_seen and x.last_seen >= day0), n_groups=my_groups(u).count(),
                   donut=charts.donut([("Qabul qilindi", ps["accepted"], "#2fb67c"), ("Tekshirilmoqda", ps["pending"], "#6b5bd2"),
                                       ("Qayta topshiring", ps["returned"], "#f4d44d")]),
                   line=charts.line(_day_counts(atts, "created", 14), _day_counts(subs, "submitted_at", 14)),
                   tiles=charts.tiles(_test_tiles(at[:300])), top=sorted(stu, key=lambda x: -x.points)[:5])
        if main:
            allu = UserModel.objects.all()
            nu = _day_counts(allu, "date_joined", 14)
            mx = max(nu or [1]) or 1
            ctx.update(n_users=allu.count(), n_assist=allu.filter(role="assistant").count(),
                       n_blocked=allu.filter(is_blocked=True).count(), n_courses=CourseModel.objects.filter(group__isnull=True).count(),
                       n_tests=TestModel.objects.count(), n_lessons=LessonModel.objects.count(),
                       n_online=sum(1 for x in allu.filter(last_seen__isnull=False) if x.online),
                       n_inc=SecurityIncidentModel.objects.filter(last_at__gte=timezone.now() - timedelta(days=7)).count(),
                       nu_bars=[{"v": v, "h": round(v / mx * 100)} for v in nu],
                       role_donut=charts.donut([("Talabalar", allu.filter(role="student").count(), "#6b5bd2"),
                                                ("Yordamchilar", allu.filter(role="assistant").count(), "#ff9db5"),
                                                ("Asosiy", allu.filter(role="main").count(), "#f4d44d")]))
        return render(request, "shared/stats.html", ctx)
    if tab == "users":
        rows = []
        for x in users:
            at = [a for a in atts if a.user_id == x.pk]
            sd = x.is_student
            link = reverse("user_detail", args=[x.pk]) if (u.can_view("users") and (main or sd) and x.pk != u.pk) else ""
            rows.append({"title": x.full_name, "sub": x.get_role_display(), "avatar": True, "url": link, "tags": [T(x.get_role_display())],
                         "cells": [x.full_name, x.get_role_display(), ", ".join(gg.name for gg in x.member_groups.all()) or "—", x.points if sd else "—",
                                   f"{round(sum(a.percent for a in at)/len(at))}%" if at else "—", len(at) if sd else "—",
                                   SubmissionModel.objects.filter(student=x).count() if sd else "—",
                                   SubmissionModel.objects.filter(reviewer=x).count() if not sd else "—",
                                   x.logins.filter(ok=True).count(), x.last_seen.strftime("%d.%m %H:%M") if x.last_seen else "—"], "f": dict(fv)})
        L = make_list(request, rows, ["Foydalanuvchi", "Rol", "Guruh", "Ball", "Test o‘rtachasi", "Test urinishlari", "Topshirgan vazifa", "Tekshirgan vazifa", "Kirishlar", "Oxirgi faollik"], filters)
    elif tab == "tests":
        rows = []
        for a in atts.order_by("-created"):
            tt = T(f"{a.percent}%", "f" if a.percent >= 70 else "x")
            rows.append({"title": f"{a.user.full_name} {a.test.title}", "sub": a.test.title, "url": reverse("attempt_detail", args=[a.pk]), "tags": [tt],
                         "cells": [a.user.full_name, a.test.title, a.created, f"{a.score} / {a.total}", tt, a.score * 10],
                         "f": dict(fv, tst=a.test.title, res="O‘tdi (70% va yuqori)" if a.percent >= 70 else "O‘tmadi")})
        L = make_list(request, rows, ["Foydalanuvchi", "Test", "Sana", "To‘g‘ri javoblar", "Natija", "Ball"],
                      filters + [("tst", "Test", [t.title for t in TestModel.objects.all()]), ("res", "Natija", ["O‘tdi (70% va yuqori)", "O‘tmadi"])])
    else:
        rows = []
        for sb in subs.order_by("-submitted_at"):
            lab = dict(SubmissionModel.STATUS)[sb.status]
            tt = T(lab, "f" if sb.status == "accepted" else "" if sb.status == "pending" else "x")
            rows.append({"title": f"{sb.student.full_name} {sb.task.title}", "sub": sb.task.title, "url": reverse("submission_review", args=[sb.pk]), "tags": [tt],
                         "cells": [sb.student.full_name, sb.task.title, sb.task.lesson.title, sb.task.deadline or "—", sb.submitted_at,
                                   sb.graded_at or "—", f"{sb.score}/{sb.task.max_score}" if sb.score is not None else "—", tt], "f": dict(fv, st=lab)})
        L = make_list(request, rows, ["Foydalanuvchi", "Vazifa", "Dars", "Muddat", "Topshirgan sana", "Baholangan sana", "Ball", "Holat"],
                      filters + [("st", "Holat", [x[1] for x in SubmissionModel.STATUS])])
    ctx["L"] = L
    return render(request, "shared/stats.html", ctx)

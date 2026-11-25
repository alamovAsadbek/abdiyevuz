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
    P = u.acts("groups") if u.is_teacher else {}
    rows = []
    for g in qs.annotate(mc=Count("members", filter=Q(members__show_on_site=True), distinct=True)):
        st = T("Aktiv", "f") if g.is_active else T("Noaktiv", "x")
        acts = []
        if P.get("edit"):
            acts += [A("edit-2", "Tahrirlash", url=reverse("group_detail", args=[g.pk]) + "?tab=set"),
                     A("pause" if g.is_active else "play", "Aktiv/Noaktiv", post=reverse("group_toggle", args=[g.pk]), confirm="Guruh holati o‘zgartirilsinmi?")]
        if P.get("delete"):
            acts.append(A("trash-2", "O‘chirish", post=reverse("group_delete", args=[g.pk]), confirm=f"“{g.name}” guruhi o‘chirilsinmi?", cls="x"))
        nv = g.course.modules.first().lessons.count() if hasattr(g, "course") and g.course.modules.exists() else 0
        rows.append({"title": g.name, "sub": g.kind_label, "url": reverse("group_detail", args=[g.pk]), "tags": [T(g.kind_label), st],
                     "cells": [g.name, T(g.kind_label, "" if g.kind == "online" else "f"), f"{g.mc} ta", f"{nv} ta", st], "actions": acts,
                     "f": {"ty": g.kind_label, "st": "Aktiv" if g.is_active else "Noaktiv"}})
    add = [{"icon": "plus", "label": "Yangi guruh", "url": reverse("group_new")}] if P.get("add") else None
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
           "perm": u.acts("groups") if u.is_teacher else {},
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
    members = g.members.filter(show_on_site=True)
    if tab == "vid":
        ctx["lessons"] = [{"l": l, "seen": LessonProgressModel.objects.filter(lesson=l, user__in=members).count()} for l in lessons]
    elif tab == "mem":
        ctx["members"] = members
        ctx["free"] = json.dumps([{"id": s.pk, "t": s.full_name, "s": s.uid + (" · " + s.phone if s.phone else ""),
                                   "off": g.members.filter(pk=s.pk).exists(),
                                   "tg": ", ".join(x.name for x in s.member_groups.exclude(pk=g.pk))}
                                  for s in scoped_students(u)], ensure_ascii=False)
    elif tab == "tch":
        ctx["assistants"] = g.assistants.filter(show_on_site=True)
        ctx["all_ass"] = json.dumps([{"id": a.pk, "t": a.full_name, "s": a.uid, "off": g.assistants.filter(pk=a.pk).exists()}
                                     for a in UserModel.objects.on_site().filter(role="assistant")], ensure_ascii=False)
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
        a = UserModel.objects.on_site().filter(pk=to_int(i), role="assistant").first()
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
    ctx["group_lessons"] = gl[:4] if u.can_view("groups") else []
    from apps.courses.views import student_open_tasks
    ctx["see_tasks"] = u.can_view("tasks")
    ctx["tasks"] = student_open_tasks(u)[:6] if ctx["see_tasks"] else []
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
           "groups": [(g, g.members.filter(show_on_site=True).count()) for g in my_groups(u)[:4]],
           "events": EventModel.objects.filter(Q(user_id__in=sids) | Q(actor=u)).select_related("user", "course")[:5],
           "last_attempts": atts.select_related("user", "test")[:5]}
    ctx.update(_meet_ctx(u))
    return render(request, "staff/dashboard.html", ctx)


# ---------------------------------------------------------------- statistics
PERIOD = {"Bugun": 1, "7 kun": 7, "30 kun": 30}


def _bars(vals):
    mx = max(vals) if vals and max(vals) else 1
    return [{"v": v, "h": max(4, round(v / mx * 100)) if v else 4} for v in vals]


def _stat_scope(u):
    """Statistika qamrovi: talaba — faqat o'zi; yordamchi — o'z guruhlaridagi talabalar; asosiy — saytdagi hamma."""
    if u.is_student:
        return UserModel.objects.filter(pk=u.pk)
    if u.is_assistant:
        return scoped_students(u)
    return UserModel.objects.on_site()


@login_required
def stats(request):
    from apps.courses.models import CourseModel
    u = request.user
    g = request.GET
    tab_keys = ["sum", "tst", "tsk"] if u.is_student else ["sum", "usr", "tst", "tsk"]
    tab_names = ({"sum": "Umumiy", "tst": "Test natijalarim", "tsk": "Vazifalarim"} if u.is_student else
                 {"sum": "Umumiy", "usr": "Foydalanuvchilar" if u.is_main else "Talabalarim", "tst": "Test natijalari", "tsk": "Vazifalar"})
    tab = g.get("tab") if g.get("tab") in tab_keys else "sum"
    per = g.get("f_per", "")
    since = timezone.now() - timedelta(days=PERIOD[per]) if per in PERIOD else None

    scope = _stat_scope(u)
    if u.is_teacher:
        if g.get("f_role"):
            scope = scope.filter(role={"Talaba": "student", "Yordamchi o‘qituvchi": "assistant", "Asosiy o‘qituvchi": "main"}.get(g["f_role"], "-"))
        if g.get("f_grp"):
            scope = scope.filter(member_groups__name=g["f_grp"], member_groups__in=my_groups(u))
    if g.get("f_crs"):
        scope = scope.filter(accesses__course__title=g["f_crs"]) if u.is_teacher else scope
    scope = scope.distinct()
    users = list(scope.prefetch_related("member_groups"))
    ids = [x.pk for x in users]
    stu_ids = [x.pk for x in users if x.is_student]
    atts = AttemptModel.objects.filter(user_id__in=stu_ids).select_related("test", "user")
    subs = SubmissionModel.objects.filter(student_id__in=stu_ids).select_related("task__lesson", "student")
    if u.is_student and g.get("f_crs"):
        subs = subs.filter(task__lesson__module__course__title=g["f_crs"])
    if since:
        atts, subs = atts.filter(created__gte=since), subs.filter(submitted_at__gte=since)

    if u.is_student:
        filters = [("crs", "Kurs", [c.title for c in CourseModel.objects.filter(group__isnull=True, accesses__user=u).distinct()]),
                   ("per", "Davr", ["Bugun", "7 kun", "30 kun"])]
    else:
        filters = ([("role", "Rol", ["Talaba", "Yordamchi o‘qituvchi", "Asosiy o‘qituvchi"])] if u.is_main else [])
        filters += [("grp", "Guruh", [x.name for x in my_groups(u)]),
                    ("crs", "Kurs", [c.title for c in CourseModel.objects.filter(group__isnull=True)]), ("per", "Davr", ["Bugun", "7 kun", "30 kun"])]
    ctx = {"tab": tab, "tabs": [(k, tab_names[k]) for k in tab_keys], "student": u.is_student, "main": u.is_main, "filters_raw": filters}

    per_status = {k: subs.filter(status=k).count() for k in ("accepted", "pending", "returned")}
    pcts = [a.percent for a in atts]
    avg = round(sum(pcts) / len(pcts)) if pcts else 0
    donut = charts.donut([("Qabul qilindi", per_status["accepted"], "#2fb67c"), ("Tekshirilmoqda", per_status["pending"], "#6b5bd2"),
                          ("Qayta topshiring", per_status["returned"], "#f4d44d")])

    if tab == "sum" and u.is_student:
        prog = LessonProgressModel.objects.filter(user=u)
        if since:
            prog = prog.filter(last_seen__gte=since)
        own = list(atts.order_by("created"))
        ctx.update(points=u.points, n_att=len(own), avg=avg, best=max(pcts) if pcts else 0, n_sub=subs.count(),
                   n_ok=per_status["accepted"], n_pending=per_status["pending"], n_returned=per_status["returned"],
                   n_views=prog.count(), donut=donut, ph=charts.phbar(avg),
                   line=charts.line([a.percent for a in own[-12:]], [70] * min(12, len(own))),
                   week_bars=_bars(_day_counts(LessonProgressModel.objects.filter(user=u), "last_seen", 7)),
                   tiles=charts.tiles(_test_tiles(own[-300:])))
        return render(request, "shared/stats.html", ctx)

    if tab == "sum":
        stu = [x for x in users if x.is_student]
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        ctx.update(n_students=len(stu), points=sum(x.points for x in stu), n_att=atts.count(), avg=avg, n_sub=subs.count(),
                   n_pending=per_status["pending"], n_returned=per_status["returned"],
                   active_today=sum(1 for x in stu if x.last_seen and x.last_seen >= today),
                   n_groups=my_groups(u).count(), donut=donut,
                   line=charts.line(_day_counts(atts, "created", 14), _day_counts(subs, "submitted_at", 14)),
                   tiles=charts.tiles(_test_tiles(atts[:300])), top=sorted(stu, key=lambda x: -x.points)[:5])
        if u.is_main:
            from apps.courses.models import LessonModel as LM
            allu = UserModel.objects.on_site()
            ctx.update(n_users=allu.count(), n_assist=allu.filter(role="assistant").count(), n_online=sum(1 for x in users if x.online),
                       n_courses=CourseModel.objects.filter(group__isnull=True).count(), n_lessons=LM.objects.count(), n_tests=TestModel.objects.count(),
                       n_blocked=allu.filter(is_blocked=True).count(),
                       views=sum(LessonProgressModel.objects.filter(user_id__in=stu_ids).values_list("views", flat=True)),
                       nu_bars=_bars(_day_counts(allu, "date_joined", 14)),
                       role_donut=charts.donut([("Talabalar", allu.filter(role="student").count(), "#6b5bd2"),
                                                ("Yordamchilar", allu.filter(role="assistant").count(), "#ff9db5"),
                                                ("Asosiy", allu.filter(role="main").count(), "#f4d44d")]))
        return render(request, "shared/stats.html", ctx)

    ap = _applied(request, filters)
    if tab == "usr":
        rows = []
        for x in users:
            at = [a for a in atts if a.user_id == x.pk]
            sd = x.is_student
            rows.append({"title": x.full_name, "sub": x.get_role_display(), "avatar": True,
                         "url": reverse("user_detail", args=[x.pk]) if (u.can_view("users") and x.pk != u.pk) else "",
                         "tags": [T(x.get_role_display())],
                         "cells": [x.full_name, x.get_role_display(), ", ".join(gg.name for gg in x.member_groups.all()) or "—", x.points if sd else "—",
                                   f"{round(sum(a.percent for a in at) / len(at))}%" if at else "—", len(at) if sd else "—",
                                   SubmissionModel.objects.filter(student=x).count() if sd else "—",
                                   SubmissionModel.objects.filter(reviewer=x).count() if not sd else "—",
                                   x.logins.filter(ok=True).count(), x.last_seen.strftime("%d.%m %H:%M") if x.last_seen else "—"], "f": dict(ap)})
        L = make_list(request, rows, ["Foydalanuvchi", "Rol", "Guruh", "Ball", "Test o‘rtachasi", "Test urinishlari", "Topshirgan vazifa", "Tekshirgan vazifa", "Kirishlar", "Oxirgi faollik"], filters)
    elif tab == "tst":
        rows = []
        for a in atts.order_by("-created"):
            tt = T(f"{a.percent}%", "f" if a.percent >= 70 else "x")
            cells = ([] if u.is_student else [a.user.full_name]) + [a.test.title, a.created, f"{a.score} / {a.total}", tt]
            rows.append({"title": a.test.title if u.is_student else f"{a.user.full_name} {a.test.title}", "sub": a.test.title,
                         "url": reverse("attempt_detail", args=[a.pk]), "tags": [tt], "cells": cells,
                         "f": {**ap, "tst": a.test.title, "res": "O‘tdi (70% va yuqori)" if a.percent >= 70 else "O‘tmadi"}})
        heads = ([] if u.is_student else ["Foydalanuvchi"]) + ["Test", "Sana", "To‘g‘ri javoblar", "Natija"]
        tests_opts = sorted({a.test.title for a in atts}) if u.is_student else [t.title for t in TestModel.objects.all()]
        L = make_list(request, rows, heads, filters + [("tst", "Test", tests_opts), ("res", "Natija", ["O‘tdi (70% va yuqori)", "O‘tmadi"])])
    else:
        rows = []
        for s in subs.order_by("-submitted_at"):
            lab = dict(SubmissionModel.STATUS)[s.status]
            tt = T(lab, "f" if s.status == "accepted" else "" if s.status == "pending" else "x")
            url = (reverse("lesson_detail", args=[s.task.lesson_id]) + "?tab=task") if u.is_student else reverse("submission_review", args=[s.pk])
            cells = ([] if u.is_student else [s.student.full_name]) + [s.task.title, s.task.lesson.title, s.task.deadline or "—", s.submitted_at,
                                                                         s.graded_at or "—", f"{s.score}/{s.task.max_score}" if s.score is not None else "—", tt]
            rows.append({"title": s.task.title if u.is_student else f"{s.student.full_name} {s.task.title}", "sub": s.task.title, "url": url, "tags": [tt],
                         "cells": cells, "f": {**ap, "st": lab}})
        heads = ([] if u.is_student else ["Foydalanuvchi"]) + ["Vazifa", "Dars", "Muddat", "Topshirgan sana", "Baholangan sana", "Ball", "Holat"]
        L = make_list(request, rows, heads, filters + [("st", "Holat", [x[1] for x in SubmissionModel.STATUS])])
    ctx["L"] = L
    return render(request, "shared/stats.html", ctx)


def _applied(request, filters):
    """Rol/guruh/kurs/davr filtrlari so'rovning o'zida (queryset) qo'llangan — qatorlar shu qiymatlar bilan belgilanadi."""
    return {k: request.GET.get("f_" + k) for k, _, _ in filters if request.GET.get("f_" + k)}

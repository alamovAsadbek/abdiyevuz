import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.helpers import A, T, clean_html, make_list, to_int
from apps.core.models import EventModel, log_event
from apps.core.perms import deny, login_required, perm_required, post_only
from apps.core.protected import NOSTORE, office_to_pdf
from apps.core.validators import DOC_EXT, VIDEO_EXT, VIEW_EXT, check_upload
from . import video
from .models import (CourseAccessModel, CourseModel, GuideFileModel, GuideModel, LessonMaterialModel, LessonModel,
                     LessonProgressModel, ModuleModel, SubmissionModel, TaskModel)
from apps.accounts.models import UserModel
from .services import (student_open_tasks, can_access, completed_count, enrolled, has_access_row, lesson_done, lock_reason, my_course_ids,
                       scoped_students, visible_courses)

BUILTIN = [("pt", "Mendeleyev davriy jadvali", "Jadval", "118 ta element, kategoriyalar bo‘yicha rangli"),
           ("sol", "Moddalarning suvda eruvchanligi", "Jadval", "Kislota, asos va tuzlar jadvali"),
           ("act", "Metallarning kuchlanish qatori", "Jadval", "Faollik bo‘yicha joylashuv"),
           ("acid", "Kuchli va kuchsiz kislota, asoslar", "Jadval", "Elektrolit kuchi bo‘yicha"),
           ("frm", "Asosiy kimyoviy formulalar", "Formula", "Mol, konsentratsiya, pH"),
           ("ind", "Indikatorlar rangi", "Amaliy", "Kislotali, neytral va ishqoriy muhit")]


def lesson_section(course):
    return "groups" if course.is_hidden else "courses"


def can_manage_lessons(user, course, action=None):
    """Dars/qo'llanma boshqaruvi: guruh kursi — «Guruhlar», oddiy kurs — «Kurslar» bo'limi ruxsati.
    action: add / edit / delete (None — biror yozish amali)."""
    return user.is_authenticated and user.is_teacher and user.can(lesson_section(course), action)


def lesson_rows(user, module):
    lessons = list(module.lessons.prefetch_related("tasks"))
    seen, subs = set(), set()
    if user.is_authenticated and user.is_student:
        seen = set(LessonProgressModel.objects.filter(user=user, lesson__in=lessons).values_list("lesson_id", flat=True))
        subs = set(SubmissionModel.objects.filter(student=user, task__lesson__in=lessons).values_list("task_id", flat=True))
    out = []
    for l in lessons:
        out.append({"l": l, "lock": lock_reason(user, l), "done": lesson_done(user, l, seen, subs) if seen else False,
                    "ntasks": len([t for t in l.tasks.all() if t.is_active or (user.is_authenticated and user.is_teacher)]),
                    "seen_n": LessonProgressModel.objects.filter(lesson=l).count() if user.is_authenticated and user.is_teacher else 0})
    return out


def embed_url(u):
    m = re.search(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([\w-]{11})", u)
    if m:
        return "https://www.youtube.com/embed/" + m.group(1)
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", u)
    if m:
        return "https://player.vimeo.com/video/" + m.group(1)
    m = re.search(r"rutube\.ru/(?:video|play/embed)/(\w+)", u)
    if m:
        return "https://rutube.ru/play/embed/" + m.group(1)
    return ""


def read_video(request, old=None):
    """Forma ma'lumotidan video sozlamasini oladi -> (dict, xato)."""
    P, kind = request.POST, request.POST.get("video_kind", "none")
    if kind == "none":
        return {"video_kind": "none", "video_url": ""}, None
    if kind == "link":
        u = P.get("video_url", "").strip()
        if not re.match(r"^https://", u):
            return None, "Havola https:// bilan boshlanishi kerak"
        if not (embed_url(u) or re.search(r"\.(mp4|webm|ogg)(\?|$)", u, re.I)):
            return None, "Faqat YouTube, Vimeo, Rutube yoki to‘g‘ridan-to‘g‘ri .mp4 havolasi qabul qilinadi"
        return {"video_kind": "link", "video_url": u}, None
    if kind == "iframe":
        m = re.search(r"src=[\"']([^\"']+)[\"']", P.get("video_iframe", ""))
        if not m or not embed_url(m.group(1)) and not re.match(r"^https://(www\.youtube\.com|player\.vimeo\.com|rutube\.ru)/", m.group(1)):
            return None, "Iframe kodidan ruxsat etilgan (YouTube/Vimeo/Rutube) src topilmadi"
        return {"video_kind": "iframe", "video_url": embed_url(m.group(1)) or m.group(1)}, None
    f = request.FILES.get("video_file")
    if f:
        try:
            check_upload(f, VIDEO_EXT, __import__("django.conf", fromlist=["settings"]).settings.MAX_VIDEO_MB)
        except ValidationError as e:
            return None, e.messages[0]
        return {"video_kind": "file", "_file": f}, None
    if old and old.video_kind == "file":
        return {"video_kind": "file"}, None
    return None, "Video faylni tanlang"


def apply_video(lesson, vd):
    f = vd.pop("_file", None)
    for k, v in vd.items():
        setattr(lesson, k, v)
    if vd.get("video_kind") != "file":
        lesson.video_src = None
    lesson.save()
    if f:
        lesson.video_name = f.name[:200]
        lesson.hls_status, lesson.hls_error = "processing", ""
        lesson.video_src.save(f.name, f, save=False)
        lesson.save()
        video.start(lesson.pk)


# ---------------------------------------------------------------- courses
def courses(request):
    u = request.user
    teacher = u.is_authenticated and u.is_teacher
    P = u.acts("courses") if teacher else {}
    rows = []
    for c in visible_courses(u).prefetch_related("modules"):
        paid = c.is_paid
        price = ("dan " if c.is_modular and paid else "") + ("%s so‘m" % f"{c.min_price():,}".replace(",", " ") if paid else "Bepul")
        pt = T(price, "x" if paid else "f")
        acts = []
        if P.get("edit"):
            acts.append(A("edit-2", "Sozlamalar", url=reverse("course_detail", args=[c.pk]) + "?tab=set"))
        if P.get("delete"):
            acts.append(A("trash-2", "O‘chirish", post=reverse("course_delete", args=[c.pk]), confirm="Kurs o‘chirilsinmi?", cls="x"))
        rows.append({"title": c.title, "sub": ("Modulli" if c.is_modular else "Modulsiz") + " kurs", "url": reverse("course_detail", args=[c.pk]), "tags": [pt],
                     "cells": [c.title, T("Modulli" if c.is_modular else "Modulsiz"), c.modules.count(), c.lesson_count, "Ketma-ket" if c.sequential else "Ixtiyoriy", pt],
                     "actions": acts, "f": {"ty": "Modulli" if c.is_modular else "Modulsiz", "pr": "Pullik" if paid else "Bepul", "sq": "Ketma-ket" if c.sequential else "Ixtiyoriy"}})
    add = [{"icon": "plus", "label": "Yangi kurs", "url": reverse("course_new")}] if P.get("add") else None
    return render(request, "shared/courses/list.html", {"L": make_list(request, rows, ["Kurs nomi", "Turi", "Modullar", "Darslar", "Tartib", "Narx"],
                  [("ty", "Turi", ["Modulli", "Modulsiz"]), ("pr", "Narx", ["Bepul", "Pullik"]), ("sq", "Tartib", ["Ketma-ket", "Ixtiyoriy"])], add)})


@perm_required("courses")
def course_new(request):
    """Avval faqat kurs yaratiladi. Keyin kurs sahifasida modul (modulli kurs) yoki video dars qo'shiladi."""
    kinds = [("0", "Modulsiz (darslar to‘g‘ridan-to‘g‘ri)"), ("1", "Modulli (modullar ichida darslar)")]
    if request.method == "POST":
        P = request.POST
        t = P.get("title", "").strip()
        if not t:
            messages.error(request, "Kurs nomini kiriting")
            return render(request, "staff/courses/form.html", {"d": P, "kinds": kinds})
        modular = P.get("is_modular") == "1"
        c = CourseModel.objects.create(title=t[:160], description=P.get("description", ""), is_modular=modular, sequential=bool(P.get("sequential")),
                                       price=0 if modular else max(0, to_int(P.get("price"))))
        if not modular:
            c.first_module()
        log_event("course_new", request.user, course=c)
        messages.success(request, "Kurs yaratildi — endi " + ("modul" if modular else "video dars") + " qo‘shing")
        return redirect("course_detail", pk=c.pk)
    return render(request, "staff/courses/form.html", {"d": {}, "kinds": kinds})


def _course(request, pk):
    c = get_object_or_404(CourseModel, pk=pk, group__isnull=True)
    if not c.is_active and not (request.user.is_authenticated and request.user.is_teacher):
        raise Http404
    return c


def _price_label(c):
    if not c.is_paid:
        return "Bepul"
    return ("dan " if c.is_modular else "") + f"{c.min_price():,}".replace(",", " ") + " so‘m"


def course_info(c, lessons):
    """Kurs bo'yicha umumiy raqamlar (kurs sahifasining yuqori qismi uchun)."""
    lids = [l.pk for l in lessons]
    return {"n_mod": c.modules.count(), "n_les": len(lessons), "dur": sum(l.duration for l in lessons),
            "n_task": TaskModel.objects.filter(lesson_id__in=lids, is_active=True).count(),
            "n_mat": LessonMaterialModel.objects.filter(lesson_id__in=lids).count(),
            "n_video": sum(1 for l in lessons if l.video_kind != "none"),
            "views": sum(l.views for l in lessons),
            "n_stu": CourseAccessModel.objects.filter(course=c, user__show_on_site=True).values("user").distinct().count()}


def course_detail(request, pk):
    c = _course(request, pk)
    u = request.user
    staff = u.is_authenticated and u.is_teacher
    perm = u.acts("courses") if staff else {}
    mg = bool(perm.get("any"))
    first = "mod" if c.is_modular else "les"
    names = {"mod": "Modullar", "les": "Darslar", "about": "Kurs haqida", "set": "Sozlamalar", "stu": "Talabalar", "his": "Tarix"}
    hints = {"mod": "Kursdagi modullar va ulardagi darslar", "les": "Kursdagi video darslar ro‘yxati",
             "about": "Kurs tavsifi, tarkibi va narxi", "set": "Kurs nomi, tavsifi, narxi va tartibini o‘zgartirish",
             "stu": "Kurs ochilgan talabalar va ularning jarayoni", "his": "Kurs bo‘yicha barcha amallar tarixi"}
    keys = [first, "about"] + (["set"] if perm.get("edit") or perm.get("delete") else []) + (["stu", "his"] if staff else [])
    tab = request.GET.get("tab") if request.GET.get("tab") in keys else first
    lessons = list(LessonModel.objects.filter(module__course=c).order_by("module__order", "module_id", "order", "id"))
    info = course_info(c, lessons)
    ctx = {"c": c, "mg": mg, "perm": perm, "staff": staff, "info": info, "price_label": _price_label(c),
           "tabs": [(k, names[k]) for k in keys], "tab_hints": hints, "tab": tab,
           "first_lesson": lessons[0] if lessons else None,
           "teacher": UserModel.objects.on_site().filter(role="main").first()}
    module = c.first_module() if not c.is_modular else None
    ctx["module"] = module
    # Talaba (yoki mehmon) uchun kirish va jarayon
    if c.is_modular:
        ctx["has_access"] = any(can_access(u, c, m) for m in c.modules.filter(is_active=True)) if not staff else True
    else:
        ctx["has_access"] = can_access(u, c, module)
    ctx["can_buy"] = bool(u.is_authenticated and u.is_student and not c.is_modular and c.price > 0 and not ctx["has_access"])
    if u.is_authenticated and u.is_student:
        done, tot = completed_count(u, c)
        last = LessonProgressModel.objects.filter(user=u, lesson__module__course=c).select_related("lesson").order_by("-last_seen").first()
        pct = round(done / tot * 100) if tot else 0
        ctx["progress"] = {"done": done, "tot": tot, "pct": pct, "off": round(113 - 1.13 * pct, 1), "last": last.lesson if last else None}
    if tab == "mod":
        mods = c.modules.all() if staff else c.modules.filter(is_active=True)
        seen = set(LessonProgressModel.objects.filter(user=u, lesson__module__course=c).values_list("lesson_id", flat=True)) if u.is_authenticated and u.is_student else set()
        rows = []
        for m in mods.prefetch_related("lessons"):
            ls = list(m.lessons.all())
            rows.append({"m": m, "n": len(ls), "ok": can_access(u, c, m), "lessons": ls[:4], "dur": sum(x.duration for x in ls),
                         "pct": round(sum(1 for x in ls if x.pk in seen) / len(ls) * 100) if ls and seen else 0,
                         "own": u.is_authenticated and u.is_student and has_access_row(u, c, m)})
        ctx["mods"] = rows
    elif tab == "les":
        ctx.update(rows=lesson_rows(u, module), ok=ctx["has_access"])
    elif tab == "stu":
        ids = list(CourseAccessModel.objects.filter(course=c).values_list("user_id", flat=True))
        rows = []
        for s in scoped_students(u).filter(pk__in=ids):
            done, tot = completed_count(s, c)
            rows.append({"u": s, "n": done, "pct": round(done / tot * 100) if tot else 0,
                         "mods": [a.module.title if a.module else "Barcha modullar" for a in CourseAccessModel.objects.filter(user=s, course=c).select_related("module")]})
        ctx["students"] = rows
    elif tab == "his":
        ctx["events"] = EventModel.objects.filter(course=c).select_related("user", "actor")[:100]
    return render(request, "shared/courses/detail.html", ctx)


@perm_required("courses")
@post_only
def course_settings(request, pk):
    c = _course(request, pk)
    P = request.POST
    if not P.get("title", "").strip():
        messages.error(request, "Kurs nomini kiriting")
    else:
        c.title, c.description = P["title"].strip(), P.get("description", "")
        c.login_required, c.sequential = bool(P.get("login_required")), bool(P.get("sequential"))
        if not c.is_modular:
            c.price = max(0, to_int(P.get("price")))
        c.save()
        messages.success(request, "Saqlandi")
    return redirect(reverse("course_detail", args=[pk]) + "?tab=set")


@perm_required("courses")
@post_only
def course_toggle(request, pk):
    c = _course(request, pk)
    c.is_active = not c.is_active
    c.save(update_fields=["is_active"])
    log_event("course_act" if c.is_active else "course_deact", request.user, course=c)
    messages.success(request, "Kurs aktiv qilindi" if c.is_active else "Kurs noaktiv qilindi")
    return redirect(reverse("course_detail", args=[pk]) + "?tab=set")


@perm_required("courses")
@post_only
def course_delete(request, pk):
    _course(request, pk).delete()
    messages.success(request, "Kurs o‘chirildi")
    return redirect("courses")


# ---------------------------------------------------------------- modules
def _module(request, pk):
    m = get_object_or_404(ModuleModel.objects.select_related("course"), pk=pk, course__group__isnull=True)
    if (not m.course.is_active or (m.course.is_modular and not m.is_active)) and not (request.user.is_authenticated and request.user.is_teacher):
        raise Http404
    return m


def module_detail(request, pk):
    m = _module(request, pk)
    c, u = m.course, request.user
    ok = can_access(u, c, m)
    perm = u.acts("courses") if u.is_authenticated and u.is_teacher else {}
    ls = list(m.lessons.all())
    return render(request, "shared/courses/module.html", {"m": m, "c": c, "rows": lesson_rows(u, m), "ok": ok, "mg": bool(perm.get("any")), "perm": perm,
                                                         "n_les": len(ls), "dur": sum(x.duration for x in ls),
                                                         "n_task": TaskModel.objects.filter(lesson__in=ls, is_active=True).count(),
                                                         "can_buy": u.is_authenticated and u.is_student and m.price > 0 and not ok})


@perm_required("courses")
def module_form(request, cid=None, pk=None):
    m = get_object_or_404(ModuleModel, pk=pk, course__group__isnull=True) if pk else None
    c = m.course if m else get_object_or_404(CourseModel, pk=cid, is_modular=True, group__isnull=True)
    if request.method == "POST":
        P = request.POST
        if not P.get("title", "").strip():
            messages.error(request, "Modul nomini kiriting")
        else:
            m = m or ModuleModel(course=c, order=c.modules.count())
            m.title, m.description, m.price = P["title"].strip(), P.get("description", ""), max(0, to_int(P.get("price")))
            m.is_active = bool(P.get("is_active"))
            m.save()
            messages.success(request, "Modul saqlandi")
            return redirect("module_detail", pk=m.pk)
    return render(request, "staff/courses/module_form.html", {"m": m, "c": c, "active": m.is_active if m else True})


@perm_required("courses")
@post_only
def module_toggle(request, pk):
    m = _module(request, pk)
    m.is_active = not m.is_active
    m.save(update_fields=["is_active"])
    messages.success(request, "Modul aktiv qilindi" if m.is_active else "Modul noaktiv qilindi")
    return redirect(request.POST.get("next") or reverse("module_detail", args=[pk]))


@perm_required("courses")
@post_only
def module_delete(request, pk):
    m = _module(request, pk)
    cid = m.course_id
    m.delete()
    messages.success(request, "Modul o‘chirildi")
    return redirect("course_detail", pk=cid)


# ---------------------------------------------------------------- lessons
def _lesson(request, pk):
    return get_object_or_404(LessonModel.objects.select_related("module__course__group"), pk=pk)


def lesson_detail(request, pk):
    l = _lesson(request, pk)
    u, m, c = request.user, l.module, l.module.course
    msg = lock_reason(u, l)
    back = reverse("group_detail", args=[c.group_id]) if c.is_hidden else reverse("module_detail", args=[m.pk]) if c.is_modular else reverse("course_detail", args=[c.pk])
    if msg:
        return render(request, "shared/lesson/locked.html", {"l": l, "msg": msg, "back": back})
    mg = can_manage_lessons(u, c)
    lp = u.acts(lesson_section(c)) if u.is_authenticated and u.is_teacher else {}
    keys = ["video", "mat", "task"] + (["stu"] if u.is_authenticated and u.is_teacher else []) + (["set"] if mg else []) + ["info"]
    names = {"video": "Video", "mat": "Qo‘llanma", "task": "Vazifalar", "stu": "O‘quvchilar", "set": "Sozlamalar", "info": "Kurs haqida"}
    tab = request.GET.get("tab") if request.GET.get("tab") in keys else "video"
    ctx = {"l": l, "c": c, "m": m, "back": back, "mg": mg, "lp": lp, "tabs": [(k, names[k]) for k in keys], "tab": tab,
           "can_tasks": u.is_authenticated and u.is_teacher and u.can("tasks", "add"),
           "see_tasks": u.is_authenticated and u.is_teacher and u.can_view("tasks"), "my_views": 0}
    if u.is_authenticated and u.is_student and tab == "video":
        p, created = LessonProgressModel.objects.get_or_create(user=u, lesson=l)
        if not created and request.method == "GET" and not request.GET.get("noc"):
            LessonProgressModel.objects.filter(pk=p.pk).update(views=p.views + 1, last_seen=timezone.now())
            p.views += 1
        LessonModel.objects.filter(pk=l.pk).update(views=l.views + 1)
        l.views += 1
        ctx["my_views"] = p.views
    sibs = list(m.lessons.all())
    i = [s.pk for s in sibs].index(l.pk)
    ctx["prev"], ctx["next"] = (sibs[i - 1] if i else None), (sibs[i + 1] if i + 1 < len(sibs) else None)
    if tab == "video":
        ctx.update(n_mats=l.materials.count(), n_tasks=l.tasks.filter(is_active=True).count())
        ctx["embed"] = embed_url(l.video_url) if l.video_kind == "link" else l.video_url
        ctx["direct"] = l.video_kind == "link" and not embed_url(l.video_url)
    elif tab == "mat":
        ctx["mats"] = l.materials.all()
    elif tab == "task":
        tasks = l.tasks.all() if u.is_authenticated and u.is_teacher else l.tasks.filter(is_active=True)
        subs = {s.task_id: s for s in SubmissionModel.objects.filter(student=u, task__in=tasks)} if u.is_authenticated and u.is_student else {}
        ctx["tasks"] = [{"t": t, "s": subs.get(t.pk), "count": t.submissions.count()} for t in tasks]
    elif tab == "stu":
        en = enrolled(l, u)
        ctx["students"] = [{"u": s, "p": LessonProgressModel.objects.filter(user=s, lesson=l).first(),
                            "tasks": [(t, SubmissionModel.objects.filter(task=t, student=s).first()) for t in l.tasks.all()]} for s in en]
        ctx["n_seen"] = LessonProgressModel.objects.filter(user__in=en, lesson=l).count()
    elif tab == "info":
        ctx.update(teacher=UserModel.objects.on_site().filter(role="main").first(), total=LessonModel.objects.filter(module__course=c).count(),
                   pct=round(completed_count(u, c)[0] / max(1, LessonModel.objects.filter(module__course=c).count()) * 100) if u.is_authenticated and u.is_student else None)
    return render(request, "shared/lesson/detail.html", ctx)


def _lesson_form(request, module=None, lesson=None):
    m = module or lesson.module
    c = m.course
    if not can_manage_lessons(request.user, c, "edit" if lesson else "add"):
        return deny(request)
    if request.method == "POST":
        t = request.POST.get("title", "").strip()
        vd, err = read_video(request, lesson)
        if not t:
            err = "Dars nomini kiriting"
        if err:
            messages.error(request, err)
        else:
            l = lesson or LessonModel(module=m, order=m.lessons.count())
            l.title, l.description = t[:200], request.POST.get("description", "").strip()
            l.save()
            apply_video(l, vd)
            messages.success(request, "Dars saqlandi" + (" — video qayta ishlanmoqda (siqish + shifrlash)" if l.hls_status == "processing" else ""))
            return redirect("lesson_detail", pk=l.pk)
    return render(request, "staff/lessons/form.html", {"l": lesson, "m": m, "c": c, "kinds": [("none", "Videosiz"), ("link", "Havola"), ("iframe", "Iframe"), ("file", "Video fayl")]})


@login_required
def lesson_new(request, mid):
    return _lesson_form(request, module=get_object_or_404(ModuleModel, pk=mid))


@login_required
def lesson_edit(request, pk):
    return _lesson_form(request, lesson=_lesson(request, pk))


@login_required
@post_only
def lesson_delete(request, pk):
    l = _lesson(request, pk)
    if not can_manage_lessons(request.user, l.module.course, "delete"):
        return deny(request)
    m = l.module
    import shutil
    shutil.rmtree(video.hls_dir(l.pk), ignore_errors=True)
    l.delete()
    messages.success(request, "Dars o‘chirildi")
    c = m.course
    return redirect("group_detail", pk=c.group_id) if c.is_hidden else redirect("module_detail", pk=m.pk) if c.is_modular else redirect("course_detail", pk=c.pk)


@login_required
def material_new(request, pk):
    l = _lesson(request, pk)
    if not can_manage_lessons(request.user, l.module.course, "edit"):
        return deny(request)
    if request.method == "POST":
        t, url, f = request.POST.get("title", "").strip(), request.POST.get("url", "").strip(), request.FILES.get("file")
        try:
            if not t:
                raise ValidationError("Qo‘llanma nomini kiriting")
            if not url and not f:
                raise ValidationError("Havola kiriting yoki fayl yuklang")
            if url and not url.startswith("https://"):
                raise ValidationError("Havola https:// bilan boshlanishi kerak")
            if f:
                ext = check_upload(f)
                if ext in (".doc", ".docx", ".ppt", ".pptx", ".odt"):
                    pdf = office_to_pdf(f)
                    if pdf:
                        f, ext = ContentFile(pdf, name=f.name.rsplit(".", 1)[0] + ".pdf"), ".pdf"
                M = LessonMaterialModel(lesson=l, title=t, kind="file", filename=f.name)
                M.file.save(f.name, f, save=True)
            else:
                LessonMaterialModel.objects.create(lesson=l, title=t, kind="link", url=url)
            messages.success(request, "Qo‘llanma qo‘shildi")
            return redirect(reverse("lesson_detail", args=[pk]) + "?tab=mat")
        except ValidationError as e:
            messages.error(request, e.messages[0])
    return render(request, "staff/lessons/material_form.html", {"l": l})


@login_required
@post_only
def material_delete(request, pk):
    mt = get_object_or_404(LessonMaterialModel, pk=pk)
    if not can_manage_lessons(request.user, mt.lesson.module.course, "edit"):
        return deny(request)
    lid = mt.lesson_id
    mt.file.delete(save=False) if mt.file else None
    mt.delete()
    messages.success(request, "Qo‘llanma o‘chirildi")
    return redirect(reverse("lesson_detail", args=[lid]) + "?tab=mat")


# ---------------------------------------------------------------- video streaming (AES-128 HLS)
def _stream_lesson(request, pk):
    l = get_object_or_404(LessonModel.objects.select_related("module__course__group"), pk=pk)
    if lock_reason(request.user, l) or l.hls_status != "ready":
        raise PermissionDenied if lock_reason(request.user, l) else Http404
    return l


def stream_playlist(request, pk):
    l = _stream_lesson(request, pk)
    txt = (video.hls_dir(l.pk) / "index.m3u8").read_text()
    out = "\n".join(f"/stream/{l.pk}/seg/{ln}" if ln and not ln.startswith("#") else ln for ln in txt.splitlines())
    return HttpResponse(out, content_type="application/vnd.apple.mpegurl", headers=NOSTORE)


def stream_key(request, pk):
    l = _stream_lesson(request, pk)
    return HttpResponse((video.hls_dir(l.pk) / "enc.key").read_bytes(), content_type="application/octet-stream", headers=NOSTORE)


def stream_seg(request, pk, name):
    l = _stream_lesson(request, pk)
    if not re.fullmatch(r"seg\d{5}\.ts", name):
        raise Http404
    p = video.hls_dir(l.pk) / name
    if not p.exists():
        raise Http404
    r = FileResponse(open(p, "rb"), content_type="video/mp2t")
    for k, v in NOSTORE.items():
        r[k] = v
    return r


# ---------------------------------------------------------------- guides
def ensure_builtin():
    if GuideModel.objects.filter(builtin_key__gt="").count() < len(BUILTIN):
        have = set(GuideModel.objects.exclude(builtin_key="").values_list("builtin_key", flat=True))
        for k, t, cat, s in BUILTIN:
            if k not in have:
                g = GuideModel.objects.create(title=t, category=cat, summary=s, builtin_key=k)
                log_event("guide_create", None, guide=g)


@login_required
def guides(request):
    ensure_builtin()
    u = request.user
    mg = u.is_teacher and u.can("guides")
    P = u.acts("guides") if u.is_teacher else {}
    rows = []
    for g in GuideModel.objects.all():
        if not g.is_active and not mg:
            continue
        st = T("Aktiv", "f") if g.is_active else T("Noaktiv", "x")
        acts = []
        if P.get("edit"):
            acts.append(A("pause" if g.is_active else "play", "Aktiv/Noaktiv", post=reverse("guide_toggle", args=[g.pk]), confirm="Qo‘llanma holati o‘zgartirilsinmi?"))
        if P.get("delete"):
            acts.append(A("trash-2", "O‘chirish", post=reverse("guide_delete", args=[g.pk]), confirm="Qo‘llanma o‘chirilsinmi?", cls="x"))
        typ = "Standart" if g.builtin_key else "O‘qituvchi qo‘shgan"
        rows.append({"title": g.title, "sub": g.summary or (("Qo‘shgan: " + g.author.full_name) if g.author else ""), "url": reverse("guide_detail", args=[g.pk]),
                     "tags": [T(g.category), st], "cells": [g.title, T(g.category), typ, st], "actions": acts, "f": {"cat": g.category, "st": "Aktiv" if g.is_active else "Noaktiv"}})
    add = [{"icon": "plus", "label": "Qo‘llanma qo‘shish", "url": reverse("guide_new")}] if P.get("add") else None
    flt = [("cat", "Kategoriya", GuideModel.CATS)] + ([("st", "Status", ["Aktiv", "Noaktiv"])] if mg else [])
    return render(request, "shared/guides/list.html", {"L": make_list(request, rows, ["Nomi", "Kategoriya", "Turi", "Status"], flt, add)})


@perm_required("guides")
def guide_new(request):
    if request.method == "POST":
        t, body = request.POST.get("title", "").strip(), clean_html(request.POST.get("body", ""))
        files = request.FILES.getlist("files")
        try:
            if not t:
                raise ValidationError("Sarlavhani kiriting")
            if not re.sub(r"<[^>]+>", "", body).strip() and "<img" not in body and not files:
                raise ValidationError("Matn yozing yoki fayl yuklang")
            for f in files:
                check_upload(f)
            cat = request.POST.get("category")
            g = GuideModel.objects.create(title=t, category=cat if cat in GuideModel.CATS else "Boshqa", body=body, author=request.user)
            for f in files:
                x = GuideFileModel(guide=g, name=f.name)
                x.file.save(f.name, f, save=True)
            log_event("guide_create", request.user, guide=g)
            messages.success(request, "Qo‘llanma qo‘shildi")
            return redirect("guides")
        except ValidationError as e:
            messages.error(request, e.messages[0])
    return render(request, "staff/guides/form.html", {"cat_opts": [(c, c) for c in GuideModel.CATS]})


@login_required
def guide_detail(request, pk):
    g = get_object_or_404(GuideModel, pk=pk)
    mg = request.user.is_teacher and request.user.can("guides")
    if not g.is_active and not mg:
        raise Http404
    ctx = {"g": g, "mg": mg, "tab": request.GET.get("tab", "") if mg else "", "files": g.files.all()}
    if ctx["tab"] == "his":
        ctx["events"] = EventModel.objects.filter(guide=g)[:100]
    return render(request, "shared/guides/detail.html", ctx)


@perm_required("guides")
@post_only
def guide_toggle(request, pk):
    g = get_object_or_404(GuideModel, pk=pk)
    g.is_active = not g.is_active
    g.save(update_fields=["is_active"])
    log_event("guide_act" if g.is_active else "guide_deact", request.user, guide=g)
    messages.success(request, "Qo‘llanma aktiv qilindi" if g.is_active else "Qo‘llanma noaktiv qilindi")
    return redirect(request.POST.get("next") or "guides")


@perm_required("guides")
@post_only
def guide_delete(request, pk):
    g = get_object_or_404(GuideModel, pk=pk)
    log_event("guide_delete", request.user, note=g.title)
    g.delete()
    messages.success(request, "Qo‘llanma o‘chirildi")
    return redirect("guides")

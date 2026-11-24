import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserModel
from apps.core.helpers import A, T, clean_html, jload, make_list, parse_local, to_int
from apps.core.models import log_event
from apps.core.perms import deny, login_required, perm_required, post_only
from apps.core.protected import office_to_pdf
from apps.core.realtime import push_all
from apps.core.validators import DOC_EXT, IMG_EXT, VIEW_EXT, check_upload
from apps.courses.models import PurchaseRequestModel
from apps.courses.services import scoped_students, student_in_scope
from apps.notifications.services import notify, notify_staff
from .models import AttemptModel, ErrorReportModel, QuestionModel, RetakeGrantModel, TestAccessModel, TestModel
from .services import attempt_count, can_try, grants_left, has_paid_access, score_answers


def _mg(user):
    return user.is_authenticated and user.is_teacher and user.can("tests")


def tests(request):
    u = request.user
    rows = []
    for t in TestModel.objects.all().prefetch_related("questions"):
        lab = t.label
        st = T(*lab)
        pt = T(f"{t.price:,}".replace(",", " ") + " so‘m", "x") if t.is_paid else T("Bepul", "f")
        acts = []
        if _mg(u):
            acts = [A("edit-2", "Tahrirlash", url=reverse("test_edit", args=[t.pk])),
                    A("pause" if t.is_active else "play", "Aktiv/Noaktiv", post=reverse("test_toggle", args=[t.pk]), confirm="Test holati o‘zgartirilsinmi?"),
                    A("trash-2", "O‘chirish", post=reverse("test_delete", args=[t.pk]), confirm=f"“{t.title}” testi o‘chirilsinmi?", cls="x")]
        n = t.questions.count()
        rows.append({"title": t.title, "sub": f"{n} ta savol", "url": reverse("test_detail", args=[t.pk]), "tags": [st],
                     "cells": [t.title, f"{n} ta", t.start_at, t.end_at, st, pt], "actions": acts,
                     "f": {"st": lab[0], "pr": "Pullik" if t.is_paid else "Bepul"}})
    add = [{"icon": "plus", "label": "Yangi test", "url": reverse("test_new")}] if _mg(u) else None
    return render(request, "shared/tests/list.html", {"L": make_list(request, rows, ["Test nomi", "Savollar", "Boshlanishi", "Tugashi", "Status", "Narx"],
                  [("st", "Status", ["Aktiv", "Noaktiv", "Tugagan", "Kutilmoqda"]), ("pr", "Narx", ["Bepul", "Pullik"])], add)})


def test_detail(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    u = request.user
    mg = _mg(u)
    if not mg and not (u.is_authenticated and u.is_teacher):
        pass
    st = t.live_status
    ctx = {"t": t, "st": st, "label": t.label, "n": t.questions.count(), "mg": mg, "is_staff": u.is_authenticated and u.is_teacher}
    ctx["paid_block"] = t.is_paid and not has_paid_access(t, u)
    ctx["guest_block"] = (not u.is_authenticated) and (t.is_paid or not t.allow_guest)
    ctx["can_try"] = can_try(t, u)
    ctx["tries"] = attempt_count(t, u) if u.is_authenticated else 0
    ctx["grants"] = grants_left(t, u) if u.is_authenticated else 0
    ctx["can_start"] = st == "active" and ctx["can_try"] and not ctx["paid_block"] and not ctx["guest_block"]
    if ctx["is_staff"]:
        keys = ["info", "q", "res", "rep"]
        tab = request.GET.get("tab") if request.GET.get("tab") in keys else "info"
        ctx.update(tab=tab, tabs=[("info", "Ma‘lumot"), ("q", "Savollar"), ("res", "Natijalar"), ("rep", "Xato xabarlari")])
        if tab == "q":
            ctx["questions"] = t.questions.all()
        elif tab == "res":
            ats = AttemptModel.objects.filter(test=t).select_related("user")
            if u.is_assistant:
                ats = ats.filter(user__in=scoped_students(u))
            seen, rows = set(), []
            for a in ats:
                first = a.user_id not in seen
                seen.add(a.user_id)
                rows.append({"a": a, "first": first, "n": ats.filter(user=a.user).count() if first else 0,
                             "grant": grants_left(t, a.user) > 0 if first else False})
            ctx["rows"] = rows
        elif tab == "rep":
            ctx["reports"] = t.reports.select_related("user")
        if mg:
            ctx["students_json"] = json.dumps([{"id": s.pk, "t": s.full_name, "s": s.uid, "off": TestAccessModel.objects.filter(test=t, user=s).exists()}
                                               for s in scoped_students(u)], ensure_ascii=False) if t.is_paid else "[]"
    return render(request, "shared/tests/detail.html", ctx)


def _parse_form(request, test=None):
    P = request.POST
    title = P.get("title", "").strip()
    st, en = parse_local(P.get("start_at")), parse_local(P.get("end_at"))
    mode = test.mode if test else ("file" if P.get("mode") == "file" else "manual")
    if not title:
        return None, "Test nomini kiriting"
    if not st or not en:
        return None, "Boshlanish va tugash vaqtini kiriting"
    if en <= st:
        return None, "Tugash vaqti boshlanishdan keyin bo‘lishi kerak"
    qs = []
    if mode == "manual":
        data = jload(P.get("payload"), [])
        for i, q in enumerate(data):
            opts = [clean_html(o) for o in q.get("options", [])][:8]
            if len(opts) < 2 or any(not o.strip() for o in opts):
                return None, f"{i+1}-savolda kamida 2 ta to‘ldirilgan variant bo‘lishi kerak"
            c = to_int(q.get("correct"))
            if not 0 <= c < len(opts):
                return None, f"{i+1}-savol uchun to‘g‘ri javob belgilanmagan"
            qs.append({"text": clean_html(q.get("text")), "options": opts, "correct": c, "solution": clean_html(q.get("solution"))})
        if not qs:
            return None, "Kamida 1 ta savol qo‘shing"
    else:
        keys = jload(P.get("keys"), [])
        K = min(8, max(2, to_int(P.get("kopts"), 4)))
        for i, k in enumerate(keys):
            c = to_int(k.get("correct"), -1)
            if not 0 <= c < K:
                return None, f"{i+1}-savol uchun to‘g‘ri javob belgilanmagan"
            qs.append({"text": "", "options": list("ABCDEFGH"[:K]), "correct": c, "solution": clean_html(k.get("solution"))})
        if not qs:
            return None, "Kalit varaqasini yarating"
        f = request.FILES.get("testfile")
        if not f and not (test and test.file):
            return None, "Test faylini yuklang"
    return {"title": title[:200], "start_at": st, "end_at": en, "price": max(0, to_int(P.get("price"))), "is_active": bool(P.get("is_active")),
            "allow_retake": bool(P.get("allow_retake")), "max_attempts": max(0, to_int(P.get("max_attempts"))), "allow_guest": bool(P.get("allow_guest")),
            "mode": mode, "qs": qs}, None


def _save_test(request, test):
    d, err = _parse_form(request, test)
    if err:
        return None, err
    f = request.FILES.get("testfile")
    if f:
        try:
            ext = check_upload(f, DOC_EXT, 50)
            if ext in (".doc", ".docx", ".ppt", ".pptx", ".odt"):
                pdf = office_to_pdf(f)
                if not pdf:
                    return None, "Word faylini PDF ga aylantirib bo‘lmadi — PDF yoki rasm yuklang"
                f = ContentFile(pdf, name=f.name.rsplit(".", 1)[0] + ".pdf")
            elif ext not in VIEW_EXT:
                return None, "Test fayli PDF yoki rasm bo‘lishi kerak"
        except ValidationError as e:
            return None, e.messages[0]
    t = test or TestModel(created_by=request.user)
    for k in ("title", "start_at", "end_at", "price", "is_active", "allow_retake", "max_attempts", "allow_guest", "mode"):
        setattr(t, k, d[k])
    t.status = t.compute_status()
    if f:
        if t.file:
            t.file.delete(save=False)
        t.file_name = f.name[:200]
        t.file.save(f.name, f, save=False)
    t.save()
    old = list(t.questions.all())
    for i, q in enumerate(d["qs"]):
        o = old[i] if i < len(old) else QuestionModel(test=t)
        o.order, o.text, o.options, o.correct, o.solution = i, q["text"], q["options"], q["correct"], q["solution"]
        img = request.FILES.get(f"solimg_{i}")
        if img:
            try:
                check_upload(img, IMG_EXT, 8)
            except ValidationError as e:
                return None, e.messages[0]
            o.solution_image.save(img.name, img, save=False)
        o.save()
    for o in old[len(d["qs"]):]:
        o.delete()
    return t, None


@perm_required("tests")
def test_new(request):
    if request.method == "POST":
        t, err = _save_test(request, None)
        if not err:
            push_all({"type": "refresh", "what": "tests"})
            messages.success(request, "Test saqlandi")
            return redirect("test_detail", pk=t.pk)
        messages.error(request, err)
    return render(request, "staff/tests/form.html", {"t": None, "init": "[]", "active": True, "guest": True, "mode_opts": [("manual", "Savollar saytda"), ("file", "Test fayli + kalitlar")]})


@perm_required("tests")
def test_edit(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    if request.method == "POST":
        _, err = _save_test(request, t)
        if not err:
            messages.success(request, "Test saqlandi")
            return redirect("test_detail", pk=t.pk)
        messages.error(request, err)
    init = [{"text": q.text, "options": q.options, "correct": q.correct, "solution": q.solution, "img": bool(q.solution_image)} for q in t.questions.all()]
    return render(request, "staff/tests/form.html", {"t": t, "init": json.dumps(init, ensure_ascii=False).replace("</", "<\\/"), "active": t.is_active, "guest": t.allow_guest, "mode_opts": []})


@perm_required("tests")
@post_only
def test_toggle(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    t.is_active = not t.is_active
    t.status = t.compute_status()
    t.save(update_fields=["is_active", "status"])
    push_all({"type": "test_status", "id": t.pk, "status": t.status, "title": t.title})
    messages.success(request, "Test holati o‘zgartirildi")
    return redirect(request.POST.get("next") or reverse("test_detail", args=[pk]))


@perm_required("tests")
@post_only
def test_delete(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    t.file.delete(save=False) if t.file else None
    t.delete()
    messages.success(request, "Test o‘chirildi")
    return redirect("tests")


@perm_required("tests")
@post_only
def test_time(request, pk, action):
    t = get_object_or_404(TestModel, pk=pk)
    now = timezone.now()
    if action == "start":
        t.start_at, t.is_active = now, True
        if t.end_at <= now:
            t.end_at = now + timezone.timedelta(days=1)
    elif action == "end":
        t.end_at = now
    else:
        v = parse_local(request.POST.get("start_at"))
        if not v or v >= t.end_at:
            messages.error(request, "Boshlanish vaqti tugash vaqtidan oldin bo‘lishi kerak")
            return redirect("test_detail", pk=pk)
        t.start_at = v
    t.status = t.compute_status()
    t.save()
    push_all({"type": "test_status", "id": t.pk, "status": t.status, "title": t.title})
    messages.success(request, {"start": "Test boshlandi — talabalar ishlay oladi", "end": "Test tugatildi"}.get(action, "Boshlanish vaqti o‘zgartirildi"))
    return redirect("test_detail", pk=pk)


@login_required
def test_run(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    return _run(request, t)


def test_run_public(request, pk):
    return _run(request, get_object_or_404(TestModel, pk=pk))


def _run(request, t):
    u = request.user
    back = redirect("test_detail", pk=t.pk)
    if not u.is_authenticated and (t.is_paid or not t.allow_guest):
        return redirect(f"{reverse('login')}?next={request.path}")
    if t.live_status != "active" or not has_paid_access(t, u) or not can_try(t, u):
        messages.error(request, "Bu testni hozir ishlab bo‘lmaydi")
        return back
    qs = list(t.questions.all())
    if request.method == "POST":
        ans, sc, total = score_answers(t, [request.POST.get(f"q{i}", "-1") for i in range(len(qs))])
        if u.is_authenticated and u.is_student:
            n0 = attempt_count(t, u)
            if n0 > 0 and not (t.allow_retake and (not t.max_attempts or n0 < t.max_attempts)):
                g = RetakeGrantModel.objects.filter(test=t, user=u, used=False).first()
                if g:
                    g.used = True
                    g.save(update_fields=["used"])
            a = AttemptModel.objects.create(test=t, user=u, answers=ans, score=sc, total=total)
            u.points += sc * 10
            u.save(update_fields=["points"])
            return redirect("attempt_detail", pk=a.pk)
        return render(request, "shared/tests/result.html", {"t": t, "sc": sc, "total": total, "pct": round(sc / total * 100) if total else 0,
                                                          "guest": not u.is_authenticated, "preview": u.is_authenticated})
    return render(request, "shared/tests/run.html", {"t": t, "qs": qs, "K": len(qs[0].options) if qs else 4})


@login_required
def attempt_detail(request, pk):
    a = get_object_or_404(AttemptModel.objects.select_related("test", "user"), pk=pk)
    u = request.user
    if u.is_student and a.user_id != u.pk:
        return deny(request)
    if u.is_assistant and not student_in_scope(u, a.user):
        return deny(request)
    qs = list(a.test.questions.all())
    rows = [{"q": q, "i": i, "ans": (a.answers[i] if i < len(a.answers) else -1)} for i, q in enumerate(qs)]
    return render(request, "shared/tests/attempt.html", {"a": a, "t": a.test, "rows": rows, "own": a.user_id == u.pk,
                                                       "can_retry": a.user_id == u.pk and can_try(a.test, u) and a.test.live_status == "active"})


@perm_required("tests")
@post_only
def retake(request, pk, uid, on):
    t = get_object_or_404(TestModel, pk=pk)
    s = get_object_or_404(scoped_students(request.user), pk=uid)
    if on:
        RetakeGrantModel.objects.create(test=t, user=s)
        log_event("test_grant", request.user, user=s, note=t.title)
        notify([s], f"“{t.title}” testini qayta ishlashga ruxsat berildi", f"/tests/{t.pk}/")
        messages.success(request, f"{s.full_name} ga qayta ishlash uchun ruxsat berildi")
    else:
        RetakeGrantModel.objects.filter(test=t, user=s, used=False).delete()
        messages.success(request, "Ruxsat bekor qilindi")
    return redirect(reverse("test_detail", args=[pk]) + "?tab=res")


@perm_required("tests")
@post_only
def test_access(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    d = jload(request.body, {})
    for s in scoped_students(request.user).filter(pk__in=[to_int(x) for x in d.get("uids", [])]):
        TestAccessModel.objects.get_or_create(test=t, user=s)
        notify([s], f"Sizga test ochib berildi: {t.title}", f"/tests/{t.pk}/")
    return JsonResponse({"ok": True})


@login_required
@post_only
def buy_test(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    if not PurchaseRequestModel.objects.filter(user=request.user, test=t, done=False).exists():
        PurchaseRequestModel.objects.create(user=request.user, test=t)
        notify_staff("gift", f"{request.user.full_name} “{t.title}” testini sotib olmoqchi", f"/tests/{t.pk}/?tab=info")
    messages.success(request, "So‘rov yuborildi — o‘qituvchi siz bilan bog‘lanadi")
    return redirect("test_detail", pk=pk)


# ---------------------------------------------------------------- error reports
@login_required
@post_only
def report_new(request, pk):
    t = get_object_or_404(TestModel, pk=pk)
    h = clean_html(request.POST.get("html", ""))
    if not h.strip():
        return JsonResponse({"ok": False, "error": "Xatolik haqida yozing"}, status=400)
    ErrorReportModel.objects.create(test=t, user=request.user, question_index=to_int(request.POST.get("q")), html=h)
    notify_staff("tests", f"Test xatoligi: “{t.title}”, {to_int(request.POST.get('q')) + 1}-savol ({request.user.full_name})", "/staff/reports/")
    return JsonResponse({"ok": True})


@perm_required("tests")
def reports(request):
    rows = []
    for r in ErrorReportModel.objects.select_related("test", "user"):
        tt = T("Ko‘rib chiqilgan", "f") if r.reviewed else T("Yangi", "x")
        rows.append({"title": r.test.title, "sub": f"{r.user.full_name} · {r.created:%d.%m.%Y %H:%M}", "url": reverse("report_detail", args=[r.pk]), "tags": [tt],
                     "cells": [r.test.title, f"{r.question_index + 1}-savol", r.user.full_name, r.created, tt],
                     "actions": [A("trash-2", "O‘chirish", post=reverse("report_delete", args=[r.pk]), confirm="Xabar o‘chirilsinmi?", cls="x")],
                     "f": {"st": "Ko‘rib chiqilgan" if r.reviewed else "Yangi", "ts": r.test.title}})
    return render(request, "staff/tests/reports.html", {"L": make_list(request, rows, ["Test", "Savol", "Yuborgan", "Sana", "Holat"],
                  [("st", "Holat", ["Yangi", "Ko‘rib chiqilgan"]), ("ts", "Test", [t.title for t in TestModel.objects.all()])])})


@perm_required("tests")
def report_detail(request, pk):
    r = get_object_or_404(ErrorReportModel.objects.select_related("test", "user"), pk=pk)
    q = r.test.questions.all()[r.question_index:r.question_index + 1].first()
    return render(request, "staff/tests/report_detail.html", {"r": r, "q": q})


@perm_required("tests")
@post_only
def report_done(request, pk):
    ErrorReportModel.objects.filter(pk=pk).update(reviewed=True)
    messages.success(request, "Xabar ko‘rib chiqildi deb belgilandi")
    return redirect("reports")


@perm_required("tests")
@post_only
def report_delete(request, pk):
    ErrorReportModel.objects.filter(pk=pk).delete()
    messages.success(request, "Xabar o‘chirildi")
    return redirect("reports")

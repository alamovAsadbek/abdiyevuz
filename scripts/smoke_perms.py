"""Ruxsatlar, statistika, xavfsizlik va jurnal sinovi:  python manage.py shell < scripts/smoke_perms.py  (seed_demo dan keyin)"""
import json
import traceback

from django.test import Client

from apps.accounts.models import UserModel
from apps.courses.models import CourseModel
from apps.exams.models import TestModel
from apps.security.models import AuditLogModel, SecurityIncidentModel

BAD = []


def login(u, p):
    c = Client()
    r = c.post("/login/", {"username": u, "password": p})
    assert r.status_code == 302, (u, r.status_code)
    return c


def hit(c, path, who, ok=(200,)):
    try:
        r = c.get(path)
        if r.status_code not in ok:
            BAD.append(f"[{who}] {path} -> {r.status_code} {r.headers.get('Location', '')}")
        return r
    except Exception as e:
        BAD.append(f"[{who}] {path} EXC {e}")
        traceback.print_exc(limit=-4)


main = login("abdiyev", "Admin#2026")
ass_u = UserModel.objects.get(username="yordamchi")
stu_u = UserModel.objects.get(username="ali")
c1 = CourseModel.objects.filter(group__isnull=True).first()
t = TestModel.objects.first()

# --- asosiy o'qituvchi sahifalari
for p in ["/security/", "/staff/logs/", "/stats/", "/stats/?tab=users", "/stats/?tab=tests", "/stats/?tab=tasks", "/settings/?tab=roles",
          "/settings/?tab=protect", "/settings/?tab=site", f"/staff/users/{ass_u.pk}/?tab=perm", f"/staff/users/{stu_u.pk}/?tab=perm",
          f"/staff/users/{stu_u.pk}/?tab=xavf", f"/staff/users/{stu_u.pk}/?tab=log", "/staff/users/new/", f"/courses/{c1.pk}/",
          f"/courses/{c1.pk}/?tab=about", f"/courses/{c1.pk}/?tab=set", f"/courses/{c1.pk}/?tab=stu", "/tests/"]:
    hit(main, p, "MAIN")
r = main.get("/login/")
assert r.status_code == 302, "kirgan foydalanuvchi loginga kirsa panelga o'tadi"

# --- login sahifasida sidebar yo'q
g = Client().get("/login/").content.decode()
assert 'class="side"' not in g and "lgc" in g, "login alohida sahifa bo'lishi kerak"

# --- yordamchi: testlar faqat ko'rish
r = main.post(f"/staff/users/{ass_u.pk}/perm/", json.dumps({"grants": {"tests": ["view"], "courses": ["view", "add"], "users": ["view"]}}),
              content_type="application/json", HTTP_X_REQUESTED_WITH="fetch")
assert r.json()["ok"], r.content
ass = login("yordamchi", "Yordam#2026")
hit(ass, "/tests/", "ASS")
hit(ass, "/tests/new/", "ASS(test add yo'q)", ok=(302,))
hit(ass, "/courses/new/", "ASS(course add bor)")
hit(ass, f"/courses/{c1.pk}/?tab=set", "ASS")
r = ass.post(f"/courses/{c1.pk}/delete/")
assert CourseModel.objects.filter(pk=c1.pk).exists(), "yordamchi kursni o'chira olmasligi kerak"
hit(ass, "/staff/messages/", "ASS(notify yo'q)", ok=(302,))
hit(ass, "/security/", "ASS(security yo'q)", ok=(302,))
nav = ass.get("/dashboard/").content.decode()
assert 'href="/staff/messages/"' not in nav and 'href="/security/"' not in nav, "ruxsatsiz bo'lim menyuda ko'rinmasligi kerak"
assert AuditLogModel.objects.filter(actor=ass_u, result="denied").exists(), "ruxsatsiz urinish jurnalga yozilishi kerak"

# --- talaba: statistikada boshqalar yo'q, tugagan testlar yo'q
stu = login("ali", "Talaba#2026")
s = stu.get("/stats/").content.decode()
assert "Foydalanuvchilar" not in s and "Eng faol talabalar" not in s and "Mening statistikam" in s, "talaba faqat o'z statistikasini ko'rishi kerak"
for p in ["/stats/?tab=tests", "/stats/?tab=tasks", "/stats/?tab=courses", "/tests/", f"/courses/{c1.pk}/", f"/courses/{c1.pk}/?tab=about"]:
    hit(stu, p, "STU")
fin = TestModel.objects.filter(end_at__isnull=False).order_by("end_at").first()
from django.utils import timezone
old_end, old_start = fin.end_at, fin.start_at
fin.start_at, fin.end_at = timezone.now() - timezone.timedelta(days=3), timezone.now() - timezone.timedelta(days=1)
fin.save()
tl = stu.get("/tests/?mode=table").content.decode()
assert fin.title not in tl, "tugagan test talabaga ko'rinmasligi kerak"
assert stu.get(f"/tests/{fin.pk}/").status_code == 302
assert fin.title in main.get("/tests/?mode=table&ps=50").content.decode(), "tugagan test asosiy o'qituvchiga ko'rinishi kerak"
fin.start_at, fin.end_at = old_start, old_end
fin.save()
hit(stu, "/staff/users/", "STU", ok=(302,))
assert 'data-protect="1"' in stu.get("/dashboard/").content.decode(), "talabada himoya yoqilgan bo'lishi kerak"
assert 'data-protect' not in main.get("/dashboard/").content.decode(), "asosiy o'qituvchida himoya bo'lmaydi"

# --- talabadan statistikani yashirish
main.post(f"/staff/users/{stu_u.pk}/perm/", json.dumps({"code": "stats", "action": "view", "on": 0}), content_type="application/json", HTTP_X_REQUESTED_WITH="fetch")
hit(stu, "/stats/", "STU(stats yashirilgan)", ok=(302,))
main.post(f"/staff/users/{stu_u.pk}/perm/", json.dumps({"reset": 1}), content_type="application/json", HTTP_X_REQUESTED_WITH="fetch")
hit(stu, "/stats/", "STU(qaytarildi)")

# --- skrinshot hodisasi
n0 = SecurityIncidentModel.objects.count()
r = stu.post("/security/incident/", json.dumps({"kind": "printscreen", "url": f"/courses/{c1.pk}/", "title": c1.title, "content": "Video: test"}),
             content_type="application/json", HTTP_X_REQUESTED_WITH="fetch")
assert r.json()["ok"] and SecurityIncidentModel.objects.count() == n0 + 1, r.content
inc = SecurityIncidentModel.objects.first()
hit(main, f"/security/{inc.pk}/", "MAIN")
main.post(f"/security/{inc.pk}/review/", {"act": "review", "note": "sinov"})
inc.refresh_from_db()
assert inc.reviewed
log = AuditLogModel.objects.first()
hit(main, f"/staff/logs/{log.pk}/", "MAIN")
hit(main, "/staff/logs/?f_res=Ruxsat yo‘q", "MAIN")

# yordamchi ruxsatlarini rol standartiga qaytarish
main.post(f"/staff/users/{ass_u.pk}/perm/", json.dumps({"reset": 1}), content_type="application/json", HTTP_X_REQUESTED_WITH="fetch")
print("\n".join(BAD) if BAD else "HAMMASI OK")

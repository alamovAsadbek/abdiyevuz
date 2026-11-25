"""Ruxsatlar, «Saytda ko'rinsin», rolga mos statistika va kurs sahifasi testlari.

Ishga tushirish:  python manage.py test apps.accounts
"""
from django.test import Client, TestCase
from django.urls import reverse

from apps.core import jwt_auth as J
from apps.courses.models import CourseModel, LessonModel
from .models import GroupModel, UserModel


def client_for(user):
    c = Client()
    c.cookies[J.ACCESS_COOKIE] = J.make_access(user)
    return c


class BaseCase(TestCase):
    def setUp(self):
        self.main = UserModel.objects.create_user("bosh", password="Xx#12345678", full_name="Bosh O‘qituvchi", role="main")
        self.ass = UserModel.objects.create_user("yord", password="Xx#12345678", full_name="Yordamchi Ustoz", role="assistant")
        self.stu = UserModel.objects.create_user("tal", password="Xx#12345678", full_name="Ali Talaba")
        self.stu2 = UserModel.objects.create_user("tal2", password="Xx#12345678", full_name="Vali Talaba")
        self.grp = GroupModel.objects.create(name="A guruh")
        self.grp.members.add(self.stu, self.stu2)
        self.grp.assistants.add(self.ass)
        self.course = CourseModel.objects.create(title="Kimyo asoslari", description="Kurs haqida batafsil tavsif")
        self.lesson = LessonModel.objects.create(module=self.course.first_module(), title="1-dars")

    def refresh(self, u):
        u.refresh_from_db()
        u._grants_cache = None
        return u


class PermissionTests(BaseCase):
    def test_defaults_view_only(self):
        self.assertTrue(self.ass.can_view("courses"))
        self.assertFalse(self.ass.can("courses", "add"))
        self.assertFalse(self.ass.can("users", "view"))
        self.assertTrue(self.stu.can_view("tests"))
        self.assertFalse(self.stu.can("tests", "add"))
        self.assertTrue(self.main.can("anything", "delete"))

    def test_assistant_crud_follows_grants(self):
        c = client_for(self.ass)
        self.assertEqual(c.get(reverse("course_new")).status_code, 302)  # ruxsat yo'q — qaytariladi
        self.ass.set_grants({"courses": ["add"]})
        self.ass.save()
        self.assertEqual(c.get(reverse("course_new")).status_code, 200)
        r = c.post(reverse("course_new"), {"title": "Yangi kurs", "is_modular": "0"})
        self.assertEqual(r.status_code, 302)
        new = CourseModel.objects.get(title="Yangi kurs")
        # tahrirlash / o'chirish berilmagan
        c.post(reverse("course_settings", args=[new.pk]), {"title": "O‘zgardi"})
        new.refresh_from_db()
        self.assertEqual(new.title, "Yangi kurs")
        c.post(reverse("course_delete", args=[new.pk]))
        self.assertTrue(CourseModel.objects.filter(pk=new.pk).exists())
        # endi tahrirlash va o'chirish beriladi
        self.ass.set_grants({"courses": ["view", "add", "edit", "delete"]})
        self.ass.save()
        c.post(reverse("course_settings", args=[new.pk]), {"title": "O‘zgardi"})
        new.refresh_from_db()
        self.assertEqual(new.title, "O‘zgardi")
        c.post(reverse("course_delete", args=[new.pk]))
        self.assertFalse(CourseModel.objects.filter(pk=new.pk).exists())

    def test_lesson_crud_by_action(self):
        c = client_for(self.ass)
        self.ass.set_grants({"courses": ["view", "add"]})
        self.ass.save()
        self.assertEqual(c.get(reverse("lesson_new", args=[self.lesson.module_id])).status_code, 200)
        self.assertEqual(c.get(reverse("lesson_edit", args=[self.lesson.pk])).status_code, 302)
        c.post(reverse("lesson_delete", args=[self.lesson.pk]))
        self.assertTrue(LessonModel.objects.filter(pk=self.lesson.pk).exists())

    def test_assistant_users_section(self):
        c = client_for(self.ass)
        self.assertEqual(c.get(reverse("users")).status_code, 302)
        self.ass.set_grants({"users": ["view"]})
        self.ass.save()
        r = c.get(reverse("users"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ali Talaba")
        # faqat ko'rish — o'chira olmaydi
        c.post(reverse("user_delete", args=[self.stu.pk]))
        self.assertTrue(UserModel.objects.filter(pk=self.stu.pk).exists())
        self.ass.set_grants({"users": ["view", "delete"]})
        self.ass.save()
        c.post(reverse("user_delete", args=[self.stu.pk]))
        self.assertFalse(UserModel.objects.filter(pk=self.stu.pk).exists())

    def test_student_hidden_section(self):
        c = client_for(self.stu)
        self.assertEqual(c.get(reverse("tests")).status_code, 200)
        self.stu.set_grants({"courses": ["view"], "stats": ["view"]})
        self.stu.save()
        self.assertEqual(c.get(reverse("tests")).status_code, 302)
        r = c.get(reverse("dashboard"))
        self.assertNotContains(r, 'href="/tests/"')
        # talabaga yozish amali berilmaydi (rolga mos)
        self.stu.set_grants({"tests": ["view", "add", "delete"]})
        self.assertEqual(self.stu.grants, {"tests": ["view"]})

    def test_main_grants_any_user_via_form(self):
        c = client_for(self.main)
        r = c.get(reverse("user_detail", args=[self.stu.pk]) + "?tab=perm")
        self.assertContains(r, "Talaba ruxsatlari")
        c.post(reverse("user_perm", args=[self.ass.pk]), {"p.tests": ["add", "edit"], "p.users": ["view"]})
        a = self.refresh(self.ass)
        self.assertEqual(a.grants["tests"], ["view", "add", "edit"])
        self.assertTrue(a.can("tests", "edit"))
        self.assertFalse(a.can("tests", "delete"))
        self.assertTrue(a.has_custom_grants)
        c.post(reverse("user_perm", args=[self.ass.pk]), {"reset": "1"})
        a = self.refresh(self.ass)
        self.assertFalse(a.has_custom_grants)
        self.assertFalse(a.can("tests", "edit"))

    def test_non_main_cannot_grant(self):
        self.ass.set_grants({"users": ["view", "add", "edit", "delete"]})
        self.ass.save()
        c = client_for(self.ass)
        c.post(reverse("user_perm", args=[self.stu.pk]), {"p.tests": ["view"]})
        self.assertFalse(self.refresh(self.stu).has_custom_grants)

    def test_role_defaults(self):
        c = client_for(self.main)
        c.post(reverse("role_perms"), {"role": "assistant", "p.guides": ["view", "add"]})
        a = self.refresh(self.ass)
        self.assertTrue(a.can("guides", "add"))
        self.assertFalse(a.can_view("courses"))
        self.assertEqual(c.get(reverse("settings")).status_code, 200)

    def test_legacy_list_perms(self):
        self.ass.perms = ["courses"]
        self.ass.save()
        a = self.refresh(self.ass)
        self.assertTrue(a.can("courses", "delete"))
        self.assertTrue(a.can("tasks", "edit"))


class VisibilityTests(BaseCase):
    def test_hidden_user_not_on_site(self):
        self.stu2.show_on_site = False
        self.stu2.save()
        c = client_for(self.main)
        self.assertNotContains(c.get(reverse("users")), "Vali Talaba")
        self.assertEqual(c.get(reverse("user_detail", args=[self.stu2.pk])).status_code, 404)
        self.assertNotContains(c.get(reverse("group_detail", args=[self.grp.pk]) + "?tab=mem"), "Vali Talaba")
        self.assertNotContains(c.get(reverse("stats") + "?tab=usr"), "Vali Talaba")
        self.assertContains(c.get(reverse("users")), "Ali Talaba")

    def test_hidden_user_in_admin(self):
        self.stu2.show_on_site = False
        self.stu2.save()
        c = client_for(self.main)
        r = c.get("/admin/accounts/usermodel/")
        self.assertContains(r, "tal2")


class StatsTests(BaseCase):
    def test_student_sees_only_own_stats(self):
        c = client_for(self.stu)
        r = c.get(reverse("stats"))
        self.assertContains(r, "Mening statistikam")
        self.assertNotContains(r, "Jami foydalanuvchilar")
        self.assertNotContains(r, "Eng faol talabalar")
        self.assertNotContains(r, "Vali Talaba")
        r = c.get(reverse("stats") + "?tab=usr")  # talabada bunday tab yo'q -> umumiy
        self.assertContains(r, "Mening ballim")
        for t in ("tst", "tsk"):
            self.assertEqual(c.get(reverse("stats") + "?tab=" + t).status_code, 200)

    def test_assistant_sees_own_students(self):
        other = UserModel.objects.create_user("begona", password="Xx#12345678", full_name="Begona Talaba")
        c = client_for(self.ass)
        r = c.get(reverse("stats") + "?tab=usr")
        self.assertContains(r, "Ali Talaba")
        self.assertNotContains(r, "Begona Talaba")
        self.assertNotContains(r, "Bosh O‘qituvchi")
        r = c.get(reverse("stats"))
        self.assertContains(r, "Talabalarim statistikasi")
        self.assertNotContains(r, "Jami foydalanuvchilar")

    def test_main_site_stats(self):
        c = client_for(self.main)
        r = c.get(reverse("stats"))
        self.assertContains(r, "Sayt statistikasi")
        self.assertContains(r, "Jami foydalanuvchilar")
        for t in ("usr", "tst", "tsk"):
            self.assertEqual(c.get(reverse("stats") + "?tab=" + t).status_code, 200)


class CoursePageTests(BaseCase):
    def test_course_detail_full_info(self):
        for u in (None, self.stu, self.ass, self.main):
            c = client_for(u) if u else Client()
            for tab in ("", "?tab=about"):
                r = c.get(reverse("course_detail", args=[self.course.pk]) + tab)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, "Kimyo asoslari")
                self.assertContains(r, "data-tip=")
        r = client_for(self.main).get(reverse("course_detail", args=[self.course.pk]) + "?tab=about")
        self.assertContains(r, "Kurs haqida batafsil tavsif")
        self.assertContains(r, "Darslar tartibi")
        r = client_for(self.main).get(reverse("course_detail", args=[self.course.pk]) + "?tab=set")
        self.assertContains(r, "Kurs sozlamalari")
        # yordamchi (faqat ko'rish) — sozlamalar tabi yo'q
        r = client_for(self.ass).get(reverse("course_detail", args=[self.course.pk]) + "?tab=set")
        self.assertNotContains(r, "Kurs sozlamalari")

    def test_modular_course(self):
        from apps.courses.models import ModuleModel
        mc = CourseModel.objects.create(title="Modulli kurs", is_modular=True)
        m = ModuleModel.objects.create(course=mc, title="1-modul", description="Modul tavsifi", price=50000)
        LessonModel.objects.create(module=m, title="M dars")
        for u in (self.stu, self.main):
            c = client_for(u)
            r = c.get(reverse("course_detail", args=[mc.pk]))
            self.assertContains(r, "1-modul")
            self.assertEqual(c.get(reverse("module_detail", args=[m.pk])).status_code, 200)


class LessonViewsVisibilityTests(BaseCase):
    """Ko'rishlar soni: kurs sozlamasi + «Ko'rishlar soni» ruxsati."""

    def url(self, tab=""):
        return reverse("lesson_detail", args=[self.lesson.pk]) + (f"?tab={tab}" if tab else "")

    def test_main_always_sees(self):
        self.course.show_views = False
        self.course.save()
        r = client_for(self.main).get(self.url())
        self.assertContains(r, "marta ko‘rilgan")
        r = client_for(self.main).get(self.url("stu"))
        self.assertContains(r, "Necha marta")

    def test_student_by_course_setting_and_permission(self):
        c = client_for(self.stu)
        c.get(self.url())
        self.assertContains(c.get(self.url()), "marta ko‘rdingiz")   # ikkinchi ochilish — 2 marta
        self.course.show_views = False
        self.course.save()
        self.assertNotContains(c.get(self.url()), "marta ko‘rdingiz")
        self.course.show_views = True
        self.course.save()
        self.stu.set_grants({"courses": ["view"]})   # «Ko'rishlar soni» berilmagan
        self.stu.save()
        r = c.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "marta ko‘r")

    def test_assistant_needs_permission(self):
        c = client_for(self.ass)
        self.assertContains(c.get(self.url("stu")), "Necha marta")   # standart — ruxsat bor
        self.ass.set_grants({"courses": ["view"]})
        self.ass.save()
        r = c.get(self.url("stu"))
        self.assertNotContains(r, "Necha marta")
        self.assertContains(r, "«Ko‘rishlar soni» ruxsati yo‘q")
        self.assertNotContains(c.get(self.url()), "marta ko‘rilgan")

    def test_course_setting_saved(self):
        c = client_for(self.main)
        c.post(reverse("course_settings", args=[self.course.pk]), {"title": "Kimyo asoslari", "sequential": "1"})
        self.course.refresh_from_db()
        self.assertFalse(self.course.show_views)
        c.post(reverse("course_settings", args=[self.course.pk]), {"title": "Kimyo asoslari", "show_views": "1"})
        self.course.refresh_from_db()
        self.assertTrue(self.course.show_views)

    def test_lesson_page_layout(self):
        LessonModel.objects.create(module=self.lesson.module, title="2-dars")
        r = client_for(self.stu).get(self.url())
        self.assertContains(r, 'class="lsn"')
        self.assertContains(r, "2-dars")   # yon paneldagi darslar ro'yxati


class TemplateSyntaxTests(TestCase):
    """Django teglari ({% %}, {{ }}) bir qatorda bo'lishi shart — aks holda sahifada matn bo'lib chiqadi.
    (IDE «Reformat code» teglarni bir necha qatorga bo'lib yuborishi mumkin.)"""

    def test_no_multiline_tags(self):
        import re
        from pathlib import Path
        from django.conf import settings
        pat = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.S)
        bad = []
        for root in [Path(d) for d in settings.TEMPLATES[0]["DIRS"]] + list(Path(settings.BASE_DIR, "apps").glob("*/templates")):
            for f in Path(root).rglob("*.html"):
                for m in pat.finditer(f.read_text(encoding="utf-8")):
                    if "\n" in m.group(0):
                        bad.append(f"{f.name}: {m.group(0)[:60]!r}")
        self.assertEqual(bad, [], "Ko'p qatorli teglar:\n" + "\n".join(bad))

    def test_pages_render_without_raw_tags(self):
        main = UserModel.objects.create_user("bosh", password="Xx#12345678", full_name="Bosh", role="main")
        stu = UserModel.objects.create_user("tal", password="Xx#12345678", full_name="Tal")
        c = Client()
        for url in ("/login/", "/"):
            r = c.get(url)
            self.assertNotIn(b"{%", r.content, url)
        for u, urls in ((main, ["users", "settings", "stats", "meetings", "meeting_new", "courses", "course_new"]),
                        (stu, ["dashboard", "stats", "meetings", "courses"])):
            cl = client_for(u)
            for name in urls:
                r = cl.get(reverse(name))
                self.assertEqual(r.status_code, 200, name)
                self.assertNotIn(b"{%", r.content, name)
                self.assertNotIn(b"{{", r.content, name)
        for tab in ("info", "perm", "kurs"):
            r = client_for(main).get(reverse("user_detail", args=[stu.pk]) + "?tab=" + tab)
            self.assertEqual(r.status_code, 200, tab)
            self.assertNotIn(b"{%", r.content, tab)

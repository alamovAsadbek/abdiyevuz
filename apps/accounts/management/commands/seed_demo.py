"""Demo ma'lumotlar: python manage.py seed_demo  (qayta ishga tushirsa — avval tozalaydi: --reset)"""
from datetime import timedelta

import pymupdf
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

import io
from PIL import Image
from apps.accounts.models import GroupModel, UserModel
from apps.core.models import ArticleModel, SiteSettingsModel
from apps.courses.models import (CourseAccessModel, CourseModel, LessonMaterialModel, LessonModel, LessonProgressModel,
                                 ModuleModel, SubmissionModel, TaskModel)
from apps.courses.views import ensure_builtin
from apps.exams.models import AttemptModel, QuestionModel, TestModel
from apps.notifications.models import MessageModel
from apps.notifications.services import deliver, notify

MAIN_PW, ASS_PW, ST_PW = "Admin#2026", "Yordam#2026", "Talaba#2026"


def pdf(title, lines):
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((60, 80), title, fontsize=22)
    for i, ln in enumerate(lines):
        p.insert_text((60, 130 + i * 26), ln, fontsize=13)
    return d.tobytes()


class Command(BaseCommand):
    help = "Demo ma'lumotlarni yuklaydi"

    def add_arguments(self, p):
        p.add_argument("--reset", action="store_true")

    def handle(self, *a, **o):
        if o["reset"]:
            for M in (MessageModel, TestModel, CourseModel, GroupModel, ArticleModel):
                M.objects.all().delete()
            UserModel.objects.filter(username__in=["abdiyev", "yordamchi", "ali", "nilufar", "jasur", "madina", "sardor"]).delete()
        if UserModel.objects.filter(username="abdiyev").exists():
            return self.stdout.write("Demo allaqachon mavjud (--reset bilan qayta yuklang)")
        now = timezone.now()
        main = UserModel.objects.create_user("abdiyev", password=MAIN_PW, full_name="Abdiyev Jasur", phone="+998 90 111 22 33", role="main")
        ass = UserModel.objects.create_user("yordamchi", password=ASS_PW, full_name="Karimova Dilnoza", role="assistant",
                                            perms=["users", "tasks", "groups", "activity", "notify"])
        st = [UserModel.objects.create_user(u, password=ST_PW, full_name=n, phone=ph, points=pts) for u, n, ph, pts in [
            ("ali", "Valiyev Ali", "+998 90 123 45 67", 120), ("nilufar", "Karimova Nilufar", "+998 91 765 43 21", 240),
            ("jasur", "Toshmatov Jasur", "+998 93 555 11 22", 60), ("madina", "Rahimova Madina", "", 30), ("sardor", "Aliyev Sardor", "+998 99 888 77 66", 0)]]
        # ---- guruhlar
        g1 = GroupModel.objects.create(name="Kimyo-11 (ertalabki)", kind="online", description="Du-Chor-Juma 09:00")
        g2 = GroupModel.objects.create(name="Abituriyent-2026", kind="offline", description="Se-Pay-Sha 15:00")
        g1.members.set(st[:3]); g2.members.set(st[2:]); g1.assistants.add(ass); g2.assistants.add(ass)
        for g, titles in ((g1, ["Kirish darsi", "Atom tuzilishi", "Davriy qonun"]), (g2, ["Organik kimyo asoslari"])):
            m = g.course.first_module()
            for i, t in enumerate(titles):
                LessonModel.objects.create(module=m, title=t, order=i, video_kind="link", video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        # ---- kurslar
        c1 = CourseModel.objects.create(title="Kimyo asoslari", description="Boshlang‘ich daraja uchun to‘liq kurs", is_modular=True)
        for i, (t, pr, ls) in enumerate([("Umumiy kimyo", 0, ["Moddalar va ularning xossalari", "Atom va molekula"]),
                                         ("Anorganik kimyo", 99000, ["Oksidlar", "Kislotalar", "Asoslar va tuzlar"]),
                                         ("Organik kimyo", 149000, ["Alkanlar", "Alkenlar"])]):
            m = ModuleModel.objects.create(course=c1, title=t, price=pr, order=i)
            for j, lt in enumerate(ls):
                LessonModel.objects.create(module=m, title=lt, order=j, video_kind="link", video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        c2 = CourseModel.objects.create(title="Test yechish strategiyalari", description="Bepul kirish kursi", price=0)
        m2 = c2.first_module()
        for j, lt in enumerate(["Test turlari", "Vaqtni boshqarish"]):
            LessonModel.objects.create(module=m2, title=lt, order=j, video_kind="link", video_url="https://vimeo.com/76979871")
        c3 = CourseModel.objects.create(title="Organik kimyo: reaksiyalar", description="Pullik kurs", price=199000)
        LessonModel.objects.create(module=c3.first_module(), title="Reaksiya mexanizmlari", video_kind="none")
        CourseAccessModel.objects.create(user=st[0], course=c1, module=c1.modules.all()[1], granted_by=main)
        CourseAccessModel.objects.create(user=st[1], course=c1, granted_by=main)
        # ---- dars materiallari va vazifalar
        l1 = c1.modules.first().lessons.first()
        LessonMaterialModel(lesson=l1, title="Mavzu konspekti (PDF)", kind="file", filename="konspekt.pdf").file.save("konspekt.pdf", ContentFile(pdf("Moddalar va ularning xossalari", ["Modda — materiya ko‘rinishi.", "Fizik va kimyoviy xossalar.", "Demo hujjat."])))
        LessonMaterialModel.objects.create(lesson=l1, title="Qo‘shimcha o‘qish", kind="link", url="https://uz.wikipedia.org/wiki/Kimyo")
        t1 = TaskModel.objects.create(lesson=l1, title="1-mashq: moddalar tasnifi", description="Berilgan moddalarni sinflarga ajrating.", max_score=10, deadline=now + timedelta(days=5))
        l2 = l1.module.lessons.all()[1]
        t2 = TaskModel.objects.create(lesson=l2, title="2-mashq: atom tuzilishi", description="Elektron formulalarni yozing.", max_score=20, deadline=now - timedelta(days=1), is_closed=True)
        for s in st[:2]:
            LessonProgressModel.objects.create(user=s, lesson=l1)
        sub = SubmissionModel(task=t1, student=st[0], filename="mashq1.pdf")
        sub.file.save("mashq1.pdf", ContentFile(pdf("Ali — 1-mashq", ["Javoblar: 1) oksid  2) kislota"])), save=False); sub.save()
        sub2 = SubmissionModel(task=t2, student=st[1], filename="mashq2.pdf", status="accepted", score=18, points_given=18, reviewer=main, graded_at=now, comment="Yaxshi!")
        sub2.file.save("mashq2.pdf", ContentFile(pdf("Nilufar — 2-mashq", ["1s2 2s2 2p6 ..."])), save=False); sub2.save()
        # ---- testlar
        t = TestModel.objects.create(title="Oksidlar", mode="manual", start_at=now - timedelta(hours=1), end_at=now + timedelta(days=30), allow_retake=True, max_attempts=3, created_by=main)
        for i, (q, opts, c, sol) in enumerate([
            ("Quyidagilardan qaysi biri asosli oksid?", ["CO<sub>2</sub>", "Na<sub>2</sub>O", "SO<sub>3</sub>", "P<sub>2</sub>O<sub>5</sub>"], 1, "Na<sub>2</sub>O — metall oksidi, asosli."),
            ("Suvda eriganda kislota hosil qiluvchi oksid?", ["CaO", "K<sub>2</sub>O", "SO<sub>3</sub>", "MgO"], 2, "SO<sub>3</sub> + H<sub>2</sub>O → H<sub>2</sub>SO<sub>4</sub>"),
            ("Amfoter oksidni toping.", ["ZnO", "Na<sub>2</sub>O", "CO<sub>2</sub>", "BaO"], 0, "ZnO — amfoter.")]):
            QuestionModel.objects.create(test=t, order=i, text=q, options=opts, correct=c, solution=sol)
        tf = TestModel(title="Kimyo — fayl asosida test", mode="file", start_at=now - timedelta(hours=2), end_at=now + timedelta(days=10), file_name="test.pdf", created_by=main)
        tf.file.save("test.pdf", ContentFile(pdf("Test savollari", ["1. Eng yengil element?  A) H  B) He  C) Li  D) Be", "2. Suv formulasi?  A) H2O  B) CO2  C) NaCl  D) O2"])), save=False); tf.save()
        for i, c in enumerate([0, 0]):
            QuestionModel.objects.create(test=tf, order=i, options=list("ABCD"), correct=c)
        TestModel.objects.create(title="Kislotalar (kutilmoqda)", start_at=now + timedelta(hours=3), end_at=now + timedelta(days=2), price=25000, created_by=main).status = "waiting"
        old = TestModel.objects.create(title="Davriy jadval (tugagan)", start_at=now - timedelta(days=5), end_at=now - timedelta(days=1), created_by=main)
        QuestionModel.objects.create(test=old, order=0, text="Davriy qonun muallifi?", options=["Mendeleyev", "Lomonosov", "Bor", "Dalton"], correct=0)
        for s, sc in ((st[0], 2), (st[1], 3), (st[2], 1)):
            AttemptModel.objects.create(test=t, user=s, answers=[1, 2, 0][:sc] + [-1] * (3 - sc), score=sc, total=3, created=now - timedelta(hours=sc))
        for tt in TestModel.objects.all():
            TestModel.objects.filter(pk=tt.pk).update(status=tt.compute_status())
        ensure_builtin()
        SiteSettingsModel.get()
        for i, (t_, sm, body) in enumerate([
            ("Kimyo olimpiadasiga tayyorgarlik: 5 ta maslahat", "Olimpiada masalalarini tez va to‘g‘ri yechish usullari", "<p>Olimpiadaga tayyorlanishda eng muhimi — muntazamlik. Har kuni 3 ta masala yeching, xatolaringizni daftarga yozib boring.</p><p>Davriy jadval va eruvchanlik jadvalini yoddan bilish vaqtni tejaydi.</p>"),
            ("Yangi o‘quv yili: dars jadvali e’lon qilindi", "Guruhlar bo‘yicha dars kunlari va vaqtlari", "<p>Hurmatli talabalar! Yangi o‘quv yili dars jadvali guruhlar sahifasida e’lon qilindi.</p>"),
            ("Mol tushunchasi — oddiy tilda", "Mol, molyar massa va Avogadro soni", "<p>1 mol modda tarkibida <b>6,02·10<sup>23</sup></b> ta zarracha bor. Masalan, 1 mol suv 18 g.</p>")]):
            img = Image.new("RGB", (1200, 600), [(107, 91, 210), (46, 182, 124), (244, 160, 77)][i])
            for y in range(600):
                for x in range(0, 1200, 40):
                    pass
            b = io.BytesIO(); img.save(b, "JPEG", quality=80)
            a = ArticleModel.objects.create(title=t_, summary=sm, body=body, author=main, views=10 * (i + 1))
            a.cover.save("c.jpg", ContentFile(b.getvalue()))
        # ---- uchrashuvlar (meeting)
        from apps.meetings.models import MeetingMemberModel, MeetingModel
        ass_u = UserModel.objects.get(username="yordamchi")
        m1 = MeetingModel.objects.create(title="Kimyo: jonli savol-javob", description="Hamma qo‘shilishi mumkin. Savollaringizni chatga yozing, @username bilan belgilang.", kind="public", host=main, status="live", started_at=now)
        MeetingMemberModel.objects.create(meeting=m1, user=main, invited=True)
        MeetingMemberModel.objects.create(meeting=m1, user=ass_u, role="cohost", invited=True, mperms=["kick", "mute", "comments", "invite"])
        m2 = MeetingModel.objects.create(title="Yopiq dars: organik kimyo", description="Faqat taklif qilinganlar uchun", kind="private", host=main, start_at=now + timedelta(days=1), status="scheduled")
        MeetingMemberModel.objects.create(meeting=m2, user=main, invited=True)
        for s_ in st[:3]:
            MeetingMemberModel.objects.create(meeting=m2, user=s_, invited=True)
        # ---- xabarnoma
        msg = MessageModel.objects.create(title="Yangi o‘quv yili boshlandi", short="Dars jadvali bilan tanishing", body="<p>Hurmatli talabalar, yangi o‘quv yili muborak! Dars jadvali guruhlar sahifasida.</p>",
                                          audience="students", channel="app", important=True, author=main)
        deliver(msg, st)
        notify(st, "Xush kelibsiz! Demo hisobingiz tayyor", "/dashboard/")
        self.stdout.write(self.style.SUCCESS(
            f"Tayyor!\n  Asosiy o‘qituvchi: abdiyev / {MAIN_PW}\n  Yordamchi:        yordamchi / {ASS_PW}\n  Talabalar:        ali, nilufar, jasur, madina, sardor / {ST_PW}"))

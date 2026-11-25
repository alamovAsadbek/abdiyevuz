from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.storage import (get_private_storage, guidefile_path, material_path, submission_path,
                               taskfile_path, video_src_path)

U = settings.AUTH_USER_MODEL


class CourseModel(models.Model):
    title = models.CharField("Kurs nomi", max_length=160)
    description = models.TextField("Tavsif", blank=True)
    is_modular = models.BooleanField("Modulli kurs", default=False)
    price = models.PositiveIntegerField("Narxi (modulsiz kurs)", default=0)
    sequential = models.BooleanField("Ketma-ket ko‘rish", default=True)
    is_active = models.BooleanField("Aktiv", default=True)
    login_required = models.BooleanField("Ko‘rish uchun kirish majburiy", default=False)
    show_views = models.BooleanField("Ko‘rishlar sonini ko‘rsatish", default=True,
                                     help_text="O‘chirilsa — darslar necha marta ko‘rilgani va kim ko‘rgani/ko‘rmagani faqat asosiy o‘qituvchiga ko‘rinadi. "
                                               "Yoqilsa — «Ko‘rishlar soni» ruxsati berilgan foydalanuvchilarga ham ko‘rinadi.")
    group = models.OneToOneField("accounts.GroupModel", null=True, blank=True, on_delete=models.CASCADE, related_name="course")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Kurs"
        verbose_name_plural = "Kurslar"

    def __str__(self):
        return self.title

    @property
    def is_hidden(self):
        return self.group_id is not None

    @property
    def is_paid(self):
        return self.modules.filter(price__gt=0).exists() if self.is_modular else self.price > 0

    def min_price(self):
        if self.is_modular:
            p = self.modules.filter(price__gt=0).order_by("price").values_list("price", flat=True).first()
            return p or 0
        return self.price

    @property
    def lesson_count(self):
        return LessonModel.objects.filter(module__course=self).count()

    def first_module(self):
        m = self.modules.first()
        if not m:
            m = ModuleModel.objects.create(course=self, title="Darslar")
        return m


class ModuleModel(models.Model):
    course = models.ForeignKey(CourseModel, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField("Modul nomi", max_length=160)
    description = models.TextField("Tavsif", blank=True)
    price = models.PositiveIntegerField("Narxi", default=0)
    is_active = models.BooleanField("Aktiv", default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Modul"
        verbose_name_plural = "Modullar"

    def __str__(self):
        return f"{self.course.title} · {self.title}"


class LessonModel(models.Model):
    NONE, LINK, IFRAME, FILE = "none", "link", "iframe", "file"
    KINDS = [(NONE, "Yo‘q"), (LINK, "Havola"), (IFRAME, "Iframe"), (FILE, "Video fayl")]
    HLS = [("none", "—"), ("processing", "Qayta ishlanmoqda"), ("ready", "Tayyor"), ("failed", "Xatolik")]
    module = models.ForeignKey(ModuleModel, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField("Dars nomi", max_length=200)
    description = models.TextField("Tavsif", blank=True)
    order = models.PositiveIntegerField(default=0)
    video_kind = models.CharField(max_length=10, choices=KINDS, default=NONE)
    video_url = models.URLField(max_length=500, blank=True)
    video_src = models.FileField(upload_to=video_src_path, storage=get_private_storage, null=True, blank=True)
    video_name = models.CharField(max_length=200, blank=True)
    hls_status = models.CharField(max_length=12, choices=HLS, default="none")
    hls_error = models.CharField(max_length=300, blank=True)
    duration = models.PositiveIntegerField(default=0)
    size_before = models.BigIntegerField(default=0)
    size_after = models.BigIntegerField(default=0)
    views = models.PositiveIntegerField("Jami ko‘rishlar", default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Dars"
        verbose_name_plural = "Darslar"

    def __str__(self):
        return self.title

    @property
    def course(self):
        return self.module.course

    def siblings(self):
        return list(self.module.lessons.all())

    def index(self):
        ids = [l.pk for l in self.siblings()]
        return ids.index(self.pk) if self.pk in ids else 0


class LessonMaterialModel(models.Model):
    lesson = models.ForeignKey(LessonModel, on_delete=models.CASCADE, related_name="materials")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=5, choices=[("link", "Havola"), ("file", "Fayl")], default="link")
    url = models.URLField(max_length=500, blank=True)
    file = models.FileField(upload_to=material_path, storage=get_private_storage, null=True, blank=True)
    filename = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Dars qo‘llanmasi"
        verbose_name_plural = "Dars qo‘llanmalari"


class TaskModel(models.Model):
    lesson = models.ForeignKey(LessonModel, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField("Vazifa nomi", max_length=200)
    description = models.TextField("Tavsif", blank=True)
    max_score = models.PositiveIntegerField("Eng yuqori ball", default=10)
    deadline = models.DateTimeField("Topshirish muddati", null=True, blank=True)
    is_active = models.BooleanField("Aktiv", default=True)
    is_closed = models.BooleanField("Muddat tugagan (avtomatik)", default=False, db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Vazifa"
        verbose_name_plural = "Vazifalar"

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        """Backend har doim vaqtni o'zi tekshiradi (scheduler kechiksa ham yuklash yopiq bo'ladi)."""
        return self.is_active and not (self.deadline and self.deadline <= timezone.now())

    @property
    def blocks_next(self):
        """Faqat ochiq vazifa keyingi darsni bloklaydi. Muddat tugagan vazifa bloklamaydi."""
        return self.is_open


class TaskFileModel(models.Model):
    task = models.ForeignKey(TaskModel, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=taskfile_path, storage=get_private_storage)
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Vazifa fayli"
        verbose_name_plural = "Vazifa fayllari"


class SubmissionModel(models.Model):
    PENDING, ACCEPTED, RETURNED = "pending", "accepted", "returned"
    STATUS = [(PENDING, "Tekshirilmoqda"), (ACCEPTED, "Qabul qilindi"), (RETURNED, "Qayta topshiring")]
    task = models.ForeignKey(TaskModel, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(U, on_delete=models.CASCADE, related_name="submissions")
    file = models.FileField(upload_to=submission_path, storage=get_private_storage)
    filename = models.CharField(max_length=200)
    submitted_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS, default=PENDING, db_index=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed")
    points_given = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("task", "student")]
        verbose_name = "Topshirilgan vazifa"
        verbose_name_plural = "Topshirilgan vazifalar"


class LessonProgressModel(models.Model):
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="progress")
    lesson = models.ForeignKey(LessonModel, on_delete=models.CASCADE, related_name="progress")
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)
    views = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [("user", "lesson")]
        verbose_name = "Dars ko‘rilishi"
        verbose_name_plural = "Dars ko‘rilishlari"


class CourseAccessModel(models.Model):
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="accesses")
    course = models.ForeignKey(CourseModel, on_delete=models.CASCADE, related_name="accesses")
    module = models.ForeignKey(ModuleModel, null=True, blank=True, on_delete=models.CASCADE, related_name="accesses")
    source = models.CharField(max_length=10, choices=[("gift", "Ochib berilgan"), ("purchase", "Sotib olingan")], default="gift")
    granted_by = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "course", "module")]
        verbose_name = "Kursga kirish huquqi"
        verbose_name_plural = "Kursga kirish huquqlari"


class PurchaseRequestModel(models.Model):
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="purchase_requests")
    course = models.ForeignKey(CourseModel, null=True, blank=True, on_delete=models.CASCADE)
    module = models.ForeignKey(ModuleModel, null=True, blank=True, on_delete=models.CASCADE)
    test = models.ForeignKey("exams.TestModel", null=True, blank=True, on_delete=models.CASCADE)
    done = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Sotib olish so‘rovi"
        verbose_name_plural = "Sotib olish so‘rovlari"


class GuideModel(models.Model):
    CATS = ["Jadval", "Formula", "Amaliy", "Boshqa"]
    title = models.CharField("Sarlavha", max_length=200)
    category = models.CharField("Kategoriya", max_length=20, default="Amaliy")
    body = models.TextField("Matn (HTML)", blank=True)
    builtin_key = models.CharField(max_length=10, blank=True, db_index=True)
    summary = models.CharField(max_length=200, blank=True)
    author = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField("Aktiv", default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Qo‘llanma"
        verbose_name_plural = "Qo‘llanmalar"

    def __str__(self):
        return self.title


class GuideFileModel(models.Model):
    guide = models.ForeignKey(GuideModel, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=guidefile_path, storage=get_private_storage)
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Qo‘llanma fayli"
        verbose_name_plural = "Qo‘llanma fayllari"

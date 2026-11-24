from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.storage import get_private_storage, solution_path, testfile_path

U = settings.AUTH_USER_MODEL


class TestModel(models.Model):
    MANUAL, FILE = "manual", "file"
    WAITING, ACTIVE, FINISHED, INACTIVE = "waiting", "active", "finished", "inactive"
    STATUS = [(WAITING, "Kutilmoqda"), (ACTIVE, "Aktiv"), (FINISHED, "Tugagan"), (INACTIVE, "Noaktiv")]
    LABEL = {WAITING: ("Kutilmoqda", ""), ACTIVE: ("Aktiv", "f"), FINISHED: ("Tugagan", "x"), INACTIVE: ("Noaktiv", "x")}

    title = models.CharField("Test nomi", max_length=200)
    mode = models.CharField(max_length=6, choices=[(MANUAL, "Savollar saytda"), (FILE, "Test fayli + kalitlar")], default=MANUAL)
    start_at = models.DateTimeField("Boshlanish")
    end_at = models.DateTimeField("Tugash")
    price = models.PositiveIntegerField("Narxi", default=0)
    is_active = models.BooleanField("Aktiv", default=True)
    allow_retake = models.BooleanField("Qayta ishlashga ruxsat", default=False)
    max_attempts = models.PositiveIntegerField("Eng ko‘p urinish (0 = cheksiz)", default=0)
    allow_guest = models.BooleanField("Ro‘yxatdan o‘tmasdan ishlash mumkin", default=True)
    file = models.FileField(upload_to=testfile_path, storage=get_private_storage, null=True, blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=WAITING, db_index=True)
    created_by = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Test"
        verbose_name_plural = "Testlar"

    def __str__(self):
        return self.title

    def compute_status(self, now=None):
        now = now or timezone.now()
        if not self.is_active:
            return self.INACTIVE
        if self.end_at <= now:
            return self.FINISHED
        if self.start_at > now:
            return self.WAITING
        return self.ACTIVE

    @property
    def live_status(self):
        """Doim joriy vaqtga qarab hisoblanadi (scheduler kechiksa ham to'g'ri)."""
        return self.compute_status()

    @property
    def label(self):
        return self.LABEL[self.live_status]

    @property
    def is_paid(self):
        return self.price > 0


class QuestionModel(models.Model):
    test = models.ForeignKey(TestModel, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField(default=0)
    text = models.TextField(blank=True)
    options = models.JSONField(default=list)
    correct = models.PositiveSmallIntegerField(default=0)
    solution = models.TextField(blank=True)
    solution_image = models.FileField(upload_to=solution_path, storage=get_private_storage, null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"


class AttemptModel(models.Model):
    test = models.ForeignKey(TestModel, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="attempts")
    answers = models.JSONField(default=list)
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Test urinishi"
        verbose_name_plural = "Test urinishlari"

    @property
    def percent(self):
        return round(self.score / self.total * 100) if self.total else 0


class RetakeGrantModel(models.Model):
    test = models.ForeignKey(TestModel, on_delete=models.CASCADE, related_name="grants")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="retake_grants")
    used = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Qayta ishlash ruxsati"
        verbose_name_plural = "Qayta ishlash ruxsatlari"


class TestAccessModel(models.Model):
    test = models.ForeignKey(TestModel, on_delete=models.CASCADE, related_name="accesses")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="test_accesses")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("test", "user")]
        verbose_name = "Testga kirish huquqi"
        verbose_name_plural = "Testga kirish huquqlari"


class ErrorReportModel(models.Model):
    test = models.ForeignKey(TestModel, on_delete=models.CASCADE, related_name="reports")
    question_index = models.PositiveIntegerField(default=0)
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="reports")
    html = models.TextField()
    reviewed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Xato xabari"
        verbose_name_plural = "Xato xabarlari"

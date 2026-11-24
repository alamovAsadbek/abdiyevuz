from django.conf import settings
from django.db import models

from .storage import article_path, editor_path, get_private_storage

EVENTS = {
    "give": ("Kurs ochib berildi", "f"), "revoke": ("Kursdan chiqarildi", "x"), "buy": ("Sotib olish so‘rovi", ""),
    "course_new": ("Kurs yaratildi", ""), "course_act": ("Kurs aktiv qilindi", "f"), "course_deact": ("Kurs noaktiv qilindi", "x"),
    "user_block": ("Bloklandi", "x"), "user_unblock": ("Blokdan chiqarildi", "f"),
    "group_add": ("Guruhga qo‘shildi", "f"), "group_remove": ("Guruhdan chiqarildi", "x"),
    "test_grant": ("Testga qayta ishlash ruxsati", ""), "guide_create": ("Qo‘llanma yaratildi", ""),
    "guide_act": ("Qo‘llanma aktiv qilindi", "f"), "guide_deact": ("Qo‘llanma noaktiv qilindi", "x"),
    "guide_delete": ("Qo‘llanma o‘chirildi", "x"),
}


class EventModel(models.Model):
    type = models.CharField(max_length=30, choices=[(k, v[0]) for k, v in EVENTS.items()])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="events")
    course = models.ForeignKey("courses.CourseModel", null=True, blank=True, on_delete=models.CASCADE, related_name="events")
    group = models.ForeignKey("accounts.GroupModel", null=True, blank=True, on_delete=models.CASCADE, related_name="events")
    guide = models.ForeignKey("courses.GuideModel", null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    mods = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Tarix voqeasi"
        verbose_name_plural = "Tarix"

    @property
    def label(self):
        return EVENTS.get(self.type, (self.type, ""))


class EditorImageModel(models.Model):
    file = models.FileField(upload_to=editor_path, storage=get_private_storage)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Muharrir rasmi"
        verbose_name_plural = "Muharrir rasmlari"


def log_event(type, actor=None, **kw):
    return EventModel.objects.create(type=type, actor=actor, **kw)


class SiteSettingsModel(models.Model):
    """Umumiy sozlamalar (yagona yozuv)."""
    articles_public = models.BooleanField("Maqolalarni login qilmasdan ko‘rish mumkin", default=True)
    registration_open = models.BooleanField("Ro‘yxatdan o‘tish ochiq", default=True)

    class Meta:
        verbose_name = "Umumiy sozlama"
        verbose_name_plural = "Umumiy sozlamalar"

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return "Umumiy sozlamalar"


class ArticleModel(models.Model):
    title = models.CharField("Sarlavha", max_length=220)
    summary = models.CharField("Qisqa tavsif", max_length=300, blank=True)
    body = models.TextField("Matn (HTML)")
    cover = models.FileField(upload_to=article_path, storage=get_private_storage, null=True, blank=True)
    is_active = models.BooleanField("Aktiv", default=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="articles")
    views = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Maqola"
        verbose_name_plural = "Maqolalar"

    def __str__(self):
        return self.title

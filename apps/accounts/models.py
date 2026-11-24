import secrets

from django.apps import apps
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

PERMS = [
    ("users", "Foydalanuvchilarni boshqarish", "users"),
    ("gift", "Kurs berish", "gift"),
    ("tests", "Testlarni boshqarish", "check-square"),
    ("courses", "Kurslarni boshqarish", "play-circle"),
    ("tasks", "Vazifalarni boshqarish", "clipboard"),
    ("notify", "Xabarnoma yuborish", "send"),
    ("activity", "Foydalanuvchi faolligini ko‘rish", "activity"),
    ("groups", "Guruhlarni boshqarish", "layers"),
    ("guides", "Qo‘llanma qo‘shish", "book-open"),
    ("articles", "Maqolalarni boshqarish", "file-text"),
    ("meetings", "Uchrashuv (meeting) tashkil qilish", "video"),
]
PERM_CODES = [p[0] for p in PERMS]


def gen_uid():
    M = apps.get_model("accounts", "UserModel")
    for _ in range(50):
        uid = "KM-%d" % (1000 + secrets.randbelow(9000))
        try:
            if not M.objects.filter(uid=uid).exists():
                return uid
        except Exception:  # jadval hali yo'q (migratsiya paytida)
            return uid
    return "KM-%d" % (10000 + secrets.randbelow(90000))


class UserModel(AbstractUser):
    MAIN, ASSISTANT, STUDENT = "main", "assistant", "student"
    ROLES = [(MAIN, "Asosiy o‘qituvchi"), (ASSISTANT, "Yordamchi o‘qituvchi"), (STUDENT, "Talaba")]

    uid = models.CharField("Maxsus ID", max_length=12, unique=True, default=gen_uid, editable=False)
    full_name = models.CharField("Ism familiya", max_length=120)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    role = models.CharField("Rol", max_length=10, choices=ROLES, default=STUDENT, db_index=True)
    is_blocked = models.BooleanField("Bloklangan", default=False)
    perms = models.JSONField("Yordamchi ruxsatlari", default=list, blank=True)
    points = models.PositiveIntegerField("Ball", default=0)
    last_seen = models.DateTimeField("Oxirgi faollik", null=True, blank=True)

    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        ordering = ["id"]

    def save(self, *a, **kw):
        if self.is_superuser and self.role != self.MAIN:
            self.role = self.MAIN
        if self.role == self.MAIN:
            self.is_staff = self.is_superuser = True
        else:
            self.is_staff = self.is_superuser = False
        super().save(*a, **kw)

    def __str__(self):
        return f"{self.full_name or self.username} ({self.uid})"

    @property
    def is_main(self): return self.role == self.MAIN
    @property
    def is_assistant(self): return self.role == self.ASSISTANT
    @property
    def is_student(self): return self.role == self.STUDENT
    @property
    def is_teacher(self): return self.role in (self.MAIN, self.ASSISTANT)

    @property
    def initials(self):
        return "".join(w[0] for w in (self.full_name or self.username).split()[:2]).upper() or "?"

    @property
    def online(self):
        return bool(self.last_seen and (timezone.now() - self.last_seen).total_seconds() < 300)

    def can(self, code):
        if self.is_main:
            return True
        if not self.is_assistant:
            return False
        if code in (self.perms or []):
            return True
        return code == "tasks" and "courses" in (self.perms or [])


class RefreshTokenModel(models.Model):
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name="refresh_tokens")
    jti = models.CharField(max_length=40, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked = models.BooleanField(default=False)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Refresh token"
        verbose_name_plural = "Refresh tokenlar"


class LoginHistoryModel(models.Model):
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name="logins")
    at = models.DateTimeField(auto_now_add=True)
    ok = models.BooleanField(default=True)
    reason = models.CharField(max_length=80, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    device = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=20, blank=True)
    tz = models.CharField(max_length=50, blank=True)
    screen = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-at"]
        verbose_name = "Kirish tarixi"
        verbose_name_plural = "Kirish tarixi"


class GroupModel(models.Model):
    ONLINE, OFFLINE = "online", "offline"
    name = models.CharField("Guruh nomi", max_length=100)
    kind = models.CharField("Turi", max_length=10, choices=[(ONLINE, "Onlayn"), (OFFLINE, "Oflayn")], default=ONLINE)
    description = models.TextField("Tavsif / jadval", blank=True)
    is_active = models.BooleanField("Aktiv", default=True)
    members = models.ManyToManyField(UserModel, related_name="member_groups", blank=True, limit_choices_to={"role": "student"})
    assistants = models.ManyToManyField(UserModel, related_name="assist_groups", blank=True, limit_choices_to={"role": "assistant"})
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Guruh"
        verbose_name_plural = "Guruhlar"

    def __str__(self):
        return self.name

    @property
    def kind_label(self):
        return "Onlayn" if self.kind == self.ONLINE else "Oflayn"

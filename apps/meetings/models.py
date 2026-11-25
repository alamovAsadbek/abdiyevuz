import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

U = settings.AUTH_USER_MODEL

# Yordamchi (sovedushiy) uchun meeting ichidagi ruxsatlar. Asosiy o'qituvchi va meeting egasi — hammasi.
MPERMS = [
    ("kick", "Qatnashchini chiqarib yuborish", "user-x"),
    ("mute", "Mikrofon/kamerani o‘chirish", "mic-off"),
    ("comments", "Izohlarni o‘chirish", "message-square"),
    ("invite", "Qatnashchi taklif qilish", "user-plus"),
    ("grant", "Qatnashchilarga ruxsat berish", "shield"),
    ("end", "Meetingni yakunlash", "square"),
]
MPERM_CODES = [p[0] for p in MPERMS]


def gen_code():
    return secrets.token_urlsafe(6).replace("_", "x").replace("-", "y")[:8].lower()


class MeetingModel(models.Model):
    PUBLIC, PRIVATE = "public", "private"
    SCHEDULED, LIVE, ENDED = "scheduled", "live", "ended"
    KINDS = [(PUBLIC, "Ochiq (hamma kira oladi)"), (PRIVATE, "Yopiq (faqat taklif qilinganlar)")]
    STATUS = [(SCHEDULED, "Rejalashtirilgan"), (LIVE, "Davom etmoqda"), (ENDED, "Yakunlangan")]

    title = models.CharField("Nomi", max_length=200)
    description = models.TextField("Tavsif", blank=True)
    kind = models.CharField("Turi", max_length=8, choices=KINDS, default=PRIVATE, db_index=True)
    host = models.ForeignKey(U, on_delete=models.CASCADE, related_name="hosted_meetings")
    code = models.CharField(max_length=12, unique=True, default=gen_code, editable=False)
    start_at = models.DateTimeField("Boshlanish vaqti", null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=SCHEDULED, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    empty_since = models.DateTimeField(null=True, blank=True)
    # umumiy qoidalar
    chat_on = models.BooleanField("Chat yoqilgan", default=True)
    mic_default = models.BooleanField("Qatnashchilar mikrofonni yoqa oladi", default=True)
    cam_default = models.BooleanField("Qatnashchilar kamerani yoqa oladi", default=True)
    screen_default = models.BooleanField("Qatnashchilar ekranni ulasha oladi", default=False)
    reminded = models.BooleanField(default=False)
    long_notice_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Uchrashuv"
        verbose_name_plural = "Uchrashuvlar"

    def __str__(self):
        return self.title

    @property
    def is_public(self):
        return self.kind == self.PUBLIC

    @property
    def is_live(self):
        return self.status == self.LIVE

    @property
    def is_ended(self):
        return self.status == self.ENDED

    @property
    def status_tag(self):
        return {"scheduled": ("Rejalashtirilgan", ""), "live": ("Jonli", "f"), "ended": ("Yakunlangan", "x")}[self.status]


class MeetingMemberModel(models.Model):
    """Taklif qilingan / qatnashgan foydalanuvchi. role=cohost — yordamchi o'qituvchi (ruxsatlari bilan)."""
    MEMBER, COHOST = "member", "cohost"
    meeting = models.ForeignKey(MeetingModel, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="meeting_memberships")
    role = models.CharField(max_length=6, choices=[(MEMBER, "Qatnashchi"), (COHOST, "Yordamchi")], default=MEMBER)
    mperms = models.JSONField("Yordamchi ruxsatlari", default=list, blank=True)
    # alohida qatnashchi ruxsatlari (None — meeting umumiy qoidasi)
    can_mic = models.BooleanField(null=True, blank=True)
    can_cam = models.BooleanField(null=True, blank=True)
    can_chat = models.BooleanField(null=True, blank=True)
    can_screen = models.BooleanField(null=True, blank=True)
    banned = models.BooleanField("Chiqarib yuborilgan", default=False)
    invited = models.BooleanField(default=False)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    online = models.BooleanField(default=False)
    seen_at = models.DateTimeField(null=True, blank=True)   # oxirgi «ping» — uzilib qolgan (yopilmagan) ulanishlarni aniqlash uchun
    state = models.JSONField(default=dict, blank=True)   # {"mic":bool,"cam":bool,"screen":bool,"hand":bool}
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("meeting", "user")]
        verbose_name = "Uchrashuv qatnashchisi"
        verbose_name_plural = "Uchrashuv qatnashchilari"


class MeetingCommentModel(models.Model):
    meeting = models.ForeignKey(MeetingModel, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="meeting_comments")
    text = models.CharField(max_length=1000)
    mentions = models.ManyToManyField(U, blank=True, related_name="meeting_mentions")
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created", "id"]
        verbose_name = "Uchrashuv izohi"
        verbose_name_plural = "Uchrashuv izohlari"


class MeetingEventModel(models.Model):
    """Moderatsiya tarixi: kim kimni chiqardi, mute qildi va h.k."""
    meeting = models.ForeignKey(MeetingModel, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    target = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=30)
    note = models.CharField(max_length=200, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Uchrashuv tarixi"
        verbose_name_plural = "Uchrashuv tarixi"


class MeetingSessionModel(models.Model):
    """Kim qachon kirib, qachon chiqqani (har bir ulanish alohida yozuv)."""
    meeting = models.ForeignKey(MeetingModel, on_delete=models.CASCADE, related_name="sessions")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="meeting_sessions")
    role = models.CharField(max_length=10, default="member")
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["joined_at"]
        verbose_name = "Uchrashuv kirish-chiqishi"
        verbose_name_plural = "Uchrashuv kirish-chiqishlari"


class MeetingRecordingModel(models.Model):
    """Yozib olingan meeting — maxfiy papkada saqlanadi, faqat egasi/asosiy o'qituvchi ko'radi."""
    meeting = models.ForeignKey(MeetingModel, on_delete=models.CASCADE, related_name="recordings")
    started_by = models.ForeignKey(U, null=True, on_delete=models.SET_NULL, related_name="+")
    path = models.CharField(max_length=300, blank=True)
    size = models.BigIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["started_at"]
        verbose_name = "Uchrashuv yozuvi"
        verbose_name_plural = "Uchrashuv yozuvlari"

    @property
    def seconds(self):
        return int(((self.ended_at or timezone.now()) - self.started_at).total_seconds())

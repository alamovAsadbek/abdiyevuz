from django.conf import settings
from django.db import models

U = settings.AUTH_USER_MODEL


class NotificationModel(models.Model):
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="notifications")
    text = models.CharField(max_length=300)
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"


class MessageModel(models.Model):
    AUD = {"all": "Hamma foydalanuvchilar", "students": "Barcha talabalar", "staff": "O‘qituvchilar",
           "nobuy": "Kurs sotib olmagan talabalar", "buyers": "Kurs sotib olgan talabalar",
           "inactive": "7 kundan beri kirmaganlar", "online": "Hozir onlayn", "group": "Guruhlar bo‘yicha",
           "users": "Tanlangan foydalanuvchilar", "mygroups": "Mening guruhlarim talabalari"}
    CH = {"app": "Sayt ichida", "sms": "SMS", "both": "Sayt ichida + SMS"}
    title = models.CharField("Sarlavha", max_length=200)
    short = models.CharField("Qisqa tavsif", max_length=200, blank=True)
    body = models.TextField("Matn (HTML)")
    audience = models.CharField(max_length=10, choices=list(AUD.items()))
    groups = models.ManyToManyField("accounts.GroupModel", blank=True)
    users = models.ManyToManyField(U, blank=True, related_name="+")
    channel = models.CharField(max_length=5, choices=list(CH.items()), default="app")
    important = models.BooleanField("Muhim", default=False)
    author = models.ForeignKey(U, null=True, on_delete=models.SET_NULL, related_name="sent_messages")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Xabarnoma"
        verbose_name_plural = "Xabarnomalar"

    def __str__(self):
        return self.title

    @property
    def channels(self):
        return ["app", "sms"] if self.channel == "both" else [self.channel]


class MessageDeliveryModel(models.Model):
    message = models.ForeignKey(MessageModel, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=5)
    ok = models.BooleanField(default=True)
    reason = models.CharField(max_length=120, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Xabarnoma yetkazilishi"
        verbose_name_plural = "Xabarnoma yetkazilishlari"

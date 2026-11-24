from django.conf import settings
from django.db import models

U = settings.AUTH_USER_MODEL

HIGH, MEDIUM, LOW = "high", "medium", "low"
SEVERITY = [(HIGH, "Yuqori"), (MEDIUM, "O‘rta"), (LOW, "Past")]
SEV_TAG = {HIGH: "x", MEDIUM: "", LOW: "f"}

# tur -> (nomi, daraja, ikonka, izoh)
KINDS = {
    "printscreen": ("Skrinshot (PrintScreen)", HIGH, "camera", "PrintScreen tugmasi bosildi — ekran rasmi olinishi mumkin"),
    "snip": ("Skrinshot vositasi", HIGH, "scissors", "Win+Shift+S / Cmd+Shift+3,4,5 kabi skrinshot tugmalari yoki «Ножницы» vositasi"),
    "record": ("Ekran yozib olish urinishi", HIGH, "video", "Win+Alt+R, Win+G (Game Bar), Cmd+Shift+5 kabi ekran yozish tugmalari"),
    "capture": ("Ekranni ulashish / yozish (brauzer)", HIGH, "monitor", "Sahifa ichidan ekranni ushlash API si chaqirildi"),
    "print": ("Sahifani chop etish", HIGH, "printer", "Ctrl+P yoki brauzer menyusidan chop etish"),
    "devtools": ("Dasturchi vositalari (DevTools)", HIGH, "terminal", "F12 / Ctrl+Shift+I — sahifa kodi va fayllarini olishga urinish"),
    "save": ("Sahifani saqlash", MEDIUM, "save", "Ctrl+S — sahifani kompyuterga saqlashga urinish"),
    "source": ("Sahifa kodini ko‘rish", MEDIUM, "code", "Ctrl+U — sahifa manba kodini ochishga urinish"),
    "copy": ("Matnni nusxalash", MEDIUM, "copy", "Himoyalangan matnni nusxalashga urinish"),
    "context": ("O‘ng tugma menyusi", LOW, "mouse-pointer", "Himoyalangan kontentda o‘ng tugma bosildi"),
    "blur": ("Himoyalangan kontentdan chiqib ketdi", LOW, "eye-off", "Video/fayl ochiq turganda boshqa oynaga o‘tildi (skrinshot vositasi ochilishi mumkin)"),
}


def kind_info(k):
    return KINDS.get(k, (k, LOW, "alert-triangle", ""))


class SecurityIncidentModel(models.Model):
    user = models.ForeignKey(U, on_delete=models.CASCADE, related_name="incidents")
    kind = models.CharField("Turi", max_length=20, db_index=True)
    severity = models.CharField("Daraja", max_length=10, choices=SEVERITY, default=LOW, db_index=True)
    url = models.CharField("Sahifa", max_length=400, blank=True)
    page_title = models.CharField("Sahifa nomi", max_length=200, blank=True)
    content = models.CharField("Kontent", max_length=200, blank=True, help_text="Ochiq turgan video/fayl/test")
    count = models.PositiveIntegerField("Takrorlar", default=1)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    device = models.CharField(max_length=80, blank=True)
    screen = models.CharField(max_length=20, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    reviewed = models.BooleanField("Ko‘rib chiqilgan", default=False, db_index=True)
    reviewed_by = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField("Izoh", blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    last_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_at", "-id"]
        verbose_name = "Xavfsizlik hodisasi"
        verbose_name_plural = "Xavfsizlik hodisalari"

    def __str__(self):
        return f"{self.user} — {self.label}"

    @property
    def label(self):
        return kind_info(self.kind)[0]

    @property
    def icon(self):
        return kind_info(self.kind)[2]

    @property
    def desc(self):
        return kind_info(self.kind)[3]

    @property
    def sev_label(self):
        return dict(SEVERITY).get(self.severity, self.severity)

    @property
    def sev_tag(self):
        return SEV_TAG.get(self.severity, "")


# ---------------------------------------------------------------- tizim jurnali (audit log)
CATS = [("auth", "Kirish / chiqish"), ("users", "Foydalanuvchilar"), ("perms", "Ruxsatlar"), ("courses", "Kurslar"),
        ("tests", "Testlar"), ("tasks", "Vazifalar"), ("groups", "Guruhlar"), ("articles", "Maqolalar"),
        ("guides", "Qo‘llanmalar"), ("notify", "Xabarnomalar"), ("meetings", "Uchrashuvlar"), ("files", "Fayllar"),
        ("security", "Xavfsizlik"), ("settings", "Sozlamalar"), ("other", "Boshqa")]


class AuditLogModel(models.Model):
    OK, FAIL, DENIED = "ok", "fail", "denied"
    RESULTS = [(OK, "Bajarildi"), (FAIL, "Xato"), (DENIED, "Ruxsat yo‘q")]

    actor = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    actor_name = models.CharField(max_length=160, blank=True)
    actor_role = models.CharField(max_length=10, blank=True)
    action = models.CharField("Amal kodi", max_length=60, db_index=True)
    label = models.CharField("Amal", max_length=160)
    category = models.CharField(max_length=12, choices=CATS, default="other", db_index=True)
    result = models.CharField(max_length=8, choices=RESULTS, default=OK, db_index=True)
    method = models.CharField(max_length=8, blank=True)
    path = models.CharField(max_length=400, blank=True)
    status = models.PositiveSmallIntegerField(default=0)
    obj_type = models.CharField(max_length=40, blank=True)
    obj_id = models.CharField(max_length=40, blank=True)
    obj_label = models.CharField(max_length=200, blank=True)
    target_user = models.ForeignKey(U, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_about")
    data = models.JSONField(default=dict, blank=True)
    message = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    device = models.CharField(max_length=80, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Jurnal yozuvi"
        verbose_name_plural = "Tizim jurnali"

    def __str__(self):
        return f"{self.created:%d.%m %H:%M} {self.actor_name} — {self.label}"

    @property
    def cat_label(self):
        return dict(CATS).get(self.category, self.category)

    @property
    def result_tag(self):
        return {"ok": ("Bajarildi", "f"), "fail": ("Xato", "x"), "denied": ("Ruxsat yo‘q", "x")}[self.result]

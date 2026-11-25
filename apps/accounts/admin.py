from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import GroupModel, LoginHistoryModel, RefreshTokenModel, UserModel


@admin.register(UserModel)
class UserModelAdmin(UserAdmin):
    list_display = ("username", "full_name", "uid", "role", "phone", "show_on_site", "is_blocked", "points", "last_seen")
    list_editable = ("show_on_site",)
    list_filter = ("show_on_site", "role", "is_blocked", "is_active")
    search_fields = ("username", "full_name", "uid", "phone")
    readonly_fields = ("uid", "last_seen", "last_login", "date_joined")
    actions = ["hide_from_site", "show_on_site_action"]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Shaxsiy", {"fields": ("full_name", "phone", "uid", "role", "points")}),
        ("Saytda ko‘rinishi va holati", {"fields": ("show_on_site", "is_blocked", "is_active"),
                                          "description": "«Saytda ko‘rinsin» o‘chirilsa, foydalanuvchi saytdagi ro‘yxat, statistika, guruh va "
                                                         "tanlash oynalarida ko‘rinmaydi va saytdan boshqarilmaydi — faqat shu yerda (Django admin)."}),
        ("Ruxsatlar", {"fields": ("perms",), "classes": ("collapse",)}),
        ("Vaqtlar", {"fields": ("last_seen", "last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "full_name", "phone", "role", "show_on_site", "password1", "password2")}),)

    @admin.action(description="Saytda yashirish (faqat adminda ko‘rinadi)")
    def hide_from_site(self, request, queryset):
        n = queryset.update(show_on_site=False)
        self.message_user(request, f"{n} ta foydalanuvchi saytdan yashirildi")

    @admin.action(description="Saytda ko‘rsatish")
    def show_on_site_action(self, request, queryset):
        n = queryset.update(show_on_site=True)
        self.message_user(request, f"{n} ta foydalanuvchi saytda ko‘rinadigan qilindi")


@admin.register(GroupModel)
class GroupModelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_active", "created")
    filter_horizontal = ("members", "assistants")
    search_fields = ("name",)


@admin.register(LoginHistoryModel)
class LoginHistoryModelAdmin(admin.ModelAdmin):
    list_display = ("user", "at", "ok", "reason", "ip", "device")
    list_filter = ("ok",)
    readonly_fields = [f.name for f in LoginHistoryModel._meta.fields]


@admin.register(RefreshTokenModel)
class RefreshTokenModelAdmin(admin.ModelAdmin):
    list_display = ("user", "created", "expires_at", "revoked", "ip")
    list_filter = ("revoked",)

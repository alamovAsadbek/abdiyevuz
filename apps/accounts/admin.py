from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import GroupModel, LoginHistoryModel, RefreshTokenModel, UserModel


@admin.register(UserModel)
class UserModelAdmin(UserAdmin):
    list_display = ("username", "full_name", "uid", "role", "phone", "is_blocked", "points", "last_seen")
    list_filter = ("role", "is_blocked", "is_active")
    search_fields = ("username", "full_name", "uid", "phone")
    readonly_fields = ("uid", "last_seen", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Shaxsiy", {"fields": ("full_name", "phone", "uid", "role", "is_blocked", "perms", "points")}),
        ("Holat", {"fields": ("is_active", "last_seen", "last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "full_name", "phone", "role", "password1", "password2")}),)


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

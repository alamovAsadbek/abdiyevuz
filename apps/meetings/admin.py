from django.contrib import admin

from .models import MeetingCommentModel, MeetingEventModel, MeetingMemberModel, MeetingModel


class MemberInline(admin.TabularInline):
    model = MeetingMemberModel
    extra = 0
    raw_id_fields = ("user",)


@admin.register(MeetingModel)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "host", "start_at", "created")
    list_filter = ("kind", "status")
    search_fields = ("title", "code")
    raw_id_fields = ("host",)
    inlines = [MemberInline]


@admin.register(MeetingCommentModel)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("meeting", "user", "text", "is_deleted", "created")
    list_filter = ("is_deleted",)
    raw_id_fields = ("meeting", "user", "deleted_by")


@admin.register(MeetingEventModel)
class EventAdmin(admin.ModelAdmin):
    list_display = ("meeting", "action", "actor", "target", "created")
    list_filter = ("action",)
    raw_id_fields = ("meeting", "actor", "target")

from django.contrib import admin

from . import models as m


class ModuleInline(admin.TabularInline):
    model = m.ModuleModel
    extra = 0


@admin.register(m.CourseModel)
class CourseModelAdmin(admin.ModelAdmin):
    list_display = ("title", "is_modular", "price", "sequential", "is_active", "group")
    list_filter = ("is_modular", "is_active")
    search_fields = ("title",)
    inlines = [ModuleInline]


@admin.register(m.ModuleModel)
class ModuleModelAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "price", "is_active", "order")
    list_filter = ("course", "is_active")


@admin.register(m.LessonModel)
class LessonModelAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "video_kind", "hls_status", "views")
    list_filter = ("video_kind", "hls_status")
    readonly_fields = ("hls_status", "hls_error", "size_before", "size_after", "duration", "views")


for mod in (m.LessonMaterialModel, m.TaskFileModel, m.LessonProgressModel, m.PurchaseRequestModel, m.GuideFileModel):
    admin.site.register(mod)


@admin.register(m.TaskModel)
class TaskModelAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "max_score", "deadline", "is_active", "is_closed")
    list_filter = ("is_active", "is_closed")


@admin.register(m.SubmissionModel)
class SubmissionModelAdmin(admin.ModelAdmin):
    list_display = ("task", "student", "status", "score", "submitted_at")
    list_filter = ("status",)


@admin.register(m.CourseAccessModel)
class CourseAccessModelAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "module", "source", "granted_by", "created")
    list_filter = ("source", "course")


@admin.register(m.GuideModel)
class GuideModelAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "builtin_key")

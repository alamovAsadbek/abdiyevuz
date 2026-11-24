from django.contrib import admin

from . import models as m


class QuestionInline(admin.StackedInline):
    model = m.QuestionModel
    extra = 0


@admin.register(m.TestModel)
class TestModelAdmin(admin.ModelAdmin):
    list_display = ("title", "mode", "start_at", "end_at", "price", "is_active", "status")
    list_filter = ("mode", "is_active", "status")
    readonly_fields = ("status",)
    inlines = [QuestionInline]


@admin.register(m.AttemptModel)
class AttemptModelAdmin(admin.ModelAdmin):
    list_display = ("test", "user", "score", "total", "created")
    list_filter = ("test",)


for mod in (m.RetakeGrantModel, m.TestAccessModel, m.ErrorReportModel):
    admin.site.register(mod)

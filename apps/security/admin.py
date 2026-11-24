from django.contrib import admin

from .models import AuditLogModel, SecurityIncidentModel


@admin.register(SecurityIncidentModel)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("created", "user", "kind", "severity", "count", "url", "reviewed")
    list_filter = ("severity", "kind", "reviewed")
    search_fields = ("user__full_name", "user__username", "user__uid", "url")


@admin.register(AuditLogModel)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("created", "actor_name", "actor_role", "label", "obj_label", "result", "ip")
    list_filter = ("category", "result", "actor_role")
    search_fields = ("actor_name", "label", "obj_label", "path")
    readonly_fields = [f.name for f in AuditLogModel._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

from django.contrib import admin

from .models import ArticleModel, EditorImageModel, EventModel, SiteSettingsModel

admin.site.register(EditorImageModel)


@admin.register(EventModel)
class EventModelAdmin(admin.ModelAdmin):
    list_display = ("type", "user", "course", "group", "actor", "created")
    list_filter = ("type",)


@admin.register(ArticleModel)
class ArticleModelAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "author", "views", "created")
    list_filter = ("is_active",)
    search_fields = ("title",)


@admin.register(SiteSettingsModel)
class SiteSettingsModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "articles_public", "registration_open")

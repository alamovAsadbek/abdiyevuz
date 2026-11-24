from django.contrib import admin

from . import models as m


@admin.register(m.NotificationModel)
class NotificationModelAdmin(admin.ModelAdmin):
    list_display = ("user", "text", "is_read", "created")
    list_filter = ("is_read",)


@admin.register(m.MessageModel)
class MessageModelAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "channel", "important", "author", "created")


@admin.register(m.MessageDeliveryModel)
class MessageDeliveryModelAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "channel", "ok", "reason", "is_read")
    list_filter = ("ok", "channel", "is_read")

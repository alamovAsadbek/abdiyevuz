from django.urls import path

from . import views as v

urlpatterns = [
    path("notifications/", v.notifications, name="notifications"),
    path("notifications/read-all/", v.read_all, name="read_all"),
    path("notifications/<str:kind>/<int:pk>/", v.notification_open, name="notification_open"),
    path("staff/messages/", v.messages_list, name="messages"),
    path("staff/messages/new/", v.message_new, name="message_new"),
    path("staff/messages/count/", v.recipients_count, name="recipients_count"),
    path("staff/messages/<int:pk>/", v.message_detail, name="message_detail"),
    path("staff/messages/<int:pk>/edit/", v.message_edit, name="message_edit"),
    path("staff/messages/<int:pk>/resend/", v.message_resend, name="message_resend"),
    path("staff/messages/<int:pk>/delete/", v.message_delete, name="message_delete"),
]

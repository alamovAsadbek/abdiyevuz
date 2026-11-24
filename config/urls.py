from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Abdiyev.uz — boshqaruv"
admin.site.site_title = "Abdiyev.uz"
handler403 = "apps.core.views.err403"
handler404 = "apps.core.views.err404"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.courses.urls")),
    path("", include("apps.exams.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.meetings.urls")),
]

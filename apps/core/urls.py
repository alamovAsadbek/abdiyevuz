from django.urls import path

from . import views as v

urlpatterns = [
    path("", v.home, name="home"),
    path("articles/new/", v.article_new, name="article_new"),
    path("articles/<int:pk>/", v.article_detail, name="article_detail"),
    path("articles/<int:pk>/edit/", v.article_edit, name="article_edit"),
    path("articles/<int:pk>/toggle/", v.article_toggle, name="article_toggle"),
    path("articles/<int:pk>/delete/", v.article_delete, name="article_delete"),
    path("articles/<int:pk>/cover/", v.article_cover, name="article_cover"),
    path("settings/site/", v.site_settings, name="site_settings"),
    path("f/<str:kind>/<int:pk>/info/", v.file_info, name="file_info"),
    path("f/<str:kind>/<int:pk>/<int:n>.png", v.file_page, name="file_page"),
    path("f/<str:kind>/<int:pk>/download/", v.file_download, name="file_download"),
    path("editor/upload/", v.editor_upload, name="editor_upload"),
    path("editor/img/<int:pk>/", v.editor_img, name="editor_img"),
]

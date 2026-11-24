from django.urls import path

from . import views as v

urlpatterns = [
    path("meetings/", v.meetings, name="meetings"),
    path("meetings/new/", v.meeting_new, name="meeting_new"),
    path("meetings/j/<str:code>/", v.meeting_by_code, name="meeting_code"),
    path("meetings/<int:pk>/", v.meeting_detail, name="meeting_detail"),
    path("meetings/<int:pk>/edit/", v.meeting_edit, name="meeting_edit"),
    path("meetings/<int:pk>/delete/", v.meeting_delete, name="meeting_delete"),
    path("meetings/<int:pk>/start/", v.meeting_start, name="meeting_start"),
    path("meetings/<int:pk>/end/", v.meeting_end, name="meeting_end"),
    path("meetings/<int:pk>/room/", v.meeting_room, name="meeting_room"),
    path("meetings/<int:pk>/invite/", v.meeting_invite, name="meeting_invite"),
    path("meetings/<int:pk>/cohost/", v.meeting_cohost_add, name="meeting_cohost_add"),
    path("meetings/<int:pk>/member/<int:uid>/", v.member_action, name="meeting_member"),
    path("meetings/<int:pk>/rec/start/", v.rec_start, name="meeting_rec_start"),
    path("meetings/<int:pk>/rec/stop/", v.rec_stop, name="meeting_rec_stop"),
    path("meetings/<int:pk>/rec/<int:rid>/chunk/", v.rec_chunk, name="meeting_rec_chunk"),
    path("meetings/<int:pk>/rec/<int:rid>/", v.rec_file, name="meeting_rec_file"),
]

from django.urls import path

from .ws import NotifyConsumer

from apps.meetings.consumers import MeetingConsumer

websocket_urlpatterns = [
    path("ws/live/", NotifyConsumer.as_asgi()),
    path("ws/meeting/<int:pk>/", MeetingConsumer.as_asgi()),
]

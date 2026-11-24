from django.urls import path

from . import views as v

urlpatterns = [
    path("security/incident/", v.incident, name="security_incident"),
    path("security/", v.incidents, name="security"),
    path("security/<int:pk>/", v.incident_detail, name="security_detail"),
    path("security/<int:pk>/review/", v.incident_review, name="security_review"),
    path("staff/logs/", v.logs, name="logs"),
    path("staff/logs/<int:pk>/", v.log_detail, name="log_detail"),
]

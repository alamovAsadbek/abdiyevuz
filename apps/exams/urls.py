from django.urls import path

from . import views as v

urlpatterns = [
    path("tests/", v.tests, name="tests"),
    path("tests/new/", v.test_new, name="test_new"),
    path("tests/<int:pk>/", v.test_detail, name="test_detail"),
    path("tests/<int:pk>/edit/", v.test_edit, name="test_edit"),
    path("tests/<int:pk>/toggle/", v.test_toggle, name="test_toggle"),
    path("tests/<int:pk>/delete/", v.test_delete, name="test_delete"),
    path("tests/<int:pk>/time/<str:action>/", v.test_time, name="test_time"),
    path("tests/<int:pk>/run/", v.test_run_public, name="test_run"),
    path("tests/<int:pk>/access/", v.test_access, name="test_access"),
    path("tests/<int:pk>/buy/", v.buy_test, name="buy_test"),
    path("tests/<int:pk>/report/", v.report_new, name="report_new"),
    path("tests/<int:pk>/retake/<int:uid>/<int:on>/", v.retake, name="retake"),
    path("attempts/<int:pk>/", v.attempt_detail, name="attempt_detail"),
    path("staff/reports/", v.reports, name="reports"),
    path("staff/reports/<int:pk>/", v.report_detail, name="report_detail"),
    path("staff/reports/<int:pk>/done/", v.report_done, name="report_done"),
    path("staff/reports/<int:pk>/delete/", v.report_delete, name="report_delete"),
]

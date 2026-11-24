from django.apps import AppConfig


class CoursesConfig(AppConfig):
    name = "apps.courses"
    verbose_name = "Kurslar"

    def ready(self):
        from . import signals  # noqa

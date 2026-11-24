import os
import sys

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    verbose_name = "Tizim"

    def ready(self):
        from django.conf import settings
        skip = {"migrate", "makemigrations", "collectstatic", "seed_demo", "test", "shell", "check", "createsuperuser", "run_scheduler"}
        if not settings.RUN_SCHEDULER or skip & set(sys.argv):
            return
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return
        from . import scheduler
        scheduler.start()

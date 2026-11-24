from django.core.management.base import BaseCommand

from apps.core import scheduler


class Command(BaseCommand):
    help = "Test/vazifa statuslarini avtomatik o'zgartiruvchi fon jarayoni (alohida process sifatida)"

    def handle(self, *a, **kw):
        self.stdout.write("Scheduler ishlayapti (Ctrl+C — to'xtatish)")
        scheduler.loop()

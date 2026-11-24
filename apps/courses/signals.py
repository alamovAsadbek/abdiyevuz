from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import GroupModel
from .models import CourseModel


@receiver(post_save, sender=GroupModel)
def group_course(sender, instance, created, **kw):
    """Har bir guruh uchun yashirin kurs (guruh videodarslari shu kursda saqlanadi)."""
    c = CourseModel.objects.filter(group=instance).first()
    if not c:
        c = CourseModel.objects.create(group=instance, title=instance.name, price=0, sequential=False)
    elif c.title != instance.name:
        c.title = instance.name
        c.save(update_fields=["title"])
    c.first_module()

from django.db.models import Q

from apps.accounts.models import GroupModel, UserModel
from .models import CourseAccessModel, LessonModel, LessonProgressModel, SubmissionModel


def my_groups(user):
    return GroupModel.objects.all() if user.is_main else user.assist_groups.all()


def scoped_students(user):
    """Foydalanuvchi boshqara oladigan talabalar («Saytda ko'rinsin» o'chirilganlar kirmaydi)."""
    qs = UserModel.objects.on_site().filter(role=UserModel.STUDENT)
    if user.is_assistant:
        qs = qs.filter(member_groups__assistants=user).distinct()
    return qs


def student_in_scope(viewer, student):
    return viewer.is_main or (viewer.is_assistant and student.is_student and
                              student.member_groups.filter(assistants=viewer).exists())


def has_access_row(user, course, module):
    return CourseAccessModel.objects.filter(user=user, course=course).filter(Q(module__isnull=True) | Q(module=module)).exists()


def can_access(user, course, module):
    """Kurs/modulga kirish — faqat backend hal qiladi."""
    auth = user.is_authenticated
    if course.group_id:
        if not auth:
            return False
        g = course.group
        if user.is_main:
            return True
        if user.is_assistant:
            return g.assistants.filter(pk=user.pk).exists()
        return g.is_active and g.members.filter(pk=user.pk).exists()
    if auth and user.is_teacher:
        return True
    if not course.is_active:
        return False
    if course.is_modular and not module.is_active:
        return False
    if course.login_required and not auth:
        return False
    if auth and has_access_row(user, course, module):
        return True
    return (module.price if course.is_modular else course.price) == 0


def lock_reason(user, lesson):
    """Dars qulfi sababi ('' — ochiq). Muddati tugagan vazifa keyingi darsni BLOKLAMAYDI."""
    module, course = lesson.module, lesson.module.course
    if user.is_authenticated and user.is_teacher:
        return ""
    if not can_access(user, course, module):
        if course.group_id:
            return "Bu videodars faqat guruh a’zolari uchun"
        if not course.is_active:
            return "Kurs hozircha mavjud emas"
        if course.login_required and not user.is_authenticated:
            return "Ko‘rish uchun tizimga kiring"
        return "Avval sotib oling"
    sibs = list(module.lessons.all())
    idx = next((i for i, l in enumerate(sibs) if l.pk == lesson.pk), 0)
    if idx == 0:
        return ""
    prev = sibs[idx - 1]
    open_tasks = [t for t in prev.tasks.all() if t.blocks_next]
    if not user.is_authenticated:
        return "Davom etish uchun ro‘yxatdan o‘ting" if (open_tasks or course.sequential) else ""
    if open_tasks:
        done = set(SubmissionModel.objects.filter(student=user, task__in=open_tasks).values_list("task_id", flat=True))
        if any(t.pk not in done for t in open_tasks):
            return "Avvalgi darsning vazifasini yuboring"
    if course.sequential and not LessonProgressModel.objects.filter(user=user, lesson=prev).exists():
        return "Avvalgi darsni ko‘rib chiqing"
    return ""


def lesson_done(user, lesson, seen_ids, sub_task_ids):
    if lesson.pk not in seen_ids:
        return False
    return all((t.pk in sub_task_ids) or not t.blocks_next for t in lesson.tasks.all() if t.is_active)


def completed_count(user, course):
    lessons = list(LessonModel.objects.filter(module__course=course).prefetch_related("tasks"))
    seen = set(LessonProgressModel.objects.filter(user=user, lesson__in=lessons).values_list("lesson_id", flat=True))
    subs = set(SubmissionModel.objects.filter(student=user, task__lesson__in=lessons).values_list("task_id", flat=True))
    return sum(1 for l in lessons if lesson_done(user, l, seen, subs)), len(lessons)


def enrolled(lesson, viewer):
    """Shu darsni ko'rishga haqli (yoki ko'rgan/topshirgan) talabalar."""
    course = lesson.module.course
    if course.group_id:
        qs = course.group.members.filter(role=UserModel.STUDENT, show_on_site=True)
    else:
        ids = set(CourseAccessModel.objects.filter(course=course).filter(Q(module__isnull=True) | Q(module=lesson.module))
                  .values_list("user_id", flat=True))
        ids |= set(LessonProgressModel.objects.filter(lesson=lesson).values_list("user_id", flat=True))
        ids |= set(SubmissionModel.objects.filter(task__lesson=lesson).values_list("student_id", flat=True))
        qs = UserModel.objects.on_site().filter(role=UserModel.STUDENT, id__in=ids)
    if viewer is not None and viewer.is_assistant:
        qs = qs.filter(member_groups__assistants=viewer).distinct()
    return qs


def visible_courses(user):
    from .models import CourseModel
    qs = CourseModel.objects.filter(group__isnull=True)
    if not (user.is_authenticated and user.is_teacher):
        qs = qs.filter(is_active=True)
    return qs


def my_course_ids(user):
    return set(CourseAccessModel.objects.filter(user=user).values_list("course_id", flat=True))


def student_open_tasks(user):
    from .models import TaskModel
    done = set(SubmissionModel.objects.filter(student=user).values_list("task_id", flat=True))
    out = []
    for t in TaskModel.objects.filter(is_active=True).select_related("lesson__module__course__group")[:300]:
        if t.pk in done or not t.is_open:
            continue
        if lock_reason(user, t.lesson) == "" and can_access(user, t.lesson.module.course, t.lesson.module):
            out.append(t)
    return out

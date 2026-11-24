from .models import AttemptModel, RetakeGrantModel, TestAccessModel


def attempt_count(test, user):
    return AttemptModel.objects.filter(test=test, user=user).count() if user.is_authenticated else 0


def grants_left(test, user):
    return RetakeGrantModel.objects.filter(test=test, user=user, used=False).count() if user.is_authenticated else 0


def can_try(test, user):
    if not user.is_authenticated or not user.is_student:
        return True
    n = attempt_count(test, user)
    return n == 0 or bool(test.allow_retake and (not test.max_attempts or n < test.max_attempts)) or grants_left(test, user) > 0


def has_paid_access(test, user):
    if not test.is_paid:
        return True
    if not user.is_authenticated:
        return False
    return user.is_teacher or TestAccessModel.objects.filter(test=test, user=user).exists()


def score_answers(test, answers):
    qs = list(test.questions.all())
    ans = [(int(a) if str(a).lstrip("-").isdigit() else -1) for a in answers][:len(qs)]
    ans += [-1] * (len(qs) - len(ans))
    sc = sum(1 for q, a in zip(qs, ans) if a == q.correct)
    return ans, sc, len(qs)

import traceback
from django.test import Client
from django.urls import reverse
from apps.courses.models import *
from apps.exams.models import *
from apps.accounts.models import *
from apps.notifications.models import *

def login(u, p):
    c = Client(); r = c.post("/login/", {"username": u, "password": p}); assert r.status_code == 302, (u, r.status_code); return c

def hit(c, path, who, ok=(200,)):
    try:
        r = c.get(path, follow=False)
        if r.status_code not in ok: print(f"  [{who}] {path} -> {r.status_code}", r.headers.get("Location", ""))
        return r
    except Exception as e:
        print(f"  [{who}] {path} EXC {type(e).__name__}: {e}"); traceback.print_exc(limit=-3)

lesson = LessonModel.objects.filter(module__course__title="Kimyo asoslari").first()
glesson = LessonModel.objects.filter(module__course__group__isnull=False).first()
common = ["/", "/login/", "/register/", "/courses/", "/tests/", "/dashboard/", "/profile/", "/settings/", "/stats/", "/stats/?tab=1", "/stats/?tab=2", "/stats/?tab=3",
 "/groups/", "/guides/", "/tasks/", "/notifications/", "/notifications/?mode=table"]
t = TestModel.objects.get(title="Oksidlar"); tf = TestModel.objects.get(mode="file"); g = GroupModel.objects.first()
c1 = CourseModel.objects.get(title="Kimyo asoslari"); mod = c1.modules.first(); task = TaskModel.objects.first(); sub = SubmissionModel.objects.first()
gd = GuideModel.objects.first(); att = AttemptModel.objects.first(); u0 = UserModel.objects.get(username="ali")
pages = common + [f"/courses/{c1.pk}/", f"/modules/{mod.pk}/", f"/modules/{c1.modules.all()[1].pk}/", f"/lessons/{lesson.pk}/", f"/lessons/{lesson.pk}/?tab=mat", f"/lessons/{lesson.pk}/?tab=task",
 f"/lessons/{lesson.pk}/?tab=info", f"/groups/{g.pk}/", f"/tests/{t.pk}/", f"/tests/{tf.pk}/", f"/tests/{t.pk}/run/", f"/tests/{tf.pk}/run/", f"/attempts/{att.pk}/", f"/guides/{gd.pk}/",
 f"/guides/{GuideModel.objects.filter(builtin_key='pt').first().pk}/"]
staff_pages = pages + ["/staff/users/", "/staff/users/?mode=table", "/staff/users/new/", "/staff/users/bulk/", f"/staff/users/{u0.pk}/"] + [f"/staff/users/{u0.pk}/?tab={k}" for k in ["kurs","guruh","test","vazifa","info","xabar","faol","tarix"]] + [
 "/courses/new/", f"/courses/{c1.pk}/?tab=set", f"/courses/{c1.pk}/?tab=stu", f"/courses/{c1.pk}/?tab=his", f"/courses/{c1.pk}/modules/new/", f"/modules/{mod.pk}/edit/", f"/modules/{mod.pk}/lessons/new/",
 f"/lessons/{lesson.pk}/edit/", f"/lessons/{lesson.pk}/materials/new/", f"/lessons/{lesson.pk}/tasks/new/", f"/lessons/{lesson.pk}/?tab=stu", f"/lessons/{lesson.pk}/?tab=set", "/tasks/add/", f"/tasks/{task.pk}/",
 f"/tasks/{task.pk}/?tab=non", f"/tasks/{task.pk}/?tab=info", f"/tasks/{task.pk}/?tab=set", f"/staff/submissions/{sub.pk}/", "/guides/new/", f"/guides/{gd.pk}/?tab=his", "/groups/new/", f"/groups/{g.pk}/?tab=mem",
 f"/groups/{g.pk}/?tab=set", f"/groups/{g.pk}/?tab=stat", f"/groups/{g.pk}/?tab=tch", "/tests/new/", f"/tests/{t.pk}/edit/", f"/tests/{tf.pk}/edit/", f"/tests/{t.pk}/?tab=q", f"/tests/{t.pk}/?tab=res", f"/tests/{t.pk}/?tab=rep",
 "/staff/reports/", "/staff/messages/", "/staff/messages/new/", f"/staff/messages/new/?uid={u0.pk}", f"/staff/gift/data/?uid={u0.pk}", f"/staff/gift/data/?course={c1.pk}",
 f"/f/mat/{LessonMaterialModel.objects.filter(kind='file').first().pk}/info/", f"/f/mat/{LessonMaterialModel.objects.filter(kind='file').first().pk}/1.png", f"/f/sub/{sub.pk}/info/", f"/f/test/{tf.pk}/1.png"]
m = MessageModel.objects.first(); staff_pages += [f"/staff/messages/{m.pk}/", f"/staff/messages/{m.pk}/?tab=rcp", f"/staff/messages/{m.pk}/edit/"]
for who, (u, p), pg in [("MAIN", ("abdiyev", "Admin#2026"), staff_pages), ("ASS", ("yordamchi", "Yordam#2026"), staff_pages), ("STU", ("ali", "Talaba#2026"), pages + [f"/groups/{g.pk}/", f"/f/sub/{sub.pk}/1.png", f"/f/mat/{LessonMaterialModel.objects.filter(kind='file').first().pk}/1.png"]), ("GUEST", (None, None), ["/", "/login/", "/register/", "/courses/", "/tests/", f"/tests/{t.pk}/", f"/courses/{c1.pk}/", f"/tests/{t.pk}/run/"])]:
    c = login(u, p) if u else Client()
    print(who, len(pg), "pages")
    for path in pg:
        hit(c, path, who, ok=(200, 302))

import json, re
from datetime import timedelta
from django.test import Client
from django.utils import timezone
from apps.courses.models import *
from apps.exams.models import *
from apps.accounts.models import *
from apps.notifications.models import *
exec(open('scripts/smoke_pages.py').read().split("lesson = ")[0])  # helpers
def lg(u,p):
    c=Client(); c.post("/login/",{"username":u,"password":p}); return c
M=lg("abdiyev","Admin#2026"); S=lg("ali","Talaba#2026"); S2=lg("madina","Talaba#2026")
chk=lambda name,cond: print(("OK  " if cond else "FAIL"), name)
# 1) redirects of main on a few pages
for p in ["/login/","/tests/%d/run/"%TestModel.objects.get(mode='file').pk]:
    r=M.get(p); print("main",p,r.status_code,r.headers.get("Location"))
# 2) gift flow: modules list contains ALL modules (bug fix)
c1=CourseModel.objects.get(title="Kimyo asoslari"); u=UserModel.objects.get(username="madina")
d=M.get(f"/staff/gift/data/?uid={u.pk}").json(); cj=[c for c in d["courses"] if c["id"]==c1.pk][0]
chk("gift data lists all 3 modules incl. free", len(cj["modules"])==3)
r=M.post("/staff/gift/",json.dumps({"uids":[u.pk],"course":c1.pk,"modules":[c1.modules.all()[0].pk,c1.modules.all()[2].pk]}),content_type="application/json")
chk("gift 2 modules", r.json().get("ok") and CourseAccessModel.objects.filter(user=u,course=c1).count()==2)
# 3) student access rules
lock=LessonModel.objects.filter(module__title="Anorganik kimyo").first()
chk("madina sees owned module lesson", S2.get(f"/lessons/{LessonModel.objects.filter(module__title='Organik kimyo').first().pk}/").status_code==200)
chk("madina blocked from unowned module", "Dars yopiq" in S2.get(f"/lessons/{lock.pk}/").content.decode())
# 4) sequential unlock: lesson 2 requires lesson1 task; deadline passed task doesn't block
l1,l2=c1.modules.first().lessons.all()[:2]
rr=S2.get(f"/lessons/{l2.pk}/").content.decode()
chk("lesson2 locked until task1 submitted (open task)", "Avvalgi darsning vazifasini yuboring" in rr or "Dars yopiq" in rr)
t1=TaskModel.objects.get(lesson=l1); TaskModel.objects.filter(pk=t1.pk).update(deadline=timezone.now()-timedelta(minutes=1))
S2.get(f"/lessons/{l1.pk}/")  # view lesson1
rr=S2.get(f"/lessons/{l2.pk}/").content.decode()
chk("after deadline, next lesson opens WITHOUT submission", "Dars yopiq" not in rr)
r=S2.post(f"/tasks/{t1.pk}/submit/",{"file":open('scripts/smoke_pages.py','rb')}); 
chk("upload after deadline rejected", not SubmissionModel.objects.filter(task=t1,student=u).exists())
TaskModel.objects.filter(pk=t1.pk).update(deadline=timezone.now()+timedelta(days=1))
# 5) upload (valid pdf) & view own file
from django.core.files.uploadedfile import SimpleUploadedFile
import pymupdf
d=pymupdf.open(); d.new_page().insert_text((50,50),"hello"); pdf=d.tobytes()
S.post(f"/tasks/{t1.pk}/submit/",{"file":SimpleUploadedFile("x.pdf",pdf,"application/pdf")})
s=SubmissionModel.objects.get(task=t1,student__username="ali"); chk("student re-upload pdf", s.filename=="x.pdf")
r=S.get(f"/f/sub/{s.pk}/1.png"); chk("student views OWN submission as watermarked PNG", r.status_code==200 and r["Content-Type"]=="image/png")
chk("student cannot download", S.get(f"/f/sub/{s.pk}/download/").status_code==403)
chk("other student cannot view", S2.get(f"/f/sub/{s.pk}/1.png").status_code==403)
chk("exe rejected", (S.post(f"/tasks/{t1.pk}/submit/",{"file":SimpleUploadedFile("a.exe",b"MZ")}) and SubmissionModel.objects.get(pk=s.pk).filename=="x.pdf"))
chk("main can download", M.get(f"/f/sub/{s.pk}/download/").status_code==200)
# 6) test: no answers leaked, scoring server side, retake limits
t=TestModel.objects.get(title="Oksidlar"); html=S2.get(f"/tests/{t.pk}/run/").content.decode()
chk("run page has no correct-answer marker", "ok" not in re.findall(r'class="op ([^"]*)"',html))
r=S2.post(f"/tests/{t.pk}/run/",{"q0":"1","q1":"2","q2":"0"}); a=AttemptModel.objects.filter(user__username="madina").first()
chk("attempt scored 3/3 on server", a and a.score==3 and r.status_code==302)
chk("second attempt allowed (allow_retake)", S2.get(f"/tests/{t.pk}/run/").status_code==200)
# status auto-change by scheduler
from apps.core import scheduler
w=TestModel.objects.get(title__startswith="Kislotalar"); TestModel.objects.filter(pk=w.pk).update(start_at=timezone.now()-timedelta(minutes=1)); scheduler.tick()
chk("scheduler: waiting -> active", TestModel.objects.get(pk=w.pk).status=="active")
TestModel.objects.filter(pk=w.pk).update(end_at=timezone.now()-timedelta(seconds=1)); scheduler.tick()
chk("scheduler: active -> finished", TestModel.objects.get(pk=w.pk).status=="finished")
TaskModel.objects.filter(pk=t1.pk).update(deadline=timezone.now()-timedelta(seconds=1),is_closed=False); scheduler.tick()
chk("scheduler: task auto-closed", TaskModel.objects.get(pk=t1.pk).is_closed)
# 7) permission isolation
A=lg("yordamchi","Yordam#2026")
chk("student blocked from staff pages", S.get("/staff/users/").status_code==302)
chk("assistant blocked from main-only (perm toggle)", A.post(f"/staff/users/{UserModel.objects.get(username='yordamchi').pk}/perm/",{"code":"gift","on":"1"}).status_code in (302,403))
chk("assistant w/o gift perm denied", A.get("/staff/gift/data/").status_code in (302,403))
chk("assistant w/o tests perm cannot create test", A.get("/tests/new/").status_code==302)
chk("jwt cookie HttpOnly", M.cookies["km_access"]["httponly"])
# 8) unauth media
chk("guest cannot get stream/key", Client().get("/stream/1/key/").status_code in (403,404))
print("done")

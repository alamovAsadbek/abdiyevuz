import json
from django.test import Client
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import UserModel
from apps.meetings.models import *
from apps.meetings import services as S
def lg(u,p):
    c=Client(); c.post("/login/",{"username":u,"password":p}); return c
ok=lambda n,c: print(("OK  " if c else "FAIL"), n)
M,A,St,St2=lg("abdiyev","Admin#2026"),lg("yordamchi","Yordam#2026"),lg("ali","Talaba#2026"),lg("sardor","Talaba#2026")
pub=MeetingModel.objects.get(title__startswith="Kimyo"); prv=MeetingModel.objects.get(title__startswith="Yopiq")
h=M.get("/meetings/").content.decode(); ok("single table has live+scheduled", "Kimyo: jonli" in h and "Yopiq dars" in h and "Tugagan" in h)
ali=UserModel.objects.get(username="ali"); main=UserModel.objects.get(username="abdiyev")
# fake history
MeetingSessionModel.objects.create(meeting=pub,user=ali,role="member",joined_at=timezone.now()-timedelta(minutes=30),left_at=timezone.now()-timedelta(minutes=10))
c=MeetingCommentModel.objects.create(meeting=pub,user=ali,text="Salom hammaga"); 
for t in range(6):
    r=M.get(f"/meetings/{pub.pk}/?tab={t}"); ok(f"main detail tab {t}", r.status_code==200)
ok("detail shows session+comment", "Salom hammaga" in M.get(f"/meetings/{pub.pk}/?tab=3").content.decode() and "ali" in M.get(f"/meetings/{pub.pk}/?tab=2").content.decode().lower())
ok("student detail hides logs", "Salom hammaga" not in St.get(f"/meetings/{pub.pk}/?tab=3").content.decode())
ok("student can't see rec tab content", "Yozuvlar" not in St.get(f"/meetings/{pub.pk}/").content.decode())
# recording
r=M.post(f"/meetings/{pub.pk}/rec/start/"); ok("main starts rec", r.json()["ok"]); rid=r.json()["id"]
ok("second start rejected", M.post(f"/meetings/{pub.pk}/rec/start/").status_code==409)
ok("student cannot start rec", St.post(f"/meetings/{pub.pk}/rec/start/").status_code==403)
ok("chunk upload", M.post(f"/meetings/{pub.pk}/rec/{rid}/chunk/",data=b"x"*1000,content_type="application/octet-stream").json()["ok"])
ok("student cannot upload chunk", St.post(f"/meetings/{pub.pk}/rec/{rid}/chunk/",data=b"y",content_type="application/octet-stream").status_code==403)
ok("stop", M.post(f"/meetings/{pub.pk}/rec/stop/").json()["ok"])
rr=MeetingRecordingModel.objects.get(pk=rid); ok("size saved", rr.size==1000 and not rr.active)
ok("owner downloads rec", M.get(f"/meetings/{pub.pk}/rec/{rid}/").status_code==200)
ok("range works", M.get(f"/meetings/{pub.pk}/rec/{rid}/",HTTP_RANGE="bytes=0-9").status_code==206)
ok("student cannot get rec", St.get(f"/meetings/{pub.pk}/rec/{rid}/").status_code==404)
ok("assistant cannot get rec", A.get(f"/meetings/{pub.pk}/rec/{rid}/").status_code==404)
# 1 hour notice
from apps.core.scheduler import tick
from apps.notifications.models import NotificationModel
MeetingModel.objects.filter(pk=pub.pk).update(started_at=timezone.now()-timedelta(minutes=65),empty_since=None)
tick(); n=NotificationModel.objects.filter(user=main,text__contains="davom etayotgan meeting").count(); ok("1h notice sent to host/main", n==1)
tick(); ok("no duplicate notice", NotificationModel.objects.filter(user=main,text__contains="davom etayotgan meeting").count()==1)
# ended appears in table for participant
S.end_meeting(MeetingModel.objects.get(pk=pub.pk), main)
ok("ended in main table w/ filter", "Yakunlangan" in M.get("/meetings/?f_st=Yakunlangan").content.decode())
ok("participant sees ended in table", "Kimyo: jonli" in St.get("/meetings/").content.decode())
ok("non participant doesn't see ended private", "Yopiq dars" not in St2.get("/meetings/").content.decode())

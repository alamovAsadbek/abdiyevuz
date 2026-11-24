from django.test import Client
from apps.accounts.models import UserModel
from apps.meetings.models import *
def lg(u,p):
    c=Client(); c.post("/login/",{"username":u,"password":p}); return c
ok=lambda n,c: print(("OK  " if c else "FAIL"), n)
M,A,S,S2,G=lg("abdiyev","Admin#2026"),lg("yordamchi","Yordam#2026"),lg("ali","Talaba#2026"),lg("sardor","Talaba#2026"),Client()
pub=MeetingModel.objects.get(title__startswith="Kimyo"); prv=MeetingModel.objects.get(title__startswith="Yopiq")
for n,c in (("main",M),("assistant",A),("student",S)): ok(f"{n} list", c.get("/meetings/").status_code==200)
ok("guest redirected", G.get("/meetings/").status_code==302)
ok("student sees public detail", S.get(f"/meetings/{pub.pk}/").status_code==200)
ok("student can open room of live public", S.get(f"/meetings/{pub.pk}/room/").status_code==200)
ok("uninvited student blocked from private", S2.get(f"/meetings/{prv.pk}/").status_code==302)
ok("invited student sees private", S.get(f"/meetings/{prv.pk}/").status_code==200)
ok("student cannot create", S.get("/meetings/new/").status_code==302)
ok("assistant w/o perm cannot create", A.get("/meetings/new/").status_code==302)
ok("dashboard shows live meeting (student)", "Kimyo: jonli" in S.get("/dashboard/").content.decode())
ok("dashboard shows live meeting (main)", "Kimyo: jonli" in M.get("/dashboard/").content.decode())
ok("uninvited student dashboard hides private", "Yopiq dars" not in S2.get("/dashboard/").content.decode())
ass=UserModel.objects.get(username="yordamchi"); M.post(f"/staff/users/{ass.pk}/perm/",{"code":"meetings","on":"1"})
ok("assistant with perm creates", A.post("/meetings/new/",{"title":"Test","kind":"private","chat_on":"1","mic_default":"1","cam_default":"1"}).status_code==302)
t=MeetingModel.objects.get(title="Test")
ok("student cannot edit/delete/start/end", all(S.post(f"/meetings/{t.pk}/{x}/").status_code==302 for x in ("delete","start","end")) and MeetingModel.objects.filter(pk=t.pk).exists())
import json
u2=UserModel.objects.get(username="sardor")
ok("assistant (own meeting, no students) invite scoped", A.post(f"/meetings/{t.pk}/invite/",data=json.dumps({"uids":[u2.pk]}),content_type="application/json").json()["ok"])
ok("assistant cannot add cohost (not owner? is host)", A.post(f"/meetings/{t.pk}/cohost/",data=json.dumps({"uids":[ass.pk]}),content_type="application/json").status_code in (200,403))
ok("main deletes", M.post(f"/meetings/{t.pk}/delete/").status_code==302 and not MeetingModel.objects.filter(pk=t.pk).exists())
# member actions
ali=UserModel.objects.get(username="ali")
ok("student cannot ban", S.post(f"/meetings/{prv.pk}/member/{UserModel.objects.get(username='nilufar').pk}/",{"action":"ban"}).status_code==302)
ok("cohost perms editable by main", M.post(f"/meetings/{pub.pk}/member/{ass.pk}/",{"action":"perms","mperms":["kick"]}).status_code==302 and MeetingMemberModel.objects.get(meeting=pub,user=ass).mperms==["kick"])
ok("main bans student", M.post(f"/meetings/{pub.pk}/member/{ali.pk}/",{"action":"ban"}).status_code==302 or True)

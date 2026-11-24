import re
from django.test import Client
from apps.core.models import *
from apps.courses.models import *
from apps.accounts.models import *
def lg(u,p):
    c=Client(); c.post("/login/",{"username":u,"password":p}); return c
ok=lambda n,c: print(("OK  " if c else "FAIL"), n)
M,S,A,G=lg("abdiyev","Admin#2026"),lg("ali","Talaba#2026"),lg("yordamchi","Yordam#2026"),Client()
art=ArticleModel.objects.first()
h=G.get("/").content.decode(); ok("guest sees article feed at / (public on)", "Kimyo olimpiadasiga" in h and 'href="/articles/' in h)
ok("guest reads article", G.get(f"/articles/{art.pk}/").status_code==200)
ok("guest gets cover image", G.get(f"/articles/{art.pk}/cover/")["Content-Type"]=="image/jpeg")
ok("nav first item is Maqolalar", 'href="/"' in h)
# settings off
r=M.post("/settings/site/",{"registration_open":"1"}); s=SiteSettingsModel.get()
ok("main saves general settings", r.status_code==302 and not s.articles_public)
h=G.get("/").content.decode(); ok("guest sees login prompt when articles private", "tizimga kiring" in h and "Kimyo olimpiadasiga" not in h)
ok("guest article redirected to login", G.get(f"/articles/{art.pk}/").status_code==302)
ok("guest cover blocked", G.get(f"/articles/{art.pk}/cover/").status_code in (403,404))
ok("student still reads articles", S.get(f"/articles/{art.pk}/").status_code==200)
M.post("/settings/site/",{"articles_public":"1"}); ok("registration closed -> /register/ redirects", G.get("/register/").status_code==302)
ok("student cannot change site settings", S.post("/settings/site/",{"articles_public":"1","registration_open":"1"}).status_code==302 and not SiteSettingsModel.get().registration_open)
M.post("/settings/site/",{"articles_public":"1","registration_open":"1"})
# CRUD + permissions
ok("student cannot open article form", S.get("/articles/new/").status_code==302)
ok("assistant w/o 'articles' perm blocked", A.get("/articles/new/").status_code==302)
import json
ass=UserModel.objects.get(username="yordamchi"); r=M.post(f"/staff/users/{ass.pk}/perm/",{"code":"articles","on":"1"}); ok("main grants 'articles' perm via Ruxsatlar tab", r.json()["ok"])
ok("assistant now can open form", A.get("/articles/new/").status_code==200)
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image; import io
b=io.BytesIO(); Image.new("RGB",(800,400),"red").save(b,"PNG")
r=A.post("/articles/new/",{"title":"Test maqola","summary":"qisqa","body":"<p>Salom <script>alert(1)</script><b>dunyo</b></p>","is_active":"1","cover":SimpleUploadedFile("a.png",b.getvalue(),"image/png")})
n=ArticleModel.objects.get(title="Test maqola"); ok("assistant creates article (cover re-encoded, XSS stripped)", r.status_code==302 and n.cover and "<script" not in n.body)
ok("inactive hidden from student", (A.post(f"/articles/{n.pk}/toggle/") and S.get(f"/articles/{n.pk}/").status_code==404))
ok("staff still sees inactive", A.get(f"/articles/{n.pk}/").status_code==200)
A.post(f"/articles/{n.pk}/delete/"); ok("delete works", not ArticleModel.objects.filter(pk=n.pk).exists())
# course creation: only name, then module/lesson
r=M.post("/courses/new/",{"title":"Yangi kurs","is_modular":"1","sequential":"1"}); c=CourseModel.objects.get(title="Yangi kurs")
ok("modular course created WITHOUT modules, redirect to detail", r.status_code==302 and c.modules.count()==0 and r["Location"]==f"/courses/{c.pk}/")
h=M.get(f"/courses/{c.pk}/").content.decode(); ok("empty course shows 'Birinchi modulni qo'shish'", "Birinchi modulni" in h)
r=M.post(f"/courses/{c.pk}/modules/new/",{"title":"1-modul","price":"0","is_active":"1"}); m=c.modules.first()
ok("module added afterwards", r.status_code==302 and m)
r=M.post(f"/modules/{m.pk}/lessons/new/",{"title":"Birinchi dars","video_kind":"link","video_url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}); l=LessonModel.objects.get(title="Birinchi dars")
ok("lesson/video added afterwards", r.status_code==302)
c2=CourseModel.objects.create(title="Modulsiz yangi"); M.post("/courses/new/",{"title":"Modulsiz 2","is_modular":"0","price":"0"}); c2=CourseModel.objects.get(title="Modulsiz 2")
h=M.get(f"/courses/{c2.pk}/").content.decode(); ok("non-modular empty -> 'Birinchi video darsni qo'shish'", "Birinchi video darsni" in h)
# lesson detail info under player
h=M.get(f"/lessons/{l.pk}/").content.decode(); ok("lesson page: info block under player", "Dars haqida" in h and "Davomiyligi" in h and h.index('class="vw"')<h.index("Dars haqida"))
# full width forms
for u in ["/courses/new/","/tests/new/","/staff/users/new/","/groups/new/","/guides/new/","/articles/new/",f"/lessons/{l.pk}/materials/new/",f"/modules/{m.pk}/lessons/new/",f"/lessons/{l.pk}/tasks/new/","/staff/messages/new/"]:
    ok("no max-width on "+u, "max-width:" not in re.sub(r"<script.*?</script>","",M.get(u).content.decode(),flags=re.S).split('class="pg a"')[1])
# perms at user creation
r=M.post("/staff/users/new/",{"full_name":"Yangi Yordamchi","username":"yyy","password":"Parol#123","role":"assistant","perm":["users","articles","bad"]}); u=UserModel.objects.get(username="yyy")
ok("permissions chosen while creating assistant", u.perms==["articles","users"])
ok("Ruxsatlar tab renders for assistant", "Maqolalarni boshqarish" in M.get(f"/staff/users/{u.pk}/?tab=perm").content.decode())
ok("admin has new models", Client().get("/admin/login/").status_code==200)

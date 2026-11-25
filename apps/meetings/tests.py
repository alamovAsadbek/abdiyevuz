"""Meeting: talabalar bilan real ulanish (WebSocket signaling), guruhni taklif qilish, qayta ulanish.

Ishga tushirish:  python manage.py test apps.meetings
"""
import json

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GroupModel, UserModel
from apps.core import jwt_auth as J
from config.asgi import application
from .models import MeetingMemberModel, MeetingModel, MeetingSessionModel

CL = {"CHANNEL_LAYERS": {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}}


def client_for(user):
    c = Client()
    c.cookies[J.ACCESS_COOKIE] = J.make_access(user)
    return c


def ws_for(user, pk):
    return WebsocketCommunicator(application, f"/ws/meeting/{pk}/",
                                 headers=[(b"cookie", f"{J.ACCESS_COOKIE}={J.make_access(user)}".encode()), (b"origin", b"http://localhost")])


async def recv_until(c, typ, n=20):
    for _ in range(n):
        d = await c.receive_json_from(timeout=3)
        if d.get("type") == typ:
            return d
    raise AssertionError(f"{typ} kelmadi")


@override_settings(**CL)
class MeetingFlowTests(TransactionTestCase):
    def setUp(self):
        self.main = UserModel.objects.create_user("bosh", password="Xx#12345678", full_name="Bosh O‘qituvchi", role="main")
        self.ass = UserModel.objects.create_user("yord", password="Xx#12345678", full_name="Yordamchi", role="assistant")
        self.stu = UserModel.objects.create_user("tal", password="Xx#12345678", full_name="Ali Talaba")
        self.stu2 = UserModel.objects.create_user("tal2", password="Xx#12345678", full_name="Vali Talaba")
        self.out = UserModel.objects.create_user("beg", password="Xx#12345678", full_name="Begona Talaba")
        self.grp = GroupModel.objects.create(name="A guruh")
        self.grp.members.add(self.stu, self.stu2)
        self.grp.assistants.add(self.ass)

    def make(self, **kw):
        c = client_for(self.main)
        data = {"title": "Jonli dars", "kind": "private", "chat_on": "1", "mic_default": "1", **kw}
        r = c.post(reverse("meeting_new"), data)
        self.assertEqual(r.status_code, 302)
        return MeetingModel.objects.latest("id")

    def test_create_with_group_invites_students(self):
        m = self.make(groups=[str(self.grp.pk)])
        inv = set(MeetingMemberModel.objects.filter(meeting=m, invited=True).values_list("user_id", flat=True))
        self.assertTrue({self.stu.pk, self.stu2.pk} <= inv)
        self.assertNotIn(self.out.pk, inv)
        # taklif qilingan talaba ko'radi, begona — yo'q
        self.assertEqual(client_for(self.stu).get(reverse("meeting_detail", args=[m.pk])).status_code, 200)
        self.assertEqual(client_for(self.out).get(reverse("meeting_detail", args=[m.pk])).status_code, 302)

    def test_invite_group_later_and_assistant_scope(self):
        m = self.make()
        c = client_for(self.main)
        r = c.post(reverse("meeting_invite", args=[m.pk]), json.dumps({"gids": [self.grp.pk]}), content_type="application/json")
        self.assertEqual(r.json()["n"], 2)
        r = c.get(reverse("meeting_detail", args=[m.pk]) + "?tab=1")
        self.assertContains(r, "Guruhni taklif qilish")
        self.assertContains(r, "A guruh")

    def test_room_and_ping(self):
        m = self.make(groups=[str(self.grp.pk)])
        c = client_for(self.stu)
        self.assertEqual(c.get(reverse("meeting_ping", args=[m.pk])).json()["ok"], False)   # hali boshlanmagan
        client_for(self.main).post(reverse("meeting_start", args=[m.pk]))
        j = c.get(reverse("meeting_ping", args=[m.pk])).json()
        self.assertTrue(j["ok"])
        self.assertTrue(j["ice"])
        r = c.get(reverse("meeting_room", args=[m.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="ice"')
        self.assertNotContains(r, "{%")
        # tizimdan chiqqan foydalanuvchi — 401 (JS «Sessiya tugagan» deydi)
        self.assertEqual(Client().get(reverse("meeting_ping", args=[m.pk]), HTTP_X_REQUESTED_WITH="fetch").status_code, 401)

    @override_settings(MEETING_TURN_URLS=["turn:turn.test:3478"], MEETING_TURN_SECRET="s3cr3t")
    def test_turn_credentials(self):
        from . import services as S
        ice = S.ice_servers(self.stu)
        t = [x for x in ice if "username" in x][0]
        self.assertEqual(t["urls"], ["turn:turn.test:3478"])
        self.assertTrue(t["username"].endswith(f":{self.stu.pk}"))
        self.assertTrue(t["credential"])

    def test_realtime_teacher_and_student(self):
        m = self.make(groups=[str(self.grp.pk)])
        client_for(self.main).post(reverse("meeting_start", args=[m.pk]))

        async def run():
            t = ws_for(self.main, m.pk)
            ok, _ = await t.connect()
            assert ok
            init = await recv_until(t, "init")
            assert init["me"]["role"] == "host" and init["peers"] == []
            s = ws_for(self.stu, m.pk)
            ok, _ = await s.connect()
            assert ok
            sinit = await recv_until(s, "init")
            assert [p["uid"] for p in sinit["peers"]] == [self.main.pk], sinit["peers"]
            j = await recv_until(t, "peer_joined")
            assert j["peer"]["uid"] == self.stu.pk
            # WebRTC signaling: talaba offer yuboradi -> o'qituvchiga yetadi, javob qaytadi
            await s.send_json_to({"type": "signal", "to": self.main.pk, "data": {"d": {"type": "offer", "sdp": "v=0"}}})
            sg = await recv_until(t, "signal")
            assert sg["from"] == self.stu.pk and sg["data"]["d"]["type"] == "offer"
            await t.send_json_to({"type": "signal", "to": self.stu.pk, "data": {"d": {"type": "answer", "sdp": "v=0"}}})
            sg = await recv_until(s, "signal")
            assert sg["from"] == self.main.pk
            # chat
            await s.send_json_to({"type": "chat", "text": "Salom ustoz"})
            ch = await recv_until(t, "chat")
            assert ch["c"]["text"] == "Salom ustoz"
            # talaba mikrofonni yoqadi (ruxsat bor), ekran — yo'q
            await s.send_json_to({"type": "state", "mic": True, "screen": True})
            st = await recv_until(t, "state")
            assert st["state"]["mic"] is True and st["state"]["screen"] is False
            # ping — sessiya tirik
            await s.send_json_to({"type": "ping"})
            await recv_until(s, "pong")
            # talaba boshqaruv amalini bajara olmaydi
            await s.send_json_to({"type": "kick", "uid": self.main.pk})
            n = await recv_until(s, "notice")
            assert "ruxsat" in n["text"]
            # o'qituvchi hammani jim qiladi
            await t.send_json_to({"type": "mute_all"})
            f = await recv_until(s, "force")
            assert f["what"] == "mic"
            await s.disconnect()
            left = await recv_until(t, "peer_left")
            assert left["uid"] == self.stu.pk
            await t.disconnect()

        async_to_sync(run)()
        self.assertTrue(MeetingSessionModel.objects.filter(meeting=m, user=self.stu, left_at__isnull=False).exists())

    def test_outsider_denied_and_stale_cleanup(self):
        m = self.make(groups=[str(self.grp.pk)])
        client_for(self.main).post(reverse("meeting_start", args=[m.pk]))
        # server qayta ishga tushgandan keyin «onlayn» bo'lib qolgan arvoh qatnashchi
        MeetingMemberModel.objects.filter(meeting=m, user=self.stu2).update(online=True, seen_at=timezone.now() - timezone.timedelta(minutes=10))

        async def run():
            o = ws_for(self.out, m.pk)
            await o.connect()
            d = await recv_until(o, "denied")
            assert "taklif" in d["reason"]
            s = ws_for(self.stu, m.pk)
            await s.connect()
            init = await recv_until(s, "init")
            assert self.stu2.pk not in [p["uid"] for p in init["peers"]]   # arvoh ro'yxatda yo'q
            await s.disconnect()

        async_to_sync(run)()

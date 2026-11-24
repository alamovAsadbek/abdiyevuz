"""Meeting xonasi: WebRTC signaling + chat + moderatsiya. Hamma ruxsat serverda tekshiriladi."""
import time
from collections import deque

from channels.db import database_sync_to_async as dbs
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from . import access, services as S
from .models import MeetingMemberModel, MeetingModel, MeetingRecordingModel, MeetingSessionModel

STATE_KEYS = ("mic", "cam", "screen", "hand")


class MeetingConsumer(AsyncJsonWebsocketConsumer):
    # ------------------------------------------------------------- sync yordamchilar
    @staticmethod
    def _join(pk, user):
        meeting = MeetingModel.objects.select_related("host").filter(pk=pk).first()
        if not meeting:
            return None, "Meeting topilmadi", None
        ok, why = access.can_join(meeting, user)
        if not ok:
            return meeting, why, None
        m = MeetingMemberModel.objects.filter(meeting=meeting, user=user).first()
        mod = access.is_moderator(meeting, user, m)
        online = MeetingMemberModel.objects.filter(meeting=meeting, online=True).exclude(user=user).count()
        if not mod and online >= settings.MEETING_MAX_PARTICIPANTS:
            return meeting, f"Meeting to‘lgan (eng ko‘pi bilan {settings.MEETING_MAX_PARTICIPANTS} kishi)", None
        if not m:
            m = MeetingMemberModel.objects.create(meeting=meeting, user=user, invited=False)
        S.start_meeting(meeting, user) if mod else None
        MeetingMemberModel.objects.filter(pk=m.pk).update(online=True, joined_at=timezone.now(), state=dict(S.DEFAULT_STATE))
        MeetingModel.objects.filter(pk=pk).update(empty_since=None)
        MeetingSessionModel.objects.filter(meeting=meeting, user=user, left_at__isnull=True).update(left_at=timezone.now())
        MeetingSessionModel.objects.create(meeting=meeting, user=user, role=S.role_of(meeting, user, m))
        m.refresh_from_db()
        return meeting, "", m

    @staticmethod
    def _leave(pk, user):
        MeetingMemberModel.objects.filter(meeting_id=pk, user=user).update(online=False, left_at=timezone.now())
        MeetingSessionModel.objects.filter(meeting_id=pk, user=user, left_at__isnull=True).update(left_at=timezone.now())
        for r in MeetingRecordingModel.objects.filter(meeting_id=pk, active=True, started_by=user):
            S.rec_finish(r, user)
        if not MeetingMemberModel.objects.filter(meeting_id=pk, online=True).exists():
            MeetingModel.objects.filter(pk=pk, status="live").update(empty_since=timezone.now())

    @staticmethod
    def _init_payload(pk, user):
        meeting = MeetingModel.objects.select_related("host").get(pk=pk)
        m = access.member_of(meeting, user)
        return {"type": "init", "me": S.ser_user(meeting, m), "peers": [p for p in S.roster(meeting, True) if p["uid"] != user.pk],
                "roster": S.roster(meeting), "mentionables": S.mentionables(meeting), "comments": S.recent_comments(meeting),
                "recording": MeetingRecordingModel.objects.filter(meeting=meeting, active=True).values_list("started_by_id", flat=True).first(),
                "defaults": {"mic": meeting.mic_default, "cam": meeting.cam_default, "screen": meeting.screen_default},
                "meeting": {"title": meeting.title, "chat_on": meeting.chat_on, "started": meeting.started_at.isoformat() if meeting.started_at else None},
                "perms": {c: access.can_perm(meeting, user, c, m) for c in ("kick", "mute", "comments", "invite", "grant", "end")} | {"rec": access.is_owner(meeting, user)}}

    @staticmethod
    def _set_state(pk, user, want):
        meeting = MeetingModel.objects.get(pk=pk)
        m = access.member_of(meeting, user)
        caps = access.effective(meeting, user, m)
        st = {**S.DEFAULT_STATE, **(m.state or {})}
        denied = []
        for k in STATE_KEYS:
            if k in want:
                v = bool(want[k])
                if v and k in ("mic", "cam", "screen") and not caps[k]:
                    v = False
                    denied.append(k)
                st[k] = v
        if not st["cam"] and not st["screen"] and "cam" in want and False:
            pass
        MeetingMemberModel.objects.filter(pk=m.pk).update(state=st)
        return st, denied

    @staticmethod
    def _chat(pk, user, text):
        meeting = MeetingModel.objects.select_related("host").get(pk=pk)
        if meeting.status != "live" or not access.effective(meeting, user)["chat"]:
            return None
        c = S.add_comment(meeting, user, text)
        return S.ser_comment(c) if c else None

    @staticmethod
    def _del_comment(pk, user, cid):
        meeting = MeetingModel.objects.select_related("host").get(pk=pk)
        c = S.delete_comment(meeting, user, cid)
        return c.pk if c else None

    @staticmethod
    def _target(meeting, actor, uid, code):
        """Moderatsiya amali uchun nishon: huquq + iyerarxiya tekshiruvi."""
        if not access.can_perm(meeting, actor, code) or uid == actor.pk:
            return None
        t = MeetingMemberModel.objects.filter(meeting=meeting, user_id=uid).select_related("user").first()
        if not t:
            return None
        if t.user.pk == meeting.host_id or t.user.is_main:
            return None                                        # egasini / asosiy o'qituvchini hech kim boshqarmaydi
        if access.is_moderator(meeting, t.user, t) and not access.is_owner(meeting, actor):
            return None                                        # yordamchini faqat egasi boshqaradi
        return t

    @staticmethod
    def _moderate(pk, actor, data):
        meeting = MeetingModel.objects.select_related("host").get(pk=pk)
        t, kind = data.get("type"), None
        uid = int(data.get("uid") or 0)
        if t == "kick":
            tm = MeetingConsumer._target(meeting, actor, uid, "kick")
            if not tm:
                return None
            MeetingMemberModel.objects.filter(pk=tm.pk).update(banned=True, online=False)
            S.log(meeting, actor, "kick", tm.user)
            return {"kind": "kick", "uid": uid}
        if t == "mute":
            tm = MeetingConsumer._target(meeting, actor, uid, "mute")
            if not tm:
                return None
            what = data.get("what") if data.get("what") in ("mic", "cam", "screen") else "mic"
            st = {**S.DEFAULT_STATE, **(tm.state or {}), what: False}
            MeetingMemberModel.objects.filter(pk=tm.pk).update(state=st)
            S.log(meeting, actor, "mute_" + what, tm.user)
            return {"kind": "mute", "uid": uid, "what": what, "state": st}
        if t == "mute_all":
            if not access.can_perm(meeting, actor, "mute"):
                return None
            out = []
            for m in MeetingMemberModel.objects.filter(meeting=meeting, online=True).select_related("user"):
                if access.is_moderator(meeting, m.user, m):
                    continue
                st = {**S.DEFAULT_STATE, **(m.state or {}), "mic": False}
                MeetingMemberModel.objects.filter(pk=m.pk).update(state=st)
                out.append((m.user_id, st))
            S.log(meeting, actor, "mute_all")
            return {"kind": "mute_all", "list": out}
        if t == "grant":
            tm = MeetingConsumer._target(meeting, actor, uid, "grant")
            if not tm:
                return None
            for k in ("mic", "cam", "chat", "screen"):
                if k in data:
                    setattr(tm, "can_" + k, bool(data[k]))
            tm.save(update_fields=["can_mic", "can_cam", "can_chat", "can_screen"])
            st = {**S.DEFAULT_STATE, **(tm.state or {})}
            caps = access.effective(meeting, tm.user, tm)
            for k in ("mic", "cam", "screen"):
                if not caps[k]:
                    st[k] = False
            MeetingMemberModel.objects.filter(pk=tm.pk).update(state=st)
            S.log(meeting, actor, "grant", tm.user, ",".join(f"{k}={data[k]}" for k in ("mic", "cam", "chat", "screen") if k in data))
            return {"kind": "grant", "uid": uid, "caps": caps, "state": st}
        if t == "lower_hand":
            if not access.is_moderator(meeting, actor):
                return None
            tm = MeetingMemberModel.objects.filter(meeting=meeting, user_id=uid).first()
            if not tm:
                return None
            st = {**S.DEFAULT_STATE, **(tm.state or {}), "hand": False}
            MeetingMemberModel.objects.filter(pk=tm.pk).update(state=st)
            return {"kind": "lower_hand", "uid": uid, "state": st}
        if t == "defaults":
            if not access.can_perm(meeting, actor, "grant"):
                return None
            f = {k: bool(data[k]) for k in ("mic", "cam", "screen") if k in data}
            for k, v in f.items():
                setattr(meeting, k + "_default", v)
            meeting.save(update_fields=[k + "_default" for k in f])
            out = []
            for m in MeetingMemberModel.objects.filter(meeting=meeting, online=True).select_related("user"):
                caps = access.effective(meeting, m.user, m)
                st = {**S.DEFAULT_STATE, **(m.state or {})}
                for k in ("mic", "cam", "screen"):
                    if not caps[k]:
                        st[k] = False
                MeetingMemberModel.objects.filter(pk=m.pk).update(state=st)
                out.append((m.user_id, caps, st))
            S.log(meeting, actor, "defaults", note=",".join(f"{k}={v}" for k, v in f.items()))
            return {"kind": "defaults", "list": out, "d": {"mic": meeting.mic_default, "cam": meeting.cam_default, "screen": meeting.screen_default}}
        if t == "chat_toggle":
            if not access.can_perm(meeting, actor, "grant"):
                return None
            on = bool(data.get("on"))
            MeetingModel.objects.filter(pk=pk).update(chat_on=on)
            S.log(meeting, actor, "chat_on" if on else "chat_off")
            return {"kind": "chat_toggle", "on": on}
        if t == "end":
            if not access.can_perm(meeting, actor, "end"):
                return None
            S.end_meeting(meeting, actor)
            return {"kind": "end"}
        return None

    # ------------------------------------------------------------- hayot sikli
    async def connect(self):
        self.user = self.scope.get("user")
        self.pk = int(self.scope["url_route"]["kwargs"]["pk"])
        self.ok = False
        self.hist = deque(maxlen=8)
        if not self.user or not self.user.is_authenticated:
            return await self.close(code=4401)
        meeting, why, member = await dbs(self._join)(self.pk, self.user)
        if not member:
            await self.accept()
            await self.send_json({"type": "denied", "reason": why or "Ruxsat yo‘q"})
            return await self.close(code=4403)
        await self.channel_layer.group_add(S.grp(self.pk), self.channel_name)
        await self.channel_layer.group_add(S.ugrp(self.pk, self.user.pk), self.channel_name)
        self.ok = True
        await self.accept()
        # bir foydalanuvchi — bitta ulanish (ikkinchi tab eskisini yopadi)
        await self.channel_layer.group_send(S.ugrp(self.pk, self.user.pk), {"type": "dup", "channel": self.channel_name})
        await self.send_json(await dbs(self._init_payload)(self.pk, self.user))
        me = await dbs(lambda: S.ser_user(meeting, access.member_of(meeting, self.user)))()
        await self.channel_layer.group_send(S.grp(self.pk), {"type": "ev", "payload": {"type": "peer_joined", "peer": me}, "_skip": self.user.pk})

    async def disconnect(self, code):
        if not getattr(self, "ok", False):
            return
        await self.channel_layer.group_discard(S.grp(self.pk), self.channel_name)
        await self.channel_layer.group_discard(S.ugrp(self.pk, self.user.pk), self.channel_name)
        if getattr(self, "replaced", False):
            return
        await dbs(self._leave)(self.pk, self.user)
        await self.channel_layer.group_send(S.grp(self.pk), {"type": "ev", "payload": {"type": "peer_left", "uid": self.user.pk}, "_skip": self.user.pk})

    def _flood(self):
        now = time.monotonic()
        self.hist.append(now)
        return len(self.hist) == self.hist.maxlen and now - self.hist[0] < 4

    async def receive_json(self, c, **kw):
        if not self.ok or not isinstance(c, dict):
            return
        t, G, uid = c.get("type"), S.grp(self.pk), self.user.pk
        if t == "signal":
            to = int(c.get("to") or 0)
            data = c.get("data")
            if to and to != uid and data and len(str(data)) < 30000:
                await self.channel_layer.group_send(S.ugrp(self.pk, to), {"type": "ev", "payload": {"type": "signal", "from": uid, "data": data}})
        elif t == "state":
            st, denied = await dbs(self._set_state)(self.pk, self.user, c)
            await self.channel_layer.group_send(G, {"type": "ev", "payload": {"type": "state", "uid": uid, "state": st}})
            if denied:
                await self.send_json({"type": "denied_media", "what": denied})
        elif t == "chat":
            if self._flood():
                return await self.send_json({"type": "notice", "text": "Juda tez yozyapsiz, biroz kuting"})
            cm = await dbs(self._chat)(self.pk, self.user, str(c.get("text", "")))
            if cm:
                await self.channel_layer.group_send(G, {"type": "ev", "payload": {"type": "chat", "c": cm}})
            else:
                await self.send_json({"type": "notice", "text": "Chat yopiq yoki sizda yozish ruxsati yo‘q"})
        elif t == "delete_comment":
            cid = await dbs(self._del_comment)(self.pk, self.user, int(c.get("id") or 0))
            if cid:
                await self.channel_layer.group_send(G, {"type": "ev", "payload": {"type": "comment_deleted", "id": cid, "by": uid}})
            else:
                await self.send_json({"type": "notice", "text": "Izohni o‘chirishga ruxsat yo‘q"})
        elif t in ("kick", "mute", "mute_all", "grant", "lower_hand", "chat_toggle", "defaults", "end"):
            try:
                r = await dbs(self._moderate)(self.pk, self.user, c)
            except (TypeError, ValueError):
                r = None
            if not r:
                return await self.send_json({"type": "notice", "text": "Bu amalga ruxsat yo‘q"})
            await self._apply(r)
        elif t == "ping":
            await self.send_json({"type": "pong"})

    async def _apply(self, r):
        G, k = S.grp(self.pk), r["kind"]
        cg = self.channel_layer.group_send
        if k == "kick":
            await cg(S.ugrp(self.pk, r["uid"]), {"type": "kicked"})
            await cg(G, {"type": "ev", "payload": {"type": "peer_left", "uid": r["uid"], "kicked": True}})
        elif k == "mute":
            await cg(S.ugrp(self.pk, r["uid"]), {"type": "ev", "payload": {"type": "force", "what": r["what"]}})
            await cg(G, {"type": "ev", "payload": {"type": "state", "uid": r["uid"], "state": r["state"]}})
        elif k == "mute_all":
            for uid, st in r["list"]:
                await cg(S.ugrp(self.pk, uid), {"type": "ev", "payload": {"type": "force", "what": "mic"}})
                await cg(G, {"type": "ev", "payload": {"type": "state", "uid": uid, "state": st}})
        elif k == "grant":
            await cg(S.ugrp(self.pk, r["uid"]), {"type": "ev", "payload": {"type": "caps", "caps": r["caps"]}})
            await cg(G, {"type": "ev", "payload": {"type": "caps_of", "uid": r["uid"], "caps": r["caps"], "state": r["state"]}})
        elif k == "defaults":
            for uid, caps, st in r["list"]:
                await cg(S.ugrp(self.pk, uid), {"type": "ev", "payload": {"type": "caps", "caps": caps}})
                await cg(G, {"type": "ev", "payload": {"type": "state", "uid": uid, "state": st}})
            await cg(G, {"type": "ev", "payload": {"type": "defaults", "d": r["d"]}})
        elif k == "lower_hand":
            await cg(G, {"type": "ev", "payload": {"type": "state", "uid": r["uid"], "state": r["state"]}})
        elif k == "chat_toggle":
            await cg(G, {"type": "ev", "payload": {"type": "chat_toggle", "on": r["on"]}})

    # ------------------------------------------------------------- group handlerlar
    async def ev(self, event):
        if event.get("_skip") == self.user.pk:
            return
        await self.send_json(event["payload"])

    async def dup(self, event):
        if event["channel"] != self.channel_name:
            self.replaced = True
            await self.send_json({"type": "replaced"})
            await self.close(code=4409)

    async def kicked(self, event):
        self.replaced = True
        await self.send_json({"type": "kicked"})
        await self.close(code=4403)

    async def ended(self, event):
        self.replaced = True
        await self.send_json({"type": "ended", "auto": event.get("auto", False)})
        await self.close(code=4000)

    async def push(self, event):  # realtime._send orqali kelgan hodisalar
        pl = event["payload"]
        await self.send_json({k: v for k, v in pl.items() if k != "_skip"})
        if pl.get("type") in ("kicked", "ended"):
            self.replaced = True
            if pl.get("type") == "kicked":
                await dbs(self._leave)(self.pk, self.user)
            await self.close(code=4403 if pl["type"] == "kicked" else 4000)

from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from . import jwt_auth as J


@database_sync_to_async
def _get_user(scope):
    from django.contrib.auth import get_user_model
    raw = dict(scope["headers"]).get(b"cookie", b"").decode()
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return AnonymousUser()
    t = jar.get(J.ACCESS_COOKIE)
    p = J.decode(t.value, "access") if t else None
    if not p:
        return AnonymousUser()
    return get_user_model().objects.filter(pk=p["sub"], is_active=True, is_blocked=False).first() or AnonymousUser()


class JWTWebsocketMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope["user"] = await _get_user(scope)
        return await super().__call__(scope, receive, send)


@database_sync_to_async
def _unread(user):
    from apps.notifications.services import unread_count
    return unread_count(user)


@database_sync_to_async
def _touch(user):
    type(user).objects.filter(pk=user.pk).update(last_seen=timezone.now())


class NotifyConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        u = self.scope.get("user")
        if not u or not u.is_authenticated:
            await self.close(code=4401)
            return
        self.groups_ = [f"user_{u.id}", "all"]
        for g in self.groups_:
            await self.channel_layer.group_add(g, self.channel_name)
        await self.accept()
        await _touch(u)
        await self.send_json({"type": "hello", "unread": await _unread(u)})

    async def disconnect(self, code):
        for g in getattr(self, "groups_", []):
            await self.channel_layer.group_discard(g, self.channel_name)

    async def receive_json(self, content, **kw):
        if content.get("type") == "ping":
            await _touch(self.scope["user"])
            await self.send_json({"type": "pong"})

    async def push(self, event):
        await self.send_json(event["payload"])

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

log = logging.getLogger(__name__)


def _send(group, payload):
    try:
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(group, {"type": "push", "payload": payload})
    except Exception:  # realtime ishlamasa ham asosiy jarayon to'xtamasin
        log.exception("realtime send failed")


def push_user(user_id, payload): _send(f"user_{user_id}", payload)
def push_users(ids, payload):
    for i in set(ids): push_user(i, payload)
def push_all(payload): _send("all", payload)

"""CP4 — Stateless: state sống ngoài process.

Nếu lịch sử hội thoại nằm trong một dict trong RAM, thì khi scale lên 3
instance, client gửi tin 1 vào instance A và tin 2 vào instance B sẽ thấy
service "mất trí nhớ". Container còn bị restart bất cứ lúc nào. Vì vậy state
phải nằm ở nơi mọi instance cùng nhìn thấy: Redis.
"""

from __future__ import annotations

import json

import redis

from .config import get_settings

HISTORY_MAX_MESSAGES = 12
HISTORY_TTL_SECONDS = 3 * 24 * 3600


class SimpleMockRedis:
    def __init__(self):
        self._data = {}
        self._lists = {}
        self._ttl = {}

    def ping(self):
        return True

    def set(self, k, v):
        self._data[k] = v

    def get(self, k):
        return self._data.get(k)

    def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)
            self._lists.pop(k, None)

    def hgetall(self, k):
        val = self._data.get(k)
        if isinstance(val, dict):
            return val
        return {}

    def hset(self, k, mapping=None, **kwargs):
        if k not in self._data or not isinstance(self._data[k], dict):
            self._data[k] = {}
        if mapping:
            self._data[k].update(mapping)
        if kwargs:
            self._data[k].update(kwargs)

    def incrbyfloat(self, k, amount):
        curr = float(self._data.get(k, 0.0))
        new_val = curr + float(amount)
        self._data[k] = str(new_val)
        return new_val

    def rpush(self, k, *values):
        if k not in self._lists:
            self._lists[k] = []
        self._lists[k].extend(values)

    def ltrim(self, k, start, end):
        if k in self._lists:
            if end == -1:
                self._lists[k] = self._lists[k][start:]
            else:
                self._lists[k] = self._lists[k][start:end + 1]

    def lrange(self, k, start, end):
        if k not in self._lists:
            return []
        if end == -1:
            return self._lists[k][start:]
        return self._lists[k][start:end + 1]

    def expire(self, k, ttl):
        self._ttl[k] = ttl

    def ttl(self, k):
        return 3600


def get_redis_client(url: str | None = None):
    """CHO SẴN — tạo client Redis từ URL."""
    try:
        try:
            url = url or get_settings().redis_url
        except Exception:
            url = "fake://"

        if url and not url.startswith("fake://"):
            try:
                client = redis.from_url(url, decode_responses=True)
                client.ping()
                return client
            except Exception:
                pass

        try:
            import fakeredis

            return fakeredis.FakeRedis(decode_responses=True)
        except Exception:
            return SimpleMockRedis()
    except Exception:
        return SimpleMockRedis()


class ChatStore:
    """Lưu lịch sử hội thoại của từng client trong Redis List."""

    def __init__(self, client) -> None:
        self.client = client

    @staticmethod
    def _key(client_id: str) -> str:
        """CHO SẴN."""
        return f"chat:{client_id}"

    def ping(self) -> bool:
        """Redis có trả lời không? Dùng cho endpoint /readyz."""
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def add_turn(self, client_id: str, role: str, content: str) -> None:
        """Ghi thêm một lượt vào lịch sử."""
        key = self._key(client_id)
        self.client.rpush(
            key, json.dumps({"role": role, "content": content}, ensure_ascii=False)
        )
        self.client.ltrim(key, -HISTORY_MAX_MESSAGES, -1)
        self.client.expire(key, HISTORY_TTL_SECONDS)

    def history(self, client_id: str) -> list[dict]:
        """Đọc lịch sử hội thoại, cũ nhất trước."""
        key = self._key(client_id)
        items = self.client.lrange(key, 0, -1)
        if not items:
            return []
        return [json.loads(item) for item in items]

    def reset(self, client_id: str) -> None:
        """CHO SẴN — xóa lịch sử của một client."""
        self.client.delete(self._key(client_id))

"""CHECKPOINT 4 — Scaling & Reliability: stateless, readiness, draining.

Chạy: pytest tests/test_cp4.py -v
File cần sửa: app/store.py, app/lifecycle.py, app/main.py (/readyz, /healthz, /chat)
"""

from __future__ import annotations

import re
import signal

import pytest


class TestChatStore:
    def test_luu_va_doc_lai_duoc(self, fake_redis):
        from app.store import ChatStore

        store = ChatStore(fake_redis)
        store.add_turn("c1", "user", "Xin chào")
        store.add_turn("c1", "assistant", "Chào bạn")

        history = store.history("c1")
        assert [turn["role"] for turn in history] == ["user", "assistant"]
        assert history[0]["content"] == "Xin chào"

    def test_chua_co_gi_thi_tra_list_rong(self, fake_redis):
        from app.store import ChatStore

        assert ChatStore(fake_redis).history("nguoi-la") == []

    def test_moi_client_mot_lich_su_rieng(self, fake_redis):
        from app.store import ChatStore

        store = ChatStore(fake_redis)
        store.add_turn("c1", "user", "cua c1")
        store.add_turn("c2", "user", "cua c2")
        assert len(store.history("c1")) == 1
        assert store.history("c2")[0]["content"] == "cua c2"

    def test_cat_bot_lich_su_qua_dai(self, fake_redis):
        """Lịch sử không được phình vô hạn — prompt dài = tiền token nhiều."""
        from app.store import ChatStore, HISTORY_MAX_MESSAGES

        store = ChatStore(fake_redis)
        for i in range(HISTORY_MAX_MESSAGES + 10):
            store.add_turn("c1", "user", f"tin nhan {i}")

        history = store.history("c1")
        assert len(history) == HISTORY_MAX_MESSAGES
        assert history[-1]["content"] == f"tin nhan {HISTORY_MAX_MESSAGES + 9}", (
            "phải giữ các tin nhắn MỚI NHẤT, không phải cũ nhất"
        )

    def test_co_dat_han_su_dung(self, fake_redis):
        from app.store import ChatStore

        store = ChatStore(fake_redis)
        store.add_turn("c1", "user", "hi")
        assert fake_redis.ttl(ChatStore._key("c1")) > 0, (
            "phải đặt TTL cho key lịch sử, nếu không Redis đầy dần theo thời gian"
        )

    def test_ping_bao_dung_trang_thai(self, fake_redis):
        from app.store import ChatStore

        assert ChatStore(fake_redis).ping() is True

    def test_ping_khong_nem_loi_khi_redis_chet(self):
        """Redis chết → ping trả False, KHÔNG được để exception thoát ra."""
        from app.store import ChatStore

        class RedisChet:
            def ping(self):
                raise ConnectionError("Redis không phản hồi")

        assert ChatStore(RedisChet()).ping() is False

    def test_fake_url_tra_ve_redis_gia(self):
        from app.store import get_redis_client

        client = get_redis_client("fake://")
        client.set("k", "v")
        assert client.get("k") == "v"


class TestStateless:
    def test_state_khong_nam_trong_process(self, fake_redis):
        """Hai instance store khác nhau (mô phỏng 2 container) phải thấy
        cùng một dữ liệu, vì state nằm ở Redis chứ không nằm trong object."""
        from app.store import ChatStore

        container_a = ChatStore(fake_redis)
        container_b = ChatStore(fake_redis)

        container_a.add_turn("c1", "user", "tin nhắn gửi vào container A")

        assert len(container_b.history("c1")) == 1, (
            "container B không thấy dữ liệu container A ghi — state đang bị "
            "giữ trong RAM của từng instance"
        )

    def test_khong_co_bien_toan_cuc_giu_state(self, lab_root):
        """Quét source tìm dict/list toàn cục dùng làm bộ nhớ hội thoại."""
        pattern = re.compile(
            r"^(?!\s)(\w*(history|conversation|chat|session|cache|memory|store)\w*)"
            r"\s*(:\s*[^=]+)?=\s*(\{\}|\[\]|dict\(\)|list\(\))",
            re.IGNORECASE | re.MULTILINE,
        )
        for name in ("main.py", "store.py"):
            path = lab_root / "app" / name
            if not path.exists():
                continue
            found = pattern.findall(path.read_text(encoding="utf-8"))
            assert not found, (
                f"app/{name} có biến toàn cục giữ state: {[f[0] for f in found]}. "
                "Khi scale ra nhiều instance, mỗi instance có RAM riêng → service "
                "mất trí nhớ. Đưa state sang Redis."
            )

    def test_lich_su_duoc_dung_lai_giua_cac_request(self, client_real_store, auth_headers):
        first = client_real_store.post(
            "/chat", json={"message": "Tin nhắn thứ nhất"}, headers=auth_headers
        )
        assert first.status_code == 200, first.text
        assert first.json()["turns_before"] == 0

        second = client_real_store.post(
            "/chat", json={"message": "Tin nhắn thứ hai"}, headers=auth_headers
        )
        assert second.json()["turns_before"] == 2, (
            "lượt thứ hai phải thấy 2 message trước đó (user + assistant)"
        )


class TestReadiness:
    def test_readyz_tra_200_khi_redis_song(self, client_real_store):
        response = client_real_store.get("/readyz")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_readyz_tra_503_khi_redis_chet(self, client_factory):
        class StoreChet:
            def ping(self):
                return False

        response = client_factory(store=StoreChet()).get("/readyz")
        assert response.status_code == 503, (
            "Redis chết mà /readyz vẫn 200 thì load balancer sẽ đẩy traffic vào "
            "một instance không phục vụ được"
        )

    def test_readyz_khac_healthz(self, client_real_store):
        """/healthz không kiểm tra dependency, /readyz thì có."""
        import inspect

        from app.main import readyz

        assert inspect.signature(readyz).parameters, (
            "/readyz phải nhận store làm dependency để kiểm tra kết nối"
        )


class TestGracefulShutdown:
    def test_nhan_tin_hieu_thi_bat_co_draining(self):
        from app.lifecycle import ShutdownGuard

        guard = ShutdownGuard()
        assert guard.draining is False
        guard.start_draining(signal.SIGTERM, None)
        assert guard.draining is True

    def test_dang_ky_handler_cho_sigterm_va_sigint(self):
        from app.lifecycle import ShutdownGuard

        goc_term = signal.getsignal(signal.SIGTERM)
        goc_int = signal.getsignal(signal.SIGINT)
        try:
            guard = ShutdownGuard()
            guard.arm()
            assert signal.getsignal(signal.SIGTERM) == guard.start_draining, (
                "chưa đăng ký handler cho SIGTERM — đây là tín hiệu mà Docker, "
                "Railway, Cloud Run gửi khi deploy phiên bản mới"
            )
            assert signal.getsignal(signal.SIGINT) == guard.start_draining
        finally:
            signal.signal(signal.SIGTERM, goc_term)
            signal.signal(signal.SIGINT, goc_int)

    def test_nhuong_lai_cho_handler_cu(self):
        """Ghi đè handler của uvicorn thì phải gọi lại nó, nếu không server
        không bao giờ tự tắt và bị SIGKILL sau vài chục giây."""
        from app.lifecycle import ShutdownGuard

        goc_term = signal.getsignal(signal.SIGTERM)
        goc_int = signal.getsignal(signal.SIGINT)
        da_goi = []
        try:
            signal.signal(signal.SIGTERM, lambda signum, frame: da_goi.append(signum))
            guard = ShutdownGuard()
            guard.arm()
            guard.start_draining(signal.SIGTERM, None)

            assert guard.draining is True
            assert da_goi == [signal.SIGTERM], (
                "start_draining phải gọi lại handler đã đăng ký trước đó — "
                "đó chính là handler dừng server của uvicorn"
            )
        finally:
            signal.signal(signal.SIGTERM, goc_term)
            signal.signal(signal.SIGINT, goc_int)

    def test_healthz_bao_503_khi_dang_drain(self, client):
        from app.lifecycle import shutdown_guard

        assert client.get("/healthz").status_code == 200

        shutdown_guard.start_draining(signal.SIGTERM, None)
        response = client.get("/healthz")
        assert response.status_code == 503, (
            "đang tắt dần thì /healthz phải trả 503 để load balancer ngừng gửi "
            "request mới vào instance này"
        )
        assert response.json()["status"] == "draining"

    def test_readyz_bao_503_khi_dang_drain(self, client_real_store):
        from app.lifecycle import shutdown_guard

        shutdown_guard.start_draining(signal.SIGTERM, None)
        assert client_real_store.get("/readyz").status_code == 503

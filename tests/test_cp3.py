"""CHECKPOINT 3 — API Security: Bearer auth, token bucket, cost guard.

Chạy: pytest tests/test_cp3.py -v
File cần sửa: app/auth.py, app/rate_limiter.py, app/cost_guard.py, app/main.py (/chat)
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException


class TestBearerAuth:
    def test_khong_co_header_thi_401(self, client):
        response = client.post("/chat", json={"message": "Xin chào"})
        assert response.status_code == 401

    def test_sai_token_thi_401(self, client):
        response = client.post(
            "/chat",
            json={"message": "Xin chào"},
            headers={"Authorization": "Bearer token-bia-dat"},
        )
        assert response.status_code == 401

    def test_sai_scheme_thi_401(self, client, api_token):
        """Token đúng nhưng gửi kiểu Basic → vẫn phải từ chối."""
        response = client.post(
            "/chat",
            json={"message": "Xin chào"},
            headers={"Authorization": f"Basic {api_token}"},
        )
        assert response.status_code == 401

    def test_thieu_scheme_thi_401(self, client, api_token):
        """Gửi trần token không có chữ Bearer → không đúng chuẩn, từ chối."""
        response = client.post(
            "/chat",
            json={"message": "Xin chào"},
            headers={"Authorization": api_token},
        )
        assert response.status_code == 401

    def test_401_kem_header_www_authenticate(self, client):
        """Chuẩn HTTP: 401 phải nói cho client biết cách xác thực."""
        response = client.post("/chat", json={"message": "Hi"})
        assert "www-authenticate" in {k.lower() for k in response.headers}, (
            "response 401 thiếu header WWW-Authenticate: Bearer"
        )

    def test_dung_token_thi_200(self, client, auth_headers):
        response = client.post(
            "/chat", json={"message": "Docker là gì?"}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["reply"]

    def test_scheme_khong_phan_biet_hoa_thuong(self, client, api_token):
        """RFC 6750: scheme so sánh không phân biệt hoa thường."""
        response = client.post(
            "/chat",
            json={"message": "Hi"},
            headers={"Authorization": f"bearer {api_token}"},
        )
        assert response.status_code == 200, response.text

    def test_tra_ve_dung_client_id(self, client, api_token):
        response = client.post(
            "/chat",
            json={"message": "Hi"},
            headers={"Authorization": f"Bearer {api_token}", "X-Client-Id": "sv-123"},
        )
        assert response.json()["client_id"] == "sv-123"

    def test_khong_gui_client_id_thi_thanh_anonymous(self, client, api_token):
        from app.auth import ANONYMOUS_CLIENT

        response = client.post(
            "/chat",
            json={"message": "Hi"},
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.json()["client_id"] == ANONYMOUS_CLIENT

    def test_so_sanh_token_chong_timing_attack(self, lab_root):
        """Phải GỌI secrets.compare_digest, không chỉ nhắc tới trong comment."""
        import ast

        tree = ast.parse((lab_root / "app" / "auth.py").read_text(encoding="utf-8"))
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert "compare_digest" in called, (
            "so sánh token bằng secrets.compare_digest(a, b), không dùng =="
        )


class TestTokenBucket:
    def test_client_moi_thi_xo_day(self, fake_redis):
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=5, refill_per_minute=5)
        assert bucket.available("c1", now=1000.0) == pytest.approx(5.0)

    def test_tieu_het_suc_chua_thi_429(self, fake_redis):
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=3, refill_per_minute=3)
        for _ in range(3):
            bucket.consume("c1", now=1000.0)

        with pytest.raises(HTTPException) as err:
            bucket.consume("c1", now=1000.0)
        assert err.value.status_code == 429

    def test_moi_lan_tieu_giam_dung_mot_token(self, fake_redis):
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=10, refill_per_minute=10)
        bucket.consume("c1", now=1000.0)
        bucket.consume("c1", now=1000.0)
        assert bucket.available("c1", now=1000.0) == pytest.approx(8.0)

    def test_token_nap_lai_theo_thoi_gian(self, fake_redis):
        """10 token/phút → sau 30 giây có thêm 5 token."""
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=10, refill_per_minute=10)
        for _ in range(10):
            bucket.consume("c1", now=1000.0)
        assert bucket.available("c1", now=1000.0) == pytest.approx(0.0)

        assert bucket.available("c1", now=1030.0) == pytest.approx(5.0, abs=0.01)
        bucket.consume("c1", now=1030.0)  # còn token thì không được chặn

    def test_khong_nap_qua_suc_chua(self, fake_redis):
        """Im lặng một ngày cũng chỉ được đầy xô, không tích vô hạn."""
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=10, refill_per_minute=10)
        bucket.consume("c1", now=1000.0)
        assert bucket.available("c1", now=1000.0 + 86400) == pytest.approx(10.0)

    def test_moi_client_mot_xo_rieng(self, fake_redis):
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=1, refill_per_minute=1)
        bucket.consume("c1", now=1000.0)
        bucket.consume("c2", now=1000.0)  # client khác không bị ảnh hưởng

    def test_429_kem_header_retry_after(self, fake_redis):
        from app.rate_limiter import TokenBucket

        bucket = TokenBucket(fake_redis, capacity=1, refill_per_minute=6)
        bucket.consume("c1", now=1000.0)
        with pytest.raises(HTTPException) as err:
            bucket.consume("c1", now=1000.0)
        assert (err.value.headers or {}).get("Retry-After"), (
            "429 phải kèm header Retry-After để client biết khi nào gọi lại"
        )

    def test_qua_http_thi_tra_429(self, client_factory, auth_headers):
        client = client_factory(capacity=3, refill=0)
        for _ in range(3):
            assert client.post(
                "/chat", json={"message": "x"}, headers=auth_headers
            ).status_code == 200

        blocked = client.post("/chat", json={"message": "x"}, headers=auth_headers)
        assert blocked.status_code == 429

    def test_401_duoc_kiem_tra_truoc_429(self, client_factory):
        """Request không có token phải dừng ở 401, không tiêu token của ai cả."""
        client = client_factory(capacity=1, refill=0)
        for _ in range(5):
            assert client.post("/chat", json={"message": "x"}).status_code == 401


class TestCostGuard:
    def test_chua_tieu_gi_thi_spent_bang_0(self, fake_redis):
        from app.cost_guard import CostGuard

        assert CostGuard(fake_redis, 1.0).spent("c1") == pytest.approx(0.0)

    def test_record_cong_don(self, fake_redis):
        from app.cost_guard import CostGuard

        guard = CostGuard(fake_redis, 1.0)
        guard.record("c1", 0.5)
        guard.record("c1", 0.25)
        assert guard.spent("c1") == pytest.approx(0.75)

    def test_con_ngan_sach_thi_cho_qua(self, fake_redis):
        from app.cost_guard import CostGuard

        guard = CostGuard(fake_redis, 1.0)
        guard.record("c1", 0.9)
        guard.check("c1", estimated_cost=0.05)

    def test_vuot_ngan_sach_thi_402(self, fake_redis):
        from app.cost_guard import CostGuard

        guard = CostGuard(fake_redis, 1.0)
        guard.record("c1", 0.9)
        with pytest.raises(HTTPException) as err:
            guard.check("c1", estimated_cost=0.5)
        assert err.value.status_code == 402

    def test_ngan_sach_tinh_theo_ngay(self, fake_redis):
        """Tiêu hết hôm nay không ảnh hưởng hạn mức ngày khác."""
        from app.cost_guard import CostGuard

        guard = CostGuard(fake_redis, 1.0)
        guard.record("c1", 5.0, day="2026-08-01")
        guard.check("c1", estimated_cost=0.5, day="2026-08-02")

    def test_moi_client_mot_ngan_sach_rieng(self, fake_redis):
        from app.cost_guard import CostGuard

        guard = CostGuard(fake_redis, 1.0)
        guard.record("c1", 5.0)
        guard.check("c2", estimated_cost=0.5)

    def test_qua_http_thi_tra_402(self, client, fake_redis, auth_headers):
        """Đã tiêu quá ngân sách → /chat trả 402 Payment Required."""
        from app.cost_guard import CostGuard

        fake_redis.set(CostGuard._key("sv-test"), "999")
        response = client.post("/chat", json={"message": "x"}, headers=auth_headers)
        assert response.status_code == 402

    def test_chat_ghi_nhan_chi_phi(self, client, fake_redis, auth_headers):
        from app.cost_guard import CostGuard

        client.post("/chat", json={"message": "Chi phí bao nhiêu?"}, headers=auth_headers)
        assert CostGuard(fake_redis, 1.0).spent("sv-test") > 0, (
            "/chat phải gọi guard.record() sau khi trả lời, nếu không ngân sách "
            "không bao giờ tăng và cost guard trở nên vô dụng"
        )


class TestChatResponse:
    def test_tra_du_cac_truong(self, client, auth_headers):
        body = client.post(
            "/chat", json={"message": "Kubernetes là gì?"}, headers=auth_headers
        ).json()
        for field in ("reply", "client_id", "turns_before", "usd_cost", "usage"):
            assert field in body, f"response thiếu trường {field!r}"
        assert set(body["usage"]) == {"prompt", "completion"}

    def test_tin_nhan_rong_thi_422(self, client, auth_headers):
        response = client.post("/chat", json={"message": ""}, headers=auth_headers)
        assert response.status_code == 422

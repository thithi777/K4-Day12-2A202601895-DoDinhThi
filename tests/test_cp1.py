"""CHECKPOINT 1 — 12-Factor Config, Health Check & Structured Logging.

Chạy: pytest tests/test_cp1.py -v
File cần sửa: app/config.py, app/logging_utils.py, app/main.py (/healthz)
"""

from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

# Những chuỗi không bao giờ được xuất hiện trong code cấu hình
FORBIDDEN_SECRETS = ["sk-", "secret-key-123", "password123", "AKIA"]


class TestConfig:
    def test_settings_co_du_cac_truong(self):
        """Settings khai báo đủ 7 trường theo bảng trong app/config.py."""
        from app.config import Settings

        for field in (
            "port",
            "api_token",
            "redis_url",
            "bucket_capacity",
            "refill_per_minute",
            "daily_budget_usd",
            "log_level",
        ):
            assert field in Settings.model_fields, f"thiếu trường '{field}'"

    def test_doc_gia_tri_tu_bien_moi_truong(self, monkeypatch):
        """Đổi biến môi trường → cấu hình đổi theo, không cần sửa code."""
        from app.config import Settings

        monkeypatch.setenv("API_TOKEN", "token-tu-env")
        monkeypatch.setenv("PORT", "9123")
        monkeypatch.setenv("BUCKET_CAPACITY", "42")
        monkeypatch.setenv("DAILY_BUDGET_USD", "3.5")

        settings = Settings(_env_file=None)
        assert settings.api_token == "token-tu-env"
        assert settings.port == 9123
        assert settings.bucket_capacity == 42
        assert settings.daily_budget_usd == pytest.approx(3.5)

    def test_gia_tri_mac_dinh_hop_ly(self, monkeypatch):
        """Các trường không phải secret thì có mặc định dùng được ngay."""
        from app.config import Settings

        monkeypatch.setenv("API_TOKEN", "x")
        for name in ("PORT", "REDIS_URL", "BUCKET_CAPACITY", "REFILL_PER_MINUTE",
                     "DAILY_BUDGET_USD", "LOG_LEVEL"):
            monkeypatch.delenv(name, raising=False)

        settings = Settings(_env_file=None)
        assert settings.port == 8000
        assert settings.bucket_capacity == 10
        assert settings.refill_per_minute == 10
        assert settings.daily_budget_usd == pytest.approx(1.0)
        assert "redis" in settings.redis_url

    def test_thieu_api_token_thi_fail_fast(self, monkeypatch):
        """Không có API_TOKEN → app phải chết ngay lúc khởi động."""
        from app.config import Settings

        monkeypatch.delenv("API_TOKEN", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_khong_hardcode_secret(self, lab_root):
        """Không có secret nào nằm trong source code."""
        for name in ("config.py", "main.py", "auth.py"):
            path = lab_root / "app" / name
            if not path.exists():
                continue
            source = path.read_text(encoding="utf-8")
            for bad in FORBIDDEN_SECRETS:
                assert bad not in source, f"{name} chứa secret hardcode: {bad!r}"


class TestStructuredLogging:
    def test_emit_tra_ve_json_hop_le(self):
        from app.logging_utils import emit

        parsed = json.loads(emit("test_event"))
        assert parsed["event"] == "test_event"
        assert parsed["severity"] == "INFO"
        assert "ts" in parsed

    def test_emit_gan_them_truong_tuy_y(self):
        from app.logging_utils import emit

        parsed = json.loads(emit("chat_completed", client_id="sv01", usd_cost=0.12))
        assert parsed["client_id"] == "sv01"
        assert parsed["usd_cost"] == pytest.approx(0.12)

    def test_severity_luon_viet_hoa(self):
        """Google Cloud Logging chỉ hiểu severity viết hoa."""
        from app.logging_utils import emit

        assert json.loads(emit("e", severity="error"))["severity"] == "ERROR"

    def test_log_ra_stdout_dung_mot_dong(self, capsys):
        """Cloud gom log theo dòng — một event xuống dòng là một log bị vỡ."""
        from app.logging_utils import emit

        emit("mot_dong", chi_tiet="a")
        out = capsys.readouterr().out.strip()
        assert out, "emit phải in ra stdout"
        assert len(out.splitlines()) == 1, "log JSON phải nằm gọn trên 1 dòng"
        json.loads(out)

    def test_ts_dung_dinh_dang_iso(self):
        from app.logging_utils import emit

        stamp = json.loads(emit("e"))["ts"]
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp), stamp


class TestHealthzEndpoint:
    def test_healthz_tra_ve_200(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_healthz_khong_can_token(self, client):
        """Probe của platform không gửi token — bắt buộc token là tự sát."""
        assert client.get("/healthz").status_code == 200

    def test_healthz_khong_phu_thuoc_dependency_nao(self):
        """Redis chết thì /healthz vẫn phải 200, nếu không cả cụm bị restart.

        Cách kiểm tra: hàm healthz() không được nhận tham số dependency nào.
        """
        import inspect

        from app.main import healthz

        params = list(inspect.signature(healthz).parameters)
        assert not params, f"/healthz không được phụ thuộc dependency: {params}"

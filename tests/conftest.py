"""Cấu hình chung cho toàn bộ checkpoint.

Test chấm code trong thư mục ``app/`` ở gốc repo.

Nguyên tắc thiết kế: checkpoint sau được phép dùng code của checkpoint
trước, nhưng KHÔNG bao giờ ngược lại. Vì vậy test CP1/CP3 dùng ``StubStore``
thay cho ``ChatStore`` — bạn không bị mất điểm CP3 chỉ vì chưa làm CP4.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "solution" if os.getenv("LAB_TARGET") == "solution" else ROOT

# Ưu tiên thư mục đang chấm, sau đó tới gốc repo (để `import utils` luôn chạy)
for path in (str(ROOT), str(TARGET)):
    if path in sys.path:
        sys.path.remove(path)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TARGET))

# Nạp .env để lấy LOCAL_FALLBACK / DEPLOY_API_TOKEN cho CP5 (nếu có)
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

# Giá trị cố định cho lúc test, không phụ thuộc file .env của học viên
TEST_API_TOKEN = "test-token-cua-lab"
os.environ["API_TOKEN"] = TEST_API_TOKEN
os.environ["REDIS_URL"] = "fake://"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "docker: test cần Docker đang chạy, tự bỏ qua nếu không có"
    )


class StubStore:
    """Store giả lập, luôn hoạt động — dùng cho test CP1 và CP3."""

    def __init__(self) -> None:
        self._data: dict[str, list[dict]] = {}

    def ping(self) -> bool:
        return True

    def add_turn(self, client_id: str, role: str, content: str) -> None:
        self._data.setdefault(client_id, []).append({"role": role, "content": content})

    def history(self, client_id: str) -> list[dict]:
        return list(self._data.get(client_id, []))

    def reset(self, client_id: str) -> None:
        self._data.pop(client_id, None)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def lab_root() -> Path:
    """Thư mục chứa code Python đang được chấm."""
    return TARGET


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Gốc repo — nơi đặt Dockerfile, docker-compose.yml, DEPLOYMENT.md."""
    return ROOT


@pytest.fixture
def fake_redis():
    """Redis giả trong RAM — mỗi test một instance sạch."""
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def api_token() -> str:
    return os.environ["API_TOKEN"]


@pytest.fixture
def auth_headers(api_token) -> dict:
    return {"Authorization": f"Bearer {api_token}", "X-Client-Id": "sv-test"}


@pytest.fixture(autouse=True)
def _reset_draining():
    """Mỗi test bắt đầu ở trạng thái 'đang chạy bình thường'."""
    try:
        from app.lifecycle import shutdown_guard

        shutdown_guard.draining = False
        yield
        shutdown_guard.draining = False
    except Exception:
        yield


def _build_client(store, fake_redis, *, capacity=10, refill=10, budget=1.0):
    """CHO SẴN — dựng TestClient và thay toàn bộ dependency Redis."""
    from fastapi.testclient import TestClient

    from app import main as main_module
    from app.cost_guard import CostGuard
    from app.rate_limiter import TokenBucket

    app = main_module.app
    app.dependency_overrides[main_module.get_store] = lambda: store
    app.dependency_overrides[main_module.get_bucket] = lambda: TokenBucket(
        fake_redis, capacity=capacity, refill_per_minute=refill
    )
    app.dependency_overrides[main_module.get_cost_guard] = lambda: CostGuard(
        fake_redis, daily_budget_usd=budget
    )
    # Không dùng `with TestClient(...)`: lifespan sẽ đăng ký signal handler,
    # không cần thiết khi test và dễ gây nhiễu cho pytest.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(fake_redis):
    """Client dùng StubStore — không phụ thuộc bài làm CP4."""
    from app import main as main_module

    yield _build_client(StubStore(), fake_redis)
    main_module.app.dependency_overrides.clear()


@pytest.fixture
def client_factory(fake_redis):
    """Client tùy chỉnh hạn mức, ví dụ ``client_factory(capacity=2)``."""
    from app import main as main_module

    def _factory(store=None, **kwargs):
        return _build_client(store or StubStore(), fake_redis, **kwargs)

    yield _factory
    main_module.app.dependency_overrides.clear()


@pytest.fixture
def client_real_store(fake_redis):
    """Client dùng ChatStore thật (bài làm CP4) trên Redis giả."""
    from app import main as main_module
    from app.store import ChatStore

    yield _build_client(ChatStore(fake_redis), fake_redis)
    main_module.app.dependency_overrides.clear()

"""
key_pool.py — Quản lý "bể" key + trạng thái xoay vòng.

Tách hẳn khỏi DB: engine không quan tâm key tới từ SQLAlchemy/Redis/file nào.
Bạn nạp vào một list `KeyConfig`, pool lo phần xoay vòng, cooldown, loại key.

Trạng thái mỗi key (KeyStatus):
  ACTIVE   : sẵn sàng dùng
  COOLDOWN : đang ngủ tới `available_at` (vd dính rate limit/phút)
  DISABLED : chết trong phiên này (auth fail / quota ngày / sai model)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class KeyStatus(str, Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


@dataclass(slots=True)
class KeyConfig:
    """Cấu hình 1 key. Map từ DB/Redis của bạn sang đây trước khi nạp vào pool."""
    id: str                       # định danh duy nhất (vd: str(api_config.id))
    provider: str                 # "openai" | "gemini" | "groq" | "anthropic" ...
    model_name: str               # tên model litellm: "gemini/gemini-2.0-flash" ...
    api_key: str                  # ĐÃ giải mã (decrypt trước khi đưa vào đây)
    capability: str = ""          # "llm" | "embedding"; profile sẽ điền nếu bỏ trống
    api_base: str | None = None   # cho endpoint tự host / OpenAI-compatible
    endpoint_id: str | None = None
    enabled: bool = True
    locked: bool = False          # platform admin có thể khoá key/endpoint/model
    lock_reason: str = ""
    tenant_allowlist: set[str] = field(default_factory=set)
    app_allowlist: set[str] = field(default_factory=set)
    extra: dict = field(default_factory=dict)  # tham số phụ tuỳ provider

    def is_allowed_for(self, tenant_id: str | None, app_id: str | None) -> bool:
        if self.tenant_allowlist and tenant_id not in self.tenant_allowlist:
            return False
        if self.app_allowlist and app_id not in self.app_allowlist:
            return False
        return True


@dataclass(slots=True)
class KeyState:
    config: KeyConfig
    status: KeyStatus = KeyStatus.ACTIVE
    available_at: float = 0.0     # epoch giây — chỉ dùng được khi now() >= mốc này
    disabled_reason: str = ""
    success_count: int = 0
    fail_count: int = 0
    consecutive_fails: int = 0

    @property
    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.locked:
            return False
        if self.status == KeyStatus.DISABLED:
            return False
        if self.status == KeyStatus.COOLDOWN and time.monotonic() < self.available_at:
            return False
        return True


class PoolExhausted(Exception):
    """Không còn key nào khả dụng (tất cả disabled, hoặc tất cả đang cooldown)."""


class KeyPool:
    """
    Vòng xoay round-robin có nhớ trạng thái.

    Dùng:
        pool = KeyPool([KeyConfig(...), KeyConfig(...)])
        key = pool.acquire()        # lấy key khả dụng kế tiếp (raise PoolExhausted nếu hết)
        ...gọi API...
        pool.report_success(key)    # hoặc:
        pool.cooldown(key, 60)      # cho ngủ 60s
        pool.disable(key, "reason") # loại hẳn phiên này
    """

    def __init__(self, configs: list[KeyConfig]):
        if not configs:
            raise ValueError("KeyPool cần ít nhất 1 key.")
        self._states: list[KeyState] = [KeyState(config=c) for c in configs]
        self._cursor = 0

    # ---- Truy vấn trạng thái pool -----------------------------------------
    @property
    def total(self) -> int:
        return len(self._states)

    @property
    def alive_count(self) -> int:
        """Số key CHƯA bị disable (kể cả đang cooldown)."""
        return sum(1 for s in self._states if s.status != KeyStatus.DISABLED)

    @property
    def available_now_count(self) -> int:
        return sum(1 for s in self._states if s.is_available)

    @property
    def locked_count(self) -> int:
        return sum(1 for s in self._states if s.config.locked or not s.config.enabled)

    def next_available_at(self) -> float | None:
        """Mốc thời gian (monotonic) sớm nhất mà 1 key cooldown sẽ tỉnh dậy."""
        waking = [
            s.available_at for s in self._states
            if s.status == KeyStatus.COOLDOWN
        ]
        return min(waking) if waking else None

    # ---- Lấy key kế tiếp ---------------------------------------------------
    def acquire(self) -> KeyState:
        """
        Round-robin: quét toàn vòng từ con trỏ hiện tại, trả về key khả dụng đầu tiên.
        Hết key sống -> PoolExhausted (engine quyết định: đợi cooldown hay dừng).
        """
        n = len(self._states)
        for offset in range(n):
            idx = (self._cursor + offset) % n
            state = self._states[idx]
            if state.is_available:
                self._cursor = (idx + 1) % n   # lần sau bắt đầu từ key kế
                return state
        raise PoolExhausted(
            f"Không còn key khả dụng. alive={self.alive_count}/{self.total}, "
            f"available_now={self.available_now_count}, locked={self.locked_count}"
        )

    def retry_next(self, state: KeyState) -> None:
        """Đặt con trỏ để lần acquire kế tiếp ưu tiên đúng key vừa dùng."""
        for idx, current in enumerate(self._states):
            if current is state:
                self._cursor = idx
                return

    # ---- Cập nhật trạng thái sau mỗi lần gọi ------------------------------
    def report_success(self, state: KeyState) -> None:
        state.success_count += 1
        state.consecutive_fails = 0
        # Key chạy ổn -> nếu đang cooldown thì gỡ (hiếm, nhưng cho chắc)
        if state.status == KeyStatus.COOLDOWN and state.is_available:
            state.status = KeyStatus.ACTIVE

    def cooldown(self, state: KeyState, seconds: float) -> None:
        state.fail_count += 1
        state.consecutive_fails += 1
        state.status = KeyStatus.COOLDOWN
        state.available_at = time.monotonic() + max(0.0, seconds)

    def disable(self, state: KeyState, reason: str) -> None:
        state.fail_count += 1
        state.consecutive_fails += 1
        state.status = KeyStatus.DISABLED
        state.disabled_reason = reason

    def note_failure(self, state: KeyState) -> None:
        """Lỗi không liên quan tới sức khoẻ key (vd network) — chỉ đếm, không phạt."""
        state.fail_count += 1
        state.consecutive_fails += 1

    # ---- Tiện ích cho dashboard -------------------------------------------
    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        return [
            {
                "id": s.config.id,
                "provider": s.config.provider,
                "model": s.config.model_name,
                "capability": s.config.capability,
                "endpoint_id": s.config.endpoint_id,
                "status": s.status.value,
                "enabled": s.config.enabled,
                "locked": s.config.locked,
                "lock_reason": s.config.lock_reason,
                "cooldown_remaining": max(0.0, s.available_at - now)
                if s.status == KeyStatus.COOLDOWN else 0.0,
                "success": s.success_count,
                "fail": s.fail_count,
                "disabled_reason": s.disabled_reason,
            }
            for s in self._states
        ]

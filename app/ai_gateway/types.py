from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.ai_gateway.key_pool import KeyConfig


class AICapability(StrEnum):
    EMBEDDING = "embedding"
    LLM = "llm"


@dataclass(slots=True)
class ModelProfile:
    """
    Runtime profile cho một nhóm key/model cùng capability.

    Platform Admin sau này sẽ load profile này từ DB/Redis. Trong gateway, profile
    chỉ là cấu hình đã được service/repository chuẩn hoá và giải mã key.
    """

    id: str
    capability: AICapability | str
    keys: list[KeyConfig]
    default_params: dict[str, Any] = field(default_factory=dict)
    expected_dim: int | None = None
    max_batch_size: int | None = None
    enabled: bool = True
    locked: bool = False
    lock_reason: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        self.capability = AICapability(str(self.capability))
        for key in self.keys:
            if not key.capability:
                key.capability = self.capability.value

    def usable_keys(self, tenant_id: str | None = None, app_id: str | None = None) -> list[KeyConfig]:
        if not self.enabled or self.locked:
            return []
        return [
            key
            for key in self.keys
            if key.enabled
            and not key.locked
            and key.capability == self.capability.value
            and key.is_allowed_for(tenant_id, app_id)
        ]


@dataclass(frozen=True, slots=True)
class GatewayRequestContext:
    tenant_id: str | None = None
    app_id: str | None = None
    collection_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    endpoint: str | None = None
    request_id: str | None = None


@dataclass(slots=True)
class UsageRecord:
    profile_id: str
    capability: str
    provider: str | None
    key_id: str | None
    model: str | None
    endpoint_id: str | None
    success: bool
    attempts: int
    latency_ms: float
    tenant_id: str | None = None
    app_id: str | None = None
    collection_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    endpoint: str | None = None
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    error_reason: str = ""
    last_verdict_action: str | None = None
    input_count: int | None = None


class UsageRecorder(Protocol):
    def __call__(self, record: UsageRecord) -> Any:
        ...


class AdminNotifier(Protocol):
    def __call__(self, record: UsageRecord) -> Any:
        ...

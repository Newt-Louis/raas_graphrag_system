"""
base_rotator.py — Vòng lặp xoay vòng chung cho MỌI loại model (LLM, embedding...).

Tách bạch 2 trách nhiệm:
  - BaseRotator   : LOGIC xoay vòng + áp dụng Verdict (không biết gì về litellm call cụ thể)
  - subclass._call: CÁCH gọi API thật (LLM dùng acompletion, embedding dùng aembedding)

Subclass chỉ cần override `_call(key, **kwargs) -> Any`.
Toàn bộ xử lý lỗi/xoay/cooldown/abort đã nằm ở đây.
"""

from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .errors import ErrorAction, Verdict, classify_error
from .key_pool import KeyConfig, KeyPool, KeyState, PoolExhausted

logger = logging.getLogger("rotation")


@dataclass(slots=True)
class RotationResult:
    success: bool
    data: Any = None
    used_key_id: str | None = None
    used_model: str | None = None
    attempts: int = 0
    verdicts: list[Verdict] = field(default_factory=list)  # lịch sử lỗi đã gặp
    final_reason: str = ""

    @property
    def last_verdict(self) -> Verdict | None:
        return self.verdicts[-1] if self.verdicts else None


class AdminAlert(Exception):
    """Ném ra khi gặp lỗi cấu hình cần admin can thiệp (ErrorAction.ABORT_ADMIN)."""
    def __init__(self, verdict: Verdict):
        self.verdict = verdict
        super().__init__(verdict.reason)


class BaseRotator(abc.ABC):
    """
    Tham số:
      max_attempts        : tổng số lần gọi API tối đa cho 1 request (chặn vòng lặp vô hạn)
      max_retry_same      : số lần retry CHÍNH 1 key khi lỗi mạng trước khi bỏ cuộc với key đó
      wait_for_cooldown   : khi pool cạn vì cooldown, có ĐỢI key tỉnh dậy không (True)
                            hay bỏ luôn (False)
      max_cooldown_wait   : nếu wait_for_cooldown=True, đợi tối đa bao lâu (giây)
    """

    def __init__(
        self,
        keys: list[KeyConfig],
        *,
        max_attempts: int = 12,
        max_retry_same: int = 2,
        wait_for_cooldown: bool = True,
        max_cooldown_wait: float = 65.0,
    ):
        self.pool = KeyPool(keys)
        self.max_attempts = max_attempts
        self.max_retry_same = max_retry_same
        self.wait_for_cooldown = wait_for_cooldown
        self.max_cooldown_wait = max_cooldown_wait

    # -----------------------------------------------------------------------
    # PHẦN SUBCLASS PHẢI CÀI ĐẶT
    # -----------------------------------------------------------------------
    @abc.abstractmethod
    async def _call(self, key: KeyState, **kwargs) -> Any:
        """
        Gọi API thật với 1 key cụ thể, trả về dữ liệu đã parse.
        Ném litellm exception nếu lỗi — BaseRotator sẽ bắt và phân loại.
        """
        ...

    # Hook tuỳ chọn: subclass / engine override để đẩy cảnh báo lên dashboard.
    async def _on_admin_notify(self, key: KeyState, verdict: Verdict) -> None:
        logger.warning(
            "[ADMIN] key=%s model=%s | %s | %s",
            key.config.id, key.config.model_name, verdict.reason, verdict.raw,
        )

    # -----------------------------------------------------------------------
    # VÒNG LẶP CHÍNH
    # -----------------------------------------------------------------------
    async def run(self, **kwargs) -> RotationResult:
        result = RotationResult(success=False)
        retry_same_count = 0

        while result.attempts < self.max_attempts:
            # 1) Lấy key khả dụng (xử lý trường hợp pool cạn vì cooldown)
            try:
                key = self.pool.acquire()
            except PoolExhausted as exc:
                waited = await self._maybe_wait_for_cooldown()
                if waited:
                    continue
                result.final_reason = f"Hết key khả dụng: {exc}"
                logger.error(result.final_reason)
                return result

            result.attempts += 1

            # 2) Gọi API thật
            try:
                data = await self._call(key, **kwargs)
                self.pool.report_success(key)
                result.success = True
                result.data = data
                result.used_key_id = key.config.id
                result.used_model = key.config.model_name
                return result

            # 3) Có lỗi -> phân loại -> áp dụng Verdict
            except Exception as exc:  # noqa: BLE001 - cố ý bắt rộng rồi phân loại
                verdict = classify_error(exc)
                result.verdicts.append(verdict)

                if verdict.notify_admin:
                    await self._on_admin_notify(key, verdict)

                retry_same_count = await self._apply_verdict(
                    key, verdict, retry_same_count, result
                )
                if result.final_reason:  # _apply_verdict ra lệnh dừng
                    return result

        result.final_reason = f"Vượt quá max_attempts={self.max_attempts}."
        logger.error(result.final_reason)
        return result

    # -----------------------------------------------------------------------
    # ÁP DỤNG VERDICT — bảng quyết định trung tâm
    # -----------------------------------------------------------------------
    async def _apply_verdict(
        self,
        key: KeyState,
        verdict: Verdict,
        retry_same_count: int,
        result: RotationResult,
    ) -> int:
        """Trả về retry_same_count mới. Set result.final_reason nếu cần DỪNG hẳn."""
        action = verdict.action
        logger.info(
            "key=%s action=%s reason=%s",
            key.config.id, action.value, verdict.reason,
        )

        if action is ErrorAction.RETRY_SAME:
            if retry_same_count < self.max_retry_same:
                if verdict.retry_after:
                    await asyncio.sleep(verdict.retry_after)
                # KHÔNG advance cursor: ép acquire() trả lại đúng key này lần sau
                self.pool._cursor = (self.pool._cursor - 1) % self.pool.total
                self.pool.note_failure(key)
                return retry_same_count + 1
            # Hết lượt retry cùng key -> coi như xoay sang key khác
            self.pool.note_failure(key)
            return 0

        if action is ErrorAction.ROTATE_KEY:
            self.pool.note_failure(key)
            return 0

        if action is ErrorAction.COOLDOWN_KEY:
            self.pool.cooldown(key, verdict.retry_after)
            return 0

        if action is ErrorAction.DISABLE_KEY:
            self.pool.disable(key, verdict.reason)
            return 0

        if action is ErrorAction.SKIP_REQUEST:
            # Không key nào làm được REQUEST này -> dừng, KHÔNG phạt key.
            result.final_reason = f"Bỏ request: {verdict.reason}"
            return retry_same_count

        if action is ErrorAction.ABORT_ADMIN:
            # Lỗi cấu hình -> dừng ngay, đừng đốt thêm key.
            result.final_reason = f"Cần admin xử lý: {verdict.reason}"
            raise AdminAlert(verdict)

        # Không nên tới đây
        result.final_reason = f"Action không xác định: {action}"
        return retry_same_count

    async def _maybe_wait_for_cooldown(self) -> bool:
        """
        Pool cạn. Nếu còn key đang cooldown và được phép đợi -> ngủ tới khi key tỉnh.
        Trả True nếu đã đợi (nên thử acquire lại), False nếu nên bỏ cuộc.
        """
        if not self.wait_for_cooldown:
            return False
        wake_at = self.pool.next_available_at()
        if wake_at is None:
            return False  # không key nào cooldown -> tất cả đã disabled -> bó tay
        import time as _t
        wait = min(self.max_cooldown_wait, max(0.0, wake_at - _t.monotonic()) + 0.5)
        if wait <= 0:
            return True
        if wait > self.max_cooldown_wait:
            return False
        logger.info("Pool cạn tạm thời, đợi %.1fs cho key tỉnh dậy...", wait)
        await asyncio.sleep(wait)
        return True

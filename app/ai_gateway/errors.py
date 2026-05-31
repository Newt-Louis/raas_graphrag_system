"""
errors.py — Phân loại lỗi khi gọi LLM qua litellm.

Đây là "bộ não" của engine xoay vòng. Mỗi lỗi được map thành 1 `Verdict` cho biết:
  - action     : engine nên LÀM GÌ (xoay key, cho key ngủ, loại key, bỏ request, báo admin...)
  - retry_after: chờ bao lâu (giây)
  - notify_admin: có cần hiện lên dashboard cho admin xử lý không
  - permanent  : lỗi này hôm nay retry cũng vô ích (vd quota ngày)

Triết lý phân loại (4 nhóm):
  1. Lỗi của KEY hiện tại     -> xoay sang key khác (key vẫn / không còn dùng được)
  2. Lỗi tạm thời của PROVIDER -> retry / xoay, không phải lỗi của ta
  3. Lỗi của REQUEST           -> mọi key đều fail như nhau -> bỏ request hoặc báo admin
  4. Lỗi CẤU HÌNH             -> báo admin chỉnh, đừng đốt key vô ích
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import litellm


# ---------------------------------------------------------------------------
# Engine nên làm gì khi gặp lỗi
# ---------------------------------------------------------------------------
class ErrorAction(str, Enum):
    RETRY_SAME = "retry_same"      # Lỗi mạng tạm thời -> chờ rồi thử LẠI CHÍNH key này
    ROTATE_KEY = "rotate_key"      # Lỗi phía provider (5xx) -> sang key kế, key này vẫn ổn
    COOLDOWN_KEY = "cooldown_key"  # Rate limit -> cho key này NGỦ N giây rồi sang key kế
    DISABLE_KEY = "disable_key"    # Key chết (sai/hết hạn/sai model) -> LOẠI khỏi vòng xoay
    SKIP_REQUEST = "skip_request"  # Không key nào làm được REQUEST này -> bỏ qua request
    ABORT_ADMIN = "abort_admin"    # Lỗi cấu hình -> dừng, báo admin (mọi key fail như nhau)


@dataclass(slots=True)
class Verdict:
    action: ErrorAction
    reason: str
    retry_after: float = 0.0      # giây — dùng cho RETRY_SAME / COOLDOWN_KEY
    notify_admin: bool = False    # nổi lên dashboard admin
    permanent: bool = False       # hôm nay retry vô ích (vd: quota/ngày, billing)
    raw: str = ""                 # chuỗi lỗi gốc (đã cắt ngắn) để log


# ---------------------------------------------------------------------------
# Hằng số có thể tinh chỉnh
# ---------------------------------------------------------------------------
COOLDOWN_RATE_LIMIT_MINUTE = 60.0      # rate limit theo phút -> ngủ 60s
COOLDOWN_RATE_LIMIT_DAY = 24 * 3600.0  # quota theo ngày -> ngủ tới mai (thực tế: disable)
BACKOFF_NETWORK = 3.0                  # lỗi mạng -> backoff ngắn
BACKOFF_PROVIDER_5XX = 5.0             # provider 5xx -> backoff vừa

# Từ khoá để PHÂN BIỆT rate-limit theo NGÀY (nặng) vs theo PHÚT (nhẹ).
# Free tier của Gemini/Groq/... thường ghi rõ trong message.
_DAILY_HINTS = (
    "per day", "/day", "daily", "rpd", "requests per day",
    "quota", "exhausted", "insufficient_quota", "billing",
    "free tier", "credit", "out of", "limit reached for the day",
)


def _msg(exc: Exception) -> str:
    return str(exc).lower()


def _is_daily_limit(text: str) -> bool:
    """Đoán xem rate-limit là theo NGÀY (cooldown dài) hay theo PHÚT (cooldown ngắn)."""
    return any(h in text for h in _DAILY_HINTS)


def _trim(text: str, n: int = 400) -> str:
    text = str(text)
    return text if len(text) <= n else text[:n] + "…"


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


# ---------------------------------------------------------------------------
# HÀM CHÍNH: phân loại exception -> Verdict
# Thứ tự except QUAN TRỌNG: con phải đứng TRƯỚC cha.
#   ContextWindowExceededError, ContentPolicyViolationError  ⊂  BadRequestError
# ---------------------------------------------------------------------------
def classify_error(exc: Exception) -> Verdict:
    raw = _trim(exc)
    text = _msg(exc)

    # ---- NHÓM 4: Lỗi REQUEST cấp con của BadRequest (xoay key vô ích) ----------
    if isinstance(exc, litellm.ContextWindowExceededError):
        # Input vượt context window. Đổi key KHÔNG cứu được.
        # Với RAG: chunk quá to / lịch sử chat quá dài -> cần cắt bớt trước khi gọi.
        return Verdict(
            ErrorAction.SKIP_REQUEST,
            reason="Input vượt quá context window của model.",
            notify_admin=True,   # admin có thể cần giảm chunk_size / cắt history
            raw=raw,
        )

    if isinstance(exc, litellm.ContentPolicyViolationError):
        # Nội dung bị bộ lọc an toàn của provider chặn.
        # Đổi key CÙNG provider vô ích; engine có thể thử provider khác (tuỳ chính sách).
        return Verdict(
            ErrorAction.SKIP_REQUEST,
            reason="Nội dung bị chặn bởi content policy của provider.",
            notify_admin=False,
            raw=raw,
        )

    # ---- NHÓM 1: KEY chết hẳn -> loại khỏi vòng xoay ---------------------------
    if isinstance(exc, litellm.AuthenticationError):
        return Verdict(
            ErrorAction.DISABLE_KEY,
            reason="API key sai hoặc đã hết hạn (401).",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    if isinstance(exc, litellm.PermissionDeniedError):
        return Verdict(
            ErrorAction.DISABLE_KEY,
            reason="Key không có quyền truy cập model/endpoint này (403).",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    if isinstance(exc, getattr(litellm, "BudgetExceededError", ())):
        return Verdict(
            ErrorAction.DISABLE_KEY,
            reason="Key đã vượt ngân sách (budget) cấu hình.",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    if isinstance(exc, litellm.NotFoundError):
        # Model name sai / endpoint không tồn tại cho key này.
        # Đây là cấu hình của RIÊNG key này -> loại key + báo admin sửa model_name.
        return Verdict(
            ErrorAction.DISABLE_KEY,
            reason="Model/endpoint không tồn tại với key này (404). Kiểm tra model_name.",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    # ---- NHÓM 1: Rate limit -> cho key NGỦ rồi xoay tiếp -----------------------
    if isinstance(exc, litellm.RateLimitError):
        if _is_daily_limit(text):
            return Verdict(
                ErrorAction.DISABLE_KEY,   # quota/ngày: coi như chết tới mai
                reason="Đã chạm quota theo NGÀY của key này.",
                retry_after=COOLDOWN_RATE_LIMIT_DAY,
                notify_admin=False,
                permanent=True,            # hôm nay đừng đụng lại
                raw=raw,
            )
        return Verdict(
            ErrorAction.COOLDOWN_KEY,      # limit/phút: ngủ ngắn rồi quay lại
            reason="Rate limit theo phút (RPM/TPM). Cho key nghỉ ngắn.",
            retry_after=COOLDOWN_RATE_LIMIT_MINUTE,
            notify_admin=False,
            raw=raw,
        )

    # ---- NHÓM 2: Provider lỗi tạm thời -> retry/xoay ---------------------------
    if isinstance(exc, (litellm.Timeout, litellm.APIConnectionError)):
        return Verdict(
            ErrorAction.RETRY_SAME,
            reason="Timeout / lỗi kết nối mạng. Thử lại chính key này.",
            retry_after=BACKOFF_NETWORK,
            raw=raw,
        )

    if isinstance(exc, (litellm.ServiceUnavailableError, litellm.InternalServerError)):
        return Verdict(
            ErrorAction.ROTATE_KEY,
            reason="Provider đang lỗi (5xx). Xoay sang key/endpoint khác.",
            retry_after=BACKOFF_PROVIDER_5XX,
            raw=raw,
        )

    # ---- NHÓM 4: BadRequest tổng quát (sau khi đã loại 2 con ở trên) -----------
    if isinstance(exc, (litellm.BadRequestError, litellm.UnprocessableEntityError)):
        # Payload sai cấu trúc / tham số không hợp lệ / schema sai.
        # MỌI key sẽ fail y hệt -> dừng, báo admin sửa, đừng đốt key.
        return Verdict(
            ErrorAction.ABORT_ADMIN,
            reason="Request sai cấu trúc/tham số (4xx). Mọi key đều fail như nhau.",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    # Một số provider/litellm adapter bọc lỗi 4xx vào APIError chung.
    # Phân loại theo nội dung để tránh retry/rotate tới khi hết max_attempts.
    if _contains_any(text, ("invalid api key", "api key not valid", "unauthorized", "authentication", "401")):
        return Verdict(
            ErrorAction.DISABLE_KEY,
            reason="API key sai hoặc provider từ chối xác thực.",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    if _contains_any(text, ("model not found", "not found", "404", "unknown model", "model does not exist")):
        return Verdict(
            ErrorAction.DISABLE_KEY,
            reason="Model/endpoint không tồn tại hoặc key không truy cập được model này.",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    if _contains_any(text, ("bad request", "invalid request", "invalid argument", "400")):
        return Verdict(
            ErrorAction.ABORT_ADMIN,
            reason="Request LLM sai tham số hoặc model không hỗ trợ payload này.",
            notify_admin=True,
            permanent=True,
            raw=raw,
        )

    # ---- NHÓM 2: APIError chung chung -> xoay thử ------------------------------
    if isinstance(exc, litellm.APIError):
        return Verdict(
            ErrorAction.ROTATE_KEY,
            reason="Lỗi API không xác định rõ. Xoay sang key khác để thử.",
            retry_after=BACKOFF_PROVIDER_5XX,
            raw=raw,
        )

    # ---- FALLBACK: lỗi hoàn toàn lạ (vd parse JSON, lỗi code của ta) -----------
    # KHÔNG đổ lỗi cho key. Mặc định bỏ request + báo admin để soi log.
    return Verdict(
        ErrorAction.SKIP_REQUEST,
        reason=f"Lỗi không thuộc nhóm litellm đã biết: {type(exc).__name__}",
        notify_admin=True,
        raw=raw,
    )

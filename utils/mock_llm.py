"""Mock LLM — CHO SẴN, KHÔNG CẦN SỬA.

Trả lời tất định (cùng câu hỏi → cùng câu trả lời) nên không cần API key,
không tốn tiền, và test luôn cho kết quả ổn định.

Dùng:
    from utils.mock_llm import generate_reply
    result = generate_reply("Docker là gì?", history=[...])
    result["text"], result["prompt_tokens"], result["completion_tokens"], result["usd_cost"]
"""

from __future__ import annotations

import hashlib

# Giá giả lập, tính theo 1.000 token (giống thang giá gpt-4o-mini)
PRICE_PROMPT_PER_1K = 0.00015
PRICE_COMPLETION_PER_1K = 0.00060

_TEMPLATES = [
    "Theo mình hiểu, {q} liên quan tới cách hệ thống được đóng gói và vận hành. "
    "Điểm mấu chốt là tách cấu hình ra khỏi code và giữ service ở trạng thái stateless.",
    "Câu hỏi hay. {q} thường được giải quyết bằng cách chuẩn hóa môi trường chạy: "
    "cùng một image chạy giống nhau ở laptop và trên cloud.",
    "Ngắn gọn: {q} phụ thuộc vào ba yếu tố — cấu hình qua biến môi trường, "
    "health check để orchestrator biết trạng thái, và giới hạn tài nguyên.",
    "Với {q}, cách làm phổ biến trong production là đặt một lớp gateway phía trước "
    "để lo authentication, rate limiting và bảo vệ chi phí.",
]


def _estimate_tokens(text: str) -> int:
    """Ước lượng thô: ~4 ký tự / token, tối thiểu 1."""
    return max(1, len(text) // 4)


def generate_reply(message: str, history: list[dict] | None = None) -> dict:
    """Giả lập một lượt gọi LLM.

    Args:
        message: tin nhắn của người dùng.
        history: lịch sử hội thoại, list các dict {"role": ..., "content": ...}.

    Returns:
        dict gồm text, prompt_tokens, completion_tokens, usd_cost.
    """
    history = history or []
    digest = hashlib.sha256(message.strip().lower().encode("utf-8")).hexdigest()
    template = _TEMPLATES[int(digest[:8], 16) % len(_TEMPLATES)]
    text = template.format(q=message.strip().rstrip("?") or "vấn đề bạn hỏi")

    if history:
        text += f" (Mình đang nhớ {len(history)} lượt trao đổi trước đó.)"

    prompt_text = message + "".join(turn.get("content", "") for turn in history)
    prompt_tokens = _estimate_tokens(prompt_text)
    completion_tokens = _estimate_tokens(text)
    cost = (
        prompt_tokens / 1000 * PRICE_PROMPT_PER_1K
        + completion_tokens / 1000 * PRICE_COMPLETION_PER_1K
    )

    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "usd_cost": round(cost, 8),
    }

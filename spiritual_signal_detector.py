"""
Spiritual Signal Detector Module
Detects Spiritual SOS signals from Thai LINE OA messages using keyword-based triggers.
Supports C-Stage classification: C1 (Engage/Soft), C2 (Connect), C3 (Transform).
"""

import re
from typing import List, Optional, Dict, Any

# ───────────────────────────────────────────────────────────────
# Trigger Words — exact phrases from product.md
# ───────────────────────────────────────────────────────────────
TRIGGER_WORDS = {
    "C3_CRITICAL": [
        "อยากเชื่อ",
        "ฉันเชื่อแล้ว",
        "อธิษฐานรับพระเยซูแล้ว",
        "อยากให้พระเจ้ามานำชีวิต",
        "รู้สึกเหมือนได้เริ่มใหม่",
        "ชีวิตเปลี่ยนจริงๆ",
        "หัวใจเปิด 100%",
    ],
    "C2_HIGH_INTENT": [
        "อยากรู้จักพระเจ้าให้มากขึ้น",
        "อยากรู้จักพระเจ้า",
        "พระเจ้าฟังเราไหม",
        "พระเจ้าฟังไหม",
        "อยากลองเชื่อดู",
        "ถ้าจะเชื่อต้องทำยังไง",
        "ถ้าจะเชื่อทำยังไง",
        "รู้สึกว่าพระเจ้ากำลังเรียกเรา",
        "พระเจ้ากำลังเรียก",
        "เริ่มอธิษฐานแล้วรู้สึกแปลกๆ",
        "เริ่มอธิษฐาน",
    ],
    "C1_SOFT_URGENT": [
        "เหนื่อยมาก ไม่รู้จะอยู่ไปเพื่ออะไร",
        "รู้สึกว่างเปล่า",
        "อยากหาที่พึ่ง",
        "มีใครสักคนที่เข้าใจไหม",
        "เหมือนมีอะไรบางอย่างกำลังเรียกเรา",
    ],
}

# Confidence weights per stage (higher = more urgent)
STAGE_CONFIDENCE = {
    "C3": 0.95,
    "C2": 0.80,
    "C1": 0.65,
}


def _normalize(text: str) -> str:
    """Normalize Thai text for matching: lowercase, strip extra spaces."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _find_matches(text: str, triggers: List[str]) -> List[str]:
    """Find all trigger phrases present in text (substring match)."""
    normalized = _normalize(text)
    matches = []
    for phrase in triggers:
        if _normalize(phrase) in normalized:
            matches.append(phrase)
    return matches


def detect_spiritual_signal(
    message: str,
    context_messages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Detect spiritual SOS signals from a single message with optional context.

    Args:
        message: The latest incoming message (Thai).
        context_messages: Last 3-5 messages before `message` for context aggregation.

    Returns:
        {
            "detected": bool,
            "c_stage": "C1" | "C2" | "C3" | None,
            "confidence": float,
            "matched_signals": list[str],
        }
    """
    if not message or not isinstance(message, str):
        return {
            "detected": False,
            "c_stage": None,
            "confidence": 0.0,
            "matched_signals": [],
        }

    # Build aggregated text: context + current message
    aggregated_parts = []
    if context_messages:
        # Take last 3-5 messages before current
        recent_context = context_messages[-5:]
        aggregated_parts.extend(recent_context)
    aggregated_parts.append(message)
    aggregated_text = " ".join(aggregated_parts)

    # Check each stage in descending urgency (C3 → C2 → C1)
    for stage_key, stage_label in [("C3_CRITICAL", "C3"), ("C2_HIGH_INTENT", "C2"), ("C1_SOFT_URGENT", "C1")]:
        triggers = TRIGGER_WORDS[stage_key]
        matches = _find_matches(aggregated_text, triggers)
        if matches:
            return {
                "detected": True,
                "c_stage": stage_label,
                "confidence": STAGE_CONFIDENCE[stage_label],
                "matched_signals": matches,
            }

    # No match
    return {
        "detected": False,
        "c_stage": None,
        "confidence": 0.0,
        "matched_signals": [],
    }


# ───────────────────────────────────────────────────────────────
# Quick test / CLI usage
# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        ("สบายดีค่ะ วันนี้อากาศดี", None),
        ("รู้สึกว่างเปล่ามากเลยค่ะ", None),
        ("อยากรู้จักพระเจ้าให้มากขึ้นค่ะ", None),
        ("ฉันเชื่อแล้วค่ะ พระเยซู", None),
        ("สวัสดี", ["เหนื่อยมาก ไม่รู้จะอยู่ไปเพื่ออะไร", "รู้สึกว่างเปล่า"]),
    ]
    for msg, ctx in test_cases:
        result = detect_spiritual_signal(msg, ctx)
        print(f"MSG: {msg[:40]:<40} → {result}")

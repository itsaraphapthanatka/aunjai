"""
Unified Classifier Module
Combines Physical SOS + Spiritual SOS classification into a single priority-ranked output.

Priority Logic (descending):
  Physical CRITICAL > Spiritual C3 > Physical HIGH > Spiritual C2 > Physical MEDIUM > Spiritual C1 > rest
"""

from typing import List, Optional, Dict, Any
from spiritual_signal_detector import detect_spiritual_signal


# ───────────────────────────────────────────────────────────────
# Physical SOS stubs (to be replaced by existing physical classifier integration)
# ───────────────────────────────────────────────────────────────
def _detect_physical_sos(message: str) -> Optional[Dict[str, Any]]:
    """
    Stub for existing physical SOS classifier.
    Returns: {"level": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW", "confidence": float} or None.
    """
    # TODO: integrate with existing physical classifier
    # For now, return None to let spiritual signals take priority in demo
    return None


# ───────────────────────────────────────────────────────────────
# Priority ranking constants
# ───────────────────────────────────────────────────────────────
PRIORITY_RANK = {
    ("physical", "CRITICAL"): 1,
    ("spiritual", "C3"): 2,
    ("physical", "HIGH"): 3,
    ("spiritual", "C2"): 4,
    ("physical", "MEDIUM"): 5,
    ("spiritual", "C1"): 6,
    ("physical", "LOW"): 7,
}

SLA_MINUTES = {
    ("spiritual", "C3"): 5,
    ("spiritual", "C2"): 15,
    ("spiritual", "C1"): 30,
    ("physical", "CRITICAL"): 5,
    ("physical", "HIGH"): 15,
    ("physical", "MEDIUM"): 30,
    ("physical", "LOW"): 60,
}

ALERT_CARD_TYPE = {
    ("physical", "CRITICAL"): "physical_critical",
    ("physical", "HIGH"): "physical_high",
    ("physical", "MEDIUM"): "physical_medium",
    ("physical", "LOW"): "physical_low",
    ("spiritual", "C3"): "spiritual_c3",
    ("spiritual", "C2"): "spiritual_c2",
    ("spiritual", "C1"): "spiritual_c1",
}


def classify(
    message: str,
    context_messages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Unified classification for Physical + Spiritual SOS.

    Args:
        message: Latest incoming message.
        context_messages: Last 3-5 messages before detection.

    Returns:
        {
            "type": "physical" | "spiritual" | "none",
            "level": str,            # physical level or spiritual C-stage
            "c_stage": str | None,   # spiritual C-stage if applicable
            "confidence": float,
            "escalate": bool,
            "response_time_minutes": int,
            "alert_card_type": str,
            "physical": dict | None,
            "spiritual": dict | None,
        }
    """
    # Run both classifiers
    physical = _detect_physical_sos(message)
    spiritual = detect_spiritual_signal(message, context_messages)

    candidates = []

    if physical:
        level = physical.get("level", "LOW")
        conf = physical.get("confidence", 0.5)
        candidates.append({
            "type": "physical",
            "level": level,
            "c_stage": None,
            "confidence": conf,
            "rank": PRIORITY_RANK.get(("physical", level), 99),
            "detail": physical,
        })

    if spiritual and spiritual["detected"]:
        c_stage = spiritual["c_stage"]
        conf = spiritual["confidence"]
        candidates.append({
            "type": "spiritual",
            "level": c_stage,
            "c_stage": c_stage,
            "confidence": conf,
            "rank": PRIORITY_RANK.get(("spiritual", c_stage), 99),
            "detail": spiritual,
        })

    if not candidates:
        return {
            "type": "none",
            "level": "none",
            "c_stage": None,
            "confidence": 0.0,
            "escalate": False,
            "response_time_minutes": 0,
            "alert_card_type": "none",
            "physical": physical,
            "spiritual": spiritual,
        }

    # Pick highest priority (lowest rank number)
    winner = min(candidates, key=lambda c: c["rank"])

    key = (winner["type"], winner["level"])
    response_time = SLA_MINUTES.get(key, 60)
    alert_card = ALERT_CARD_TYPE.get(key, "unknown")
    escalate = winner["rank"] <= 4  # CRITICAL / C3 / HIGH / C2

    return {
        "type": winner["type"],
        "level": winner["level"],
        "c_stage": winner["c_stage"],
        "confidence": winner["confidence"],
        "escalate": escalate,
        "response_time_minutes": response_time,
        "alert_card_type": alert_card,
        "physical": physical,
        "spiritual": spiritual,
    }


# ───────────────────────────────────────────────────────────────
# Quick test / CLI usage
# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_msgs = [
        "สบายดีค่ะ",
        "รู้สึกว่างเปล่ามากเลยค่ะ",
        "อยากรู้จักพระเจ้าให้มากขึ้นค่ะ",
        "ฉันเชื่อแล้วค่ะ พระเยซู",
    ]
    for m in test_msgs:
        print(classify(m))

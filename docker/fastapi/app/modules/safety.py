from __future__ import annotations

import re


BLOCKED_PATTERNS = [
    r"\bminor\b",
    r"\bunderage\b",
    r"\bchild\b",
    r"\brape\b",
]


def assert_safe_text(text: str) -> None:
    lowered = text.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            raise ValueError(
                "Request blocked by safety policy: only consensual fictional adults or rights-cleared adults are allowed."
            )


def assert_adult_age(age: int) -> None:
    if age < 15:
        raise ValueError("Character age must be 15 or older.")

"""One helper to print a counted noun in English: "1 call", "2 calls"."""
from __future__ import annotations


def contar(n: int, singular: str, plural: str | None = None) -> str:
    """`contar(1, "call")` → "1 call"; `contar(2, "call")` → "2 calls" (`plural` for irregular nouns)."""
    return f"{n} {singular if n == 1 else plural or singular + 's'}"

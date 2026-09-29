"""
numeric.py — Exact-decimal parse / multiply / format helpers for Phase 2.
The only module that imports `decimal` (PHASE2_ARCHITECTURE.md section 1.3).

Stage 2 builds parse/format (config.NUMERIC_VALUE_RE is the single definition
of "numeric", shared with the P17 template value check). `multiply` and the
Inexact-trapping arithmetic path are Stage 3's calculation work
(PHASE2_ARCHITECTURE.md section 14 row 3), but the function is trivial and
uses only what is already defined here, so it is included now.

The two contexts below are used EXPLICITLY everywhere in this module
(`ARITH_CONTEXT.multiply`, `quantize(..., context=...)`). The thread-local
global context (`decimal.getcontext()`) is never read or modified, because
Streamlit runs sessions on worker threads (section 2.2).
"""

from __future__ import annotations

import re
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
)

import config

ARITH_CONTEXT = Context(
    prec=config.ARITH_PRECISION,
    rounding=ROUND_HALF_EVEN,
    traps=[InvalidOperation, DivisionByZero, Overflow, Inexact],
)
ROUNDING_CONTEXT = Context(
    prec=config.ARITH_PRECISION,
    rounding=ROUND_HALF_UP,
    traps=[InvalidOperation],
)

_NUMERIC_VALUE_RE = re.compile(config.NUMERIC_VALUE_RE)


class NotANumber(ValueError):
    """Raised by parse_number; .text is the stripped offending text."""

    def __init__(self, text: str) -> None:
        super().__init__(f"not a number: {text!r}")
        self.text = text


def is_plain_number(text: str) -> bool:
    """re.fullmatch(config.NUMERIC_VALUE_RE, text.strip()) is not None.

    Blank text returns False — callers test blank first (section 2.1).
    """
    return _NUMERIC_VALUE_RE.fullmatch(text.strip()) is not None


def parse_number(text: str) -> Decimal | None:
    """None if text.strip() == ""; NotANumber if not is_plain_number(text);
    else Decimal(text.strip()) (section 2.1). The Decimal() constructor is
    exact and context-independent — no context is consulted here.
    """
    stripped = text.strip()
    if stripped == "":
        return None
    if not is_plain_number(stripped):
        raise NotANumber(stripped)
    return Decimal(stripped)


def multiply(*values: Decimal) -> Decimal:
    """Left-to-right ARITH_CONTEXT.multiply (section 2.2).

    Raises decimal.Inexact if an exact result would need more than
    config.ARITH_PRECISION significant digits — the caller converts that
    into a P2W_VALUE_TOO_PRECISE warning (Stage 3).
    """
    result = values[0]
    for value in values[1:]:
        result = ARITH_CONTEXT.multiply(result, value)
    return result


def format_number(value: Decimal) -> str:
    """Fixed notation, exact, no exponent, no trailing zeros (section 2.3)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text


def format_rounded(value: Decimal, quantum: str) -> str:
    """value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP,
    context=ROUNDING_CONTEXT), then format(q, "f") with trailing zeros KEPT
    ("2.00"); a negative zero ("-0.00") becomes "0.00" (section 2.3).
    """
    quantized = value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP, context=ROUNDING_CONTEXT)
    text = format(quantized, "f")
    if quantized.is_zero() and text.startswith("-"):
        text = text[1:]
    return text

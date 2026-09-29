"""
csv_writer.py — Timestamped filenames + UTF-8-BOM bytes for download.
No streamlit import, no filesystem writes, zero arithmetic. This module
never reads or transforms data — it only formats a filename string and
encodes an already-final DataFrame to bytes.

`now` is injectable on both filename builders purely so tests can assert
the exact filename string deterministically (ARCHITECTURE.md section 1).
"""

from __future__ import annotations

from datetime import datetime

import config


def build_master_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'Master_Instacart_2026-09-07_1430.csv' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.MASTER_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


def build_exception_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'Exceptions_Instacart_2026-09-07_1430.csv' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.EXCEPTION_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


# =============================================================================
# PHASE 2 — same {name}/{timestamp} contract as the two builders above
# (PHASE2_ARCHITECTURE.md section 1.13). build_final_filename and
# build_phase2_warnings_filename are Stage 4 consumers (final_builder.py,
# report.py); added now since all three share the identical shape.
# =============================================================================


def build_template_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'studyname_master_Instacart_2026-09-28_1430.xlsx' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.TEMPLATE_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


def build_final_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'after_formulas_master_Instacart_2026-09-28_1430.csv' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.FINAL_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


def build_phase2_warnings_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'phase2_warnings_Instacart_2026-09-28_1430.csv' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.PHASE2_WARNINGS_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


def to_csv_bytes(df) -> bytes:
    """df.to_csv(index=False).encode(config.OUTPUT_ENCODING).

    MUST NOT pass float_format. MUST NOT be preceded by any rounding —
    see ARCHITECTURE.md section 5's banned-call list. Every cell entering
    this function is already a Python str (guaranteed upstream by
    file_reader._finalize and schema.py), so to_csv never has anything to
    coerce.
    """
    return df.to_csv(index=False).encode(config.OUTPUT_ENCODING)

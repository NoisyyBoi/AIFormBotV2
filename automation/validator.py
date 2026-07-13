"""
Phase 2 — Field map validator.

Responsibilities:
  - Detect duplicate AutomationIds.
  - Detect input controls with missing (empty) labels.
  - Detect duplicate label strings.
  - Log every violation clearly.
  - Return a ValidationResult so callers decide whether to abort or continue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter

from loguru import logger

from ui.field_mapper import FieldEntry


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    duplicate_ids: list[str] = field(default_factory=list)
    missing_labels: list[str] = field(default_factory=list)   # automation_ids
    duplicate_labels: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(
            self.duplicate_ids
            or self.missing_labels
            or self.duplicate_labels
        )


# ── Individual checks ─────────────────────────────────────────────────────────

def _check_duplicate_ids(entries: list[FieldEntry]) -> list[str]:
    """Return automation_ids that appear more than once."""
    counts = Counter(e.automation_id for e in entries)
    return [aid for aid, n in counts.items() if n > 1]


def _check_missing_labels(entries: list[FieldEntry]) -> list[str]:
    """Return automation_ids whose resolved label is empty."""
    return [e.automation_id for e in entries if not e.label.strip()]


def _check_duplicate_labels(entries: list[FieldEntry]) -> list[str]:
    """Return label strings that are assigned to more than one control."""
    labelled = [e.label.strip() for e in entries if e.label.strip()]
    counts = Counter(labelled)
    return [lbl for lbl, n in counts.items() if n > 1]


# ── Public API ────────────────────────────────────────────────────────────────

def validate_field_map(entries: list[FieldEntry]) -> ValidationResult:
    """
    Run all validation checks against *entries*.

    Logs every violation at WARNING level.
    Logs a final PASS / FAIL summary.
    Does NOT raise — callers inspect ValidationResult.has_errors.
    """
    result = ValidationResult(
        duplicate_ids=_check_duplicate_ids(entries),
        missing_labels=_check_missing_labels(entries),
        duplicate_labels=_check_duplicate_labels(entries),
    )

    # ── report duplicate IDs ──────────────────────────────────────────────────
    if result.duplicate_ids:
        logger.warning(
            "VALIDATION — {} duplicate AutomationId(s) found:",
            len(result.duplicate_ids),
        )
        for aid in result.duplicate_ids:
            logger.warning("  duplicate id: '{}'", aid)
    else:
        logger.debug("VALIDATION — no duplicate AutomationIds.")

    # ── report missing labels ─────────────────────────────────────────────────
    if result.missing_labels:
        logger.warning(
            "VALIDATION — {} control(s) have no label:",
            len(result.missing_labels),
        )
        for aid in result.missing_labels:
            logger.warning("  missing label for id: '{}'", aid)
    else:
        logger.debug("VALIDATION — all controls have labels.")

    # ── report duplicate labels ───────────────────────────────────────────────
    if result.duplicate_labels:
        logger.warning(
            "VALIDATION — {} duplicate label(s) found:",
            len(result.duplicate_labels),
        )
        for lbl in result.duplicate_labels:
            logger.warning("  duplicate label: '{}'", lbl)
    else:
        logger.debug("VALIDATION — no duplicate labels.")

    # ── summary ───────────────────────────────────────────────────────────────
    if result.has_errors:
        logger.warning(
            "VALIDATION FAILED — {} duplicate id(s), {} missing label(s), "
            "{} duplicate label(s).",
            len(result.duplicate_ids),
            len(result.missing_labels),
            len(result.duplicate_labels),
        )
    else:
        logger.info("VALIDATION PASSED — no issues found.")

    return result

"""Findings read as a CI check reads them: the verdict, the checklist that ends a command's lines, and the gate.

Every verb that judges a part says its findings alike through here: ``cadgen fea solve`` today, and a manufacturing
check the same way. A finding is the KiCad/FEA/CAM dict (``severity``, ``type``, ``summary``, ``items``), and may
carry what it ``measured`` against its limit (``{"value", "limit", "units", "pass_when"}``, optionally
``"quantity"``) and the ``fix`` that makes it pass (``{"action", "summary", "where", "params"}``, optionally
``"alternatives"``); :func:`cadgen._internal.fea.analyses.base.finding` makes one.

- :func:`verdict`: CAM's shape, ``{"status": "ready" | "fix", "headline", "errors", "warnings", "passed"}``. Ready
  means no error: a warning is a risk to weigh, never a stop.
- :func:`checklist_lines`: one plain line per check, failures first (``FAIL``, ``WARN``, ``PASS``: what it measured
  against its limit, where, and ``fix:``), then the verdict.
- :func:`fail_on_value`, :func:`gate_failed` and :func:`exit_code`: a caller's gate. ``fail_on`` ``"error"`` fails on
  any error, ``"warning"`` on any error or warning. A result that ran but failed its gate exits
  :data:`cadgen._internal.cli_from_function.GATE_EXIT` (3) through a generated CLI when it carries ``gate_failed``;
  ``ok`` never carries it.

Stdlib only, and nothing else of cadgen's at import: results and their ``human_lines`` call it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

__all__ = ["CHECK_WORDS", "FAIL_ON", "checklist_lines", "exit_code", "fail_on_value", "gate_failed", "verdict"]

#: The severities a caller may fail on, the least that fails the gate.
FAIL_ON = ("error", "warning")
#: A checklist line's status word for each severity: an ``info`` that measured something is a check that passed.
CHECK_WORDS = {"error": "FAIL", "warning": "WARN", "info": "PASS"}
_RANK = {"error": 0, "warning": 1, "info": 2}
#: The units written against their number, with no space between.
_CLOSE_UNITS = ("", "×", "%", "°")


def _is_check(finding: dict) -> bool:
    """An error, a warning, or an ``info`` that measured something (a pass); a note that measured nothing is not."""
    return finding.get("severity") in ("error", "warning") or bool(finding.get("measured"))


def _words(kind: str) -> str:
    return str(kind).replace("_", " ")


def verdict(findings: Iterable[dict], *, ready: str = "Ready") -> dict:
    """The findings' verdict in CAM's shape: ``status`` ``ready`` (no error) or ``fix``, a ``headline``, and how many
    ``errors``, ``warnings`` and ``passed`` checks.

    ready: the headline when nothing is to fix, the process's words ("Ready to cast · solid in 41 s"). With errors it
        is "1 to fix · shrinkage hot spot" (each kind of error once, in the findings' order).
    """
    found = list(findings)
    errors = [f for f in found if f.get("severity") == "error"]
    warnings = sum(1 for f in found if f.get("severity") == "warning")
    passed = sum(1 for f in found if f.get("severity") == "info" and f.get("measured"))
    if errors:
        kinds = ", ".join(dict.fromkeys(_words(f.get("type", "")) for f in errors))
        headline = f"{len(errors)} to fix · {kinds}"
    else:
        headline = ready
    return {"status": "fix" if errors else "ready", "headline": headline, "errors": len(errors), "warnings": warnings,
            "passed": passed}


def fail_on_value(value: str | None) -> str | None:
    """``fail_on`` as given, or a ValueError naming it: ``None``, ``"error"`` or ``"warning"``."""
    if value is not None and value not in FAIL_ON:
        raise ValueError(f"fail_on: {value!r} is not a severity to fail on; use {' or '.join(FAIL_ON)}")
    return value


def gate_failed(found_verdict: dict, fail_on: str | None) -> bool:
    """Whether a :func:`verdict` fails the gate ``fail_on``: ``"error"`` on any error, ``"warning"`` on any error or
    warning; ``None`` never."""
    if fail_on_value(fail_on) is None:
        return False
    return found_verdict["errors"] > 0 or (fail_on == "warning" and found_verdict["warnings"] > 0)


def exit_code(found_verdict: dict, fail_on: str | None) -> int:
    """The exit code a verdict gives a run that ran: ``GATE_EXIT`` (3) when it fails ``fail_on``, else 0."""
    from cadgen._internal.cli_from_function import GATE_EXIT

    return GATE_EXIT if gate_failed(found_verdict, fail_on) else 0


def _figure(value: float) -> str:
    """A measured number as a checklist says it: three significant figures, plainly (0.873, 25.8, 6780)."""
    value = float(value)
    if value == 0 or not math.isfinite(value):
        return f"{value:g}"
    return f"{round(value, max(0, 2 - math.floor(math.log10(abs(value))))):g}"


def _measured_words(measured: dict) -> str:
    """"liquid cut off: 6780 mm³, needs below 13.6 mm³": the value against its limit, and which side passes, or the
    value alone when the check judges no limit ("largest distortion: 0.43 mm"). A unit written against its number
    takes no space: "1.1×", "26%", "0.724°"."""
    units = str(measured.get("units") or "")

    def amount(number) -> str:
        return f"{_figure(number)}{'' if units in _CLOSE_UNITS else ' '}{units}"

    head = f"{measured['quantity']}: " if measured.get("quantity") else ""
    if measured.get("limit") is None:
        return f"{head}{amount(measured['value'])}"
    return f"{head}{amount(measured['value'])}, needs {measured.get('pass_when', 'below')} {amount(measured['limit'])}"


def _where_words(finding: dict) -> str:
    """Where a finding is, from its first item: "at #o1.f5 [0.667, -4.333, 3.0] mm", or the face or point alone."""
    items = finding.get("items") or ()
    if not items:
        return ""
    ref, at = items[0].get("ref"), items[0].get("at")
    place = " ".join(part for part in (ref or "", f"{list(at)} mm" if at else "") if part)
    return f"at {place}" if place else ""


def checklist_lines(findings: Iterable[dict], found_verdict: dict | None = None, *, fail_on: str | None = None) -> list[str]:
    """The checklist that ends a command's lines: an engineer's read of the findings, as a CI check prints its own.

    One line per check, failures first, then warnings, then passes (stable within each): the status word, the
    finding's type, what it measured against its limit, where, and ``fix:`` with the fix's sentence::

        FAIL  shrinkage_hot_spot  liquid cut off: 6780 mm³, needs below 13.6 mm³; at [50.3, -1.1, 14.1] mm; fix: ...
        PASS  hand_check          simulation against the rule: 1.1×, needs below 3×

    A note (an ``info`` that measured nothing) is no check and is left out: its sentence is the caller's to print.
    Then the verdict (``found_verdict``, or the findings' own), and the gate when one is given:
    ``Verdict: 1 to fix · shrinkage hot spot · 1 failed, 1 warning, 2 passed; fails --fail-on error``.
    """
    found = list(findings)
    checks = sorted((f for f in found if _is_check(f)), key=lambda f: _RANK.get(f.get("severity"), 2))
    width = max((len(str(f.get("type", ""))) for f in checks), default=0)
    lines = []
    for f in checks:
        parts = [words for words in (
            _measured_words(f["measured"]) if f.get("measured") else "",
            _where_words(f),
            f"fix: {f['fix']['summary']}" if (f.get("fix") or {}).get("summary") else "",
        ) if words]
        head = f"{CHECK_WORDS[f['severity']]}  {str(f.get('type', '')):<{width}}"
        lines.append(f"{head}  {'; '.join(parts)}".rstrip())
    said = found_verdict if found_verdict else verdict(found)
    warnings = said["warnings"]
    line = (f"Verdict: {said['headline']} · {said['errors']} failed, {warnings} warning{'' if warnings == 1 else 's'}, "
            f"{said.get('passed', 0)} passed")
    if fail_on is not None:
        line += f"; {'fails' if gate_failed(said, fail_on) else 'passes'} --fail-on {fail_on}"
    return [*lines, line]

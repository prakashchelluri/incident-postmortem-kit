"""Load, render and lint structured incident files."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

# Prose sections in render order: (yaml key, heading).
TEXT_SECTIONS = [
    ("summary", "Summary"),
    ("impact", "Impact"),
    ("detection", "Detection"),
    ("root_cause", "Root cause"),
]
LIST_SECTIONS = [
    ("what_went_well", "What went well"),
    ("what_went_wrong", "What went wrong"),
    ("lessons", "Lessons learned"),
]
REQUIRED = ["title", *(k for k, _ in TEXT_SECTIONS), "timeline", "action_items",
            *(k for k, _ in LIST_SECTIONS)]

# Timeline entries may carry one of these markers; durations are measured from "start".
MARKERS = {"detected": "Time to detect", "mitigated": "Time to mitigate",
           "resolved": "Time to resolve"}

BLAME_WORDS = [
    "fault", "blame", "blamed", "careless", "carelessness", "should have known",
    "human error", "negligent", "negligence", "incompetent", "sloppy", "lazy",
    "screwed up", "dropped the ball",
]
BLAME_RE = re.compile(r"\b(" + "|".join(map(re.escape, BLAME_WORDS)) + r")\b", re.IGNORECASE)
RELATIVE_RE = re.compile(r"T\+(?:0|(?=\d)(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?)", re.IGNORECASE)


def load(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return data


def parse_time(value: Any) -> datetime | timedelta:
    """ISO 8601 timestamps become datetimes; relative times like 'T+1d 2h 30m' become
    offsets from incident start. Durations work as long as one file uses one style."""
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    m = RELATIVE_RE.fullmatch(text)
    if m:
        d, h, mins = (int(g or 0) for g in m.groups())
        return timedelta(days=d, hours=h, minutes=mins)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"unrecognised time {text!r} (use ISO 8601 or T+1d 2h 30m)") from None


def durations(timeline: list[dict]) -> dict[str, timedelta]:
    """Compute time to detect / mitigate / resolve from the first entry of each marker."""
    marks: dict[str, datetime | timedelta] = {}
    for entry in timeline or []:
        kind = entry.get("kind")
        if kind and kind not in marks:
            marks[kind] = parse_time(entry.get("at"))
    if "start" not in marks:
        return {}
    try:
        if len({type(v) for v in marks.values()}) > 1:
            raise TypeError
        return {label: marks[k] - marks["start"] for k, label in MARKERS.items() if k in marks}
    except TypeError:
        raise ValueError("timeline mixes time styles (absolute vs relative, or naive vs "
                         "timezone-aware); durations cannot be computed") from None


def fmt_duration(td: timedelta) -> str:
    minutes = int(td.total_seconds() // 60)
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    parts = [f"{days}d"] if days else []
    if days or hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins:02d}m" if parts else f"{mins}m")
    return " ".join(parts)


def fmt_time(value: Any) -> str:
    """Absolute times are normalised; relative times are shown as written."""
    try:
        parsed = parse_time(value)
    except ValueError:
        return str(value)
    if isinstance(parsed, datetime):
        return parsed.strftime("%Y-%m-%d %H:%M %Z").strip()
    return str(value)


def _cell(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split()).replace("|", "\\|")


def render(inc: dict[str, Any]) -> str:
    out = [f"# Postmortem: {inc.get('title', 'Untitled incident')}", ""]
    facts = [(k.capitalize(), inc.get(k)) for k in ("date", "severity", "status")]
    facts.append(("Authors", ", ".join(inc.get("authors") or [])))
    facts += [(label, fmt_duration(td)) for label, td in durations(inc.get("timeline")).items()]
    out += ["| | |", "|---|---|"]
    out += [f"| **{k}** | {_cell(v)} |" for k, v in facts if v]
    out += ["", "_Blameless postmortem: we look at how systems and processes allowed this to "
            "happen, not at who did what._", ""]

    for key, heading in TEXT_SECTIONS[:3]:
        out += [f"## {heading}", "", str(inc.get(key) or "_Not filled in._").strip(), ""]

    out += ["## Timeline", "", "| Time | Event |", "|---|---|"]
    for entry in inc.get("timeline") or []:
        marker = f" **[{entry['kind']}]**" if entry.get("kind") else ""
        out.append(f"| {_cell(fmt_time(entry.get('at')))} | {_cell(entry.get('event'))}{marker} |")
    out.append("")

    key, heading = TEXT_SECTIONS[3]
    out += [f"## {heading}", "", str(inc.get(key) or "_Not filled in._").strip(), ""]

    for key, heading in LIST_SECTIONS[:2]:
        out += [f"## {heading}", ""] + [f"- {item}" for item in inc.get(key) or ["_None._"]]
        out.append("")

    out += ["## Action items", "", "| # | Action | Owner | Due | Status |", "|---|---|---|---|---|"]
    for n, a in enumerate(inc.get("action_items") or [], 1):
        out.append(f"| {n} | {_cell(a.get('action'))} | {_cell(a.get('owner')) or '**unowned**'}"
                   f" | {_cell(a.get('due'))} | {_cell(a.get('status', 'open'))} |")
    out.append("")

    key, heading = LIST_SECTIONS[2]
    out += [f"## {heading}", ""] + [f"- {item}" for item in inc.get(key) or ["_None._"]]
    return "\n".join(out) + "\n"


def _strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def lint(inc: dict[str, Any]) -> list[str]:
    problems = [f"missing section: {key}" for key in REQUIRED if not inc.get(key)]

    for i, a in enumerate(inc.get("action_items") or []):
        what = _cell(a.get("action")) or "(no description)"
        for field in ("owner", "due"):
            if not a.get(field):
                problems.append(f"action_items[{i}] has no {field}: {what}")

    previous = None
    for i, entry in enumerate(inc.get("timeline") or []):
        try:
            current = parse_time(entry.get("at"))
            if previous is not None and current < previous:
                problems.append(f"timeline[{i}] is earlier than the entry before it")
            previous = current
        except ValueError as exc:
            problems.append(f"timeline[{i}].at: {exc}")
        except TypeError:
            problems.append(f"timeline[{i}].at: mixes absolute and relative time styles")
    try:
        durations(inc.get("timeline"))
    except ValueError as exc:
        problems.append(f"timeline: {exc}")

    for path, text in _strings(inc):
        for m in BLAME_RE.finditer(text):
            problems.append(f"{path}: blame-oriented wording {m.group(0)!r}; describe the "
                            "system or process gap instead")
    return problems

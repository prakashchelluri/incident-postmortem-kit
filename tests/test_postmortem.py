from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from postmortem.cli import main
from postmortem.core import durations, fmt_duration, lint, load, parse_time, render

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def incident(**overrides):
    base = {
        "title": "Test incident",
        "summary": "s", "impact": "i", "detection": "d", "root_cause": "r",
        "timeline": [
            {"at": "2026-01-10T10:00:00Z", "kind": "start", "event": "deploy"},
            {"at": "2026-01-10T10:12:00Z", "kind": "detected", "event": "alert fires"},
            {"at": "2026-01-10T11:05:00Z", "kind": "mitigated", "event": "rollback"},
            {"at": "2026-01-11T12:30:00Z", "kind": "resolved", "event": "fix deployed"},
        ],
        "action_items": [{"action": "add alert", "owner": "SRE", "due": "Sprint +1"}],
        "what_went_well": ["w"], "what_went_wrong": ["x"], "lessons": ["l"],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("value,expected", [
    ("T+0", timedelta()),
    ("T+45m", timedelta(minutes=45)),
    ("T+1d 2h 5m", timedelta(days=1, hours=2, minutes=5)),
    ("2026-01-10T10:00:00+00:00", datetime(2026, 1, 10, 10, tzinfo=UTC)),
    (datetime(2026, 1, 10, 10), datetime(2026, 1, 10, 10)),
])
def test_parse_time(value, expected):
    assert parse_time(value) == expected


@pytest.mark.parametrize("bad", ["T+", "T+5", "yesterday", ""])
def test_parse_time_rejects(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


def test_durations_absolute():
    d = durations(incident()["timeline"])
    assert d == {
        "Time to detect": timedelta(minutes=12),
        "Time to mitigate": timedelta(hours=1, minutes=5),
        "Time to resolve": timedelta(days=1, hours=2, minutes=30),
    }


def test_durations_relative_and_partial():
    tl = [{"at": "T+0", "kind": "start"}, {"at": "T+40m", "kind": "detected"}]
    assert durations(tl) == {"Time to detect": timedelta(minutes=40)}
    assert durations([{"at": "T+40m", "kind": "detected"}]) == {}  # no start, nothing to compute


def test_durations_mixed_styles_is_an_error():
    tl = [{"at": "T+0", "kind": "start"}, {"at": "2026-01-10T10:00:00", "kind": "detected"}]
    with pytest.raises(ValueError, match="mixes time styles"):
        durations(tl)


@pytest.mark.parametrize("td,text", [
    (timedelta(minutes=7), "7m"),
    (timedelta(hours=2, minutes=5), "2h 05m"),
    (timedelta(days=1, minutes=3), "1d 0h 03m"),
])
def test_fmt_duration(td, text):
    assert fmt_duration(td) == text


def test_render_sections_and_tables():
    md = render(incident(action_items=[{"action": "a | b", "due": "soon"}]))
    assert md.startswith("# Postmortem: Test incident\n")
    for heading in ["Summary", "Impact", "Detection", "Timeline", "Root cause",
                    "What went well", "What went wrong", "Action items", "Lessons learned"]:
        assert f"\n## {heading}\n" in md
    assert "| **Time to detect** | 12m |" in md
    assert "| **Time to resolve** | 1d 2h 30m |" in md
    assert "| 2026-01-10 10:12 UTC | alert fires **[detected]** |" in md
    assert "| 1 | a \\| b | **unowned** | soon | open |" in md


def test_lint_clean_incident():
    assert lint(incident()) == []


def test_lint_flags_missing_owner_sections_blame_and_order():
    inc = incident(
        lessons=[],
        action_items=[{"action": "fix it", "due": "x"}],
        summary="The outage was the on-call engineer's fault; he should have known.",
    )
    inc["timeline"][1]["at"] = "2026-01-10T09:00:00Z"
    problems = lint(inc)
    assert "missing section: lessons" in problems
    assert "action_items[0] has no owner: fix it" in problems
    assert "timeline[1] is earlier than the entry before it" in problems
    blame = [p for p in problems if "blame-oriented" in p]
    assert len(blame) == 2 and all(p.startswith("summary:") for p in blame)


def test_lint_does_not_flag_blameless():
    assert lint(incident(summary="This is a blameless review.")) == []


def test_examples_are_lint_clean_and_rendered_copies_are_current():
    for src in sorted(EXAMPLES.glob("*.yaml")):
        inc = load(src)
        assert lint(inc) == [], src.name
        assert src.with_suffix(".md").read_text(encoding="utf-8") == render(inc), src.name


def test_cli_new_render_lint(tmp_path, capsys):
    assert main(["new", "disk-full", "--dir", str(tmp_path)]) == 0
    path = tmp_path / "disk-full.yaml"
    assert yaml.safe_load(path.read_text())["title"] == "Disk full"
    assert main(["new", "disk-full", "--dir", str(tmp_path)]) == 2  # refuses to overwrite
    assert main(["new", "Bad Slug", "--dir", str(tmp_path)]) == 2

    assert main(["lint", str(path)]) == 1  # scaffold is empty, so lint complains
    assert "missing section: summary" in capsys.readouterr().out

    out = tmp_path / "out.md"
    assert main(["render", str(path), "-o", str(out)]) == 0
    assert out.read_text().startswith("# Postmortem: Disk full")

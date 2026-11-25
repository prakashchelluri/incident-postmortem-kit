"""Command line entry point: postmortem new | render | lint."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .core import lint, load, render

SCAFFOLD = """\
# Blameless postmortem source. Render with: postmortem render {slug}.yaml
# Times: ISO 8601 (2026-01-31T09:15:00Z) or relative to start (T+0, T+45m, T+1d 2h).
# Mark timeline entries with kind: start | detected | mitigated | resolved
# to get time-to-detect / mitigate / resolve computed for you.
title: "{title}"
date: ""
severity: ""
status: draft
authors: []

summary: ""
impact: ""
detection: ""

timeline:
  - at: "T+0"
    kind: start
    event: ""

root_cause: ""

what_went_well: []
what_went_wrong: []

action_items:
  - action: ""
    owner: ""
    due: ""
    status: open

lessons: []
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="postmortem", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="scaffold <slug>.yaml")
    n.add_argument("slug")
    n.add_argument("--dir", default=".", help="where to write the file (default: .)")
    r = sub.add_parser("render", help="render an incident YAML to markdown")
    r.add_argument("file")
    r.add_argument("-o", "--output", help="write to this file instead of stdout")
    li = sub.add_parser("lint", help="check an incident YAML; exit 1 on findings")
    li.add_argument("file")
    args = p.parse_args(argv)

    try:
        if args.cmd == "new":
            return _new(args.slug, Path(args.dir))
        incident = load(args.file)
        if args.cmd == "render":
            text = render(incident)
            if args.output:
                Path(args.output).write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            return 0
        problems = lint(incident)
        for problem in problems:
            print(f"{args.file}: {problem}")
        print(f"{len(problems)} problem(s) found" if problems else f"{args.file}: OK")
        return 1 if problems else 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _new(slug: str, directory: Path) -> int:
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise ValueError("slug must be lowercase words joined by hyphens, e.g. etcd-timeouts")
    path = directory / f"{slug}.yaml"
    if path.exists():
        raise ValueError(f"{path} already exists")
    title = slug.replace("-", " ").capitalize()
    path.write_text(SCAFFOLD.format(slug=slug, title=title), encoding="utf-8")
    print(f"created {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

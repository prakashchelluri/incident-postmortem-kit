# incident-postmortem-kit

A small toolkit for blameless postmortems: write the incident as structured YAML, render it to consistent markdown with computed time-to-detect/mitigate/resolve, and lint it for gaps and blame-oriented wording.

> Lab project: a clean-room reference implementation of a pattern I use at work. It contains no employer code or data.

## The problem

Postmortems written free-form in a wiki drift: sections get skipped, timelines are hard to read, nobody computes how long detection actually took, action items end up without an owner (so they never happen), and under pressure the wording slides from "what allowed this to happen" to "who did it". Keeping the source as YAML makes the structure checkable in review and in CI, and the markdown output stays uniform across teams.

## What is in here

- `TEMPLATE.md`: a blank blameless postmortem template (summary, impact, detection, timeline, root cause, what went well, what went wrong, action items with owner/due/status, lessons) for people who just want to fill in markdown.
- `postmortem new <slug>`: scaffolds `<slug>.yaml` with every field.
- `postmortem render incident.yaml [-o out.md]`: renders the markdown postmortem.
- `postmortem lint incident.yaml`: reports problems; exits 1 if there are any, so it can gate a pull request.
- `examples/`: two worked, sanitised incidents as YAML plus the rendered markdown:
  - [etcd timeouts on Dev and QA Kubernetes clusters](examples/etcd-timeouts.md)
  - [Artifact downloads failing after a DNS cut-over](examples/artifact-dns-cutover.md)

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q

postmortem new disk-full
postmortem lint disk-full.yaml
postmortem render examples/etcd-timeouts.yaml
```

## Example output

Real output from a local run. A fresh scaffold fails lint until it is filled in:

```text
$ postmortem new disk-full
created disk-full.yaml
$ postmortem lint disk-full.yaml
disk-full.yaml: missing section: summary
disk-full.yaml: missing section: impact
disk-full.yaml: missing section: detection
disk-full.yaml: missing section: root_cause
disk-full.yaml: missing section: what_went_well
disk-full.yaml: missing section: what_went_wrong
disk-full.yaml: missing section: lessons
disk-full.yaml: action_items[0] has no owner: (no description)
disk-full.yaml: action_items[0] has no due: (no description)
9 problem(s) found
```

A filled-in draft with an unowned action item and blame-oriented wording in the summary:

```text
$ postmortem lint blamey.yaml
blamey.yaml: action_items[0] has no owner: Add a disk usage alert
blamey.yaml: summary: blame-oriented wording 'careless'; describe the system or process gap instead
blamey.yaml: summary: blame-oriented wording 'should have known'; describe the system or process gap instead
3 problem(s) found
```

Rendering (start of [examples/artifact-dns-cutover.md](examples/artifact-dns-cutover.md)):

```text
$ postmortem render examples/artifact-dns-cutover.yaml
# Postmortem: Artifact downloads failing after a DNS cut-over

| | |
|---|---|
| **Date** | Relative timeline (T+0 = GeoDNS change applied) |
| **Severity** | SEV2 |
| **Status** | resolved |
| **Authors** | Platform SRE |
| **Time to detect** | 40m |
| **Time to mitigate** | 2h 30m |
| **Time to resolve** | 1d 2h 00m |
...
## Timeline

| Time | Event |
|---|---|
| T+0 | GeoDNS updated so artifacts.example.com resolves to the new site for one region. **[start]** |
| T+40m | Pipelines in the region report artifact pulls hanging. **[detected]** |
...
```

## Incident file format

```yaml
title: Disk full on build node
date: "2026-01-10"
severity: SEV3
status: draft
authors: [Platform SRE]
summary: ...
impact: ...
detection: ...
timeline:
  - {at: "2026-01-10T10:00:00Z", kind: start,     event: Disk reaches 100%}
  - {at: "2026-01-10T10:25:00Z", kind: detected,  event: Builds fail}
  - {at: "2026-01-10T10:50:00Z", kind: mitigated, event: Old images pruned}
root_cause: ...
what_went_well: [...]
what_went_wrong: [...]
action_items:
  - {action: Add a disk usage alert, owner: Platform SRE, due: Sprint +1, status: open}
lessons: [...]
```

Timeline times are either ISO 8601 timestamps or times relative to the start (`T+0`, `T+45m`, `T+1d 2h 30m`). Use one style per file.

## How it works

- **Durations**: the first timeline entry with `kind: start` is the reference point. Time to detect, mitigate and resolve are measured from it to the first entry marked `detected`, `mitigated` and `resolved`. A missing marker just leaves that row out; mixing absolute and relative times (or naive and timezone-aware timestamps) is reported as an error rather than guessed.
- **Render**: a fixed section order matching `TEMPLATE.md`, a facts table, a timeline table with markers, and an action item table where a missing owner shows as **unowned**. Table cells are escaped so a `|` in text does not break the table.
- **Lint** checks:
  - every section is present and non-empty;
  - every action item has an owner and a due date;
  - timeline times parse and are in order;
  - durations can be computed (no mixed time styles);
  - no blame-oriented wording anywhere in the file, from a short word list (`fault`, `blame`, `careless`, `should have known`, `human error`, `negligent`, ...), matched as whole words so "blameless" is fine.
- The tests also check that both examples are lint-clean and that the committed `.md` files match a fresh render.

## Limitations

- The blame check is a word list, not language understanding. It misses blame phrased politely and will flag technical uses such as "fault-tolerant"; rephrase or treat it as a prompt for a human reviewer.
- No HTML/PDF output and no publishing to a wiki; the output is markdown.
- Durations are measured from the first `start` marker only; there is no support for incidents with several separate impact windows beyond describing them in the timeline (as in the DNS example).
- The YAML is checked for the fields above, not against a full schema; unknown keys are ignored.

## License

MIT

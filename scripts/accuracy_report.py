# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""An offline maintainer report from benchmark outputs, never another run.

    python scripts/accuracy_report.py --results /tmp/benchmark-results \
        --out /tmp/accuracy/index.html [--factor-results factors.json] \
        [--history /tmp/bench-history] [--now /tmp/now]

Only current.json contains raw replay observations. expected.json and
reading.json are proposed baseline updates, and are never observations.
The report has no scripts, external assets, page photos or recognised text.
"""

import argparse
import html
import json
import math
from pathlib import Path


def load(path):
    """Read one supplied artifact. Malformed input is an error, not a pass."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def number(value):
    """Finite measurements only; bool is not a score."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(value):
    return f"{value:g}" if number(value) else "Not measured"


def delta(now, before):
    return (
        f"{now - before:+.2f}"
        if number(now) and number(before)
        else "Not comparable"
    )


def table(head, rows):
    """Escape every value, including identifiers supplied by an artifact."""
    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join(f'<th scope="col">{esc(x)}</th>' for x in head)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{esc(x)}</td>" for x in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def meter(value, maximum, label):
    """A visible value stays available when a browser cannot draw a meter."""
    if not number(value) or not number(maximum) or maximum <= 0:
        return f"<p>{esc(label)}: Not measured</p>"
    # Values are not clipped in the label, even for an out-of-range input.
    return (
        f"<p>{esc(label)}: <strong>{fmt(value)} / {fmt(maximum)}</strong> "
        f'<meter min="0" max="{maximum}" value="{value}" '
        f'aria-label="{esc(label)}">{fmt(value)}</meter></p>'
    )


def factor_chart(pages, old_pages, states):
    """Paired factor means on one 0..10 scale, excluding invalid pages."""
    factors = sorted(
        {n for p in pages.values() for n in p.get("scores", {})},
        key=lambda n: int(n) if n.isdigit() else 100,
    )
    rows = []
    for factor in factors:
        pairs = [
            (
                old_pages.get(name, {}).get("scores", {}).get(factor),
                page.get("scores", {}).get(factor),
            )
            for name, page in pages.items()
            if states.get(name, {}).get("state") == "valid"
        ]
        pairs = [(a, b) for a, b in pairs if number(a) and number(b)]
        if not pairs:
            continue
        before = sum(a for a, _b in pairs) / len(pairs)
        now = sum(b for _a, b in pairs) / len(pairs)
        label = (
            f"Factor {factor}: accepted {before:.2f}, observed {now:.2f}, "
            f"{len(pairs)} paired pages"
        )
        rows.append(
            f'<div class="factor"><span>F{esc(factor)} · {len(pairs)} paired pages</span>'
            f'<svg role="img" aria-label="{esc(label)}" viewBox="0 0 360 60">'
            f"<title>{esc(label)}</title>"
            f'<rect x="1" y="2" width="{max(0, min(before, 10)) * 26:.2f}" height="16" '
            'fill="none" stroke="currentColor" stroke-dasharray="4 2"/>'
            f'<text x="275" y="16" fill="currentColor">{before:.2f}</text>'
            f'<rect x="1" y="30" width="{max(0, min(now, 10)) * 26:.2f}" height="16" '
            'fill="currentColor"/>'
            f'<text x="275" y="44" fill="currentColor">{now:.2f}</text></svg></div>'
        )
    if not rows:
        return "<p>No valid paired factor measurements for a chart.</p>"
    return (
        "<h3>Factor scores on paired valid pages</h3>"
        "<p>Mean scores, 0 to 10. Dashed: accepted baseline. Solid: observed. "
        "Only pages with both measurements are paired; the count is shown. "
        "A higher score is not a detection-accuracy claim.</p>"
        '<div class="factors">' + "".join(rows) + "</div>"
    )


def replay_section(run):
    observed = run.get("observed", {})
    baseline = run.get("baseline", {})
    pages = observed.get("scores", {}).get("pages", {})
    old_pages = baseline.get("scores", {}).get("pages", {})
    reading = observed.get("reading") or {}
    old_reading = baseline.get("reading") or {}
    states = run.get("page_states", {})
    names = sorted(set(states) | set(pages) | set(old_pages))
    found = sum(p.get("sentences_found", 0) for p in pages.values())
    written = sum(s.get("written_lines", 0) for s in states.values())
    out = [
        f'<section><h2>{esc(run.get("set", "Unknown set"))}</h2>',
        f'<p><strong>{esc(run.get("status", "unknown"))}</strong> · '
        f'{esc(run.get("source", "Unknown source"))} · '
        f'commit {esc(run.get("sha") or "unknown")} · '
        f'{esc(run.get("date", "Unknown date"))}</p>',
        "<p>Current observations and accepted baselines are kept separately. "
        "A score change needs review; a higher score alone is not proof of better accuracy.</p>",
        meter(found, written, "Written lines scored (all expected pages)"),
        f'<p>Raw CER: <strong>{fmt(reading.get("cer"))}%</strong>; '
        f'accepted CER baseline: {fmt(old_reading.get("cer"))}%; '
        f'change: {delta(reading.get("cer"), old_reading.get("cer"))} percentage points.</p>',
        f'<p>{esc(run.get("reading_note", ""))}</p>',
    ]
    out.append(factor_chart(pages, old_pages, states))
    diagnostics = run.get("diagnostics", [])
    if diagnostics:
        out.append(
            "<h3>Run diagnostics</h3><ul>"
            + "".join(f"<li>{esc(x)}</li>" for x in diagnostics)
            + "</ul>"
        )
    rows, changes = [], []
    for name in names:
        page, old = pages.get(name, {}), old_pages.get(name, {})
        state = states.get(name, {})
        current_cer = reading.get("pages", {}).get(name, {}).get("cer")
        previous_cer = old_reading.get("pages", {}).get(name, {}).get("cer")
        rows.append(
            [
                name,
                state.get("state", "missing"),
                f'{fmt(page.get("sentences_found"))}/{fmt(state.get("written_lines"))}',
                fmt(page.get("repeats")),
                fmt(page.get("unmatched")),
                fmt(current_cer),
                fmt(previous_cer),
                delta(current_cer, previous_cer),
                "; ".join(state.get("diagnostics", [])),
            ]
        )
        scores = {"overall": page.get("overall"), **page.get("scores", {})}
        previous = {"overall": old.get("overall"), **old.get("scores", {})}
        for factor in sorted(
            set(scores) | set(previous), key=lambda n: (n != "overall", n)
        ):
            now, before = scores.get(factor), previous.get(factor)
            if now != before or not number(now):
                changes.append(
                    [
                        name,
                        factor,
                        fmt(before),
                        fmt(now),
                        delta(now, before),
                        state.get("state", "missing"),
                    ]
                )
    out += [
        "<h3>Page coverage and reading</h3>",
        table(
            [
                "Page",
                "State",
                "Lines scored/written",
                "Repeated",
                "Unmatched",
                "Raw CER %",
                "Baseline CER %",
                "CER change (pp)",
                "Diagnostic",
            ],
            rows,
        ),
        "<h3>Factor changes and unavailable measurements</h3>",
    ]
    out.append(
        table(
            [
                "Page",
                "Factor",
                "Accepted score",
                "Observed score",
                "Change",
                "Page state",
            ],
            changes,
        )
        if changes
        else "<p>No factor changes or unavailable measurements.</p>"
    )
    out.append("</section>")
    return "\n".join(out)


def factor_section(run):
    """Use measured pairs, never an accepted floor as a catch observation."""
    rows = []
    summary, baseline = run.get("summary", {}), run.get("baseline", {})
    for kind in sorted(set(summary) | (set(baseline) - {"same_passage"})):
        entry = summary.get(kind, {})
        targets = entry.get("targets", {})
        for factor in sorted(set(targets) | set(baseline.get(kind, {}))):
            target = targets.get(factor, {})
            count = target.get("measured", 0)
            attempted = (
                sum(r.get("kind") == kind for r in run["rows"])
                if "rows" in run
                else None
            )
            skipped = attempted - count if attempted is not None else None
            state = (
                "skipped"
                if count == 0
                else ("partial" if skipped else "measured")
            )
            observed = target.get("caught") if count > 0 else None
            before = baseline.get(kind, {}).get(factor)
            rows.append(
                [
                    kind,
                    factor,
                    state,
                    count,
                    fmt(attempted),
                    fmt(skipped),
                    entry.get("writers", 0),
                    fmt(observed),
                    fmt(before),
                    delta(observed, before),
                    fmt(target.get("drop")),
                    ", ".join(
                        f"F{n}: {fmt(v)}"
                        for n, v in entry.get("side_effects", {}).items()
                    )
                    or "None reported",
                ]
            )
    return "\n".join(
        [
            f'<section><h2>Planted detection: {esc(run.get("set", "factor output"))}</h2>',
            f'<p>Source: {esc(run.get("source", "factor_tests.py output; mode not recorded"))}. '
            f'Commit: {esc(run.get("sha") or "not recorded")}. '
            f'Status: {esc(run.get("status", "not recorded"))}.</p>',
            "<p>Catch rate is the share of measured clean/planted pairs with a factor drop "
            "of at least 0.1 points. Zero measured pairs means skipped, not a zero catch rate. "
            "Side effects are the largest reported changes in other factors.</p>",
            table(
                [
                    "Mistake",
                    "Factor",
                    "State",
                    "Measured pairs",
                    "Attempted pairs",
                    "Skipped pairs",
                    "Writers",
                    "Observed catch",
                    "Accepted floor",
                    "Change",
                    "Mean score drop",
                    "Other factor changes",
                ],
                rows,
            ),
            "<ul>"
            + "".join(f"<li>{esc(x)}</li>" for x in run.get("diagnostics", []))
            + "</ul>",
            "</section>",
        ]
    )


def spark(values, label):
    """Inline SVG leaves gaps at unavailable observations, never joins them."""
    valid = [v for v in values if number(v)]
    if not valid:
        return "<span>Not measured</span>"
    lo, hi = min(valid), max(valid)
    points, segments = [], []
    for index, value in enumerate(values):
        if not number(value):
            if points:
                segments.append(points)
                points = []
            continue
        x = 8 + index * 304 / max(1, len(values) - 1)
        y = 48 if hi == lo else 88 - (value - lo) * 80 / (hi - lo)
        points.append((x, y))
    if points:
        segments.append(points)
    drawings = []
    for segment in segments:
        drawings.append(
            '<polyline fill="none" stroke="currentColor" stroke-width="2" '
            'points="'
            + " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
            + '"/>'
        )
        drawings.extend(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="currentColor"/>'
            for x, y in segment
        )
    return (
        f'<svg role="img" aria-label="{esc(label)}" viewBox="0 0 320 96">'
        f"<title>{esc(label)}; min {fmt(lo)}, max {fmt(hi)}. Gaps are unavailable.</title>"
        + "".join(drawings)
        + "</svg>"
    )


def detection_history(group):
    """Historical floors and observations retain distinct provenance."""
    rows, keys = [], set()
    for record in group:
        floors = record.get("catch_baseline") or {}
        if "catch_source" not in record:
            floors = record.get("catch") or {}
        measured = (
            (record.get("catch") or {})
            if record.get("catch_source") == "measured factor pairs"
            else {}
        )
        keys.update(measured)
        for key in sorted(set(floors) | set(measured)):
            rows.append(
                [
                    record.get("date", ""),
                    (record.get("sha") or "")[:12],
                    key,
                    fmt(floors.get(key)),
                    fmt(measured.get(key)),
                    record.get("catch_source", "legacy accepted floors"),
                ]
            )
    out = ["<h4>Detection history</h4>"]
    if not keys:
        out.append(
            "<p>No measured catch history is available. "
            "Accepted floors below are review baselines.</p>"
        )
    for key in sorted(keys):
        values = [
            (
                (r.get("catch") or {}).get(key)
                if r.get("catch_source") == "measured factor pairs"
                and r.get("valid") is not False
                else None
            )
            for r in group
        ]
        out.append(
            f"<p>{esc(key)}: observed catch rate</p>" + spark(values, key)
        )
    if rows:
        out.append(
            "<details><summary>Accepted floors and available measurements</summary>"
            + table(
                [
                    "Date",
                    "Commit",
                    "Mistake/factor",
                    "Accepted floor",
                    "Observed catch",
                    "Provenance",
                ],
                rows,
            )
            + "</details>"
        )
    return "".join(out)


def history_section(lines):
    """Legacy catch fields are documented floors, not measured accuracy."""
    groups = {}
    for line in lines:
        groups.setdefault(line.get("set", "Unknown set"), []).append(line)
    out = [
        "<section><h2>Historical observations</h2>",
        "<p>Old history catch fields came from accepted floors. They are excluded "
        "from measured detection trends. A missing validity field is legacy, "
        "unverified data. Invalid observations leave gaps.</p>",
    ]
    if not groups:
        out.append("<p>No history supplied.</p>")
    for name, group in sorted(groups.items()):
        group = group[-50:]
        out.append(
            f"<h3>{esc(name)}: last {len(group)} records, oldest first</h3>"
        )
        for key, label in [
            ("cer", "CER %"),
            ("sentences_found", "Written lines scored"),
            ("overall_mean", "Mean overall score (not accuracy)"),
            ("eye", "Agreement with ranking by eye"),
        ]:
            values = [
                r.get(key) if r.get("valid") is not False else None
                for r in group
            ]
            out.append(f"<h4>{esc(label)}</h4>" + spark(values, label))
        out.append(
            table(
                [
                    "Date",
                    "Commit",
                    "Validity",
                    "CER %",
                    "Lines scored/written",
                    "Catch provenance",
                ],
                [
                    [
                        r.get("date", ""),
                        (r.get("sha") or "")[:12],
                        (
                            "valid"
                            if r.get("valid") is True
                            else (
                                "invalid"
                                if r.get("valid") is False
                                else "legacy / unverified"
                            )
                        ),
                        fmt(r.get("cer")),
                        f'{fmt(r.get("sentences_found"))}/{fmt(r.get("sentences_total"))}',
                        r.get(
                            "catch_source",
                            "legacy accepted floors; not measured",
                        ),
                    ]
                    for r in group
                ],
            )
        )
        out.append(detection_history(group))
    out.append("</section>")
    return "\n".join(out)


STYLE = """
:root { color-scheme: light dark; }
body { font: 16px/1.5 system-ui,sans-serif; margin: 0; background: Canvas; color: CanvasText; }
main { max-width: 1200px; margin: auto; padding: 2rem; }
h1 { margin-bottom: .3rem; } section { border-top: 2px solid; margin-top: 2rem; padding-top: 1rem; }
.scroll { overflow-x: auto; } table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th,td { padding: .55rem; border: 1px solid; text-align: left; vertical-align: top; }
svg { width: min(100%, 420px); height: 126px; }
.factors { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 1rem; }
.factor svg { height: 70px; display: block; }
meter { width: min(55vw, 420px); }
li { overflow-wrap: anywhere; } a { color: LinkText; }
@media (max-width: 600px) { main { padding: 1rem; } }
@media print { .scroll { overflow: visible; } table { font-size: 8pt; } }
"""


def render(runs=(), factors=(), lines=(), notes=()):
    """A standalone, non-interactive HTML artifact suitable for CI download."""
    out = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>Accuracy regression report</title>",
        f"<style>{STYLE}</style></head><body><main>",
        "<h1>Accuracy regression report</h1>",
        "<p>Maintainer evidence from existing benchmark outputs. "
        "No OCR or scoring is run by this report.</p>",
    ]
    for note in notes:
        out.append(f"<p>{esc(note)}</p>")
    if not runs:
        out.append("<p>Replay observations: unavailable in these inputs.</p>")
    out.extend(replay_section(run) for run in runs)
    if not factors:
        out.append(
            "<p>Planted detection: not measured in these inputs. "
            "Supply the existing factor job output to show it.</p>"
        )
    out.extend(factor_section(run) for run in factors)
    out.append(history_section(lines))
    out.append("</main></body></html>")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    parser.add_argument(
        "--results", help="benchmark.py check --results directory"
    )
    parser.add_argument(
        "--expected-set",
        action="append",
        default=[],
        help="a replay set expected even if its job produced no file",
    )
    parser.add_argument("--factor-results", action="append", default=[])
    parser.add_argument("--history", help="bench-history checkout, read only")
    parser.add_argument(
        "--now", help="bench_history.py collect output directory"
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    runs, factors, lines, notes = [], [], [], []
    if args.results:
        folder = Path(args.results)
        runs = [load(p) for p in sorted(folder.glob("*/current.json"))]
        expected = (
            set(args.expected_set)
            | {p.name for p in folder.iterdir() if p.is_dir()}
            if folder.is_dir()
            else set(args.expected_set)
        )
        present = {p.parent.name for p in folder.glob("*/current.json")}
        for missing in sorted(expected - present):
            notes.append(
                f"Replay {missing}: unavailable; no current.json. "
                "The job may have failed or been skipped."
            )
        if not runs:
            notes.append(
                "No current.json observations found. Legacy expected.json and "
                "reading.json artifacts are baseline candidates, not raw measurements."
            )
    for path in args.factor_results:
        if Path(path).is_file():
            factors.append(load(path))
        else:
            notes.append(
                f"Factor output missing: {Path(path).name}. Job may have failed or been skipped."
            )
    if args.history:
        for path in sorted((Path(args.history) / "history").glob("*.jsonl")):
            lines.extend(
                json.loads(row)
                for row in path.read_text(encoding="utf-8").splitlines()
                if row.strip()
            )
    if args.now:
        lines.extend(load(p) for p in sorted(Path(args.now).glob("*.json")))
    # Main's just-appended line can also be present in --now. Count it once.
    unique = {}
    for record in lines:
        key = (record.get("set"), record.get("sha"), record.get("date"))
        unique[key] = record
    lines = list(unique.values())
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render(runs, factors, lines, notes), encoding="utf-8"
    )
    print(
        f"Wrote {destination}: {len(runs)} replay sets, "
        f"{len(factors)} factor runs, {len(lines)} history records"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

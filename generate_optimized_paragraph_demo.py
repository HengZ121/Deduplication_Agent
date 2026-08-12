#!/usr/bin/env python3
"""Generate a static paragraph-level demo for optimized Rewards examples."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framenet_mapper import map_text


OUTPUT = Path("outputs") / "optimized_paragraph_frame_elements_demo.html"


@dataclass(frozen=True)
class DemoCase:
    case_id: str
    title: str
    source: str
    paragraph: str


DEMO_CASES = [
    DemoCase(
        case_id="original-1",
        title="Original 1: access-code fraud paragraph",
        source="procedure/activity/access_code.json · Access code",
        paragraph=(
            "If fraudulent activity is suspected on an EI or EI Emergency Response Benefit "
            "(EI ERB) claim, the agent does not issue the access code. For more information, "
            "the agent refers to Determining if an issue must be referred to Integrity for more information."
        ),
    ),
    DemoCase(
        case_id="optimized-1",
        title="Optimized 1: access-code fraud paragraph",
        source="Client internal LLM optimized version",
        paragraph=(
            "If fraudulent activity is suspected on an Employment Insurance (EI) claim or an EI "
            "Emergency Response Benefit (EI ERB) claim, the agent must not issue an access code. "
            "For additional guidance, refer to Determining if an issue must be referred to Integrity."
        ),
    ),
    DemoCase(
        case_id="original-2",
        title="Original 2: EI ERB work-item routing paragraph",
        source="procedure/task/performingar.json · Performing a reconsideration under EIA 112",
        paragraph=(
            "Any WIs related to an EI Emergency Response Benefit (EI ERB) claim are processed by a "
            "specialized team. For instructions on how to reassign these WIs, the officer refers to "
            "the workload management page in the EI ORT."
        ),
    ),
    DemoCase(
        case_id="optimized-2",
        title="Optimized 2: EI ERB work-item routing paragraph",
        source="Client internal LLM optimized version",
        paragraph=(
            "All work items (WIs) related to an EI Emergency Response Benefit (EI ERB) claim are "
            "processed by a specialized team. To reassign an EI ERB work item, refer to the Workload "
            "Management page in the EI ORT."
        ),
    ),
]


ELEMENT_CLASS = {
    "Agent": "agent",
    "Evaluee": "evaluee",
    "Response": "response",
    "Response_action": "response",
    "Activity": "response",
    "Reason": "reason",
    "Explanation": "reason",
    "Result": "result",
    "Time": "time",
}

ELEMENT_PRIORITY = {
    "candidate": 1,
    "Reason": 2,
    "Explanation": 2,
    "Result": 3,
    "Response": 4,
    "Response_action": 4,
    "Activity": 4,
    "Time": 5,
    "Evaluee": 6,
    "Agent": 7,
    "trigger": 8,
}


def _find_case_insensitive(haystack: str, needle: str, start: int = 0) -> int:
    return haystack.lower().find(needle.lower(), start)


def add_range(
    ranges: list[dict[str, Any]],
    paragraph: str,
    sentence_offset: int,
    sentence: str,
    text: str | None,
    label: str,
    css_class: str,
    priority: int,
) -> None:
    if not text:
        return
    local_start = _find_case_insensitive(sentence, text)
    if local_start < 0:
        return
    start = sentence_offset + local_start
    end = start + len(text)
    if 0 <= start < end <= len(paragraph):
        ranges.append(
            {
                "start": start,
                "end": end,
                "label": label,
                "class": css_class,
                "priority": priority,
            }
        )


def collect_ranges(paragraph: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    search_from = 0
    for event in result.get("events", []):
        sentence = (event.get("source") or {}).get("sentence") or ""
        sentence_offset = _find_case_insensitive(paragraph, sentence, search_from)
        if sentence_offset < 0:
            sentence_offset = _find_case_insensitive(paragraph, sentence)
        if sentence_offset < 0:
            continue
        search_from = sentence_offset + max(len(sentence), 1)

        if event.get("mappingStatus") == "candidate_only":
            ranges.append(
                {
                    "start": sentence_offset,
                    "end": sentence_offset + len(sentence),
                    "label": "candidate_only sentence",
                    "class": "candidate",
                    "priority": ELEMENT_PRIORITY["candidate"],
                }
            )
            continue

        for name, value in (event.get("frameElements") or {}).items():
            text = value.get("text") if isinstance(value, dict) else None
            add_range(
                ranges,
                paragraph,
                sentence_offset,
                sentence,
                text,
                name,
                ELEMENT_CLASS.get(name, "meta"),
                ELEMENT_PRIORITY.get(name, 3),
            )
        add_range(
            ranges,
            paragraph,
            sentence_offset,
            sentence,
            event.get("trigger"),
            "trigger",
            "trigger",
            ELEMENT_PRIORITY["trigger"],
        )
    return ranges


def render_highlighted_paragraph(paragraph: str, result: dict[str, Any]) -> str:
    ranges = collect_ranges(paragraph, result)
    classes: list[str | None] = [None] * len(paragraph)
    priorities = [0] * len(paragraph)
    labels: list[set[str]] = [set() for _ in paragraph]

    for item in ranges:
        for index in range(item["start"], item["end"]):
            labels[index].add(item["label"])
            if item["priority"] >= priorities[index]:
                priorities[index] = item["priority"]
                classes[index] = item["class"]

    parts: list[str] = []
    cursor = 0
    while cursor < len(paragraph):
        css_class = classes[cursor]
        label = " + ".join(sorted(labels[cursor]))
        end = cursor + 1
        while (
            end < len(paragraph)
            and classes[end] == css_class
            and " + ".join(sorted(labels[end])) == label
        ):
            end += 1
        text = html.escape(paragraph[cursor:end])
        if css_class:
            parts.append(
                f'<mark class="hl hl-{css_class}" title="{html.escape(label)}">'
                f"{text}</mark>"
            )
        else:
            parts.append(text)
        cursor = end
    return "".join(parts)


def event_element_rows(event: dict[str, Any]) -> str:
    rows = []
    for name, value in (event.get("frameElements") or {}).items():
        text = value.get("text") if isinstance(value, dict) else None
        if not text:
            continue
        rows.append(
            "<tr>"
            f"<td><span class='dot dot-{ELEMENT_CLASS.get(name, 'meta')}'></span>{html.escape(name)}</td>"
            f"<td>{html.escape(text)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='2' class='muted'>No frame elements extracted.</td></tr>")
    return "\n".join(rows)


def render_event(event: dict[str, Any], index: int) -> str:
    scoring = event.get("hybridScoring") or {}
    frame = event.get("frame") or "Candidate-only lexical lookup"
    status = event.get("mappingStatus") or "unknown"
    trigger = event.get("trigger") or "n/a"
    score_bits = []
    if scoring.get("ruleScore") is not None:
        score_bits.append(f"rule {scoring.get('ruleScore')}")
    if scoring.get("bertFrameScore") is not None:
        score_bits.append(f"BERT {scoring.get('bertFrameScore')}")
    if scoring.get("combinedScore") is not None:
        score_bits.append(f"combined {scoring.get('combinedScore')}")
    score_text = " · ".join(score_bits) or "no confirmed frame score"
    sentence = (event.get("source") or {}).get("sentence") or ""
    return f"""
<section class="event">
  <div class="event-title">
    <h3>Event {index}: {html.escape(str(frame))}</h3>
    <span>{html.escape(str(status))}</span>
  </div>
  <p class="event-sentence">{html.escape(sentence)}</p>
  <div class="chips">
    <span>Trigger: {html.escape(str(trigger))}</span>
    <span>{html.escape(score_text)}</span>
  </div>
  <table>
    <thead><tr><th>Frame element</th><th>Extracted text</th></tr></thead>
    <tbody>{event_element_rows(event)}</tbody>
  </table>
</section>
"""


def render_case(case: DemoCase, result: dict[str, Any]) -> str:
    confirmed = result.get("confirmedEventCount", 0)
    candidates = result.get("candidateEventCount", 0)
    events = "\n".join(render_event(event, index) for index, event in enumerate(result.get("events", []), start=1))
    warnings = result.get("warnings") or []
    warning_html = "".join(f"<li>{html.escape(str(warning))}</li>" for warning in warnings)
    return f"""
<article class="case-card" id="{html.escape(case.case_id)}">
  <div class="case-head">
    <div>
      <h2>{html.escape(case.title)}</h2>
      <p class="source">{html.escape(case.source)}</p>
    </div>
    <div class="summary-pill">{confirmed} confirmed · {candidates} candidate-only</div>
  </div>
  <p class="paragraph">{render_highlighted_paragraph(case.paragraph, result)}</p>
  <details open>
    <summary>Extracted frame elements</summary>
    {events}
  </details>
  {'<ul class="warnings">' + warning_html + '</ul>' if warnings else ''}
  <details>
    <summary>Full JSON</summary>
    <pre>{html.escape(json.dumps(result, indent=2, ensure_ascii=False))}</pre>
  </details>
</article>
"""


def main() -> None:
    results = [(case, map_text(case.paragraph, source_name=case.case_id)) for case in DEMO_CASES]
    cards = "\n".join(render_case(case, result) for case, result in results)
    summary_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(case.title)}</td>"
        f"<td>{result.get('eventCount', 0)}</td>"
        f"<td>{result.get('confirmedEventCount', 0)}</td>"
        f"<td>{result.get('candidateEventCount', 0)}</td>"
        f"<td>{html.escape(', '.join(str(event.get('frame') or 'candidate_only') for event in result.get('events', [])))}</td>"
        "</tr>"
        for case, result in results
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paragraph-Level Frame Element Demo</title>
<style>
:root{{
  --ink:#172033;--muted:#5f6b7c;--line:#d9e1ec;--bg:#f5f7fb;--card:#fff;
  --trigger:#ffe08a;--agent:#b8e0d2;--evaluee:#bde0fe;--response:#c7f0bd;
  --reason:#ddd1ff;--result:#cfe8ff;--time:#ffd6a5;--candidate:#eef2f7;--meta:#e8eef8;
}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,system-ui,sans-serif}}
main{{max-width:1220px;margin:0 auto;padding:32px 20px 56px}}
h1{{margin:0 0 8px;font-size:34px;letter-spacing:-.02em}}p{{color:var(--muted)}}h2,h3{{margin:0;color:var(--ink)}}
.intro{{max-width:920px;line-height:1.55}}.legend{{display:flex;gap:10px 16px;flex-wrap:wrap;margin:18px 0 22px;color:#39465a}}
.legend span,.chips span,.summary-pill{{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 10px;font-size:13px}}
.legend span::before,.dot{{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
.legend .trigger::before,.dot-trigger{{background:var(--trigger)}}.legend .agent::before,.dot-agent{{background:var(--agent)}}.legend .response::before,.dot-response{{background:var(--response)}}
.legend .reason::before,.dot-reason{{background:var(--reason)}}.legend .result::before,.dot-result{{background:var(--result)}}.legend .candidate::before,.dot-candidate{{background:var(--candidate);border:1px dashed #9aa6b7}}
.overview,.case-card{{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 10px 26px rgba(35,50,74,.08);padding:18px;margin:18px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;border-bottom:1px solid #e4e9f1;padding:9px 8px;vertical-align:top;font-size:14px}}th{{color:#536076;font-weight:700}}tr:last-child td{{border-bottom:0}}
.case-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}}.source{{margin:4px 0 0;font-size:13px}}
.paragraph{{font-size:18px;line-height:2;color:#172033;background:#f9fbff;border-left:4px solid #1768e5;border-radius:8px;padding:14px 16px;margin:12px 0 16px}}
.hl{{border-radius:4px;padding:2px 3px;margin:0 1px;color:#172033}}.hl small{{font-size:10px;color:#364154;margin-left:4px;font-weight:700}}
.hl-trigger{{background:var(--trigger)}}.hl-agent{{background:var(--agent)}}.hl-evaluee{{background:var(--evaluee)}}.hl-response{{background:var(--response)}}.hl-reason{{background:var(--reason)}}.hl-result{{background:var(--result)}}.hl-time{{background:var(--time)}}.hl-meta{{background:var(--meta)}}.hl-candidate{{background:var(--candidate);border-bottom:2px dashed #9aa6b7}}
details{{margin-top:12px}}summary{{cursor:pointer;font-weight:700;color:#26344a}}.event{{border-top:1px solid #e4e9f1;padding:14px 0}}.event-title{{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}}
.event-title span{{font-size:12px;background:#eef3fb;border-radius:999px;padding:4px 8px;color:#40506a}}.event-sentence{{margin:8px 0;color:#40506a;line-height:1.55}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}}.muted{{color:var(--muted)}}.warnings{{color:#7a4d00;background:#fff8dc;border:1px solid #f2d384;border-radius:8px;padding:10px 14px 10px 30px}}
pre{{white-space:pre-wrap;background:#101827;color:#dbeafe;border-radius:10px;padding:14px;overflow:auto;max-height:520px}}
</style>
</head>
<body>
<main>
  <h1>Paragraph-Level Frame Element Demo</h1>
  <p class="intro">Four paragraphs were run through the current FrameNet mapper: two original procedure paragraphs and two client-LLM optimized versions. Highlights show the extracted frame-element spans in context; hover over a highlight for its label, and use the table under each case for exact extracted text. Gray dashed text marks a sentence that only received candidate lexical-unit lookup, not a confirmed domain frame.</p>
  <div class="legend">
    <span class="trigger">Trigger</span>
    <span class="agent">Agent</span>
    <span class="response">Response / action</span>
    <span class="reason">Reason</span>
    <span class="result">Result</span>
    <span class="candidate">Candidate-only sentence</span>
  </div>
  <section class="overview">
    <h2>Run summary</h2>
    <table>
      <thead><tr><th>Text</th><th>Events</th><th>Confirmed</th><th>Candidate-only</th><th>Frames</th></tr></thead>
      <tbody>{summary_rows}</tbody>
    </table>
  </section>
  {cards}
</main>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "cases": len(results),
                "events": sum(result.get("eventCount", 0) for _, result in results),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

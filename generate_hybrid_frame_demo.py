#!/usr/bin/env python3
"""Generate a static demo for the 20-frame hybrid mapper."""

from __future__ import annotations

import html
import json
from pathlib import Path

from framenet_mapper import map_text
from hybrid_frame_mapper import FRAME_RULES, demo_sentences


OUTPUT = Path("outputs") / "hybrid_frame_demo.html"


def highlight_sentence(event: dict[str, object]) -> str:
    sentence = event["source"]["sentence"]
    spans = []
    trigger = event.get("trigger")
    if trigger:
        start = sentence.lower().find(str(trigger).lower())
        if start >= 0:
            spans.append((start, start + len(str(trigger)), "trigger", "trigger"))
    for name, value in (event.get("frameElements") or {}).items():
        text = value.get("text") if isinstance(value, dict) else None
        if not text:
            continue
        start = sentence.lower().find(str(text).lower())
        if start >= 0:
            spans.append((start, start + len(str(text)), "element", name))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    accepted = []
    occupied_until = -1
    for span in spans:
        if span[0] >= occupied_until:
            accepted.append(span)
            occupied_until = span[1]
    parts = []
    cursor = 0
    for start, end, kind, label in accepted:
        parts.append(html.escape(sentence[cursor:start]))
        parts.append(
            f"<mark class='{kind}' title='{html.escape(label)}'>"
            f"{html.escape(sentence[start:end])}<small>{html.escape(label)}</small></mark>"
        )
        cursor = end
    parts.append(html.escape(sentence[cursor:]))
    return "".join(parts)


def render_event(event: dict[str, object]) -> str:
    scoring = event.get("hybridScoring") or {}
    candidates = scoring.get("candidateFrames") or []
    candidate_rows = "".join(
        "<tr>"
        f"<td>{html.escape(candidate['frame'])}</td>"
        f"<td>{html.escape(candidate['eventType'])}</td>"
        f"<td>{candidate['ruleScore']}</td>"
        f"<td>{candidate['bertScore'] if candidate['bertScore'] is not None else 'n/a'}</td>"
        f"<td>{candidate['combinedScore']}</td>"
        "</tr>"
        for candidate in candidates
    )
    return f"""
<section class="event-card" data-frame="{html.escape((event.get('frame') or '').lower())}">
  <div class="event-head">
    <h2>{html.escape(event.get('frame') or 'domain-only')}</h2>
    <span>{html.escape(event.get('eventType') or '')}</span>
  </div>
  <p class="sentence">{highlight_sentence(event)}</p>
  <div class="stats">
    <span>trigger: {html.escape(str(event.get('trigger')))}</span>
    <span>status: {html.escape(str(event.get('mappingStatus')))}</span>
    <span>rule score: {scoring.get('ruleScore', 'n/a')}</span>
    <span>BERT: {html.escape((scoring.get('bert') or {}).get('status', 'n/a'))}</span>
  </div>
  <table>
    <thead><tr><th>Candidate frame</th><th>Event type</th><th>Rule</th><th>BERT</th><th>Combined</th></tr></thead>
    <tbody>{candidate_rows}</tbody>
  </table>
  <details><summary>JSON</summary><pre>{html.escape(json.dumps(event, indent=2, ensure_ascii=False))}</pre></details>
</section>
"""


def main() -> None:
    result = map_text(demo_sentences(), "hybrid-frame-demo")
    events = result["events"]
    cards = "\n".join(render_event(event) for event in events)
    frame_list = "\n".join(f"<li>{html.escape(rule.frame)} - {html.escape(rule.description)}</li>" for rule in FRAME_RULES)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Employment Benefits Frame Annotation Demo</title>
<style>
:root{{font-family:Inter,system-ui,sans-serif;color:#152033;background:#f5f7fb}}
body{{margin:0}}main{{max-width:1180px;margin:auto;padding:30px 20px}}
h1{{margin:0 0 8px;font-size:30px}}p{{color:#556176}}.toolbar{{position:sticky;top:0;background:#f5f7fb;padding:12px 0 16px;border-bottom:1px solid #dce3ee}}
input{{width:100%;padding:11px 12px;border:1px solid #bcc8d8;border-radius:8px;font:inherit}}
.event-card{{background:#fff;border:1px solid #dce3ee;border-radius:10px;margin:16px 0;padding:16px;box-shadow:0 8px 24px #23324a10}}
.event-head{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}}h2{{margin:0;font-size:21px}}.event-head span{{color:#5f6b7c}}
.sentence{{font-size:16px;color:#172033;background:#f9fbff;border-left:4px solid #1768e5;padding:10px 12px;line-height:1.8}}
mark{{border-radius:4px;padding:2px 3px;margin:0 1px;color:#172033}}mark small{{font-size:10px;margin-left:4px;color:#4b5563}}.trigger{{background:#ffe08a}}.element{{background:#dbeafe}}
.stats{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}}.stats span{{background:#eef3fb;border-radius:999px;padding:4px 9px;color:#40506a;font-size:13px}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}th,td{{border-bottom:1px solid #e2e8f0;text-align:left;padding:7px;font-size:14px}}th{{color:#536076}}
pre{{white-space:pre-wrap;background:#101827;color:#dbeafe;border-radius:8px;padding:12px;overflow:auto}}details{{margin-top:10px}}.frames{{columns:2;margin-bottom:20px}}
</style>
</head>
<body>
<main>
<h1>Employment Benefits Frame Annotation Demo</h1>
<p>Precomputed rule + local BERT examples for employment and social-benefit procedure frames, with inline trigger and frame-element highlights.</p>
<details><summary>20 configured frames</summary><ul class="frames">{frame_list}</ul></details>
<div class="toolbar"><input id="filter" placeholder="Filter frames, e.g. Evidence, Request, Being_employed"></div>
{cards}
</main>
<script>
const filter=document.querySelector('#filter'),cards=[...document.querySelectorAll('.event-card')];
filter.addEventListener('input',()=>{{const q=filter.value.trim().toLowerCase();for(const card of cards)card.style.display=card.dataset.frame.includes(q)?'':'none'}});
</script>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(json.dumps({"events": len(events), "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()

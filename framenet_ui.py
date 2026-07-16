#!/usr/bin/env python3
"""Local browser UI for the FrameNet penalty mapper."""

from __future__ import annotations

import argparse
import base64
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from framenet_mapper import extract_document_text, map_text


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FrameNet Penalty Mapper</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#162033;background:#f4f7fb}*{box-sizing:border-box}
body{margin:0}.shell{max-width:1100px;margin:auto;padding:34px 22px}h1{margin:0 0 7px;font-size:28px}p{color:#536076}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}.card{background:white;border:1px solid #dce3ee;border-radius:12px;padding:18px;box-shadow:0 8px 28px #26354d12}
label{display:block;font-weight:650;margin-bottom:8px}input,textarea,button{font:inherit}input[type=file],textarea{width:100%;border:1px solid #bdc8d8;border-radius:8px;padding:11px;background:#fff}textarea{height:220px;resize:vertical}
.or{text-align:center;color:#7a8699;margin:12px}.actions{display:flex;gap:10px;margin-top:14px}button{border:0;border-radius:8px;padding:10px 15px;cursor:pointer;background:#1768e5;color:white;font-weight:650}button.secondary{background:#e8eef8;color:#23324a}button:disabled{opacity:.55;cursor:wait}
pre{margin:0;min-height:385px;max-height:600px;overflow:auto;background:#101827;color:#dbeafe;border-radius:9px;padding:16px;white-space:pre-wrap}.status{min-height:24px;margin-top:10px;color:#536076}.error{color:#b42318}
.annotations{margin-top:18px}.annotated-event{padding:14px 0;border-top:1px solid #dce3ee;line-height:1.8}.annotated-event:first-of-type{border-top:0}.event-heading{font-weight:650;margin-bottom:6px}.legend{display:flex;flex-wrap:wrap;gap:8px 14px;margin:10px 0;color:#536076;font-size:13px}.legend span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}.legend .trigger::before,.hl-trigger{background:#ffe08a}.legend .agent::before,.hl-agent{background:#b8e0d2}.legend .evaluee::before,.hl-evaluee{background:#bde0fe}.legend .code::before,.hl-code{background:#ffc8dd}.legend .condition::before,.hl-condition{background:#ddd1ff}.legend .time::before,.hl-time{background:#ffd6a5}.highlight{border-radius:3px;padding:2px 1px;color:#162033}.empty{color:#7a8699}
@media(max-width:760px){.grid{grid-template-columns:1fr}.shell{padding:22px 14px}}
</style>
</head>
<body><main class="shell"><h1>FrameNet Penalty Mapper</h1><p>Upload a policy document or paste text to produce FrameNet-aligned JSON.</p>
<div class="grid"><section class="card"><label for="file">Document (.txt, .md, .json, .docx)</label><input id="file" type="file" accept=".txt,.md,.json,.docx">
<div class="or">or</div><label for="text">Paste document text</label><textarea id="text">A 25 - Maternity benefits - Minor attached disentitlement (D25) is imposed if the client has not accumulated at least 600 insurable hours.
If the information on file allows for the disentitlement to be terminated, it is terminated on the Friday of the week before the conversion week.</textarea>
<div class="actions"><button id="map">Map to JSON</button><button class="secondary" id="sample">Load sample</button></div><div class="status" id="status"></div></section>
<section class="card"><label for="output">Mapped JSON</label><pre id="output">Click “Map to JSON” to run the demo.</pre><div class="actions"><button id="download" class="secondary" disabled>Download JSON</button></div></section></div>
<section class="card annotations"><label>Annotated document</label><div class="legend" aria-label="Highlight legend"><span class="trigger">Trigger</span><span class="agent">Agent</span><span class="evaluee">Evaluee</span><span class="code">Penalty code</span><span class="condition">Condition / Reason</span><span class="time">Time</span></div><div id="annotated"><span class="empty">Mapped sentences will appear here with semantic highlights.</span></div></section></main>
<script>
const file=document.querySelector('#file'),text=document.querySelector('#text'),output=document.querySelector('#output'),annotated=document.querySelector('#annotated'),status=document.querySelector('#status'),mapButton=document.querySelector('#map'),download=document.querySelector('#download');let result=null;
function bytesToBase64(buffer){let binary='';const bytes=new Uint8Array(buffer);for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return btoa(binary)}
function addRange(ranges,sentence,value,type,priority,useLast=false){if(!value)return;const haystack=sentence.toLowerCase(),needle=String(value).toLowerCase(),start=useLast?haystack.lastIndexOf(needle):haystack.indexOf(needle);if(start>=0)ranges.push({start,end:start+String(value).length,type,priority})}
function highlightedSentence(event){const sentence=event.source.sentence,ranges=[];addRange(ranges,sentence,event.ruleCondition?.text,'condition',1);addRange(ranges,sentence,event.frameElements?.Time?.text,'time',4);addRange(ranges,sentence,event.frameElements?.Evaluee?.text,'evaluee',5);addRange(ranges,sentence,event.frameElements?.Agent?.text,'agent',6);addRange(ranges,sentence,event.penaltyCode?.code,'code',7);addRange(ranges,sentence,event.trigger,'trigger',8,true);const classes=Array(sentence.length).fill(null),priorities=Array(sentence.length).fill(0);for(const range of ranges){for(let i=range.start;i<range.end;i++){if(range.priority>=priorities[i]){classes[i]=range.type;priorities[i]=range.priority}}}const fragment=document.createDocumentFragment();let start=0;while(start<sentence.length){const type=classes[start];let end=start+1;while(end<sentence.length&&classes[end]===type)end++;const node=type?document.createElement('mark'):document.createTextNode(sentence.slice(start,end));if(type){node.className=`highlight hl-${type}`;node.textContent=sentence.slice(start,end)}fragment.appendChild(node);start=end}return fragment}
function renderAnnotations(data){annotated.replaceChildren();if(!data.events.length){const empty=document.createElement('span');empty.className='empty';empty.textContent='No supported penalty event was found.';annotated.appendChild(empty);return}data.events.forEach((event,index)=>{const section=document.createElement('section');section.className='annotated-event';const heading=document.createElement('div');heading.className='event-heading';heading.textContent=`Event ${index+1}: ${event.frame}`;const sentence=document.createElement('div');sentence.appendChild(highlightedSentence(event));section.append(heading,sentence);annotated.appendChild(section)})}
async function run(){mapButton.disabled=true;status.className='status';status.textContent='Mapping…';try{let payload={text:text.value,filename:'pasted-text'};if(file.files[0]){payload={filename:file.files[0].name,contentBase64:bytesToBase64(await file.files[0].arrayBuffer())}}const response=await fetch('/api/map',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Mapping failed');result=data;output.textContent=JSON.stringify(data,null,2);renderAnnotations(data);status.textContent=`Mapped ${data.eventCount} event(s).`;download.disabled=false}catch(error){status.className='status error';status.textContent=error.message}finally{mapButton.disabled=false}}
mapButton.addEventListener('click',run);document.querySelector('#sample').addEventListener('click',()=>{file.value='';text.value='The officer imposes a 33 - Incapacity proven but not otherwise available disentitlement (D33) when clients do not prove that they would be otherwise available for work.\nA D33 is terminated on the Friday of the week before the conversion week.'});download.addEventListener('click',()=>{const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='framenet-mapping.json';a.click();URL.revokeObjectURL(a.href)});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/map":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 15 * 1024 * 1024:
                raise ValueError("Document exceeds the 15 MB demo limit")
            payload = json.loads(self.rfile.read(length))
            filename = payload.get("filename") or "pasted-text"
            if "contentBase64" in payload:
                text = extract_document_text(filename, base64.b64decode(payload["contentBase64"], validate=True))
            else:
                text = str(payload.get("text") or "")
            if not text.strip():
                raise ValueError("Provide a document or paste some text")
            self._json(200, map_text(text, filename))
        except (ValueError, KeyError, json.JSONDecodeError, OSError) as error:
            self._json(400, {"error": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _json(self, status: int, value: object) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"FrameNet Penalty Mapper running at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

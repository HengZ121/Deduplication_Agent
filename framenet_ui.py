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
.annotations{margin-top:18px}.annotated-event{padding:14px 0;border-top:1px solid #dce3ee;line-height:1.8}.annotated-event:first-of-type{border-top:0}.event-heading{font-weight:650;margin-bottom:6px}.legend{display:flex;flex-wrap:wrap;gap:8px 14px;margin:10px 0;color:#536076;font-size:13px}.legend span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}.legend .trigger::before,.hl-trigger{background:#ffe08a}.legend .agent::before,.hl-agent{background:#b8e0d2}.legend .evaluee::before,.hl-evaluee{background:#bde0fe}.legend .response::before,.hl-response{background:#c7f0bd}.legend .code::before,.hl-code{background:#ffc8dd}.legend .reason::before,.hl-reason{background:#ddd1ff}.legend .time::before,.hl-time{background:#ffd6a5}.legend .meta::before,.hl-meta{background:#e8eef8}.highlight{border-radius:3px;padding:2px 1px;color:#162033}.field-map{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.field-chip{display:inline-flex;gap:5px;align-items:baseline;border-radius:6px;padding:3px 7px;font-size:12px;line-height:1.45;color:#162033}.field-name{font-weight:700}.field-chip.implicit{background:#f4f6fa;border:1px dashed #9aa6b7;color:#5f6b7c}.empty{color:#7a8699}
.evidence{margin-top:18px}.evidence-item{padding:14px 0;border-top:1px solid #dce3ee}.evidence-item:first-child{border-top:0}.evidence-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#e8eef8;color:#23324a;font-size:12px}.badge.ok{background:#d9f2e6;color:#145c3d}.badge.warn{background:#fff1c2;color:#765600}.evidence-grid{display:grid;grid-template-columns:150px 1fr;gap:6px 12px}.evidence-key{color:#536076}.examples{margin:8px 0 0;padding-left:20px}.examples li{margin:4px 0}
@media(max-width:760px){.grid{grid-template-columns:1fr}.shell{padding:22px 14px}}
</style>
</head>
<body><main class="shell"><h1>FrameNet Penalty Mapper</h1><p>Upload a policy document or paste text to produce FrameNet-aligned JSON.</p>
<div class="grid"><section class="card"><label for="file">Document (.txt, .md, .json, .docx)</label><input id="file" type="file" accept=".txt,.md,.json,.docx">
<div class="or">or</div><label for="text">Paste document text</label><textarea id="text">A 25 - Maternity benefits - Minor attached disentitlement (D25) is imposed if the client has not accumulated at least 600 insurable hours.
If the information on file allows for the disentitlement to be terminated, it is terminated on the Friday of the week before the conversion week.</textarea>
<div class="actions"><button id="map">Map to JSON</button><button class="secondary" id="sample">Load sample</button></div><div class="status" id="status"></div></section>
<section class="card"><label for="output">Mapped JSON</label><pre id="output">Click “Map to JSON” to run the demo.</pre><div class="actions"><button id="download" class="secondary" disabled>Download JSON</button></div></section></div>
<section class="card annotations"><label>Annotated document</label><div class="legend" aria-label="Highlight legend"><span class="trigger">Trigger</span><span class="agent">Agent</span><span class="evaluee">Evaluee</span><span class="response">Response / Activity</span><span class="code">Penalty code</span><span class="reason">Reason / Explanation</span><span class="time">Time</span><span class="meta">Metadata / implicit</span></div><div id="annotated"><span class="empty">Mapped sentences will appear here with semantic highlights.</span></div></section>
<section class="card evidence"><label>Syntactic + Official FrameNet 1.7 evidence</label><div id="evidence"><span class="empty">Dependency roles, Frame, LU and FE validation will appear after mapping.</span></div></section></main>
<script>
const file=document.querySelector('#file'),text=document.querySelector('#text'),output=document.querySelector('#output'),annotated=document.querySelector('#annotated'),evidence=document.querySelector('#evidence'),status=document.querySelector('#status'),mapButton=document.querySelector('#map'),download=document.querySelector('#download');let result=null;
const STRESS_SAMPLE=`A 25 - Maternity benefits - Minor attached disentitlement (D25) is imposed if the client has not accumulated at least 600 insurable hours.
A D25 is terminated on the Friday of the week before the conversion week.
Maternity benefits can be paid if one of the following qualifying conditions is met.
To be entitled to parental benefits, the client must meet both residence and contribution conditions.
The client must provide a signed statement attesting to the pregnancy.
A Level 1 officer can terminate the disentitlement if the information on file supports the decision.
Based on the letter that was sent, the officer can determine the reason the D15 is imposed from the C-73 prefix.
The system automatically changes the sex code to 8 and displays both the parental start week and parental end week.
Up to 15 weeks may be paid and the maximum cannot be exceeded.
The maternity window starts on the earlier of the following 2 dates and ends on the later of the listed dates.
The applicant receives correspondence after filing.`;
function bytesToBase64(buffer){let binary='';const bytes=new Uint8Array(buffer);for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return btoa(binary)}
function cleanMapping(data){return{schemaVersion:data.schemaVersion,sourceDocument:data.sourceDocument,annotationMethod:data.annotationMethod,eventCount:data.eventCount,confirmedEventCount:data.confirmedEventCount,candidateEventCount:data.candidateEventCount,events:data.events.map(event=>({eventType:event.eventType,frame:event.frame,trigger:event.trigger,frameElements:event.frameElements,candidateFrames:event.candidateFrames,mappingStatus:event.mappingStatus,structuredRule:event.structuredRule,domainExtensions:event.domainExtensions,ruleCondition:event.ruleCondition,penaltyCode:event.penaltyCode,polarity:event.polarity,modality:event.modality,source:event.source})),warnings:data.warnings}}
function addRange(ranges,sentence,value,type,priority,path,useLast=false){if(!value)return;const haystack=sentence.toLowerCase(),needle=String(value).toLowerCase(),start=useLast?haystack.lastIndexOf(needle):haystack.indexOf(needle);if(start>=0)ranges.push({start,end:start+String(value).length,type,priority,path})}
function highlightedSentence(event){const sentence=event.source.sentence,ranges=[],elements=event.frameElements||{},reasonName=elements.Reason?'Reason':elements.Explanation?'Explanation':null,responseName=elements.Response_action?'Response_action':elements.Activity?'Activity':null,handled=new Set(['Reason','Explanation','Response_action','Activity','Time','Evaluee','Agent']);addRange(ranges,sentence,reasonName?elements[reasonName].text:null,'reason',1,reasonName?`frameElements.${reasonName}`:null);addRange(ranges,sentence,event.ruleCondition?.text,'reason',1,'ruleCondition.text');addRange(ranges,sentence,responseName?elements[responseName].text:null,'response',2,responseName?`frameElements.${responseName}`:null);for(const[name,value]of Object.entries(elements)){if(!handled.has(name))addRange(ranges,sentence,value?.text,'meta',3,`frameElements.${name}`)}addRange(ranges,sentence,elements.Time?.text,'time',4,'frameElements.Time');addRange(ranges,sentence,elements.Evaluee?.text,'evaluee',5,'frameElements.Evaluee');addRange(ranges,sentence,elements.Agent?.text,'agent',6,'frameElements.Agent');addRange(ranges,sentence,event.penaltyCode?.text,'code',7,'penaltyCode.text');addRange(ranges,sentence,event.trigger,'trigger',8,'trigger',true);const classes=Array(sentence.length).fill(null),priorities=Array(sentence.length).fill(0),paths=Array.from({length:sentence.length},()=>new Set());for(const range of ranges){for(let i=range.start;i<range.end;i++){if(range.path)paths[i].add(range.path);if(range.priority>=priorities[i]){classes[i]=range.type;priorities[i]=range.priority}}}const pathKey=index=>[...paths[index]].sort().join(' + '),fragment=document.createDocumentFragment();let start=0;while(start<sentence.length){const type=classes[start],mappedPaths=pathKey(start);let end=start+1;while(end<sentence.length&&classes[end]===type&&pathKey(end)===mappedPaths)end++;const node=type?document.createElement('mark'):document.createTextNode(sentence.slice(start,end));if(type){node.className=`highlight hl-${type}`;node.textContent=sentence.slice(start,end);node.dataset.paths=mappedPaths;node.title=mappedPaths}fragment.appendChild(node);start=end}return fragment}
function fieldType(name){if(name==='Agent')return'agent';if(name==='Evaluee')return'evaluee';if(name==='Response_action'||name==='Activity')return'response';if(name==='Reason'||name==='Explanation'||name==='ruleCondition')return'reason';if(name==='Time')return'time';if(name==='trigger')return'trigger';if(name==='penaltyCode')return'code';return'meta'}
function fieldChip(name,value,type,implicit=false){const chip=document.createElement('span');chip.className=`field-chip ${implicit?'implicit':`hl-${type}`}`;const key=document.createElement('span');key.className='field-name';key.textContent=`${name}:`;const textValue=document.createElement('span');textValue.textContent=value;chip.append(key,textValue);return chip}
function mappedFields(event){const fields=document.createElement('div');fields.className='field-map';fields.append(fieldChip('eventType',event.eventType,'meta'),fieldChip('frame',event.frame||'domain-only','meta'));if(event.mappingStatus)fields.append(fieldChip('mappingStatus',event.mappingStatus,'meta'));if(event.polarity)fields.append(fieldChip('polarity',event.polarity,'meta'));if(event.modality)fields.append(fieldChip('modality',event.modality,'meta'));return fields}
function renderAnnotations(data){annotated.replaceChildren();if(!data.events.length){const empty=document.createElement('span');empty.className='empty';empty.textContent='No supported penalty event was found.';annotated.appendChild(empty);return}data.events.forEach((event,index)=>{const section=document.createElement('section');section.className='annotated-event';const heading=document.createElement('div');heading.className='event-heading';heading.textContent=`Event ${index+1}: ${event.eventType}${event.frame?` → ${event.frame}`:''}`;const sentence=document.createElement('div');sentence.appendChild(highlightedSentence(event));section.append(heading,sentence,mappedFields(event));annotated.appendChild(section)})}
function addEvidenceRow(grid,key,value){const k=document.createElement('div');k.className='evidence-key';k.textContent=key;const v=document.createElement('div');v.textContent=value||'—';grid.append(k,v)}
function renderEvidence(data){evidence.replaceChildren();data.events.forEach((event,index)=>{const fn=event.frameNet||{},syntax=event.dependencyAnalysis||{},item=document.createElement('section');item.className='evidence-item';const head=document.createElement('div');head.className='evidence-head';const title=document.createElement('strong'),evidenceTitle=fn.frameName|| (event.mappingStatus==='candidate_only'?'Candidate FrameNet lookup':'Domain-only event');title.textContent=`Event ${index+1}: ${evidenceTitle}`;const badge=document.createElement('span');badge.className=`badge ${fn.validationStatus==='validated_exact_lu'?'ok':'warn'}`;badge.textContent=fn.validationStatus||'not validated';head.append(title,badge);const grid=document.createElement('div');grid.className='evidence-grid';if(event.mappingStatus==='candidate_only'){addEvidenceRow(grid,'Mapping status','Candidate only - not a confirmed semantic parse');addEvidenceRow(grid,'Candidate frames',(event.candidateFrames||[]).map(candidate=>`${candidate.frame} (${candidate.matchedText} → ${candidate.matchedLexicalUnit})`).join('; '));addEvidenceRow(grid,'Method','NLTK FrameNet lexical-unit lookup over unmatched sentence')}else{const parsedRoles=Object.entries(event.extractionEvidence||{}).filter(([,value])=>value.method==='dependency_parse').map(([name,value])=>`${name}: ${value.relation}`).join('; ');addEvidenceRow(grid,'Dependency parser',syntax.available?`${syntax.model} (${syntax.status})`:'Unavailable - domain rules used');addEvidenceRow(grid,'Parsed roles',parsedRoles||'Domain rules / implicit roles');addEvidenceRow(grid,'Official frame',fn.frameName?`${fn.frameName} (#${fn.frameId})`:'No exact FrameNet frame assigned');addEvidenceRow(grid,'Matched LU',fn.target?`${fn.target.text} → ${fn.target.lexicalUnit}`:'No exact LU in the sentence');addEvidenceRow(grid,'Validated FEs',(fn.frameElementValidation?.valid||[]).join(', '));addEvidenceRow(grid,'Invalid FEs',(fn.frameElementValidation?.invalid||[]).join(', ')||'None')}item.append(head,grid);evidence.appendChild(item)});if(!data.events.length){const empty=document.createElement('span');empty.className='empty';empty.textContent='No FrameNet evidence available.';evidence.appendChild(empty)}}
async function run(){mapButton.disabled=true;status.className='status';status.textContent='Mapping…';try{let payload={text:text.value,filename:'pasted-text'};if(file.files[0]){payload={filename:file.files[0].name,contentBase64:bytesToBase64(await file.files[0].arrayBuffer())}}const response=await fetch('/api/map',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Mapping failed');result=cleanMapping(data);output.textContent=JSON.stringify(result,null,2);renderAnnotations(result);renderEvidence(data);status.textContent=`Mapped ${data.eventCount} event(s) with ${data.syntacticParser.model} dependency parsing and FrameNet ${data.frameNetRegistry.version} validation.`;download.disabled=false}catch(error){status.className='status error';status.textContent=error.message}finally{mapButton.disabled=false}}
mapButton.addEventListener('click',run);document.querySelector('#sample').addEventListener('click',()=>{file.value='';text.value=STRESS_SAMPLE});download.addEventListener('click',()=>{const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='framenet-mapping.json';a.click();URL.revokeObjectURL(a.href)});
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

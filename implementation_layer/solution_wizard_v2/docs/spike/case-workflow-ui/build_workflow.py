"""Workflow prototype for a wizard PoC: every role's screen comes from the BPMN.

Lanes become roles, user tasks become that role's screens, service tasks are
the AI steps (simulated with a real sandbox run's output), and the exclusive
gateway after the review is the approve / return decision. The review form
itself comes from the blueprint's target_output_spec, as in build_form.py.

Usage: build_workflow.py <blueprint.json> <workflow.bpmn> <sandbox run log> <audio or -> <out.html>
"""
import base64
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

bp_path, bpmn_path, log_path, audio_path, out = sys.argv[1:6]
bp = json.loads(Path(bp_path).read_text(encoding="utf-8"))
spec = bp["target_output_spec"]

# --- BPMN -> roles, nodes, flows -------------------------------------------
NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
proc = ET.parse(bpmn_path).getroot().find(f"{NS}process")
data_names = {d.get("id"): d.get("name") for d in proc.iter(f"{NS}dataObjectReference")}
KINDS = ("userTask", "serviceTask", "sendTask", "manualTask", "task", "scriptTask",
         "startEvent", "endEvent", "exclusiveGateway", "parallelGateway")
nodes = {}
for kind in KINDS:
    for el in proc.iter(f"{NS}{kind}"):
        nodes[el.get("id")] = {
            "id": el.get("id"),
            "kind": kind,
            "name": re.sub(r"^\[[A-Z0-9]+\]\s*", "", el.get("name") or ""),
            "inputs": [data_names.get(a.findtext(f"{NS}sourceRef")) for a in el.iter(f"{NS}dataInputAssociation")],
            "outputs": [data_names.get(a.findtext(f"{NS}targetRef")) for a in el.iter(f"{NS}dataOutputAssociation")],
        }
lanes = []
for lane in proc.iter(f"{NS}lane"):
    refs = [r.text for r in lane.iter(f"{NS}flowNodeRef")]
    for r in refs:
        if r in nodes:
            nodes[r]["lane"] = lane.get("id")
    human = any(nodes.get(r, {}).get("kind") in ("userTask", "manualTask") for r in refs)
    lanes.append({"id": lane.get("id"), "name": lane.get("name"), "human": human})
flows = [{"from": f.get("sourceRef"), "to": f.get("targetRef"), "name": f.get("name") or ""}
         for f in proc.iter(f"{NS}sequenceFlow")]

# --- the run's output ------------------------------------------------------
log = Path(log_path).read_text(encoding="utf-8", errors="ignore")
seg = log[log.find("=== POC OUTPUT BEGIN ==="): log.find("=== POC OUTPUT END ===")]
files = dict(re.findall(r"--- output/([^\n]+) ---\n(.*?)(?=\n--- output/|\Z)", seg, re.S))
record = validation = None
transcript = ""
for name, body in files.items():
    if name.endswith(".json"):
        data = json.loads(body)
        first = data[0] if isinstance(data, list) and data else data
        if isinstance(first, dict) and any(f in first for f in spec["fields"]):
            record = first
        elif isinstance(first, dict) and "passed" in first:
            validation = first
    elif name.endswith("transcript.txt"):
        transcript = body.strip()
if record is None:
    sys.exit("no record matching target_output_spec in the run output")

audio = ""
if audio_path != "-":
    audio = "data:audio/wav;base64," + base64.b64encode(Path(audio_path).read_bytes()).decode()

payload = {
    "title": (bp.get("use_case") or {}).get("name") or spec.get("schema_name"),
    "spec": spec,
    "process": {"lanes": lanes, "nodes": list(nodes.values()), "flows": flows},
    "sample": {"record": record, "validation": validation, "transcript": transcript,
               "audio": audio, "audioName": Path(audio_path).name if audio_path != "-" else ""},
}
template = Path(__file__).with_name("workflow_template.html").read_text(encoding="utf-8")
Path(out).write_text(template.replace("/*__PAYLOAD__*/null", json.dumps(payload, ensure_ascii=False)),
                     encoding="utf-8")
print("wrote", out, "| roles:", [l["name"] for l in lanes], "| nodes:", len(nodes))

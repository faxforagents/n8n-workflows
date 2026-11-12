#!/usr/bin/env python3
"""Build workflows/send-a-fax-with-human-approval.json.

The workflow is kept as code so the node ids, positions and connections stay consistent. Run it after
a change and commit the JSON it writes. Standard library only.
"""
from __future__ import annotations

import json
from pathlib import Path

API = "https://api.faxforagents.com"
OUT = Path(__file__).resolve().parent.parent / "workflows" / "send-a-fax-with-human-approval.json"

CONDITION_OPTIONS = {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2}


def nid(n: int) -> str:
    return f"f0a0f0a0-0000-4000-8000-{n:012d}"


def http(name: str, n: int, pos: list[int], method: str, url: str, body: str | None = None,
         idempotency: str | None = None) -> dict:
    params: dict = {
        "method": method,
        "url": url,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpBearerAuth",
        "options": {"timeout": 30000},
    }
    if idempotency:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": [{"name": "Idempotency-Key", "value": idempotency}]}
    if body:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = body
    return {"parameters": params, "id": nid(n), "name": name, "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": pos}


def set_node(name: str, n: int, pos: list[int], fields: list[tuple[str, str, str]]) -> dict:
    return {
        "parameters": {
            "assignments": {
                "assignments": [
                    {"id": f"{nid(n)}-{i}", "name": k, "value": v, "type": t} for i, (k, v, t) in enumerate(fields)
                ]
            },
            "options": {},
        },
        "id": nid(n), "name": name, "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": pos,
    }


def string_rule(left: str, right: str, key: str) -> dict:
    return {
        "conditions": {
            "options": CONDITION_OPTIONS,
            "conditions": [{"leftValue": left, "rightValue": right, "operator": {"type": "string", "operation": "equals"}}],
            "combinator": "and",
        },
        "renameOutput": True,
        "outputKey": key,
    }


def switch(name: str, n: int, pos: list[int], rules: list[dict]) -> dict:
    return {"parameters": {"rules": {"values": rules}, "options": {"fallbackOutput": "extra"}}, "id": nid(n),
            "name": name, "type": "n8n-nodes-base.switch", "typeVersion": 3.2, "position": pos}


def wait(name: str, n: int, pos: list[int], seconds: int) -> dict:
    return {"parameters": {"amount": seconds, "unit": "seconds"}, "id": nid(n), "name": name,
            "type": "n8n-nodes-base.wait", "typeVersion": 1.1, "position": pos, "webhookId": nid(n)}


def sticky(n: int, pos: list[int], content: str, width: int, height: int) -> dict:
    return {"parameters": {"content": content, "height": height, "width": width}, "id": nid(n),
            "name": f"Note {n}", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": pos}


QUOTE_ID = "{{ $('Quote the fax').item.json.id }}"

nodes = [
    {"parameters": {}, "id": nid(1), "name": "Run workflow", "type": "n8n-nodes-base.manualTrigger",
     "typeVersion": 1, "position": [0, 300]},
    set_node("Fax input", 2, [220, 300], [
        ("to", "+15550000001", "string"),
        ("text", "Hello from n8n. This page was prepared, quoted and sent through Fax for Agents.", "string"),
        ("filename", "hello-from-n8n", "string"),
        ("approval_message", "n8n workflow asks to send this fax. Approve it in the dashboard or by mail.", "string"),
    ]),
    http("Prepare the document", 3, [440, 300], "POST", f"{API}/v1/documents",
         body="={{ { text: $json.text, filename: $json.filename } }}",
         idempotency="=n8n-{{ $execution.id }}-document"),
    http("Quote the fax", 4, [660, 300], "POST", f"{API}/v1/fax-quotes",
         body="={{ { document_id: $json.id, to: $('Fax input').item.json.to } }}"),
    {
        "parameters": {
            "conditions": {
                "options": CONDITION_OPTIONS,
                "conditions": [{"id": "approval-required", "leftValue": "={{ $json.authorization_required }}",
                                "rightValue": True, "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                "combinator": "and",
            },
            "options": {},
        },
        "id": nid(5), "name": "Approval required?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [880, 300],
    },
    http("Ask a person to approve", 6, [1100, 140], "POST", f"{API}/v1/approval-requests",
         body="={{ { kind: 'send', quote_id: $json.id, message: $('Fax input').item.json.approval_message } }}"),
    wait("Wait 30 seconds", 7, [1320, 140], 30),
    http("Check the approval", 8, [1540, 140], "GET",
         f"={API}/v1/approval-requests/{{{{ $('Ask a person to approve').item.json.id }}}}"),
    switch("Approval status", 9, [1760, 140], [
        string_rule("={{ $json.status }}", "approved", "approved"),
        string_rule("={{ $json.status }}", "pending", "pending"),
    ]),
    set_node("Send under the approval", 10, [1980, 60], [
        ("quote_id", f"={QUOTE_ID}", "string"),
        ("approval_id", "={{ $json.id }}", "string"),
    ]),
    {"parameters": {"errorMessage": "=The approval request is {{ $json.status }}. Nothing was sent. A person decides whether to ask again."},
     "id": nid(11), "name": "Not approved", "type": "n8n-nodes-base.stopAndError", "typeVersion": 1, "position": [1980, 300]},
    set_node("Send without approval", 12, [1100, 460], [
        ("quote_id", "={{ $json.id }}", "string"),
        ("approval_id", "", "string"),
    ]),
    http("Send the fax", 13, [2200, 300], "POST", f"{API}/v1/faxes",
         body="={{ $json.approval_id ? { quote_id: $json.quote_id, approval_id: $json.approval_id } : { quote_id: $json.quote_id } }}",
         idempotency="=n8n-{{ $execution.id }}-send"),
    wait("Wait 10 seconds", 14, [2420, 300], 10),
    http("Check the fax", 15, [2640, 300], "GET", f"={API}/v1/faxes/{{{{ $('Send the fax').item.json.id }}}}"),
    switch("Fax state", 16, [2860, 300], [
        string_rule("={{ $json.state }}", "delivered", "delivered"),
        string_rule("={{ $json.state }}", "failed", "failed"),
        string_rule("={{ $json.state }}", "partial", "partial"),
        string_rule("={{ $json.state }}", "unknown", "unknown"),
    ]),
    set_node("Delivered", 17, [3080, 60], [
        ("result", "delivered", "string"),
        ("fax_id", "={{ $json.id }}", "string"),
        ("pages_sent", "={{ $json.pages_sent }}", "number"),
        ("amount_micro", "={{ $json.amount_micro }}", "number"),
        ("evidence", "={{ $json.evidence }}", "object"),
    ]),
    set_node("Failed", 18, [3080, 220], [
        ("result", "failed", "string"),
        ("fax_id", "={{ $json.id }}", "string"),
        ("failure_code", "={{ $json.failure_code }}", "string"),
        ("next_step", "A person decides whether to fix the number or the document and send again.", "string"),
    ]),
    set_node("Needs a person", 19, [3080, 400], [
        ("result", "={{ $json.state }}", "string"),
        ("fax_id", "={{ $json.id }}", "string"),
        ("pages_sent", "={{ $json.pages_sent }}", "number"),
        ("next_step", "Never retransmit on your own. Some or all pages can have reached the recipient. A person reconciles with them.", "string"),
    ]),
    sticky(20, [0, 0], (
        "## Send a fax with human approval\n"
        "Fax for Agents, https://faxforagents.com. REST API only, HTTP Request nodes with one **Bearer Auth** credential.\n\n"
        "**Before the first run** open any HTTP node and pick or create a Bearer Auth credential with your API key. "
        "A test key (`ffa_test_...`) reaches the sandbox, no carrier, no cost. Keys: https://app.faxforagents.com\n\n"
        "Edit **Fax input** for the destination and the text. Sandbox outcomes: `+15550000001` delivered, "
        "`+15550000003` partial, `+15550000005` unknown, `+15550000007` failed."
    ), 860, 260),
    sticky(21, [1100, -120], (
        "## The approvals rule\n"
        "A live send needs a human approval bound to this exact quote, or a delegated policy the account owner wrote. "
        "The workflow asks with `POST /v1/approval-requests` and polls every 30 seconds until a person decides. "
        "It can never approve its own send: an API key used by automation cannot carry `approval:decide`."
    ), 1060, 200),
    sticky(22, [2420, 560], (
        "## After the send\n"
        "`queued` is not delivered. The workflow polls `GET /v1/faxes/{id}` every 10 seconds until the carrier answers. "
        "`delivered` carries the carrier's evidence. `partial` and `unknown` stop here and a person reconciles, nothing retransmits on its own.\n\n"
        "Price card launch-v2, effective 2026-10-31: $0.039 per page sent, $0.019 per page received. "
        "`amount_micro` is USD in micro-units (39000 is $0.039)."
    ), 760, 220),
]


def connect(a: str, b: str, out: int = 0) -> None:
    connections.setdefault(a, {"main": []})
    main = connections[a]["main"]
    while len(main) <= out:
        main.append([])
    main[out].append({"node": b, "type": "main", "index": 0})


connections: dict = {}
connect("Run workflow", "Fax input")
connect("Fax input", "Prepare the document")
connect("Prepare the document", "Quote the fax")
connect("Quote the fax", "Approval required?")
connect("Approval required?", "Ask a person to approve", 0)
connect("Approval required?", "Send without approval", 1)
connect("Ask a person to approve", "Wait 30 seconds")
connect("Wait 30 seconds", "Check the approval")
connect("Check the approval", "Approval status")
connect("Approval status", "Send under the approval", 0)
connect("Approval status", "Wait 30 seconds", 1)
connect("Approval status", "Not approved", 2)
connect("Send under the approval", "Send the fax")
connect("Send without approval", "Send the fax")
connect("Send the fax", "Wait 10 seconds")
connect("Wait 10 seconds", "Check the fax")
connect("Check the fax", "Fax state")
connect("Fax state", "Delivered", 0)
connect("Fax state", "Failed", 1)
connect("Fax state", "Needs a person", 2)
connect("Fax state", "Needs a person", 3)
connect("Fax state", "Wait 10 seconds", 4)

workflow = {
    "name": "Send a fax with human approval",
    "nodes": nodes,
    "connections": connections,
    "pinData": {},
    "settings": {"executionOrder": "v1"},
    "active": False,
    "meta": {"templateCredsSetupCompleted": False},
    "tags": [],
}

OUT.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(OUT.parents[1])} with {len(nodes)} nodes")

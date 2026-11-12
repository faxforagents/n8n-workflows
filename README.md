<p align="center">
  <a href="https://faxforagents.com"><img src="https://faxforagents.com/brand/logo-512.png" width="88" alt="Fax for Agents"></a>
</p>

<h1 align="center">Fax for Agents n8n workflows</h1>

<p align="center">Ready to import n8n workflows for <a href="https://faxforagents.com">Fax for Agents</a>. HTTP Request nodes against the REST API, one Bearer Auth credential, no community node needed.</p>

<p align="center">
  <a href="https://faxforagents.com">Website</a> ·
  <a href="https://faxforagents.com/docs/quickstart/">Quickstart</a> ·
  <a href="https://faxforagents.com/docs/api/">API reference</a> ·
  <a href="https://faxforagents.com/docs/sdks/">SDKs</a> ·
  <a href="https://faxforagents.com/mcp/">MCP</a> ·
  <a href="https://app.faxforagents.com">Dashboard</a> ·
  <a href="https://faxforagents.com/pricing/">Pricing</a> ·
  <a href="https://faxforagents.com/changelog/">Changelog</a> ·
  <a href="https://faxforagents.com/affiliates/">Affiliate program</a> ·
  <a href="https://gitlab.com/faxforagents/n8n-workflows">GitLab</a>
</p>

<p align="center">
  <a href="https://github.com/faxforagents/n8n-workflows/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/faxforagents/n8n-workflows/ci.yml?branch=main&label=ci" alt="CI"></a>
  <a href="https://github.com/faxforagents/n8n-workflows/blob/main/LICENSE"><img src="https://img.shields.io/badge/licence-MIT-1f6feb" alt="MIT licence"></a>
  <a href="https://n8n.io"><img src="https://img.shields.io/badge/n8n-2.45-ea4b71" alt="n8n 2.45"></a>
</p>

Fax for Agents is a fax API, a hosted MCP server and SDKs built so AI agents can send and receive
faxes. It is made by JSB Holdings LLC and built by [Synapse](https://synapsereality.io/).

| Workflow | What it does |
|---|---|
| [`workflows/send-a-fax-with-human-approval.json`](workflows/send-a-fax-with-human-approval.json) | Prepares a document, quotes it, asks a person to approve when the API requires it, sends, then polls until the carrier answers |

An inbound workflow (webhook, signature check, notification) lives in
[faxforagents/examples](https://github.com/faxforagents/examples/tree/main/n8n). An AI agent inside n8n
can use the MCP Client Tool node with `https://mcp.faxforagents.com/mcp/` instead. The
[MCP server README](https://github.com/faxforagents/mcp#n8n) shows that setup.

## Import

1. In n8n, Workflows, Import from File, pick the JSON.
2. Open any HTTP Request node and select or create a **Bearer Auth** credential with your API key. All
   eight HTTP nodes share it. The file carries no credential.
3. Edit **Fax input** for the destination and the text, then run the workflow.

A test key (`ffa_test_...`) reaches the sandbox provider only. No carrier, no cost, the destination
number picks the outcome (`+15550000001` is delivered, `+15550000003` is partial, `+15550000005` is
unknown, `+15550000007` is failed). A live key (`ffa_live_...`) reaches the carrier and spends the
prepaid wallet. Keys are created at <https://app.faxforagents.com>.

## Send a fax with human approval, node by node

```
Run workflow -> Fax input -> Prepare the document -> Quote the fax -> Approval required?
   yes -> Ask a person to approve -> Wait 30 seconds -> Check the approval -> Approval status
             approved -> Send under the approval -> Send the fax
             pending  -> Wait 30 seconds (again)
             other    -> Not approved (stop)
   no  -> Send without approval -> Send the fax
Send the fax -> Wait 10 seconds -> Check the fax -> Fax state
   delivered -> Delivered        failed -> Failed
   partial, unknown -> Needs a person        queued, active -> Wait 10 seconds (again)
```

| Node | Type | What it does |
|---|---|---|
| Run workflow | Manual trigger | Starts a run from the editor. Swap it for a webhook, a form or a schedule |
| Fax input | Set | `to` in E.164 form, `text`, `filename` and the `approval_message` a person sees |
| Prepare the document | HTTP Request | `POST /v1/documents` with the text. Returns `doc_...`, the page count and a sha256. Nothing is sent. Carries an `Idempotency-Key` built from the execution id, so a retried run reuses the same document |
| Quote the fax | HTTP Request | `POST /v1/fax-quotes` with `document_id` and `to`. Returns `quote_...`, `amount_micro`, `expires_at` (ten minutes) and `authorization_required` |
| Approval required? | IF | True when the quote says a human approval is required |
| Ask a person to approve | HTTP Request | `POST /v1/approval-requests` with `kind: send`, the `quote_id` and the message. The request is bound to that exact quote (document sha256, destination, amount) and the organization is mailed |
| Wait 30 seconds | Wait | Pauses before each check of the approval |
| Check the approval | HTTP Request | `GET /v1/approval-requests/{id}`. `status` is `pending`, `approved`, `rejected`, `revoked` or `expired` |
| Approval status | Switch | `approved` goes on to the send, `pending` loops back to the wait, anything else stops |
| Send under the approval | Set | Carries the `quote_id` and the `approval_id`, which is the approval request's id |
| Not approved | Stop and Error | Ends the run with the status in the message. Nothing was sent |
| Send without approval | Set | Carries the `quote_id` only, for a quote that needs no approval (the sandbox, or a delegated policy) |
| Send the fax | HTTP Request | `POST /v1/faxes` with the `quote_id` and, when present, the `approval_id`, plus an `Idempotency-Key` from the execution id. Returns `fax_...` in state `queued` |
| Wait 10 seconds | Wait | Pauses before each status check |
| Check the fax | HTTP Request | `GET /v1/faxes/{id}`. `state` is `queued`, `active`, `delivered`, `partial`, `failed` or `unknown` |
| Fax state | Switch | Routes on the state. `queued` and `active` loop back to the wait |
| Delivered | Set | The fax id, pages sent, amount and the carrier's `evidence` |
| Failed | Set | The fax id and `failure_code`. A person decides whether to fix and send again |
| Needs a person | Set | For `partial` and `unknown`. Nothing retransmits on its own |

Three sticky notes in the canvas repeat the setup, the approvals rule and what to do after the send.

## The two rules the workflow keeps

A live send needs a human approval bound to that exact quote, or a delegated policy the account owner
wrote outside any workflow. The workflow can ask for approval and wait. It can never approve its own
send, because an API key used by automation cannot carry `approval:decide`.

A fax is `delivered` only when the carrier's evidence is on the attempt. `partial` and `unknown`
never retransmit on their own. The workflow stops there and leaves the decision to a person.

## Tested

Imported and executed with n8n 2.45.7 (the `docker.n8n.io/n8nio/n8n` image) on 2026-10-31, against the
sandbox with a test key. The run to `+15550000001` ended in the Delivered branch with the carrier's
evidence.
`scripts/build_workflow.py` writes the JSON, so node ids, positions and connections stay consistent.

## Prices

Price card launch-v3 is effective from 2026-11-12. $0.039 per page sent, $0.019 per page received.
$2 per number per month, $19 per month for the Agent workspace. Sandbox pages cost 0.

## Working on this repository

```bash
python3 scripts/build_workflow.py     # regenerate workflows/*.json from the builder
python3 scripts/check_workflow.py     # valid JSON, every connection names a node, no credential in the file
sh scripts/truthcheck.sh              # the copy states only what the product ships
```

## Licence

MIT. See [LICENSE](LICENSE). Security reports go to hello@faxforagents.com, see [SECURITY.md](SECURITY.md).

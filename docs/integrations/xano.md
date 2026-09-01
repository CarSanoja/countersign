# Xano — Rebuild a SaaS Tool You Hate

## What we replaced

The vendor-onboarding and contract-execution module of a procurement suite —
Coupa, Ariba, Ironclad. The part where a supplier is added, their bank details
are recorded, and a contract goes out for signature. In most companies this is
a queue of email attachments and a person with four minutes.

## Built by code, not by clicking

Both tables and their schema were created through the **Metadata API**, never
through the UI:

    POST /workspace/1/table                       vendors (id 3), audit_log (id 4)
    POST /workspace/1/table/{id}/schema/type/text
    POST /workspace/1/table/{id}/schema/type/int
    POST /workspace/1/table/{id}/schema/type/json
    POST /workspace/1/table/{id}/content          one row per gate decision
    GET  /workspace/1/table/{id}/content          reads the trail back

The schema endpoint is per column type: `POST /table/{id}/schema` returns 404,
`POST /table/{id}/schema/type/text` is the real path.

## Why the audit log lives here

Every decision the capability gate makes — allowed or denied — is a row:

    run_id · seq · agent_id · tool · capability · decision · reasons · recorded_at

The row that matters is `seq=5`, where `envelope-preparer` asked for
`foxit_execute_signature` and was refused. A product that claims an agent cannot
sign has to be able to show the attempt and the refusal, and a log the agent
could edit afterwards would prove nothing.

## Append-only enforced by the credential

Xano access tokens carry per-scope CRUD flags. The runtime token is issued with
**Workspace Database: Create + Read**, with Update and Delete left unchecked, so
the agent cannot rewrite its own trail — not by convention in our code, but
because the credential does not carry the power.

That is the same principle as the signature boundary, applied to storage: a
capability you do not hold cannot be misused.

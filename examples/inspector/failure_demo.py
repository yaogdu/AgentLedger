from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentledger.inspector import InspectorDataSource
from agentledger.runtime import Runtime


def main() -> None:
    target = Path(tempfile.mkdtemp(prefix="agentledger-inspector-failure-"))
    root = target / ".agentledger"
    rt = Runtime.local(root)

    completed_run_id, completed_step_id = rt.create_run(initial_state={"agent_run_id": "demo-success"})
    claim = rt.store.claim_step(worker_id="demo-success-worker", run_id=completed_run_id)
    if claim is None:
        raise RuntimeError("could not claim success step")
    rt.store.commit_state_patch(
        run_id=completed_run_id,
        step_id=completed_step_id,
        lease_token=claim.lease_token,
        base_version=0,
        patch={"status": "ok"},
    )

    failed_run_id, failed_step_id = rt.create_run(initial_state={"agent_run_id": "demo-failure"}, retry_policy={"max_attempts": 2})
    rt.store.mark_retry(run_id=failed_run_id, step_id=failed_step_id, error="provider timeout", error_type="TimeoutError")
    rt.store.request_approval(
        approval_key="demo-failure:payments.refund",
        run_id=failed_run_id,
        session_id=rt.store.run(failed_run_id)["session_id"],
        step_id=failed_step_id,
        tool_name="payments.refund",
        risk_level="high",
        reason="refund requires human approval",
        request_hash="sha256:demo-approval-request",
        request_ref=json.dumps({"amount": 129.5, "currency": "USD"}, sort_keys=True),
        requested_by="demo-agent",
    )
    rt.store.conn.execute(
        """
        INSERT INTO tool_ledger(
            ledger_id, run_id, session_id, step_id, tool_name, tool_version, tool_call_id,
            idempotency_key, causal_token, request_hash, request_ref, status, response_ref,
            created_at, updated_at
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "ledger-demo-unknown",
            failed_run_id,
            rt.store.run(failed_run_id)["session_id"],
            failed_step_id,
            "payments.charge",
            "1",
            "tool-call-demo-unknown",
            "idem-demo-unknown",
            "causal-demo-unknown",
            "sha256:demo-request",
            json.dumps({"amount": 129.5, "currency": "USD"}, sort_keys=True),
            "PENDING_VERIFICATION",
            "blob://unknown-payment-response",
            1.0,
            1.0,
        ),
    )
    rt.store.conn.commit()
    rt.store.append_event(
        run_id=failed_run_id,
        session_id=rt.store.run(failed_run_id)["session_id"],
        step_id=failed_step_id,
        event_type="tool_call_blocked",
        payload={"tool": "payments.refund", "reason": "policy denied high-risk refund"},
    )
    rt.store.mark_failed(
        run_id=failed_run_id,
        step_id=failed_step_id,
        error="refund policy blocked after retry",
        error_type="PolicyDenied",
    )

    source = InspectorDataSource()
    completed_report = source.from_sqlite(db_path=root / "state.db", blob_root=root / "blobs", run_id=completed_run_id, include_payloads=True)
    completed_html = target / f"{completed_run_id}-inspector.html"
    completed_report.write_html(completed_html)

    failed_report = source.from_sqlite(db_path=root / "state.db", blob_root=root / "blobs", run_id=failed_run_id, include_payloads=True)
    failed_html = target / "failed-run-inspector.html"
    failed_link_html = target / f"{failed_run_id}-inspector.html"
    failed_json = target / "failed-run-inspector.json"
    failed_report.write_html(failed_html)
    failed_report.write_html(failed_link_html)
    failed_report.write(failed_json)

    run_index = source.runs_from_sqlite(
        db_path=root / "state.db",
        blob_root=root / "blobs",
        limit=20,
        run_link_template="{run_id}-inspector.html",
    )
    index_html = target / "runs.html"
    run_index.write_html(index_html)

    print(f"run index: {index_html}")
    print(f"failed run inspector: {failed_html}")
    print(f"failed run json: {failed_json}")
    print(f"failed run id: {failed_run_id}")


if __name__ == "__main__":
    main()

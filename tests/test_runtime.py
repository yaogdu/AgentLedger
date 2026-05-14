from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from agentledger.examples import crash_once_agent, recovery_agent, register_fake_github
from agentledger.replay import ReplayEngine
from agentledger.runtime import Runtime
from agentledger.tools import PermissionDenied, ToolSpec


class RuntimeTests(unittest.TestCase):
    def test_side_effect_not_duplicated_after_crash_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt = Runtime.local(root)
            external = root / "external_issues.json"
            register_fake_github(rt, external)
            run_id, _ = rt.create_run(initial_state={"crashed_once": False})

            first_ok = asyncio.run(rt.run_once(crash_once_agent, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertFalse(first_ok)
            issues = json.loads(external.read_text())
            self.assertEqual(len(issues), 1)

            rt.store.apply_system_state_patch(
                run_id=run_id,
                patch={"crashed_once": True},
                reason="test recovery marker after simulated worker crash",
            )
            second_ok = asyncio.run(rt.run_once(recovery_agent, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertTrue(second_ok)
            issues = json.loads(external.read_text())
            self.assertEqual(len(issues), 1)
            final_state = rt.store.final_state(run_id)
            self.assertTrue(final_state["recovered"])
            self.assertEqual(final_state["issue"]["external_id"], "ISSUE-1")

    def test_replay_does_not_execute_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt = Runtime.local(root)
            external = root / "external_issues.json"
            register_fake_github(rt, external)
            run_id, _ = rt.create_run(initial_state={"crashed_once": False})
            asyncio.run(rt.run_once(crash_once_agent, run_id=run_id, agent_role="ExecutorAgent"))
            rt.store.apply_system_state_patch(
                run_id=run_id,
                patch={"crashed_once": True},
                reason="test recovery marker after simulated worker crash",
            )
            asyncio.run(rt.run_once(recovery_agent, run_id=run_id, agent_role="ExecutorAgent"))

            before = json.loads(external.read_text())
            summary = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)
            after = json.loads(external.read_text())
            self.assertEqual(before, after)
            self.assertGreater(summary.event_count, 0)
            self.assertGreater(summary.tool_call_count, 0)

    def test_low_risk_stateless_tool_can_commit_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="math.add", func=lambda args: {"sum": args["a"] + args["b"]}))
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("math.add", {"a": 2, "b": 3})
                ctx.write_state_patch("sum", result["sum"])

            ok = asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertTrue(ok)
            self.assertEqual(rt.store.final_state(run_id)["sum"], 5)

    def test_high_risk_tool_is_default_denied_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="shell.exec", func=lambda args: {"ok": True}, risk_level="high"))
            run_id, step_id = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("shell.exec", {"cmd": "echo unsafe"})

            with self.assertRaises(PermissionDenied):
                asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent"))
            event_types = [row["type"] for row in rt.store.events(run_id)]
            self.assertIn("step_failed", event_types)
            step = rt.store.conn.execute("SELECT status FROM steps WHERE step_id=?", (step_id,)).fetchone()
            self.assertEqual(step["status"], "failed")

    def test_required_tool_args_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="docs.read", func=lambda args: {"ok": True}, input_schema={"required": ["path"]}))
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("docs.read", {})

            with self.assertRaises(ValueError):
                asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ReaderAgent"))

    def test_stale_lease_cannot_commit_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, step_id = rt.create_run(initial_state={})
            claim = rt.store.claim_step(worker_id="worker-a", run_id=run_id)
            self.assertIsNotNone(claim)
            assert claim is not None
            with self.assertRaises(RuntimeError):
                rt.store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token="bad-token", base_version=0, patch={"x": 1})


if __name__ == "__main__":
    unittest.main()

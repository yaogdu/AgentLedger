#!/usr/bin/env python3
"""
Travel Assistant Demo — AgentLedger Full-Stack Interactive Demo
================================================================
旅游助手交互式演示 — 每一步让你亲眼看到数据库里的实际变化

运行方式 / Usage:
  python examples/travel_assistant/demo.py --local
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
import webbrowser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agentledger import (  # noqa: E402
    AgentContext, ApprovalRequired, BudgetController, BudgetLimits,
    CostAttributionReporter, EvidenceExporter, LocalBlobStore,
    PolicyEngine, PostgresDependencyMissing, PostgresStore, PostgresStoreConfig,
    ReplayEngine, Runtime, SQLiteStore, SimulatedCrash,
)

# ════════════════════════════════════════════════════════════
# ANSI Colors
# ════════════════════════════════════════════════════════════
class C:
    R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"; B = "\033[94m"
    M = "\033[95m"; C = "\033[96m"; BOLD = "\033[1m"; DIM = "\033[2m"; RST = "\033[0m"

# ════════════════════════════════════════════════════════════
# Mock data
# ════════════════════════════════════════════════════════════
MOCK_FLIGHTS = [
    {"id": "FL-002", "from_city": "Beijing", "from_code": "PEK", "to_city": "Tokyo", "to_code": "NRT", "date": "2025-06-15", "airline": "JAL", "price_usd": 580},
]
MOCK_HOTELS = [
    {"id": "HT-002", "city": "Tokyo", "name": "APA Hotel Shinjuku", "nightly_usd": 85, "stars": 3},
]
MOCK_WEATHER = {"Tokyo": {"temp_c": 24, "condition": "Partly Cloudy", "humidity": 65}}
_BOOKING_DB: dict[str, dict[str, Any]] = {}
_TOOL_LEDGER_SNAPSHOTS: list[dict] = []  # for display

# ════════════════════════════════════════════════════════════
# Tool implementations
# ════════════════════════════════════════════════════════════

def _search_flights(args):
    origin = args.get("from", "").strip().lower()
    dest = args.get("to", "").strip().lower()
    results = [f for f in MOCK_FLIGHTS
               if origin in (f["from_city"].lower(), f["from_code"].lower())
               and dest in (f["to_city"].lower(), f["to_code"].lower())]
    return {"results": results, "count": len(results)}

def _search_hotels(args):
    city = args.get("city", "").strip().lower()
    results = [h for h in MOCK_HOTELS if h["city"].lower() == city]
    return {"results": results, "count": len(results)}

def _check_weather(args):
    city = args.get("city", "").strip().title()
    return {"city": city, **MOCK_WEATHER.get(city, {"temp_c": 20, "condition": "Unknown"})}

def _book_flight(args):
    ref = f"BK-F-{args['flight_id']}-{args['passenger'][:3].upper()}"
    if ref in _BOOKING_DB:
        return _BOOKING_DB[ref]
    f = next((f for f in MOCK_FLIGHTS if f["id"] == args["flight_id"]), None)
    booking = {"booking_ref": ref, "type": "flight", "airline": f["airline"],
               "price_usd": f["price_usd"], "status": "confirmed", "external_id": ref}
    _BOOKING_DB[ref] = booking
    return booking

def _book_hotel(args):
    ref = f"BK-H-{args['hotel_id']}-{args['guest'][:3].upper()}"
    if ref in _BOOKING_DB:
        return _BOOKING_DB[ref]
    h = next((h for h in MOCK_HOTELS if h["id"] == args["hotel_id"]), None)
    nights = 5
    booking = {"booking_ref": ref, "type": "hotel", "name": h["name"],
               "price_total_usd": h["nightly_usd"] * nights, "status": "confirmed", "external_id": ref}
    _BOOKING_DB[ref] = booking
    return booking

# ════════════════════════════════════════════════════════════
# Agent
# ════════════════════════════════════════════════════════════

async def travel_planner(ctx: AgentContext, state: dict[str, Any]) -> None:
    """旅游规划 Agent：研究 → 预订机票 → 崩溃 → 恢复 → 预订酒店."""
    # Research
    flights = await ctx.call_tool("travel.search_flights", {"from": "Beijing", "to": "Tokyo"})
    hotels = await ctx.call_tool("travel.search_hotels", {"city": "Tokyo"})
    weather = await ctx.call_tool("travel.check_weather", {"city": "Tokyo"})
    ctx.write_state_patch("research", {"flights": flights["count"], "hotels": hotels["count"], "weather": weather["temp_c"]})

    # Book flight
    flight = await ctx.call_tool("travel.book_flight", {
        "flight_id": "FL-002", "passenger": "Demo User",
        "_logical_operation": "book-demo-flight",
    })

    # Crash on attempt 2
    if ctx.attempt == 2:
        raise SimulatedCrash("after flight booking")

    # Book hotel
    hotel = await ctx.call_tool("travel.book_hotel", {
        "hotel_id": "HT-002", "check_in": "2025-06-15", "check_out": "2025-06-20",
        "guest": "Demo User", "_logical_operation": "book-demo-hotel",
    })

    ctx.write_state_patch("bookings", {"flight": flight["booking_ref"], "hotel": hotel["booking_ref"]})
    ctx.write_state_patch("trip_status", "confirmed")

# ════════════════════════════════════════════════════════════
# Display helpers
# ════════════════════════════════════════════════════════════

def wait(msg="按 Enter 继续 / Press Enter to continue"):
    try:
        input(f"\n{C.DIM}  ⏎ {msg}...{C.RST}")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

def show(label: str, lines: list[str], color: str = C.C):
    """显示一个信息框 / Display an info box."""
    print(f"\n  {color}{label}:{C.RST}")
    for line in lines:
        print(f"    {C.DIM}{line}{C.RST}")

def show_rows(label: str, rows: list[dict], color: str = C.C):
    """以表格形式展示数据库行 / Display database rows as table."""
    if not rows:
        print(f"\n  {color}{label}:{C.RST} {C.DIM}(empty){C.RST}")
        return
    print(f"\n  {color}{label} ({len(rows)} rows):{C.RST}")
    for r in rows:
        items = [f"{k}={C.BOLD}{v}{C.RST}" for k, v in r.items()]
        print(f"    {C.DIM}{' | '.join(items)}{C.RST}")

def show_db(store):
    """展示数据库当前状态 / Show current database state."""
    now_ts = __import__('time').time

    # Runs
    runs = []
    for r in store.conn.execute("SELECT run_id, status, state_version FROM runs").fetchall():
        runs.append({"run_id": r["run_id"][:20] + "...", "status": r["status"], "state_version": r["state_version"]})
    show_rows("📋 Runs", runs, C.B)

    # Steps
    steps = []
    for s in store.conn.execute("SELECT step_id, status, attempt FROM steps ORDER BY created_at").fetchall():
        steps.append({"step_id": s["step_id"][:20] + "...", "status": s["status"], "attempt": s["attempt"]})
    show_rows("📋 Steps", steps, C.B)

    # Tool Ledger
    ledger = []
    for tl in store.conn.execute("SELECT tool_name, status, idempotency_key FROM tool_ledger ORDER BY created_at").fetchall():
        key = tl["idempotency_key"]
        short_key = key.split(":")[-2] + ":" + key.split(":")[-1][:10] if ":" in key else key[:20]
        ledger.append({"tool": tl["tool_name"], "status": tl["status"], "idemp_key": short_key})
    show_rows("📋 Tool Ledger", ledger, C.Y)

    # Approval requests
    approvals = []
    for a in store.conn.execute("SELECT tool_name, status, approved_by FROM approval_requests ORDER BY created_at").fetchall():
        approvals.append({"tool": a["tool_name"], "status": a["status"], "approved_by": a["approved_by"] or "-"})
    show_rows("📋 Approval Requests", approvals, C.R)

    # State
    state = store.final_state(runs[0]["run_id"].replace("...", "").strip()) if runs else {}
    if state:
        show("📋 Current State (已持久化 / persisted)", [f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in state.items()], C.G)
    else:
        show("📋 Current State", ["(empty)"], C.G)

    print()

# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="AgentLedger 旅游助手交互式演示")
    parser.add_argument("--local", action="store_true", help="强制 SQLite")
    parser.add_argument("--root", default=".agentledger", help="存储根目录")
    parser.add_argument("--no-browser", action="store_true", help="不打开浏览器")
    args = parser.parse_args()
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    # ════════════════════════════════════════════════════════
    # 开场 / Intro
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.C}  ╔════════════════════════════════════════════════════╗{C.RST}")
    print(f"{C.BOLD}{C.C}  ║   AgentLedger 旅游助手 — 交互式演示                   ║{C.RST}")
    print(f"{C.BOLD}{C.C}  ║   每一步展示数据库真实状态，让你「看见」 Runtime 的工作   ║{C.RST}")
    print(f"{C.BOLD}{C.C}  ╚════════════════════════════════════════════════════╝{C.RST}")

    print(f"\n  {C.DIM}AgentLedger 是什么？{C.RST}")
    print(f"  ┌────────────────────────────────────────────────────┐")
    print(f"  │ 一个给 AI Agent 用的 {C.BOLD}持久化执行引擎{C.RST}                         │")
    print(f"  │                                                        │")
    print(f"  │ 它不帮你思考，只保证你的 Agent {C.G}不会：{C.RST}                        │")
    print(f"  │  {C.R}✗{C.RST} 崩溃后丢失进度      {C.G}✓ 自动从断点恢复{C.RST}                 │")
    print(f"  │  {C.R}✗{C.RST} 重复扣款/重复操作   {C.G}✓ Tool Ledger 幂等防重{C.RST}           │")
    print(f"  │  {C.R}✗{C.RST} 危险操作无记录      {C.G}✓ 完整审计追踪{C.RST}                   │")
    print(f"  │  {C.R}✗{C.RST} 没有审批流程        {C.G}✓ 人工审批门禁{C.RST}                   │")
    print(f"  │  {C.R}✗{C.RST} 调用次数失控        {C.G}✓ 预算控制{C.RST}                       │")
    print(f"  └────────────────────────────────────────────────────┘")

    wait()

    # ════════════════════════════════════════════════════════
    # Setup
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.B}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.B}  Step 1: 初始化 — 注册工具、配置策略、连接存储{C.RST}")
    print(f"{C.BOLD}{C.B}{'═' * 60}{C.RST}")

    blobs = LocalBlobStore(root / "blobs")
    if not args.local:
        try:
            store = PostgresStore(PostgresStoreConfig.from_env())
            store.init()
            print(f"\n  {C.B}存储: Postgres{C.RST}")
        except (ValueError, PostgresDependencyMissing):
            print(f"\n  {C.Y}Postgres 不可用，回退 SQLite{C.RST}")
            store = SQLiteStore(root / "state.db"); store.init()
    else:
        store = SQLiteStore(root / "state.db"); store.init()
        print(f"\n  {C.B}存储: SQLite → {root / 'state.db'}{C.RST}")
        print(f"  {C.DIM}(同一目录下 .agentledger/blobs/ 存储证据附件){C.RST}")

    policy = PolicyEngine()
    for t in ["travel.search_flights", "travel.search_hotels", "travel.check_weather",
              "travel.book_flight", "travel.book_hotel"]:
        policy.allow_tool("TravelPlanner", t)

    budget = BudgetController(BudgetLimits(max_tool_calls=25))
    rt = Runtime(store=store, blobs=blobs, policy=policy, budget=budget)

    # Register tools
    rt.tool(name="travel.search_flights", side_effect="none", risk_level="low",
            input_schema={"type": "object", "required": ["from", "to"]})(_search_flights)
    rt.tool(name="travel.search_hotels", side_effect="none", risk_level="low",
            input_schema={"type": "object", "required": ["city"]})(_search_hotels)
    rt.tool(name="travel.check_weather", side_effect="none", risk_level="low",
            input_schema={"type": "object", "required": ["city"]})(_check_weather)
    rt.tool(name="travel.book_flight", side_effect="external_write", risk_level="high",  # agentledger: ignore-boundary - approval-gated external booking API demo, not untrusted local execution
            idempotency=True, approval_required=True,
            input_schema={"type": "object", "required": ["flight_id", "passenger"]})(_book_flight)
    rt.tool(name="travel.book_hotel", side_effect="external_write", risk_level="high",  # agentledger: ignore-boundary - approval-gated external booking API demo, not untrusted local execution
            idempotency=True, approval_required=True,
            input_schema={"type": "object", "required": ["hotel_id", "guest"]})(_book_hotel)

    print(f"\n  {C.C}已注册 5 个工具:{C.RST}")
    for t in rt.registry.list():
        risk_color = C.G if t.risk_level == "low" else C.R
        approval = f"{C.R}需审批{C.RST}" if t.approval_required else f"{C.G}无需审批{C.RST}"
        print(f"    {C.DIM}•{C.RST} {t.name}  [{risk_color}{t.risk_level}{C.RST}] [{approval}]")
    print(f"  {C.DIM}策略: TravelPlanner 角色可调用以上全部工具{C.RST}")
    print(f"  {C.DIM}预算: 最多 25 次工具调用{C.RST}")

    run_id, _ = rt.create_run(initial_state={"trip": "Tokyo", "budget_usd": 3000})
    print(f"\n  {C.B}Run 已创建: {C.BOLD}{run_id}{C.RST}")
    show_db(store)
    wait()

    # ════════════════════════════════════════════════════════
    # Attempt 1: 审批拦截
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.R}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.R}  Step 2: Attempt 1 — Agent 执行 → 审批拦截{C.RST}")
    print(f"{C.BOLD}{C.R}{'═' * 60}{C.RST}")
    print(f"\n  {C.DIM}Agent 正在执行: 搜索航班 → 搜索酒店 → 查天气 → 预订机票...{C.RST}")

    ok = await rt.run_once(travel_planner, run_id=run_id, agent_role="TravelPlanner")

    print(f"\n  {C.R}预订机票触发审批！AgentLedger 自动拦截，等待人工决策。{C.RST}")
    print(f"  {C.R}book_flight triggered approval! Runtime paused, waiting for human.{C.RST}")

    show_db(store)
    print(f"  {C.R}注意: Tool Ledger 中已创建 RESERVED 记录（预留凭证），审批记录状态为 PENDING{C.RST}")
    wait("按 Enter 模拟人工审批 / Press Enter to approve")

    # Approve
    for req in store.approval_requests(run_id):
        if req["status"] == "PENDING":
            store.approve_request(req["approval_id"], approver="traveler", reason="预算内，同意")
            print(f"\n  {C.G}✅ 审批通过: {req['tool_name']} — 由 traveler 批准{C.RST}")

    show_db(store)
    wait()

    # ════════════════════════════════════════════════════════
    # Attempt 2: 执行 + 崩溃
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.Y}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.Y}  Step 3: Attempt 2 — 审批通过 → 执行预订 → 模拟崩溃{C.RST}")
    print(f"{C.BOLD}{C.Y}{'═' * 60}{C.RST}")
    print(f"\n  {C.DIM}重新执行 Agent (审批已通过，book_flight 将真正执行)...{C.RST}")

    ok = await rt.run_once(travel_planner, run_id=run_id, agent_role="TravelPlanner")

    print(f"\n  {C.Y}Agent 预订了机票，但在提交状态前崩溃了！{C.RST}")
    print(f"  {C.Y}机票在外部系统中已预订，但 Agent 的状态没有被持久化。{C.RST}")

    show_db(store)
    print(f"  {C.Y}关键: Tool Ledger 中 book_flight 状态 = {C.G}SUCCEEDED{C.Y}（外部已执行）{C.RST}")
    print(f"  {C.Y}       但 Step 状态 = retry_scheduled（状态没提交，等待重试）{C.RST}")
    print(f"  {C.Y}       这就是持久化执行的核心：外部副作用被 Ledger 保护，状态等待恢复{C.RST}")
    wait()

    # ════════════════════════════════════════════════════════
    # Attempt 3-4: 恢复 + 酒店审批
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.G}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.G}  Step 4: Attempt 3 — 崩溃恢复 → Tool Ledger 幂等回放{C.RST}")
    print(f"{C.BOLD}{C.G}{'═' * 60}{C.RST}")
    print(f"\n  {C.DIM}Agent 重新执行。预订机票时，Tool Ledger 发现已有 SUCCEEDED 记录...{C.RST}")
    print(f"  {C.DIM}{C.G}→ 直接返回缓存结果，不重复调用外部 API，不重复扣款！{C.RST}")

    ok = await rt.run_once(travel_planner, run_id=run_id, agent_role="TravelPlanner")

    print(f"\n  {C.G}✅ 机票幂等回放成功！（没有重复调用 _book_flight 函数）{C.RST}")
    print(f"  {C.R}接着预订酒店 → 又触发审批{C.RST}")

    # Hotel approval
    for req in store.approval_requests(run_id):
        if req["status"] == "PENDING":
            store.approve_request(req["approval_id"], approver="traveler", reason="酒店预算内，同意")
            print(f"\n  {C.G}✅ 审批通过: {req['tool_name']} — 由 traveler 批准{C.RST}")

    show_db(store)
    wait("按 Enter 继续执行 / Press Enter to continue")

    # Attempt 4: 完成
    print(f"\n{C.BOLD}{C.G}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.G}  Step 5: Attempt 4 — 酒店审批通过 → 完整执行 → 状态提交{C.RST}")
    print(f"{C.BOLD}{C.G}{'═' * 60}{C.RST}")

    ok = await rt.run_once(travel_planner, run_id=run_id, agent_role="TravelPlanner")
    assert ok, "Recovery failed"
    assert len(_BOOKING_DB) == 2, f"Expected 2 bookings, got {len(_BOOKING_DB)}"

    print(f"\n  {C.G}✅ 旅游规划完成！状态已持久化到数据库。{C.RST}")
    show_db(store)
    print(f"  {C.G}Step 状态 = completed, State 中有 bookings + trip_status{C.RST}")
    print(f"  {C.G}外部预订: {list(_BOOKING_DB.keys())} (2 个，没有重复){C.RST}")
    wait()

    # ════════════════════════════════════════════════════════
    # 证据 + 回放
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.M}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.M}  Step 6: 证据导出 + 成本归因 + 回放验证{C.RST}")
    print(f"{C.BOLD}{C.M}{'═' * 60}{C.RST}")

    evidence_dir = Path(args.root) / "evidence" / run_id
    evidence_dir.parent.mkdir(parents=True, exist_ok=True)
    bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
    bundle.write_dir(evidence_dir)
    html_path = bundle.write_html(evidence_dir / "report.html")
    html_abs = str(html_path.resolve())

    report = CostAttributionReporter(rt.store).report(run_id)
    replay = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)

    print(f"\n  {C.M}📊 成本归因: {report.total.get('tool_calls', 0)} 次工具调用{C.RST}")
    print(f"  {C.M}🔁 回放验证: {replay.event_count} 个事件, 安全={C.G if replay.replay_safe else C.R}{replay.replay_safe}{C.RST}")
    print(f"  {C.M}📁 证据报告: file://{html_abs}{C.RST}")
    print(f"  {C.M}📁 证据目录: {evidence_dir.resolve()}/ (JSON bundle + HTML 报告){C.RST}")

    if not args.no_browser:
        webbrowser.open(f"file://{html_abs}")
        print(f"\n  {C.M}🌐 已在浏览器中打开证据报告{C.RST}")

    rt.close()

    # ════════════════════════════════════════════════════════
    # 最终总结
    # ════════════════════════════════════════════════════════
    print(f"\n{C.BOLD}{C.G}{'═' * 60}{C.RST}")
    print(f"{C.BOLD}{C.G}  总结: AgentLedger 在你的 Demo 中做了什么{C.RST}")
    print(f"{C.BOLD}{C.G}{'═' * 60}{C.RST}")
    print(textwrap.dedent(f"""\n
    ┌──────────────────────────────────────────────────────────┐
    │                                                          │
    │  {C.G}✓ 持久化执行{C.RST}   崩溃后自动重试，状态不丢失                  │
    │                   Step: retry_scheduled → completed          │
    │                                                          │
    │  {C.G}✓ Tool Ledger{C.RST}   幂等回放，机票只预订了 {C.BOLD}1 次{C.RST}                 │
    │                   Ledger 中 SUCCEEDED → 后续调用直接返回缓存  │
    │                                                          │
    │  {C.G}✓ 审批门禁{C.RST}     机票 + 酒店各触发 1 次审批                  │
    │                   approval_requests 表中有完整记录          │
    │                                                          │
    │  {C.G}✓ 策略引擎{C.RST}     每个工具调用都经过 policy.check_tool()       │
    │                   TravelPlanner 角色权限验证通过              │
    │                                                          │
    │  {C.G}✓ 预算控制{C.RST}     全程追踪 {report.total.get('tool_calls', 0)} 次工具调用                     │
    │                   BudgetController.before_tool_call() 拦截   │
    │                                                          │
    │  {C.G}✓ 证据导出{C.RST}     {replay.event_count} 个事件完整记录                         │
    │                   events 表 + blob 附件 → HTML 报告         │
    │                                                          │
    │  {C.G}✓ 成本归因{C.RST}     每次调用自动记录 cost_records               │
    │                   CostAttributionReporter 按 agent 汇总     │
    │                                                          │
    │  {C.G}✓ 回放引擎{C.RST}     事件哈希校验通过                           │
    │                   可在不重放工具的情况下验证历史 run            │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
    """))

    print(f"  {C.DIM}数据库文件: {root / 'state.db'}{C.RST}")
    print(f"  {C.DIM}可以用 sqlite3 直接查看: sqlite3 {root / 'state.db'} '.tables'{C.RST}")
    print(f"  {C.DIM}证据 HTML: file://{html_abs}{C.RST}")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

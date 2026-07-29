"""hermesctl — the operator surface for the Hermes control plane.

Every dashboard control in docs/GOD_LAYER.md maps onto a subcommand here, so the
UI can be wired to real capability instead of a mock. JSON output everywhere, so
the same commands drive both humans and the scheduler.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config as config_module
from . import soul as soul_module
from .ledger import Ledger
from .permissions import (
    Decision,
    PermissionClassifier,
    PermissionLevel,
    ToolDisabledError,
    UnknownToolError,
    dispatch_plan,
)
from .probe import ProbeError, probe as probe_runtime
from .queue import TaskQueue
from .revenue import (
    Lead,
    RevenueLedger,
    generate_audit,
    generate_outreach_draft,
    score_lead,
)
from .router import HealthTable, ModelRouter


def state_path(name: str) -> Path:
    return config_module.state_dir() / name


def emit(payload: Any) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


# -- soul -----------------------------------------------------------------


def cmd_soul_status(args: argparse.Namespace) -> int:
    soul = soul_module.load(args.file)
    ok, missing = soul_module.verify(soul)
    return emit(
        {
            "path": str(soul.path),
            "loaded": soul.loaded,
            "version": soul.version,
            "sha256": soul.sha256,
            "structure_ok": ok,
            "missing_sections": missing,
            "bytes": len(soul.text),
        }
    )


def cmd_soul_preamble(args: argparse.Namespace) -> int:
    soul = soul_module.load(args.file)
    print(soul_module.preamble(soul, max_chars=args.max_chars))
    return 0


# -- permissions ----------------------------------------------------------


def _classify(args: argparse.Namespace) -> Decision:
    classifier = PermissionClassifier()
    payload = json.loads(args.payload) if args.payload else {}
    return classifier.classify(
        args.tool, args.action, payload, rollback_available=args.rollback
    )


def cmd_permissions_classify(args: argparse.Namespace) -> int:
    try:
        decision = _classify(args)
    except UnknownToolError as error:
        return emit({"error": "unknown_tool", "detail": str(error)}) or 2
    except ToolDisabledError as error:
        return emit({"error": "tool_disabled", "detail": str(error)}) or 2
    payload = decision.to_dict()
    payload["dispatch_plan"] = dispatch_plan(decision)
    return emit(payload)


def cmd_permissions_matrix(_: argparse.Namespace) -> int:
    classifier = PermissionClassifier()
    matrix: dict[str, Any] = {}
    for tool in classifier.known_tools():
        spec = classifier.tool_spec(tool)
        entry: dict[str, Any] = {
            "enabled": spec.get("enabled", False),
            "default": spec.get("permission_default"),
            "health_check": spec.get("health_check", ""),
            "actions": {},
        }
        for key, value in spec.items():
            if key.endswith("_permission"):
                entry["actions"][key[: -len("_permission")]] = value
        entry["actions"].update(spec.get("actions", {}) or {})
        matrix[tool] = entry
    return emit({"version": classifier.registry.get("version", 0), "tools": matrix})


# -- queue ----------------------------------------------------------------


def _queue(args: argparse.Namespace) -> TaskQueue:
    return TaskQueue(args.db or state_path("queue.db"))


def cmd_queue_stats(args: argparse.Namespace) -> int:
    with _queue(args) as queue:
        return emit(
            {
                "counts": queue.stats(),
                "active": queue.active_count(),
                "max_active": queue.max_active,
                "queue_lag_seconds": queue.queue_lag_seconds(),
                "dead_letters": [task.task_id for task in queue.dead_letters()],
            }
        )


def cmd_queue_list(args: argparse.Namespace) -> int:
    with _queue(args) as queue:
        return emit([task.to_dict() for task in queue.list_tasks(args.status)])


def cmd_queue_enqueue(args: argparse.Namespace) -> int:
    with _queue(args) as queue:
        classifier = PermissionClassifier()
        payload = json.loads(args.payload) if args.payload else {}
        decision = classifier.classify(args.tool, args.action, payload)
        task = queue.enqueue(
            args.task_id,
            args.mission_id,
            f"{args.tool}.{args.action}",
            payload=payload,
            priority=args.priority,
            permission=str(decision.permission),
            idempotency_key=decision.idempotency_key,
        )
        return emit({"task": task.to_dict(), "decision": decision.to_dict()})


def cmd_queue_approve(args: argparse.Namespace) -> int:
    with _queue(args) as queue:
        expires = datetime.now(timezone.utc) + timedelta(minutes=args.expires_minutes)
        task = queue.approve(args.task_id, args.approver, expires_at=expires)
        if task is None:
            return emit({"error": "unknown_task", "task_id": args.task_id}) or 2
        return emit({"approved": task.to_dict(), "expires_at": expires.isoformat()})


def cmd_queue_cancel(args: argparse.Namespace) -> int:
    with _queue(args) as queue:
        queue.cancel(args.task_id, args.reason)
        return emit({"cancelled": args.task_id})


def cmd_queue_recover(args: argparse.Namespace) -> int:
    with _queue(args) as queue:
        return emit({"recovered": queue.recover_stale("hermesctl")})


# -- ledger ---------------------------------------------------------------


def _ledger(args: argparse.Namespace) -> Ledger:
    return Ledger(args.db or state_path("missions.db"))


def cmd_ledger_verify(args: argparse.Namespace) -> int:
    with _ledger(args) as ledger:
        ok, detail = ledger.verify_chain()
        emit({"chain_ok": ok, "detail": detail})
        return 0 if ok else 1


def cmd_ledger_events(args: argparse.Namespace) -> int:
    with _ledger(args) as ledger:
        return emit([event.to_dict() for event in ledger.events(args.mission_id)])


# -- models ---------------------------------------------------------------


def cmd_models_health(args: argparse.Namespace) -> int:
    health = HealthTable(args.health_file)
    router = ModelRouter(health=health)
    return emit(
        {
            "providers": health.as_list(),
            "task_classes": {
                task_class: router.chain_for(task_class)
                for task_class in router.routes
            },
        }
    )


def cmd_models_probe(args: argparse.Namespace) -> int:
    """Read the live sandbox route and record it as provider health."""
    health = HealthTable(args.health_file)
    try:
        result = probe_runtime(args.sandbox, health=health)
    except ProbeError as error:
        emit({"error": "probe_failed", "detail": str(error)})
        return 2
    emit(result)
    return 0 if result["health_status"] == "HEALTHY" else 1


def cmd_models_route(args: argparse.Namespace) -> int:
    router = ModelRouter(health=HealthTable(args.health_file))
    decision = router.select(
        args.task_class,
        required_capabilities=args.require or [],
        context_tokens=args.context_tokens,
        private=args.private,
    )
    emit(decision.to_dict())
    return 1 if decision.blocked else 0


# -- revenue --------------------------------------------------------------


def _revenue(args: argparse.Namespace) -> RevenueLedger:
    return RevenueLedger(args.db or state_path("revenue-ledger.db"))


def cmd_revenue_status(args: argparse.Namespace) -> int:
    with _revenue(args) as ledger:
        return emit({"counts": ledger.counts(), "totals": ledger.totals()})


def cmd_revenue_add_lead(args: argparse.Namespace) -> int:
    lead = Lead(
        lead_id=args.lead_id,
        company=args.company,
        contact_name=args.contact_name,
        email=args.email,
        website=args.website,
        industry=args.industry,
        problem=args.problem,
        team_size=args.team_size,
        current_tools=args.tools or [],
        urgency=args.urgency,
        consent=args.consent,
        source=args.source,
    )
    with _revenue(args) as ledger:
        return emit(ledger.add_lead(lead))


def cmd_revenue_audit(args: argparse.Namespace) -> int:
    with _revenue(args) as ledger:
        row = ledger.get_lead(args.lead_id)
        if row is None:
            return emit({"error": "unknown_lead", "lead_id": args.lead_id}) or 2
        lead = Lead(
            lead_id=row["lead_id"],
            company=row["company"],
            contact_name=row["contact_name"],
            email=row["email"],
            website=row["website"],
            industry=row["industry"],
            problem=row["problem"],
            team_size=row["team_size"],
            current_tools=json.loads(row["current_tools"]),
            urgency=row["urgency"],
            consent=bool(row["consent"]),
            source=row["source"],
        )
        score = score_lead(lead)
        body = generate_audit(lead, score, args.finding or [])
        ledger.add_audit(args.audit_id, lead.lead_id, args.track, body, score)
        ledger.set_state(lead.lead_id, "audit_ready")
        subject, draft = generate_outreach_draft(lead, f"Opportunity score: {score}/100")
        ledger.add_draft(args.draft_id, lead.lead_id, "outreach", subject, draft)
        ledger.set_state(lead.lead_id, "draft_ready")
        due = ledger.schedule_followup(args.followup_id, lead.lead_id, args.followup_days)
        return emit(
            {
                "lead_id": lead.lead_id,
                "score": score,
                "audit_id": args.audit_id,
                "draft_id": args.draft_id,
                "followup_due": due,
                "sent": False,
                "note": "draft only; sending is RED and requires scoped OSA approval",
            }
        )


# -- health ---------------------------------------------------------------


def cmd_health(args: argparse.Namespace) -> int:
    """Aggregate readiness. Mirrors /health/* for the API and dashboard."""
    report: dict[str, Any] = {"checks": {}, "status": "ok"}

    try:
        soul = soul_module.load()
        ok, missing = soul_module.verify(soul)
        report["checks"]["soul"] = {
            "ok": ok,
            "version": soul.version,
            "sha256": soul.sha256,
            "missing_sections": missing,
        }
    except FileNotFoundError as error:
        report["checks"]["soul"] = {"ok": False, "detail": str(error)}

    try:
        classifier = PermissionClassifier()
        report["checks"]["tools"] = {
            "ok": True,
            "registered": len(classifier.known_tools()),
            "enabled": classifier.enabled_tools(),
        }
    except Exception as error:  # configuration errors must surface, not crash health
        report["checks"]["tools"] = {"ok": False, "detail": str(error)}

    try:
        router = ModelRouter(health=HealthTable(args.health_file))
        decision = router.select("FALLBACK")
        report["checks"]["models"] = {
            "ok": not decision.blocked,
            "selected": decision.selected,
            "detail": decision.reason,
        }
    except Exception as error:
        report["checks"]["models"] = {"ok": False, "detail": str(error)}

    queue_db = state_path("queue.db")
    if queue_db.exists():
        with TaskQueue(queue_db) as queue:
            report["checks"]["queue"] = {
                "ok": True,
                "counts": queue.stats(),
                "lag_seconds": queue.queue_lag_seconds(),
            }
    else:
        report["checks"]["queue"] = {"ok": True, "detail": "queue not yet initialised"}

    ledger_db = state_path("missions.db")
    if ledger_db.exists():
        with Ledger(ledger_db) as ledger:
            chain_ok, detail = ledger.verify_chain()
            report["checks"]["ledger"] = {"ok": chain_ok, "detail": detail}
    else:
        report["checks"]["ledger"] = {"ok": True, "detail": "ledger not yet initialised"}

    report["status"] = "ok" if all(
        check.get("ok", False) for check in report["checks"].values()
    ) else "degraded"
    emit(report)
    return 0 if report["status"] == "ok" else 1


# -- parser ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermesctl", description="Hermes control plane")
    parser.add_argument("--db", default=None, help="override the store path for this command")
    parser.add_argument(
        "--health-file", default=None, help="model health table path override"
    )
    sub = parser.add_subparsers(dest="group", required=True)

    soul_parser = sub.add_parser("soul", help="constitution").add_subparsers(
        dest="command", required=True
    )
    status = soul_parser.add_parser("status")
    status.add_argument("--file", default=None)
    status.set_defaults(func=cmd_soul_status)
    preamble = soul_parser.add_parser("preamble")
    preamble.add_argument("--file", default=None)
    preamble.add_argument("--max-chars", type=int, default=6000)
    preamble.set_defaults(func=cmd_soul_preamble)

    perm = sub.add_parser("permissions", help="permission engine").add_subparsers(
        dest="command", required=True
    )
    classify = perm.add_parser("classify")
    classify.add_argument("tool")
    classify.add_argument("action")
    classify.add_argument("--payload", default="")
    classify.add_argument("--rollback", action="store_true")
    classify.set_defaults(func=cmd_permissions_classify)
    perm.add_parser("matrix").set_defaults(func=cmd_permissions_matrix)

    queue_parser = sub.add_parser("queue", help="durable task queue").add_subparsers(
        dest="command", required=True
    )
    queue_parser.add_parser("stats").set_defaults(func=cmd_queue_stats)
    listing = queue_parser.add_parser("list")
    listing.add_argument("--status", default=None)
    listing.set_defaults(func=cmd_queue_list)
    enqueue = queue_parser.add_parser("enqueue")
    enqueue.add_argument("task_id")
    enqueue.add_argument("mission_id")
    enqueue.add_argument("tool")
    enqueue.add_argument("action")
    enqueue.add_argument("--payload", default="")
    enqueue.add_argument("--priority", type=int, default=50)
    enqueue.set_defaults(func=cmd_queue_enqueue)
    approve = queue_parser.add_parser("approve")
    approve.add_argument("task_id")
    approve.add_argument("--approver", default="OSA")
    approve.add_argument("--expires-minutes", type=int, default=60)
    approve.set_defaults(func=cmd_queue_approve)
    cancel = queue_parser.add_parser("cancel")
    cancel.add_argument("task_id")
    cancel.add_argument("--reason", default="cancelled by operator")
    cancel.set_defaults(func=cmd_queue_cancel)
    queue_parser.add_parser("recover").set_defaults(func=cmd_queue_recover)

    ledger_parser = sub.add_parser("ledger", help="evidence ledger").add_subparsers(
        dest="command", required=True
    )
    ledger_parser.add_parser("verify").set_defaults(func=cmd_ledger_verify)
    events = ledger_parser.add_parser("events")
    events.add_argument("--mission-id", default=None)
    events.set_defaults(func=cmd_ledger_events)

    models = sub.add_parser("models", help="model router").add_subparsers(
        dest="command", required=True
    )
    models.add_parser("health").set_defaults(func=cmd_models_health)
    probe_parser = models.add_parser("probe")
    probe_parser.add_argument("--sandbox", default=None)
    probe_parser.set_defaults(func=cmd_models_probe)
    route = models.add_parser("route")
    route.add_argument("task_class")
    route.add_argument("--require", action="append")
    route.add_argument("--context-tokens", type=int, default=0)
    route.add_argument("--private", action="store_true")
    route.set_defaults(func=cmd_models_route)

    revenue = sub.add_parser("revenue", help="revenue operations").add_subparsers(
        dest="command", required=True
    )
    revenue.add_parser("status").set_defaults(func=cmd_revenue_status)
    add_lead = revenue.add_parser("add-lead")
    add_lead.add_argument("lead_id")
    add_lead.add_argument("company")
    add_lead.add_argument("--contact-name", default="")
    add_lead.add_argument("--email", default="")
    add_lead.add_argument("--website", default="")
    add_lead.add_argument("--industry", default="")
    add_lead.add_argument("--problem", default="")
    add_lead.add_argument("--team-size", default="")
    add_lead.add_argument("--tools", action="append")
    add_lead.add_argument("--urgency", default="")
    add_lead.add_argument("--consent", action="store_true")
    add_lead.add_argument("--source", default="")
    add_lead.set_defaults(func=cmd_revenue_add_lead)
    audit = revenue.add_parser("audit")
    audit.add_argument("lead_id")
    audit.add_argument("--audit-id", required=True)
    audit.add_argument("--draft-id", required=True)
    audit.add_argument("--followup-id", required=True)
    audit.add_argument("--track", default="TRACK_1_AI_SYSTEM_AUDITS")
    audit.add_argument("--finding", action="append")
    audit.add_argument("--followup-days", type=int, default=4)
    audit.set_defaults(func=cmd_revenue_audit)

    health = sub.add_parser("health", help="aggregate health")
    health.set_defaults(func=cmd_health, command="health")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

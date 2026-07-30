"""Hermes God-Layer control plane.

Modules:
    config       configuration loading (tools, models, schedule)
    permissions  GREEN/YELLOW/RED classifier and dispatch plan
    ledger       mission state machine and hash-chained evidence ledger
    queue        durable SQLite task queue with recovery and dead letters
    router       capability-aware model routing with fallback
    revenue      leads, audits, drafts, follow-ups and the revenue ledger
    redact       shared secret redaction
    soul         constitution loading and identity
"""

__all__ = [
    "config",
    "permissions",
    "ledger",
    "queue",
    "router",
    "revenue",
    "redact",
    "soul",
]

VERSION = "1.0.0"

"""Hydra World — minimal observed-state kernel.

Hydra World is not a control plane. It stores observations and exposes
read-only snapshots back to Hydra Laboratory.
"""

from .kernel import (
    KERNEL_ID,
    SCHEMA_VERSION,
    WorldKernel,
    WorldObservation,
    WorldSnapshot,
)

__all__ = [
    "KERNEL_ID",
    "SCHEMA_VERSION",
    "WorldKernel",
    "WorldObservation",
    "WorldSnapshot",
]

"""The incremental-compile digest: a topic recompiles only when its inputs change."""

from __future__ import annotations

import hashlib
import json

# Bump to force a global recompile when the compile prompt/render logic changes.
COMPILER_VERSION = 1


def compute_compile_digest(
    *,
    source_hashes: list[str],
    finding_ids: list[int],
    feedback_ids: list[int],
    model: str,
) -> str:
    """Return a stable sha256 digest over a topic's compile inputs.

    Order-independent (inputs are sorted). Any change to the contributing raw
    sources, findings, relevant feedback, the model, or ``COMPILER_VERSION``
    produces a different digest, which is what triggers a recompile.
    """
    payload = json.dumps(
        {
            "sources": sorted(source_hashes),
            "findings": sorted(finding_ids),
            "feedback": sorted(feedback_ids),
            "model": model,
            "compiler_version": COMPILER_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

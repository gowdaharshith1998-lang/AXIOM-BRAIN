from __future__ import annotations

import hashlib
from datetime import datetime


SIGNING_SCHEMES = ("ed25519", "ml_dsa_65", "hybrid")


def demo_receipt(
    *,
    action_id: str,
    decision: str,
    agent_name: str,
    index: int,
) -> dict[str, object]:
    seed = f"{action_id}:{decision}:{agent_name}:{index}".encode()
    receipt_id = hashlib.sha256(seed).hexdigest()
    root_seed = f"root:{index // 10}:{receipt_id}".encode()
    merkle_root = hashlib.sha256(root_seed).hexdigest()
    signing_scheme = SIGNING_SCHEMES[index % len(SIGNING_SCHEMES)]
    return {
        "receipt_id": receipt_id,
        "action_id": action_id,
        "decision": decision,
        "agent_name": agent_name,
        "signing_scheme": signing_scheme,
        "merkle_root": merkle_root,
        "timestamp": datetime.utcnow().isoformat(),
        "demo": True,
    }

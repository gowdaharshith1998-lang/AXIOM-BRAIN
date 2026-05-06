from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

SigningScheme = Literal["ed25519+ml-dsa-65"]


@dataclass(frozen=True, slots=True)
class SignedPayload:
    signing_scheme: SigningScheme
    payload: dict[str, Any]
    signature_ed25519_b64: str
    signature_mldsa_b64: str
    merkle_leaf_index: int | None = None


class Signer(ABC):
    @abstractmethod
    def sign(
        self,
        payload: dict[str, Any],
        *,
        scheme: SigningScheme = "ed25519+ml-dsa-65",
    ) -> SignedPayload:
        raise NotImplementedError("Signer.sign is stubbed; lands in Phase 10")

    @abstractmethod
    def verify(self, signed: SignedPayload) -> bool:
        raise NotImplementedError("Signer.verify is stubbed; lands in Phase 10")


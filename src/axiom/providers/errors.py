"""Provider registry errors."""

from __future__ import annotations


class UnknownProvider(LookupError):  # noqa: N818 — public API name from Phase 5.13.1 spec
    """Raised when ``provider_id`` is not in the registry."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"unknown provider_id={provider_id!r}")

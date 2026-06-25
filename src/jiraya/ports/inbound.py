"""Inbound ports — the use cases the application offers to driving adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import Ticket, TriageMetrics, TriageOutcome


@runtime_checkable
class TriageService(Protocol):
    """The core use case: triage tickets and report what happened."""

    def triage_ticket(self, ticket: Ticket) -> TriageOutcome: ...

    def triage_batch(self, tickets: list[Ticket]) -> list[TriageOutcome]: ...

    @property
    def metrics(self) -> TriageMetrics: ...

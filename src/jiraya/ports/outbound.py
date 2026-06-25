"""Outbound ports — interfaces the application needs the outside world to fill.

Adapters (in-memory fakes, real Jira, the Copilot CLI, etc.) implement these
``Protocol`` classes. The application depends only on these abstractions.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from ..domain import (
    Classification,
    DomainEvent,
    InboxEntry,
    Ticket,
    TicketCategory,
    TicketStatus,
    ValidationResult,
)


@runtime_checkable
class TicketSource(Protocol):
    """A source of tickets to triage (the Jira side of the world)."""

    def fetch_untriaged(self) -> list[Ticket]:
        """Return tickets currently awaiting triage (Untriaged / To Do)."""

    def transition(self, key: str, status: TicketStatus) -> Ticket:
        """Move a ticket to ``status`` and return the updated ticket."""

    def get(self, key: str) -> Ticket | None:
        """Look up a single ticket by key."""


@runtime_checkable
class Classifier(Protocol):
    """Intent classification — turns a ticket into a :class:`Classification`."""

    def classify(self, ticket: Ticket) -> Classification: ...


@runtime_checkable
class WorkerAgent(Protocol):
    """A specialized agent that validates and works a category of ticket."""

    name: str

    def handles(self, category: TicketCategory) -> bool: ...

    def validate(self, ticket: Ticket, classification: Classification) -> ValidationResult: ...


@runtime_checkable
class InboxRepository(Protocol):
    """Persistence for exceptions surfaced to the dashboard for human review."""

    def add(self, entry: InboxEntry) -> None: ...

    def all(self) -> list[InboxEntry]: ...

    def open_entries(self) -> list[InboxEntry]: ...

    def resolve(self, entry_id: str, resolution: str) -> InboxEntry | None: ...


# An event handler receives a single domain event. Handlers must be cheap or
# marshal heavy work elsewhere; adapters own their own thread-safety.
EventHandler = Callable[[DomainEvent], None]


@runtime_checkable
class EventPublisher(Protocol):
    """Publish side of the event bus (what the application is allowed to do)."""

    def publish(self, event: DomainEvent) -> None: ...


@runtime_checkable
class EventBus(EventPublisher, Protocol):
    """Full event bus: publish plus subscribe (used by inbound adapters)."""

    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        """Register ``handler``; returns a callable that unsubscribes it."""


@runtime_checkable
class Clock(Protocol):
    """Injectable time source so the harness is deterministically testable."""

    def now(self): ...

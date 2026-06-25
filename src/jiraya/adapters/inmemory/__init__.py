"""In-memory adapters — default, offline-capable implementations."""

from __future__ import annotations

from .event_bus import InMemoryEventBus
from .inbox_repo import InMemoryInboxRepository
from .seed import random_ticket, sample_tickets
from .ticket_source import InMemoryTicketSource

__all__ = [
    "InMemoryEventBus",
    "InMemoryInboxRepository",
    "InMemoryTicketSource",
    "random_ticket",
    "sample_tickets",
]

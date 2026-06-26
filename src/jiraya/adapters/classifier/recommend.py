"""Model-recommendation policy.

The classifier recommends which model the *work agent* should use for a ticket
when no work model is explicitly configured. The recommendation is a tiered
heuristic by category and complexity. These are sensible defaults — override the
tier constants (or pass an explicit ``--work-model``) for your environment.
"""

from __future__ import annotations

from ...domain import Ticket, TicketCategory

# Tiers (Copilot CLI model names; "auto" lets Copilot choose).
FAST_MODEL = "gpt-5-mini"          # cheap/fast — small, well-scoped changes
STANDARD_MODEL = "claude-sonnet-4.5"  # general coding work
DEEP_MODEL = "claude-opus-4.5"     # gnarly bugs / large features
AUTO_MODEL = "auto"                # let Copilot decide

_COMPLEXITY_SIGNALS = (
    "stack trace", "traceback", "exception", "race condition", "deadlock",
    "regression", "segfault", "memory leak", "performance", "scalab",
)


def _is_complex(ticket: Ticket) -> bool:
    text = f"{ticket.summary}\n{ticket.description}".lower()
    if any(s in text for s in _COMPLEXITY_SIGNALS):
        return True
    return len(ticket.description.strip()) >= 600


def recommend_model(category: TicketCategory, ticket: Ticket) -> str:
    """Recommend a work model for a classified ticket."""
    if category is TicketCategory.UNKNOWN:
        return AUTO_MODEL
    if category is TicketCategory.DOCUMENTATION:
        return FAST_MODEL
    # Bugs and feature requests: go deep when the ticket looks complex.
    return DEEP_MODEL if _is_complex(ticket) else STANDARD_MODEL

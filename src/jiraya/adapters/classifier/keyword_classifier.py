"""A deterministic, dependency-free intent classifier.

Used as jiraya's default classifier so the harness runs fully offline and so
tests are reproducible. The Copilot CLI classifier (``copilot_classifier``) is
the production drop-in that implements the same port.
"""

from __future__ import annotations

from ...domain import Classification, Ticket, TicketCategory
from ...ports import Classifier

_SIGNALS: dict[TicketCategory, tuple[str, ...]] = {
    TicketCategory.BUG: (
        "bug", "error", "crash", "exception", "fails", "failing", "broken",
        "not working", "doesn't work", "stack trace", "traceback", "500",
        "npe", "nullpointer", "regression", "throws",
    ),
    TicketCategory.FEATURE_REQUEST: (
        "feature", "add ", "support for", "would be nice", "enhancement",
        "implement", "ability to", "please add", "request", "nice to have",
        "new ", "allow",
    ),
    TicketCategory.DOCUMENTATION: (
        "docs", "documentation", "readme", "typo", "clarify", "example",
        "tutorial", "guide", "comment", "wording", "explain",
    ),
}

_LABEL_CATEGORY: dict[str, TicketCategory] = {
    "bug": TicketCategory.BUG,
    "defect": TicketCategory.BUG,
    "feature": TicketCategory.FEATURE_REQUEST,
    "enhancement": TicketCategory.FEATURE_REQUEST,
    "documentation": TicketCategory.DOCUMENTATION,
    "docs": TicketCategory.DOCUMENTATION,
}


class KeywordClassifier(Classifier):
    """Scores tickets against per-category keyword and label signals."""

    source_name = "keyword"

    def classify(self, ticket: Ticket) -> Classification:
        haystack = f"{ticket.summary}\n{ticket.description}".lower()
        scores: dict[TicketCategory, int] = {c: 0 for c in _SIGNALS}

        for category, signals in _SIGNALS.items():
            scores[category] += sum(1 for s in signals if s in haystack)

        for label in ticket.labels:
            mapped = _LABEL_CATEGORY.get(label.lower())
            if mapped is not None:
                scores[mapped] += 2  # explicit labels weigh more than prose

        best = max(scores, key=lambda c: scores[c])
        best_score = scores[best]
        if best_score == 0:
            return Classification(
                category=TicketCategory.UNKNOWN,
                target_project=ticket.project,
                confidence=0.2,
                rationale="No category signals found in summary or description.",
                source=self.source_name,
            )

        runner_up = max((scores[c] for c in scores if c != best), default=0)
        confidence = min(0.93, 0.55 + 0.13 * best_score)
        if best_score - runner_up <= 0:  # ambiguous tie between categories
            confidence *= 0.7

        return Classification(
            category=best,
            target_project=ticket.project,
            confidence=round(confidence, 2),
            rationale=f"Matched {best_score} '{best}' signal(s) in the ticket text.",
            source=self.source_name,
        )

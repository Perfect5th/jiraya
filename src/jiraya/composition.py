"""Composition root — the one place where concrete adapters are wired together.

Everything above this module depends only on ports; this module is allowed to
know about concrete classes. Driving adapters (CLI, TUI) ask :func:`build_system`
for a fully assembled :class:`JirayaSystem` and stay ignorant of the wiring.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .adapters.agents import default_agents
from .adapters.classifier import CopilotCliClassifier, KeywordClassifier
from .adapters.inmemory import (
    InMemoryEventBus,
    InMemoryInboxRepository,
    InMemoryTicketSource,
)
from .adapters.jira import JiraRestTicketSource
from .application import AgentRouter, TriagePoller, TriageService
from .ports import Classifier, EventBus, InboxRepository, TicketSource


@dataclass(slots=True)
class JirayaConfig:
    """User-facing configuration for assembling the system."""

    classifier: str = "keyword"      # "keyword" | "copilot"
    source: str = "memory"           # "memory" | "jira"
    interval_seconds: float = 1800.0
    confidence_threshold: float = 0.6
    copilot_model: str | None = None
    copilot_fallback_to_keyword: bool = False
    jira: "JiraConfig" = field(default_factory=lambda: JiraConfig())


@dataclass(slots=True)
class JiraConfig:
    """Connection settings for the real Jira adapter (read from env by default)."""

    base_url: str = ""
    email: str = ""
    api_token: str = ""
    jql: str = 'status in ("To Do", "Untriaged") ORDER BY created ASC'

    @classmethod
    def from_env(cls) -> "JiraConfig":
        return cls(
            base_url=os.environ.get("JIRA_BASE_URL", ""),
            email=os.environ.get("JIRA_EMAIL", ""),
            api_token=os.environ.get("JIRA_API_TOKEN", ""),
            jql=os.environ.get(
                "JIRA_JQL", 'status in ("To Do", "Untriaged") ORDER BY created ASC'
            ),
        )


@dataclass(slots=True)
class JirayaSystem:
    """A fully assembled, ready-to-run jiraya instance."""

    bus: EventBus
    source: TicketSource
    inbox: InboxRepository
    router: AgentRouter
    service: TriageService
    poller: TriagePoller


def build_classifier(config: JirayaConfig) -> Classifier:
    if config.classifier == "copilot":
        fallback = KeywordClassifier() if config.copilot_fallback_to_keyword else None
        return CopilotCliClassifier(model=config.copilot_model, fallback=fallback)
    if config.classifier == "keyword":
        return KeywordClassifier()
    raise ValueError(f"Unknown classifier: {config.classifier!r}")


def build_source(config: JirayaConfig) -> TicketSource:
    if config.source == "memory":
        return InMemoryTicketSource()
    if config.source == "jira":
        jira = config.jira
        if not jira.base_url:
            raise ValueError(
                "Jira source selected but JIRA_BASE_URL is not configured."
            )
        return JiraRestTicketSource(
            base_url=jira.base_url,
            email=jira.email or None,
            api_token=jira.api_token or None,
            jql=jira.jql,
        )
    raise ValueError(f"Unknown source: {config.source!r}")


def build_system(config: JirayaConfig | None = None) -> JirayaSystem:
    """Assemble every component for the given configuration."""
    config = config or JirayaConfig()

    bus = InMemoryEventBus()
    source = build_source(config)
    inbox = InMemoryInboxRepository()
    classifier = build_classifier(config)
    router = AgentRouter(default_agents())

    service = TriageService(
        ticket_source=source,
        classifier=classifier,
        router=router,
        inbox=inbox,
        events=bus,
        confidence_threshold=config.confidence_threshold,
    )
    poller = TriagePoller(
        ticket_source=source,
        service=service,
        events=bus,
        interval_seconds=config.interval_seconds,
    )
    return JirayaSystem(
        bus=bus,
        source=source,
        inbox=inbox,
        router=router,
        service=service,
        poller=poller,
    )

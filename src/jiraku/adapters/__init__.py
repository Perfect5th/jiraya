"""jiraku adapters — concrete implementations of the ports."""

from __future__ import annotations

from .readonly import ReadOnlyTicketSource
from .work_runner import (
    CopilotWorkAgentRunner,
    GeminiWorkAgentRunner,
    OpencodeWorkAgentRunner,
    NoopWorkAgentRunner,
)

__all__ = [
    "ReadOnlyTicketSource",
    "CopilotWorkAgentRunner",
    "GeminiWorkAgentRunner",
    "OpencodeWorkAgentRunner",
    "NoopWorkAgentRunner",
]

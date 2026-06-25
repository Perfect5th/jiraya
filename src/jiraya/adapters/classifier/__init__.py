"""Classifier adapters."""

from __future__ import annotations

from .copilot_classifier import CopilotCliClassifier, CopilotUnavailableError
from .keyword_classifier import KeywordClassifier

__all__ = ["CopilotCliClassifier", "CopilotUnavailableError", "KeywordClassifier"]

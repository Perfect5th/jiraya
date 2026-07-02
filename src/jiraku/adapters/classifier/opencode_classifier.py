"""Production classifier that delegates intent classification to opencode.

A drop-in :class:`Classifier` selected at the composition root, mirroring the
Copilot and Gemini classifiers but invoking ``opencode run`` instead. The
prompt/parse/fallback machinery is shared in :mod:`._llm_cli`; this module only
fixes the opencode-specific command, model tiers and error type.

opencode takes the prompt as a positional argument (``opencode run <prompt>``)
rather than via ``-p`` (which is opencode's ``--password``), so ``prompt_flag``
is ``None``. Classification needs no write access, so it runs opencode's
read-only ``plan`` agent — tool calls can never modify the workspace while
merely classifying.
"""

from __future__ import annotations

from .recommend import OPENCODE_TIERS
from ._llm_cli import LlmCliClassifier, LlmUnavailableError


class OpencodeUnavailableError(LlmUnavailableError):
    """Raised when opencode cannot be reached and no fallback is set."""


class OpencodeCliClassifier(LlmCliClassifier):
    """Classifies tickets by prompting opencode for JSON."""

    source_name = "opencode-cli"
    default_command = ["opencode", "run", "--agent", "plan"]
    model_tiers = OPENCODE_TIERS
    error_cls = OpencodeUnavailableError
    prompt_flag = None  # opencode takes the prompt as a positional argument

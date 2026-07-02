from __future__ import annotations

from unittest import mock

import pytest

from jiraku.adapters import (
    CopilotWorkAgentRunner,
    NoopWorkAgentRunner,
    OpencodeWorkAgentRunner,
)
from jiraku.adapters.classifier import (
    KeywordClassifier,
    OpencodeCliClassifier,
    OpencodeUnavailableError,
    recommend_model,
)
from jiraku.adapters.classifier.recommend import OPENCODE_TIERS
from jiraku.composition import JirakuConfig, build_system
from jiraku.domain import (
    Classification,
    Priority,
    RepoRef,
    RepoResolution,
    Ticket,
    TicketCategory,
)


def _ticket(summary="Add export", description="please add CSV export", labels=()):
    return Ticket(key="X-1", project="X", summary=summary, description=description,
                  reporter="r", priority=Priority.MEDIUM, labels=tuple(labels))


def _cls(**kw):
    return Classification(TicketCategory.BUG, "PROJ", 0.9, **kw)


def _res():
    return RepoResolution(RepoRef("acme/proj", "https://github.com/acme/proj.git"), 0.95)


# -- recommendation tiers ----------------------------------------------------

def test_opencode_tiers_use_provider_model_format():
    docs = _ticket("Fix typo", "typo in the readme docs page")
    assert recommend_model(TicketCategory.DOCUMENTATION, docs, OPENCODE_TIERS) == \
        "github-copilot/gpt-5-mini"
    # opencode's "auto" is empty: omit the model flag and use the CLI default.
    assert recommend_model(TicketCategory.UNKNOWN, docs, OPENCODE_TIERS) == ""
    simple = _ticket("button color", "the button is the wrong colour")
    assert recommend_model(TicketCategory.BUG, simple, OPENCODE_TIERS) == \
        "github-copilot/claude-sonnet-4.5"
    complex_bug = _ticket("Crash", "NullPointerException with a stack trace " + "x" * 50)
    assert recommend_model(TicketCategory.BUG, complex_bug, OPENCODE_TIERS) == \
        "github-copilot/claude-opus-4.5"


# -- opencode classifier -----------------------------------------------------

def test_opencode_classifier_default_command_is_read_only_plan_agent():
    # Classification needs no writes, so it runs opencode's read-only plan agent.
    assert OpencodeCliClassifier()._command == ["opencode", "run", "--agent", "plan"]


def test_opencode_classifier_passes_prompt_positionally_not_dash_p():
    # In opencode, `-p` is `--password`; the prompt is a positional argument.
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        result = mock.Mock()
        result.stdout = '{"category": "Bug", "confidence": 0.8}'
        return result

    with mock.patch("shutil.which", return_value="/bin/opencode"), \
            mock.patch("subprocess.run", side_effect=fake_run):
        OpencodeCliClassifier(model="github-copilot/gpt-5-mini").classify(_ticket("x"))

    argv = captured["argv"]
    assert argv[:4] == ["opencode", "run", "--agent", "plan"]
    assert "--model" in argv and "github-copilot/gpt-5-mini" in argv
    assert "-p" not in argv          # opencode must not receive -p
    assert argv[-1].startswith("You are a Jira triage classifier")  # positional prompt


def test_opencode_classifier_parses_runner_output():
    def fake_runner(prompt: str) -> str:
        assert "Jira triage classifier" in prompt
        # opencode prefixes a header line before the JSON; the parser tolerates it.
        return '> plan · claude\n{"category": "Feature Request", "project": "WEB", "confidence": 0.91}'

    c = OpencodeCliClassifier(runner=fake_runner).classify(_ticket("Add export"))
    assert c.category is TicketCategory.FEATURE_REQUEST
    assert c.target_project == "WEB"
    assert c.confidence == 0.91
    assert c.source == "opencode-cli"


def test_opencode_classifier_includes_hint_in_prompt():
    seen = {}

    def runner(prompt: str) -> str:
        seen["prompt"] = prompt
        return '{"category": "Bug", "confidence": 0.9}'

    OpencodeCliClassifier(runner=runner).classify(_ticket("x", "y"), hint="treat as a bug")
    assert "treat as a bug" in seen["prompt"]
    assert "reviewer hint" in seen["prompt"].lower()


def test_opencode_classifier_falls_back_to_opencode_tiers():
    def runner(prompt: str) -> str:
        return '{"category": "Documentation", "confidence": 0.9}'  # no recommended_model

    c = OpencodeCliClassifier(runner=runner).classify(_ticket("typo", "fix the docs typo"))
    assert c.recommended_model == "github-copilot/gpt-5-mini"  # opencode docs tier


def test_opencode_classifier_raises_without_fallback():
    def boom(prompt: str) -> str:
        raise OpencodeUnavailableError("cli missing")

    with pytest.raises(OpencodeUnavailableError):
        OpencodeCliClassifier(runner=boom).classify(_ticket("x"))


def test_opencode_classifier_uses_explicit_fallback():
    def boom(prompt: str) -> str:
        raise OpencodeUnavailableError("cli missing")

    c = OpencodeCliClassifier(runner=boom, fallback=KeywordClassifier())
    result = c.classify(_ticket("App crash", "exception stack trace", ("bug",)))
    assert result.category is TicketCategory.BUG
    assert result.source == "keyword"  # fell back deterministically


# -- opencode work runner ----------------------------------------------------

def test_opencode_runner_default_command_skips_permissions():
    assert OpencodeWorkAgentRunner()._command == \
        ["opencode", "run", "--dangerously-skip-permissions"]


def test_opencode_runner_skips_without_workspace():
    r = OpencodeWorkAgentRunner(runner=lambda p, c, m: "PR_URL: https://x/pull/1")
    out = r.run(_ticket(), _cls(), _res(), "")
    assert out.started is False
    assert "workspace" in out.summary.lower()


def test_opencode_runner_passes_prompt_positionally_not_dash_p(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        result = mock.Mock()
        result.stdout = "PR_URL: https://x/pull/1"
        return result

    with mock.patch("shutil.which", return_value="/bin/opencode"), \
            mock.patch("subprocess.run", side_effect=fake_run):
        OpencodeWorkAgentRunner(model="github-copilot/claude-opus-4.5").run(
            _ticket(), _cls(), _res(), str(ws))

    argv = captured["argv"]
    assert argv[:3] == ["opencode", "run", "--dangerously-skip-permissions"]
    assert "--model" in argv and "github-copilot/claude-opus-4.5" in argv
    assert "-p" not in argv
    assert argv[-1].startswith("You are an autonomous software engineer")


def test_opencode_runner_omits_model_by_default(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()
    seen = {}

    def fake(prompt, cwd, model):
        seen["model"] = model
        seen["cwd"] = cwd
        return "done\nPR_URL: https://github.com/acme/proj/pull/7\n"

    out = OpencodeWorkAgentRunner(runner=fake).run(_ticket(), _cls(), _res(), str(ws))
    assert out.started is True and out.opened_pr
    assert out.pr_url == "https://github.com/acme/proj/pull/7"
    assert out.branch == "jiraku/x-1"
    assert seen["cwd"] == str(ws)
    # No explicit model and no recommendation -> empty (CLI default), shown as "default".
    assert seen["model"] == ""
    assert out.model == "default"


def test_opencode_runner_uses_recommended_model(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()
    seen = {}

    def fake(prompt, cwd, model):
        seen["model"] = model
        return "PR_URL: https://x/pull/1"

    cls = _cls(recommended_model="github-copilot/claude-opus-4.5")
    out = OpencodeWorkAgentRunner(runner=fake).run(_ticket(), cls, _res(), str(ws))
    assert seen["model"] == "github-copilot/claude-opus-4.5"
    assert out.model == "github-copilot/claude-opus-4.5"


def test_opencode_runner_explicit_model_overrides_recommendation(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()
    seen = {}

    def fake(prompt, cwd, model):
        seen["model"] = model
        return "PR_URL: https://x/pull/1"

    cls = _cls(recommended_model="github-copilot/claude-opus-4.5")
    out = OpencodeWorkAgentRunner(runner=fake, model="github-copilot/gpt-5-mini").run(
        _ticket(), cls, _res(), str(ws))
    assert seen["model"] == "github-copilot/gpt-5-mini"  # explicit wins
    assert out.model == "github-copilot/gpt-5-mini"


def test_opencode_runner_surfaces_needs_input(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()

    def fake(prompt, cwd, model):
        return "NEEDS_INPUT: which database should I target?"

    out = OpencodeWorkAgentRunner(runner=fake).run(_ticket(), _cls(), _res(), str(ws))
    assert out.started is False
    assert out.needs_input
    assert out.question == "which database should I target?"


def test_opencode_runner_handles_failure_gracefully(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()

    def boom(prompt, cwd, model):
        raise RuntimeError("opencode exploded")

    out = OpencodeWorkAgentRunner(runner=boom).run(_ticket(), _cls(), _res(), str(ws))
    assert out.started is False
    assert "exploded" in out.summary


def test_opencode_runner_normalizes_bare_recommended_model(tmp_path):
    # A classifier may recommend a bare model name; opencode needs provider/model,
    # so the runner prefixes the default provider (github-copilot).
    ws = tmp_path / "PROJ-1"
    ws.mkdir()
    seen = {}

    def fake(prompt, cwd, model):
        seen["model"] = model
        return "PR_URL: https://x/pull/1"

    cls = _cls(recommended_model="claude-sonnet-4.6")  # bare, no provider prefix
    out = OpencodeWorkAgentRunner(runner=fake).run(_ticket(), cls, _res(), str(ws))
    assert seen["model"] == "github-copilot/claude-sonnet-4.6"
    assert out.model == "github-copilot/claude-sonnet-4.6"


def test_opencode_runner_leaves_prefixed_model_untouched(tmp_path):
    ws = tmp_path / "PROJ-1"
    ws.mkdir()
    seen = {}

    def fake(prompt, cwd, model):
        seen["model"] = model
        return "PR_URL: https://x/pull/1"

    cls = _cls(recommended_model="anthropic/claude-sonnet-4.6")  # already provider/model
    OpencodeWorkAgentRunner(runner=fake).run(_ticket(), cls, _res(), str(ws))
    assert seen["model"] == "anthropic/claude-sonnet-4.6"  # provider preserved


# -- composition selection ---------------------------------------------------

def test_composition_opencode_classifier_selected():
    system = build_system(JirakuConfig(source="memory", classifier="opencode"))
    assert type(system.service._classifier).__name__ == "OpencodeCliClassifier"


def test_composition_opencode_classifier_fallback_to_keyword():
    system = build_system(JirakuConfig(
        source="memory", classifier="opencode", copilot_fallback_to_keyword=True))
    assert isinstance(system.service._classifier._fallback, KeywordClassifier)


def test_composition_opencode_work_runner_selected():
    system = build_system(JirakuConfig(source="memory", work=True, work_agent="opencode"))
    assert isinstance(system.work_runner, OpencodeWorkAgentRunner)


def test_composition_default_work_agent_is_copilot():
    system = build_system(JirakuConfig(source="memory", work=True))
    assert isinstance(system.work_runner, CopilotWorkAgentRunner)


def test_composition_opencode_work_model_passed_to_runner():
    system = build_system(JirakuConfig(
        source="memory", work=True, work_agent="opencode",
        work_model="github-copilot/claude-opus-4.5"))
    assert system.work_runner._model == "github-copilot/claude-opus-4.5"


def test_composition_no_work_runner_when_work_off():
    system = build_system(JirakuConfig(source="memory", work_agent="opencode"))
    assert isinstance(system.work_runner, NoopWorkAgentRunner)

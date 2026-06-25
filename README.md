# jiraya — agent-powered Jira triage

An automated triage system that polls Jira for new / untriaged tickets,
classifies their intent with an LLM agent, hands them off to specialized worker
agents, and either transitions them to **In Progress** or surfaces them to a
**TUI dashboard** for human review.

This repository contains the **triage agent harness** and the **TUI dashboard**.

## Architecture

jiraya uses a **hexagonal (ports & adapters)** architecture so the business
logic is fully decoupled from Jira, the LLM, and the front-end:

```
            ┌──────────────────────── driving adapters ────────────────────────┐
            │   TUI dashboard (Textual)            CLI (jiraya run / tui)       │
            └───────────────┬───────────────────────────────┬──────────────────┘
                            │ subscribe (events)             │ use cases
                    ┌───────▼───────────────────────────────▼───────┐
                    │                 application                    │
                    │   TriageService · AgentRouter · TriagePoller   │   ← the harness
                    └───────┬───────────────────────────────┬───────┘
                            │ ports (Protocols)              │
   ┌────────────────────────▼──────┐               ┌─────────▼───────────────────┐
   │  TicketSource                 │               │  Classifier                 │
   │   • InMemory (seed/offline)   │               │   • Keyword (deterministic) │
   │   • JiraRest (httpx)          │               │   • CopilotCli (LLM)        │
   ├───────────────────────────────┤               ├─────────────────────────────┤
   │  WorkerAgent: Bug / Feature / Documentation    │  InboxRepository · EventBus │
   └────────────────────────────────────────────────┴─────────────────────────────┘
                              driven adapters
```

- **`domain/`** — pure entities (`Ticket`, `Classification`, `InboxEntry`,
  `TriageMetrics`, …) and domain events. No external dependencies.
- **`ports/`** — inbound (`TriageService`) and outbound (`TicketSource`,
  `Classifier`, `WorkerAgent`, `InboxRepository`, `EventBus`) protocols.
- **`application/`** — the harness: `TriageService` (classify → route → validate
  → transition / escalate), `AgentRouter`, and the scheduled `TriagePoller`.
- **`adapters/`** — `inmemory` (default, offline), `jira` (real REST API),
  `classifier` (keyword + Copilot CLI), `agents` (worker agents).
- **`tui/`** — the Textual dashboard (a driving adapter).
- **`composition.py`** — the composition root that wires everything together.

## Workflow

1. **Poll** — `TriagePoller` fetches `Untriaged` / `To Do` tickets on an interval.
2. **Classify** — the `Classifier` agent labels each ticket (Bug / Feature
   Request / Documentation / Unknown) with a confidence score.
3. **Route & validate** — `AgentRouter` hands the ticket to the matching worker
   agent, which performs initial validation (is the bug reproducible? is the
   feature a duplicate?).
4. **Transition or escalate** — actionable tickets are moved to **In Progress**;
   low-confidence or ambiguous tickets are surfaced to the dashboard inbox.

## Install

Requires [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Run

Launch the real-time dashboard (default command):

```bash
uv run jiraya            # or: uv run jiraya tui
```

Dashboard keys: `p` poll now · `g` inject a demo ticket · `r` resolve the
selected inbox item · `q` quit.

> The interactive TUI needs a real terminal. In CI / headless contexts use
> `jiraya run` (below) or drive the app via Textual's `run_test()` pilot.

Run the harness headlessly:

```bash
uv run jiraya run --once          # one poll cycle, print a summary
uv run jiraya run --cycles 3      # three cycles then exit
uv run jiraya run                 # poll forever (Ctrl-C to stop)
```

### Classifier and source selection

```bash
# Use the GitHub Copilot CLI as the classification agent
uv run jiraya run --once --classifier copilot

# Fall back to the deterministic keyword classifier if Copilot is unavailable
uv run jiraya run --once --classifier copilot --copilot-fallback

# Point at a real Jira instance
export JIRA_BASE_URL="https://your-org.atlassian.net"
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="…"
uv run jiraya tui --source jira --classifier copilot
```

By default jiraya runs fully offline against an in-memory Jira seeded with a
representative batch of tickets, so it is runnable with zero configuration.

## Test

```bash
uv run pytest
```

The suite covers the domain, the harness, every adapter (including the Jira
REST adapter via `httpx.MockTransport` and the Copilot classifier via an
injected runner), and the TUI via Textual's headless pilot.

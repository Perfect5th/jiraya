"""Command-line entry point for jiraya."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .composition import JiraConfig, JirayaConfig, build_system
from .domain import (
    ActivityLevel,
    ActivityLogged,
    DomainEvent,
    PollCycleCompleted,
    TriageAction,
)

_LEVEL_COLOR = {
    ActivityLevel.INFO: "\033[90m",
    ActivityLevel.SUCCESS: "\033[32m",
    ActivityLevel.WARNING: "\033[33m",
    ActivityLevel.ERROR: "\033[31m",
}
_RESET = "\033[0m"


def _config_from_args(args: argparse.Namespace) -> JirayaConfig:
    return JirayaConfig(
        classifier=args.classifier,
        source=args.source,
        interval_seconds=args.interval,
        copilot_model=args.copilot_model,
        copilot_fallback_to_keyword=args.copilot_fallback,
        jira=JiraConfig.from_env(),
    )


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--classifier", choices=["keyword", "copilot"],
                        default="keyword", help="Intent classifier to use.")
    parser.add_argument("--source", choices=["memory", "jira"], default="memory",
                        help="Ticket source (in-memory fake or real Jira).")
    parser.add_argument("--interval", type=float, default=1800.0,
                        help="Seconds between poll cycles.")
    parser.add_argument("--copilot-model", default=None,
                        help="Model for the Copilot CLI classifier.")
    parser.add_argument("--copilot-fallback", action="store_true",
                        help="Fall back to the keyword classifier if Copilot fails.")


def _make_console_printer(color: bool):
    def printer(event: DomainEvent) -> None:
        if isinstance(event, ActivityLogged) and event.activity is not None:
            a = event.activity
            if color:
                c = _LEVEL_COLOR[a.level]
                print(f"{c}[{a.level}]{_RESET} {a.agent} · {a.ticket_key}: {a.message}")
            else:
                print(f"[{a.level}] {a.agent} · {a.ticket_key}: {a.message}")
        elif isinstance(event, PollCycleCompleted):
            print(f"--- poll cycle #{event.cycle} complete: "
                  f"{event.processed} ticket(s) processed ---")
    return printer


def _print_summary(system) -> None:
    m = system.service.metrics
    print()
    print("Triage summary")
    print(f"  processed    : {m.processed}")
    print(f"  transitioned : {m.transitioned}")
    print(f"  escalated    : {m.escalated}")
    print(f"  automation   : {m.automation_rate * 100:.0f}%")
    by_cat = ", ".join(f"{k}={v}" for k, v in m.by_category.items()) or "none"
    print(f"  by category  : {by_cat}")
    open_inbox = system.inbox.open_entries()
    if open_inbox:
        print(f"\nInbox — {len(open_inbox)} item(s) need human review:")
        for e in open_inbox:
            print(f"  • {e.ticket_key} [{e.category}] {e.reason}")


def cmd_run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    system = build_system(config)
    color = sys.stdout.isatty() and not args.no_color
    system.bus.subscribe(_make_console_printer(color))

    async def _drive() -> None:
        if args.once:
            await system.poller.run_once()
        else:
            await system.poller.run_forever(max_cycles=args.cycles)

    try:
        asyncio.run(_drive())
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.")
        return 130
    _print_summary(system)
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from .tui import JirayaApp  # imported lazily so `run` works without textual TTY

    config = _config_from_args(args)
    JirayaApp(config=config, poll_interval=args.interval).run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jiraya",
        description="Agent-powered Jira triage agent with a TUI dashboard.",
    )
    sub = parser.add_subparsers(dest="command")

    p_tui = sub.add_parser("tui", help="Launch the real-time dashboard (default).")
    _add_common(p_tui)
    p_tui.set_defaults(func=cmd_tui, interval=20.0)

    p_run = sub.add_parser("run", help="Run the triage harness headlessly.")
    _add_common(p_run)
    p_run.add_argument("--once", action="store_true",
                       help="Run a single poll cycle and exit.")
    p_run.add_argument("--cycles", type=int, default=None,
                       help="Stop after N poll cycles (default: run forever).")
    p_run.add_argument("--no-color", action="store_true", help="Disable colored output.")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        # Default to the dashboard.
        args = parser.parse_args(["tui", *(argv or [])])
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

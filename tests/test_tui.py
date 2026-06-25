from __future__ import annotations

from textual.widgets import DataTable, RichLog, Static

from jiraya.composition import JirayaConfig
from jiraya.tui import JirayaApp


def _make_app() -> JirayaApp:
    # Large interval so the dashboard runs exactly one automatic cycle; further
    # cycles are triggered explicitly via key bindings in the tests.
    return JirayaApp(config=JirayaConfig(), poll_interval=10_000)


async def test_dashboard_populates_after_first_cycle(wait_for):
    app = _make_app()
    async with app.run_test() as pilot:
        ok = await wait_for(pilot, lambda: app._system.service.metrics.processed == 8)
        assert ok

        tickets = app.query_one("#tickets", DataTable)
        inbox = app.query_one("#inbox", DataTable)
        assert tickets.row_count == 8
        assert inbox.row_count == 4

        metrics_text = app.query_one("#metrics", Static).render()
        assert "Processed" in str(metrics_text)

        activity = app.query_one("#activity", RichLog)
        assert len(activity.lines) > 0


async def test_generate_action_injects_and_triages_new_ticket(wait_for):
    app = _make_app()
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: app._system.service.metrics.processed == 8)
        before = app._system.service.metrics.processed

        await pilot.press("g")
        ok = await wait_for(
            pilot, lambda: app._system.service.metrics.processed > before
        )
        assert ok
        assert app.query_one("#tickets", DataTable).row_count >= 9


async def test_resolve_action_clears_inbox_row(wait_for):
    app = _make_app()
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: app._system.service.metrics.processed == 8)
        inbox = app.query_one("#inbox", DataTable)
        assert inbox.row_count == 4
        open_before = len(app._system.inbox.open_entries())

        await pilot.press("r")
        ok = await wait_for(pilot, lambda: inbox.row_count == 3)
        assert ok
        assert len(app._system.inbox.open_entries()) == open_before - 1

"""Reliability coverage for the embedded Plaid Link launcher."""

import asyncio


def test_launcher_waits_for_an_explicit_browser_click():
    from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

    html = get_plaid_link_html("link-test", redirect_uri=None)

    listener_position = html.index('openButton.addEventListener("click"')
    open_position = html.index("handler.open()")

    assert '<button id="open-plaid" disabled>' in html
    assert listener_position < open_position
    assert "Open Plaid Link" in html


def test_launcher_surfaces_script_failure_and_timeout():
    from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

    html = get_plaid_link_html("link-test", redirect_uri=None)

    assert 'onerror="plaidScriptFailed()"' in html
    assert "15000" in html
    assert "Plaid Link did not load" in html
    assert "Plaid Link could not be initialized" in html
    assert "Plaid Link could not be opened" in html

    initialize_block = html.split("function initializePlaid()", 1)[1]
    initialize_block = initialize_block.split("onLoad: function()", 1)[0]
    assert "clearTimeout(loadTimeout)" not in initialize_block
    assert (
        "onLoad: function() {\n                            window.clearTimeout" in html
    )


def test_new_connection_requires_explicit_finish_navigation():
    from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

    html = get_plaid_link_html("link-test", redirect_uri=None)

    assert 'target="_top"' in html
    assert "Finish Connection" in html
    assert 'searchParams.set("public_token", public_token)' in html
    assert 'searchParams.set("link_success", "true")' in html


def test_relink_mode_does_not_exchange_a_public_token():
    from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

    html = get_plaid_link_html(
        "link-update-test",
        redirect_uri=None,
        mode="relink",
    )

    assert "Reconnect account" in html
    assert "Click Verify Reconnection below" in html
    assert 'searchParams.set("public_token", public_token)' not in html


def test_javascript_values_are_escaped():
    from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

    html = get_plaid_link_html(
        'link-test</script><script>alert("x")</script>',
        redirect_uri=None,
    )

    assert "</script><script>alert" not in html
    assert "\\u003c/script>" in html


def test_sequential_actions_do_not_reuse_an_event_loop_pool(monkeypatch):
    from budget_me.streamlit_app.pages import link_account

    engine_loops = []

    class FakeEngine:
        async def use(self):
            current_loop = asyncio.get_running_loop()
            if engine_loops and engine_loops[-1] is not current_loop:
                raise RuntimeError("database pool reused across event loops")
            if not engine_loops:
                engine_loops.append(current_loop)

        async def dispose(self):
            engine_loops.clear()

    class FakeGetEngine:
        def __init__(self):
            self.engine = FakeEngine()
            self.cached = False

        def __call__(self):
            self.cached = True
            return self.engine

        def cache_clear(self):
            self.engine = FakeEngine()
            self.cached = False

        def cache_info(self):
            class CacheInfo:
                currsize = int(self.cached)

            return CacheInfo()

    fake_get_engine = FakeGetEngine()
    monkeypatch.setattr(link_account, "get_engine", fake_get_engine)

    async def use_database():
        await fake_get_engine().use()
        return "ok"

    assert link_account._run_async(use_database()) == "ok"
    assert link_account._run_async(use_database()) == "ok"

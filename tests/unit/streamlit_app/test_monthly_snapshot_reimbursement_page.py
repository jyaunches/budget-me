"""Focused overview rendering tests for snapshot reimbursement flows."""

import ast
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def _load_overview_renderer():
    """Load only the pure renderer without executing the Streamlit page body."""
    page_path = Path("src/budget_me/streamlit_app/pages/monthly_snapshot.py")
    module = ast.parse(page_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "render_overview_metrics"
    )
    isolated_module = ast.fix_missing_locations(
        ast.Module(body=[function], type_ignores=[])
    )
    streamlit = SimpleNamespace(markdown=MagicMock())
    namespace = {"Decimal": Decimal, "st": streamlit}
    exec(compile(isolated_module, page_path, "exec"), namespace)
    return namespace["render_overview_metrics"], streamlit


def test_overview_renders_reimbursements_in_inclusive_cash_flow_totals() -> None:
    """Reimbursement flows remain visible and separate from income/expenses."""
    render, streamlit = _load_overview_renderer()

    render(
        {
            "income_total": 100,
            "expense_total": 50,
            "transfer_in_total": 20,
            "transfer_out_total": 10,
            "reimbursement_in_total": 7,
            "reimbursement_out_total": 3,
            "credit_card_total": 15,
            "net": 49,
        }
    )

    html = streamlit.markdown.call_args.args[0]
    assert "Reimbursements In" in html
    assert "Reimbursements Out" in html
    assert "$7.00" in html
    assert "$3.00" in html
    assert "$127.00" in html
    assert "$78.00" in html
    assert "NET: $49.00" in html
    assert streamlit.markdown.call_args.kwargs == {"unsafe_allow_html": True}

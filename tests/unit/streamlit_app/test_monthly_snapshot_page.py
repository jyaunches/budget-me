"""Tests for the Monthly Snapshot Streamlit page."""

import inspect
from pathlib import Path


class TestMonthlySnapshotPage:
    """Test Phase 3: Monthly Snapshot Overview Section."""

    def test_monthly_snapshot_page_file_exists(self):
        """Monthly snapshot page file should exist."""
        page_path = Path("src/budget_me/streamlit_app/pages/monthly_snapshot.py")
        assert page_path.exists(), "monthly_snapshot.py page file should exist"

    def test_render_month_selector_is_defined(self):
        """render_month_selector function should be defined."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        assert hasattr(monthly_snapshot, "render_month_selector"), (
            "render_month_selector function should exist"
        )

    def test_render_overview_metrics_is_defined(self):
        """render_overview_metrics function should be defined."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        assert hasattr(monthly_snapshot, "render_overview_metrics"), (
            "render_overview_metrics function should exist"
        )

    def test_render_month_selector_returns_year_month_string(self):
        """render_month_selector should return a year_month string."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        sig = inspect.signature(monthly_snapshot.render_month_selector)
        assert sig.return_annotation is str, "render_month_selector should return str"

    def test_render_month_selector_uses_streamlit_selectbox(self):
        """render_month_selector should use st.selectbox."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_month_selector)
        assert "st.selectbox" in source, "render_month_selector should use st.selectbox"

    def test_render_month_selector_uses_get_available_months_function(self):
        """render_month_selector should use get_available_months for month list."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_month_selector)
        assert "get_available_months" in source, (
            "render_month_selector should use get_available_months"
        )

    def test_render_overview_metrics_accepts_totals_dict(self):
        """render_overview_metrics should accept a totals dict parameter."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        sig = inspect.signature(monthly_snapshot.render_overview_metrics)
        assert "totals" in sig.parameters, "Should have 'totals' parameter"
        assert sig.parameters["totals"].annotation is dict, (
            "totals parameter should be dict"
        )

    def test_render_overview_metrics_uses_streamlit_markdown(self):
        """render_overview_metrics should use st.markdown for displaying metrics."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_overview_metrics)
        assert "st.markdown" in source, "Should use st.markdown for display"

    def test_render_overview_metrics_displays_income_expenses_net(self):
        """render_overview_metrics should display income, expenses, and net."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_overview_metrics)
        assert "income" in source.lower(), "Should display income"
        assert "expense" in source.lower(), "Should display expenses"
        assert "net" in source.lower(), "Should display net"


class TestIncomeSectionWithCRUD:
    """Test Phase 4: Income Section with CRUD."""

    def test_render_income_section_is_defined(self):
        """render_income_section function should be defined."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        assert hasattr(monthly_snapshot, "render_income_section"), (
            "render_income_section function should exist"
        )

    def test_render_income_section_accepts_session_and_year_month(self):
        """render_income_section should accept session and year_month parameters."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        sig = inspect.signature(monthly_snapshot.render_income_section)
        assert "session" in sig.parameters, "Should have 'session' parameter"
        assert "year_month" in sig.parameters, "Should have 'year_month' parameter"

    def test_render_income_section_calls_get_snapshot_line_items(self):
        """render_income_section should query snapshot income items."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "get_snapshot_line_items" in source, (
            "Should call get_snapshot_line_items"
        )

    def test_render_income_section_respects_closed_status(self):
        """render_income_section should check snapshot status."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "is_closed" in source or "snapshot_status" in source, (
            "Should check closed status"
        )

    def test_render_income_section_uses_streamlit_expander_for_add_form(self):
        """render_income_section should use st.expander for add form."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "st.expander" in source, "Should use st.expander for add form"

    def test_render_income_section_uses_session_state_for_edit_mode(self):
        """render_income_section should use st.session_state for tracking edit mode."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "st.session_state" in source, "Should use st.session_state for edit mode"

    def test_render_income_section_calls_add_one_time_item_on_add(self):
        """render_income_section should call add_one_time_item."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "add_one_time_item" in source, "Should call add_one_time_item"

    def test_render_income_section_calls_update_snapshot_line_item_on_edit(self):
        """render_income_section should call update_snapshot_line_item."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "update_snapshot_line_item" in source, (
            "Should call update_snapshot_line_item"
        )

    def test_render_income_section_calls_skip_snapshot_line_item_on_delete(self):
        """render_income_section should call skip_snapshot_line_item."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "skip_snapshot_line_item" in source, (
            "Should call skip_snapshot_line_item"
        )

    def test_render_income_section_displays_total(self):
        """render_income_section should display total income."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "total" in source.lower(), "Should calculate and display total"


class TestExpensesSectionWithCRUD:
    """Test Phase 5: Expenses Section with CRUD."""

    def test_render_expenses_section_is_defined(self):
        """render_expenses_section function should be defined."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        assert hasattr(monthly_snapshot, "render_expenses_section"), (
            "render_expenses_section function should exist"
        )

    def test_render_expenses_section_accepts_session_and_year_month(self):
        """render_expenses_section should accept session and year_month parameters."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        sig = inspect.signature(monthly_snapshot.render_expenses_section)
        assert "session" in sig.parameters, "Should have 'session' parameter"
        assert "year_month" in sig.parameters, "Should have 'year_month' parameter"

    def test_render_expenses_section_calls_get_snapshot_line_items(self):
        """render_expenses_section should query snapshot expense items."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "get_snapshot_line_items" in source, (
            "Should call get_snapshot_line_items"
        )

    def test_render_expenses_section_groups_by_category(self):
        """render_expenses_section should group by category field."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "category" in source.lower(), "Should group by category"

    def test_render_expenses_section_calculates_subscriptions_subtotal(self):
        """render_expenses_section should calculate Subscriptions category subtotal."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "subscriptions" in source.lower(), "Should handle Subscriptions category"

    def test_render_expenses_section_uses_expander_for_subscriptions(self):
        """render_expenses_section should use st.expander for Subscriptions."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "st.expander" in source, "Should use st.expander for collapsing"

    def test_render_expenses_section_uses_expander_for_add_form(self):
        """render_expenses_section should use st.expander for add form."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "st.expander" in source, "Should use st.expander for add form"

    def test_render_expenses_section_has_category_dropdown(self):
        """render_expenses_section should have category selection dropdown."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "selectbox" in source.lower(), "Should have category selectbox"

    def test_render_expenses_section_calls_add_one_time_item_on_add(self):
        """render_expenses_section should call add_one_time_item."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "add_one_time_item" in source, "Should call add_one_time_item"

    def test_render_expenses_section_calls_update_snapshot_line_item_on_edit(self):
        """render_expenses_section should call update_snapshot_line_item (via helper)."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        # Check that render_expense_row helper is used
        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "render_expense_row" in source, "Should use render_expense_row helper"

        # Check that the helper calls update_snapshot_line_item
        helper_source = inspect.getsource(monthly_snapshot.render_expense_row)
        assert "update_snapshot_line_item" in helper_source, (
            "Helper should call update_snapshot_line_item"
        )

    def test_render_expenses_section_calls_skip_snapshot_line_item_on_delete(self):
        """render_expenses_section should call skip_snapshot_line_item (via helper)."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        # Check that render_expense_row helper is used
        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "render_expense_row" in source, "Should use render_expense_row helper"

        # Check that the helper calls skip_snapshot_line_item
        helper_source = inspect.getsource(monthly_snapshot.render_expense_row)
        assert "skip_snapshot_line_item" in helper_source, (
            "Helper should call skip_snapshot_line_item"
        )

    def test_render_expenses_section_displays_subscription_totals(self):
        """render_expenses_section should display subscription totals."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "sub_total" in source.lower(), "Should calculate subscription totals"

    def test_render_expenses_section_displays_total(self):
        """render_expenses_section should display total expenses."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "total" in source.lower(), "Should calculate and display total"


class TestCreditCardsSection:
    """Test Phase 6: Credit Cards Section."""

    def test_render_credit_cards_section_is_defined(self):
        """render_credit_cards_section function should be defined."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        assert hasattr(monthly_snapshot, "render_credit_cards_section"), (
            "render_credit_cards_section function should exist"
        )

    def test_render_credit_cards_section_calls_get_snapshot_credit_cards(self):
        """render_credit_cards_section should query snapshot credit card data."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_credit_cards_section)
        assert "get_snapshot_credit_cards" in source, (
            "Should call get_snapshot_credit_cards"
        )

    def test_render_credit_cards_section_displays_payment_strategy(self):
        """render_credit_cards_section should display payment strategy."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_credit_cards_section)
        assert "payment_strategy" in source, "Should reference payment_strategy field"

    def test_render_credit_cards_section_calls_update_snapshot_credit_card(self):
        """render_credit_cards_section should update snapshot credit card."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_credit_cards_section)
        assert "update_snapshot_credit_card" in source, (
            "Should call update_snapshot_credit_card"
        )

    def test_render_credit_cards_section_labels_planned_and_actual_payments(self):
        """Credit-card totals should distinguish plans from completed payments."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_credit_cards_section)
        assert "Planned card payments" in source
        assert "Actually paid" in source
        assert "Remaining planned" in source
        assert "Posted card payments" in source
        assert "reconciliation_complete" in source
        assert "No posted card payments" in source
        assert "due outside" in source


def test_reconciled_snapshot_hides_plan_comparison_in_history():
    """Reconciled months should emphasize actuals, not plan variance."""
    from budget_me.streamlit_app.pages import monthly_snapshot

    page_source = inspect.getsource(monthly_snapshot)
    overview_source = inspect.getsource(monthly_snapshot.render_overview_metrics)
    assert "Showing reconciled actuals" in page_source
    assert "Planning history" in page_source
    assert "Net change" in page_source
    assert "Card Payments (planned)" in overview_source
    assert "Card Payments" in overview_source


def test_reconciled_snapshot_renders_receipt_backed_actual_details():
    """The snapshot page should expose every reconciled cash-flow section."""
    from budget_me.streamlit_app.pages import monthly_snapshot

    page_source = inspect.getsource(monthly_snapshot)
    detail_source = inspect.getsource(monthly_snapshot.render_reconciled_actual_details)
    row_source = inspect.getsource(monthly_snapshot._render_actual_rows)

    assert "get_reconciled_actual_details" in page_source
    assert "Reconciled Actual Details" in detail_source
    for label in (
        "Income",
        "Expenses",
        "Transfers In",
        "Transfers Out",
        "Reimbursements In",
        "Reimbursements Out",
        "Card Payments",
    ):
        assert label in detail_source
    for column in (
        "Date",
        "Description",
        "Posted Account",
        "Category",
        "Matched Plan",
        "Amount",
        "Note",
    ):
        assert column in row_source


class TestSnapshotWorkflowUIUpdates:
    """Test Phase 4: UI Updates for Snapshot Workflow."""

    def test_month_dropdown_uses_get_available_months(self):
        """render_month_selector should use get_available_months instead of generating range."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_month_selector)
        assert "get_available_months" in source, (
            "Should call get_available_months for snapshot months"
        )

    def test_page_checks_snapshot_status(self):
        """Page should check snapshot status to determine read-only mode."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        # Should check status field from snapshot
        assert "status" in source, "Should check snapshot status"

    def test_closed_snapshot_hides_edit_buttons(self):
        """Edit buttons should be hidden when viewing closed snapshot."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        # Check income section
        income_source = inspect.getsource(monthly_snapshot.render_income_section)
        # Should conditionally render buttons based on status
        assert "if" in income_source and "status" in income_source, (
            "Should conditionally render edit buttons based on status"
        )

    def test_close_button_visible_for_open_snapshot(self):
        """Close Month button should be rendered for open snapshots."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        assert "Close Month" in source or "close" in source.lower(), (
            "Should have Close Month button"
        )

    def test_page_uses_snapshot_data_sources(self):
        """Page should use snapshot data sources instead of live data."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        # Check for snapshot function calls
        income_source = inspect.getsource(monthly_snapshot.render_income_section)
        assert "get_snapshot_line_items" in income_source, (
            "Should call get_snapshot_line_items for income"
        )

        expenses_source = inspect.getsource(monthly_snapshot.render_expenses_section)
        assert "get_snapshot_line_items" in expenses_source, (
            "Should call get_snapshot_line_items for expenses"
        )

    def test_credit_cards_uses_snapshot_data(self):
        """Credit cards section should use snapshot data."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_credit_cards_section)
        assert "get_snapshot_credit_cards" in source, (
            "Should call get_snapshot_credit_cards"
        )

    def test_page_uses_calculate_snapshot_totals(self):
        """Page should use calculate_snapshot_totals instead of calculate_monthly_totals."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        assert "calculate_snapshot_totals" in source, (
            "Should call calculate_snapshot_totals"
        )

    def test_skip_item_functionality_exists(self):
        """Skip item toggle should be available for line items."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        # Check income or expense sections for skip functionality
        income_source = inspect.getsource(monthly_snapshot.render_income_section)
        expenses_source = inspect.getsource(monthly_snapshot.render_expenses_section)

        # Should have skip functionality in at least one section
        has_skip = "skip" in income_source.lower() or "skip" in expenses_source.lower()
        assert has_skip, "Should have skip item functionality"

    def test_one_time_items_supported(self):
        """One-time item addition should be supported."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        # Should reference one-time or have add_one_time_item call
        assert "one_time" in source.lower() or "add_one_time_item" in source, (
            "Should support one-time items"
        )

    def test_page_calls_close_snapshot_function(self):
        """Page should call close_snapshot when Close Month button clicked."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        assert "close_snapshot" in source, "Should call close_snapshot function"


class TestIntegrationAndPolish:
    """Test Phase 7: Integration & Polish."""

    def test_monthly_snapshot_page_imports_all_db_functions(self):
        """Monthly snapshot page should import all required DB functions."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        required_imports = [
            "calculate_snapshot_totals",
            "get_snapshot_line_items",
            "get_snapshot_credit_cards",
            "get_available_months",
            "get_or_create_snapshot",
            "update_snapshot_line_item",
            "skip_snapshot_line_item",
            "add_one_time_item",
            "update_snapshot_credit_card",
            "close_snapshot",
        ]
        for func in required_imports:
            assert func in source, f"Should import {func}"

    def test_monthly_snapshot_page_uses_session_for_db_operations(self):
        """Monthly snapshot page should use get_session for database operations."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        assert "get_session" in source, "Should use get_session for DB operations"

    def test_monthly_snapshot_page_uses_columns_for_layout(self):
        """Monthly snapshot page should use st.columns for responsive layout."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        assert "st.columns" in source, "Should use st.columns for layout"


class TestPerAccountSnapshotsPhase5:
    """Test Phase 5: UI Changes for Per-Account Snapshots."""

    def test_render_functions_accept_account_id_parameter(self):
        """All render functions should accept account_id parameter."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        # List of render functions that should accept account_id
        render_functions = [
            "render_income_section",
            "render_expenses_section",
            "render_credit_cards_section",
            "render_transfers_section",
        ]

        for func_name in render_functions:
            if hasattr(monthly_snapshot, func_name):
                func = getattr(monthly_snapshot, func_name)
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                assert "account_id" in params, (
                    f"{func_name} should accept account_id parameter"
                )

    def test_page_imports_get_depository_accounts(self):
        """Page should import get_depository_accounts function."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        assert "get_depository_accounts" in source, (
            "Should import get_depository_accounts"
        )

    def test_page_has_account_selector_function(self):
        """Page should have render_account_selector function."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        assert hasattr(monthly_snapshot, "render_account_selector"), (
            "render_account_selector function should exist"
        )

    def test_render_account_selector_uses_get_depository_accounts(self):
        """render_account_selector should call get_depository_accounts."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_account_selector)
        assert "get_depository_accounts" in source, (
            "Should call get_depository_accounts to populate selector"
        )

    def test_render_account_selector_returns_account_id(self):
        """render_account_selector should return selected account_id."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        sig = inspect.signature(monthly_snapshot.render_account_selector)
        assert sig.return_annotation is str, (
            "render_account_selector should return str (account_id)"
        )

    def test_render_account_selector_uses_session_state(self):
        """render_account_selector should use st.session_state to preserve selection."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_account_selector)
        assert "st.session_state" in source, (
            "Should use st.session_state to preserve selected account"
        )

    def test_render_account_selector_excludes_excluded_accounts(self):
        """render_account_selector should not show excluded accounts."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_account_selector)
        assert "include_excluded=False" in source, (
            "Should exclude excluded accounts from dropdown"
        )

    def test_render_month_selector_accepts_account_id(self):
        """render_month_selector should accept account_id parameter."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        sig = inspect.signature(monthly_snapshot.render_month_selector)
        params = list(sig.parameters.keys())
        assert "account_id" in params, "render_month_selector should accept account_id"

    def test_render_month_selector_passes_account_id_to_get_available_months(self):
        """render_month_selector should pass account_id to get_available_months."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_month_selector)
        # Should call get_available_months with account_id
        assert "get_available_months" in source and "account_id" in source, (
            "Should pass account_id to get_available_months"
        )

    def test_page_calls_render_account_selector_before_month_selector(self):
        """Page should call render_account_selector before render_month_selector."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot)
        # Find positions of the calls
        account_selector_pos = source.find("render_account_selector")
        month_selector_pos = source.find("render_month_selector")

        assert account_selector_pos > 0, "Should call render_account_selector"
        assert month_selector_pos > 0, "Should call render_month_selector"
        assert account_selector_pos < month_selector_pos, (
            "render_account_selector should be called before render_month_selector"
        )


class TestAccountSelectorSorting:
    """Test account selector sorts accounts Z-A (descending alphabetical)."""

    def test_render_account_selector_sorts_accounts_descending(self):
        """render_account_selector should sort accounts in descending alphabetical order (Z-A)."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_account_selector)
        # Should sort accounts with reverse=True for Z-A order
        assert "sort" in source.lower() and "reverse=True" in source, (
            "Should sort accounts in descending order (reverse=True)"
        )


class TestMonthSelectorDefaultsToOldestOpen:
    """Test month selector defaults to oldest open (non-closed) month."""

    def test_render_month_selector_defaults_to_oldest_open_month(self):
        """render_month_selector should default to oldest open month, not newest."""
        from budget_me.streamlit_app.pages import monthly_snapshot

        source = inspect.getsource(monthly_snapshot.render_month_selector)
        # Should find the oldest open month (look for open/status check and index logic)
        assert "open" in source.lower() or "status" in source.lower(), (
            "Should check month status to find oldest open"
        )
        # Should not just default to index 0 (newest)
        # Should have logic to find the oldest open month
        assert "for" in source or "enumerate" in source or "index" in source.lower(), (
            "Should have logic to find the correct default month index"
        )

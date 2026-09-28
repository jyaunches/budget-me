"""Unit tests for AnticipatedItemsRepo."""

import inspect
from unittest.mock import MagicMock

from budget_me.db.models.anticipated_item import AnticipatedItem
from budget_me.db.repos.anticipated_items_repo import AnticipatedItemsRepo


class TestAnticipatedItemsRepo:
    """Tests for AnticipatedItemsRepo structure and API."""

    def test_anticipated_items_repo_has_required_methods(self):
        """Verify all required methods exist."""
        mock_session = MagicMock()
        repo = AnticipatedItemsRepo(mock_session)
        required_methods = [
            "get_all",
            "get_by_id",
            "get_active",
            "get_active_by_type",
            "create",
            "update",
            "delete",
        ]
        for method_name in required_methods:
            assert hasattr(repo, method_name), f"Missing method: {method_name}"
            assert callable(getattr(repo, method_name)), (
                f"{method_name} is not callable"
            )

    def test_anticipated_items_repo_methods_are_async(self):
        """Verify all custom methods are async."""
        mock_session = MagicMock()
        repo = AnticipatedItemsRepo(mock_session)
        methods_to_check = [
            "get_all",
            "get_by_id",
            "get_active",
            "get_active_by_type",
            "create",
            "update",
            "delete",
        ]
        for method_name in methods_to_check:
            method = getattr(repo, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} should be async"

    def test_anticipated_items_repo_model_attribute(self):
        """Verify model attribute points to AnticipatedItem."""
        mock_session = MagicMock()
        repo = AnticipatedItemsRepo(mock_session)
        assert hasattr(repo, "model"), "Missing model attribute"
        assert repo.model == AnticipatedItem

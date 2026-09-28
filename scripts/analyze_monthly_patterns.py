#!/usr/bin/env python3
"""Analyze transaction patterns to identify recurring expenses and income."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select, text

from budget_me.streamlit_app.db import get_session
from budget_me.db.models.transaction import Transaction
from budget_me.db.models.account import Account
from budget_me.db.models.credit_liability import CreditLiability


def analyze_recurring_expenses():
    """Find merchants that appear multiple months - potential recurring expenses."""
    print("\n" + "=" * 80)
    print("RECURRING EXPENSE ANALYSIS")
    print("=" * 80)

    with get_session() as session:
        # Get transactions grouped by merchant and month
        stmt = text("""
            SELECT
                COALESCE(merchant_name, name) as merchant,
                COUNT(DISTINCT DATE_TRUNC('month', date)) as months_appeared,
                COUNT(*) as total_transactions,
                AVG(amount) as avg_amount,
                MIN(amount) as min_amount,
                MAX(amount) as max_amount,
                raw->'personal_finance_category'->>'primary' as category
            FROM transactions
            WHERE amount > 0  -- Expenses are positive in Plaid
            GROUP BY COALESCE(merchant_name, name), raw->'personal_finance_category'->>'primary'
            HAVING COUNT(DISTINCT DATE_TRUNC('month', date)) >= 2
            ORDER BY months_appeared DESC, avg_amount DESC
            LIMIT 50
        """)

        result = session.execute(stmt)
        rows = result.fetchall()

        print("\nMerchants appearing in 2+ months (potential recurring expenses):\n")
        print(f"{'Merchant':<40} {'Months':<8} {'Avg $':<12} {'Min $':<12} {'Max $':<12} {'Category':<20}")
        print("-" * 104)

        for row in rows:
            merchant = (row.merchant or "Unknown")[:38]
            print(f"{merchant:<40} {row.months_appeared:<8} ${row.avg_amount:>10,.2f} ${row.min_amount:>10,.2f} ${row.max_amount:>10,.2f} {(row.category or 'N/A'):<20}")


def analyze_income():
    """Find all income transactions."""
    print("\n" + "=" * 80)
    print("INCOME ANALYSIS")
    print("=" * 80)

    with get_session() as session:
        # Income in Plaid is negative (money coming in)
        stmt = text("""
            SELECT
                COALESCE(merchant_name, name) as source,
                COUNT(*) as occurrences,
                COUNT(DISTINCT DATE_TRUNC('month', date)) as months,
                AVG(ABS(amount)) as avg_amount,
                SUM(ABS(amount)) as total_amount,
                raw->'personal_finance_category'->>'primary' as category,
                raw->'personal_finance_category'->>'detailed' as detailed_category
            FROM transactions
            WHERE amount < 0  -- Income is negative in Plaid
                OR raw->'personal_finance_category'->>'primary' = 'INCOME'
            GROUP BY COALESCE(merchant_name, name),
                     raw->'personal_finance_category'->>'primary',
                     raw->'personal_finance_category'->>'detailed'
            ORDER BY total_amount DESC
            LIMIT 30
        """)

        result = session.execute(stmt)
        rows = result.fetchall()

        print("\nIncome sources:\n")
        print(f"{'Source':<40} {'Count':<8} {'Months':<8} {'Avg $':<12} {'Total $':<14} {'Category':<25}")
        print("-" * 107)

        for row in rows:
            source = (row.source or "Unknown")[:38]
            category = (row.detailed_category or row.category or "N/A")[:23]
            print(f"{source:<40} {row.occurrences:<8} {row.months:<8} ${row.avg_amount:>10,.2f} ${row.total_amount:>12,.2f} {category:<25}")


def analyze_credit_cards():
    """Analyze credit card accounts and their current state."""
    print("\n" + "=" * 80)
    print("CREDIT CARD ANALYSIS")
    print("=" * 80)

    with get_session() as session:
        # Get credit card accounts with liability info
        stmt = select(
            Account.name,
            Account.mask,
            Account.balance_current,
            Account.balance_available,
            CreditLiability.last_statement_balance,
            CreditLiability.next_payment_due_date,
            CreditLiability.minimum_payment_amount,
            CreditLiability.last_payment_amount,
            CreditLiability.last_payment_date,
        ).outerjoin(
            CreditLiability, Account.account_id == CreditLiability.account_id
        ).where(
            Account.type == 'credit'
        )

        result = session.execute(stmt)
        rows = result.fetchall()

        if not rows:
            print("\nNo credit card accounts found.")
            return

        print("\nCredit Card Accounts:\n")
        print(f"{'Card':<25} {'Mask':<8} {'Current Bal':<14} {'Statement Bal':<14} {'Due Date':<12} {'Min Due':<12}")
        print("-" * 95)

        for row in rows:
            name = (row.name or "Unknown")[:23]
            mask = row.mask or "N/A"
            current = f"${row.balance_current:,.2f}" if row.balance_current else "N/A"
            statement = f"${row.last_statement_balance:,.2f}" if row.last_statement_balance else "N/A"
            due = str(row.next_payment_due_date) if row.next_payment_due_date else "N/A"
            min_due = f"${row.minimum_payment_amount:,.2f}" if row.minimum_payment_amount else "N/A"
            print(f"{name:<25} {mask:<8} {current:<14} {statement:<14} {due:<12} {min_due:<12}")


def analyze_spending_by_card():
    """Analyze average monthly spending per credit card."""
    print("\n" + "=" * 80)
    print("SPENDING BY CREDIT CARD (Monthly Averages)")
    print("=" * 80)

    with get_session() as session:
        stmt = text("""
            SELECT
                a.name as card_name,
                a.mask,
                COUNT(DISTINCT DATE_TRUNC('month', t.date)) as months_of_data,
                SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_spending,
                SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) /
                    NULLIF(COUNT(DISTINCT DATE_TRUNC('month', t.date)), 0) as avg_monthly_spend
            FROM accounts a
            JOIN transactions t ON a.account_id = t.account_id
            WHERE a.type = 'credit'
            GROUP BY a.name, a.mask
            ORDER BY avg_monthly_spend DESC
        """)

        result = session.execute(stmt)
        rows = result.fetchall()

        if not rows:
            print("\nNo credit card spending data found.")
            return

        print("\n")
        print(f"{'Card':<30} {'Mask':<8} {'Months':<8} {'Total Spent':<14} {'Avg Monthly':<14}")
        print("-" * 84)

        for row in rows:
            name = (row.card_name or "Unknown")[:28]
            mask = row.mask or "N/A"
            print(f"{name:<30} {mask:<8} {row.months_of_data:<8} ${row.total_spending:>11,.2f} ${row.avg_monthly_spend:>11,.2f}")


def analyze_monthly_summary():
    """Show monthly income vs expenses."""
    print("\n" + "=" * 80)
    print("MONTHLY SUMMARY (Income vs Expenses)")
    print("=" * 80)

    with get_session() as session:
        stmt = text("""
            SELECT
                DATE_TRUNC('month', date) as month,
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as income,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as expenses,
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) -
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as net
            FROM transactions
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month DESC
            LIMIT 12
        """)

        result = session.execute(stmt)
        rows = result.fetchall()

        print("\n")
        print(f"{'Month':<12} {'Income':<14} {'Expenses':<14} {'Net':<14} {'Status'}")
        print("-" * 66)

        for row in rows:
            month_str = row.month.strftime('%Y-%m') if row.month else "Unknown"
            net = row.net or 0
            status = "✓ Positive" if net >= 0 else "✗ Negative"
            print(f"{month_str:<12} ${row.income:>11,.2f} ${row.expenses:>11,.2f} ${net:>11,.2f} {status}")


def analyze_specific_categories():
    """Look for specific anticipated expense categories."""
    print("\n" + "=" * 80)
    print("ANTICIPATED EXPENSE CATEGORIES")
    print("=" * 80)

    # Keywords to search for in merchant names
    keywords = {
        "Mortgage/Rent": ["mortgage", "rent", "housing", "home loan"],
        "Utilities": ["electric", "power", "gas", "water", "utility", "pge", "sdge", "edison"],
        "Childcare": ["childcare", "daycare", "preschool", "school", "tuition", "montessori", "kindercare"],
        "Phone/Cellular": ["verizon", "at&t", "t-mobile", "sprint", "cellular", "wireless", "phone"],
        "Car Payment": ["car payment", "auto loan", "toyota financial", "honda financial", "ford credit"],
        "Insurance": ["insurance", "geico", "state farm", "allstate", "progressive"],
        "Subscriptions": ["netflix", "spotify", "hulu", "disney", "amazon prime", "apple", "google storage"],
        "House Cleaning": ["cleaning", "maid", "house clean"],
    }

    with get_session() as session:
        for category, search_terms in keywords.items():
            # Build OR conditions for each search term
            conditions = " OR ".join([f"LOWER(COALESCE(merchant_name, name)) LIKE '%{term}%'" for term in search_terms])

            stmt = text(f"""
                SELECT
                    COALESCE(merchant_name, name) as merchant,
                    COUNT(*) as count,
                    AVG(ABS(amount)) as avg_amount,
                    MIN(date) as first_seen,
                    MAX(date) as last_seen
                FROM transactions
                WHERE ({conditions})
                GROUP BY COALESCE(merchant_name, name)
                ORDER BY count DESC
                LIMIT 5
            """)

            result = session.execute(stmt)
            rows = result.fetchall()

            print(f"\n{category}:")
            if rows:
                for row in rows:
                    print(f"  - {row.merchant}: {row.count} transactions, avg ${row.avg_amount:,.2f} ({row.first_seen} to {row.last_seen})")
            else:
                print("  No matches found")


if __name__ == "__main__":
    print("Budget Me - Monthly Pattern Analysis")
    print("Analyzing transaction data to identify recurring expenses and income...")

    analyze_monthly_summary()
    analyze_income()
    analyze_recurring_expenses()
    analyze_specific_categories()
    analyze_credit_cards()
    analyze_spending_by_card()

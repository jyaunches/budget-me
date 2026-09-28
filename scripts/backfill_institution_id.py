#!/usr/bin/env python3
"""
Backfill institution_id for existing Plaid items and report duplicates.

Usage:
    uv run python scripts/backfill_institution_id.py
"""

import asyncio
from collections import defaultdict

from plaid.model.item_get_request import ItemGetRequest

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.plaid.client import get_plaid_client
from sqlalchemy import text


async def backfill_institution_ids():
    """Fetch and update institution_id for all items missing it."""
    client = get_plaid_client()
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    async with get_async_session() as session:
        # Get all items
        result = await session.execute(text("""
            SELECT id, item_id, institution_id, access_token_enc, created_at
            FROM plaid_items
            ORDER BY created_at
        """))
        items = result.fetchall()

        print(f"Found {len(items)} Plaid items\n")
        print("=" * 70)
        print("STEP 1: Backfilling institution_id")
        print("=" * 70)

        updated_count = 0
        items_with_institution = []

        for item in items:
            db_id, item_id, current_institution_id, access_token_enc, created_at = item

            # Decrypt access token
            access_token = encryptor.decrypt(access_token_enc)

            # Fetch item details from Plaid
            try:
                request = ItemGetRequest(access_token=access_token)
                response = client.item_get(request)
                institution_id = response.item.institution_id

                # Update if different or NULL
                if current_institution_id != institution_id:
                    await session.execute(
                        text("UPDATE plaid_items SET institution_id = :inst_id WHERE id = :id"),
                        {"inst_id": institution_id, "id": db_id}
                    )
                    updated_count += 1
                    status = "UPDATED"
                else:
                    status = "OK"

                items_with_institution.append({
                    "db_id": db_id,
                    "institution_id": institution_id,
                    "created_at": created_at,
                })
                print(f"  [{status}] {db_id} -> {institution_id}")

            except Exception as e:
                print(f"  [ERROR] {db_id}: {e}")
                items_with_institution.append({
                    "db_id": db_id,
                    "institution_id": None,
                    "created_at": created_at,
                })

        await session.commit()
        print(f"\nUpdated {updated_count} items")

        # Step 2: Report duplicates
        print("\n" + "=" * 70)
        print("STEP 2: Checking for duplicates")
        print("=" * 70)

        # Group by institution_id
        by_institution = defaultdict(list)
        for item in items_with_institution:
            if item["institution_id"]:
                by_institution[item["institution_id"]].append(item)

        duplicates_found = False
        for inst_id, inst_items in by_institution.items():
            if len(inst_items) > 1:
                duplicates_found = True
                print(f"\n⚠️  DUPLICATE: {inst_id} ({len(inst_items)} items)")

                # Get details for each duplicate
                for item in inst_items:
                    details = await session.execute(text("""
                        SELECT
                            pi.id,
                            pi.created_at,
                            pi.status,
                            COUNT(DISTINCT a.id) as account_count,
                            COUNT(DISTINCT t.id) as transaction_count
                        FROM plaid_items pi
                        LEFT JOIN accounts a ON a.plaid_item_id = pi.id
                        LEFT JOIN transactions t ON t.plaid_item_id = pi.id
                        WHERE pi.id = :id
                        GROUP BY pi.id
                    """), {"id": item["db_id"]})
                    row = details.fetchone()

                    print(f"    ID: {row[0]}")
                    print(f"       Linked: {row[1]}")
                    print(f"       Status: {row[2]}")
                    print(f"       Accounts: {row[3]}")
                    print(f"       Transactions: {row[4]}")

        if not duplicates_found:
            print("\n✅ No duplicates found!")
        else:
            print("\n" + "-" * 70)
            print("To remove a duplicate, run:")
            print("  uv run python scripts/backfill_institution_id.py --delete <item_id>")
            print("-" * 70)


async def delete_item(item_id: str):
    """Delete a Plaid item and all associated data (cascades)."""
    async with get_async_session() as session:
        # Get item details first
        result = await session.execute(text("""
            SELECT
                pi.id,
                pi.institution_id,
                COUNT(DISTINCT a.id) as account_count,
                COUNT(DISTINCT t.id) as transaction_count
            FROM plaid_items pi
            LEFT JOIN accounts a ON a.plaid_item_id = pi.id
            LEFT JOIN transactions t ON t.plaid_item_id = pi.id
            WHERE pi.id = :id
            GROUP BY pi.id
        """), {"id": item_id})
        row = result.fetchone()

        if not row:
            print(f"❌ Item {item_id} not found")
            return

        print(f"Deleting item: {row[0]}")
        print(f"  Institution: {row[1]}")
        print(f"  Accounts: {row[2]} (will be deleted)")
        print(f"  Transactions: {row[3]} (will be deleted)")

        # Confirm
        confirm = input("\nType 'yes' to confirm deletion: ")
        if confirm.lower() != "yes":
            print("Cancelled")
            return

        # Delete (cascades to accounts, transactions, cursors, ingest_run_items)
        await session.execute(text("DELETE FROM plaid_items WHERE id = :id"), {"id": item_id})
        await session.commit()
        print(f"\n✅ Deleted item {item_id} and all associated data")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "--delete":
        asyncio.run(delete_item(sys.argv[2]))
    else:
        asyncio.run(backfill_institution_ids())

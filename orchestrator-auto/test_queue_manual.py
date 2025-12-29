#!/usr/bin/env python3
"""
Quick test script for queue items functionality.
"""

import sys
import tempfile
import os

# Add orchestrator-auto to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_auto import db

def test_queue_items():
    """Test queue items functionality."""

    # Create temporary database
    fd, temp_db = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)

    try:
        # Initialize database
        print("Initializing database...")
        db.init_db(temp_db)

        # Test 1: Check table exists
        print("\n✓ Test 1: Checking queue_items table exists...")
        with db.get_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='queue_items'
            """)
            result = cursor.fetchone()
            assert result is not None, "queue_items table not found"
        print("  PASSED: queue_items table exists")

        # Test 2: Create queue items
        print("\n✓ Test 2: Creating queue items...")
        id1 = db.create_queue_item("/project/a", "docs/plan1.md", "Feature 1", 0, temp_db)
        id2 = db.create_queue_item("/project/a", "docs/plan2.md", "Feature 2", 1, temp_db)
        id3 = db.create_queue_item("/project/a", "docs/plan3.md", "Feature 3", 2, temp_db)
        print(f"  Created items: {id1}, {id2}, {id3}")
        print("  PASSED: Created 3 queue items")

        # Test 3: List queue items (ordered by position)
        print("\n✓ Test 3: Listing queue items...")
        items = db.list_queue_items("/project/a", temp_db)
        assert len(items) == 3, f"Expected 3 items, got {len(items)}"
        assert items[0]["position"] == 0, f"Expected position 0, got {items[0]['position']}"
        assert items[1]["position"] == 1, f"Expected position 1, got {items[1]['position']}"
        assert items[2]["position"] == 2, f"Expected position 2, got {items[2]['position']}"
        print(f"  Items: {[(i['position'], i['plan_path']) for i in items]}")
        print("  PASSED: Items ordered by position")

        # Test 4: Get next queue item
        print("\n✓ Test 4: Getting next queue item...")
        next_item = db.get_next_queue_item("/project/a", temp_db)
        assert next_item is not None, "No next item found"
        assert next_item["id"] == id1, f"Expected id {id1}, got {next_item['id']}"
        assert next_item["status"] == "pending", f"Expected status 'pending', got {next_item['status']}"
        print(f"  Next item: position={next_item['position']}, status={next_item['status']}")
        print("  PASSED: Got first pending item")

        # Test 5: Update queue item
        print("\n✓ Test 5: Updating queue item...")
        result = db.update_queue_item(
            id1, temp_db,
            status="running",
            session_id="abc123",
            started_at="2025-01-01 10:00:00"
        )
        assert result is True, "Update failed"
        updated_item = db.get_queue_item_by_session_id("abc123", temp_db)
        assert updated_item is not None, "Item not found by session_id"
        assert updated_item["status"] == "running", f"Expected status 'running', got {updated_item['status']}"
        print(f"  Updated item: status={updated_item['status']}, session_id={updated_item['session_id']}")
        print("  PASSED: Updated queue item")

        # Test 6: Get next skips running items
        print("\n✓ Test 6: Getting next item (should skip running)...")
        next_item = db.get_next_queue_item("/project/a", temp_db)
        assert next_item is not None, "No next item found"
        assert next_item["id"] == id2, f"Expected id {id2}, got {next_item['id']}"
        print(f"  Next item: position={next_item['position']}, plan={next_item['plan_path']}")
        print("  PASSED: Correctly skipped running item")

        # Test 7: Clear active queue
        print("\n✓ Test 7: Clearing active queue...")
        db.update_queue_item(id3, temp_db, status="completed")  # Mark one as completed
        count = db.clear_active_queue("/project/a", temp_db)
        print(f"  Cleared {count} items")
        remaining = db.list_queue_items("/project/a", temp_db)
        assert len(remaining) == 1, f"Expected 1 item, got {len(remaining)}"
        assert remaining[0]["status"] == "completed", "Completed item should remain"
        print("  PASSED: Cleared active items, retained completed")

        # Test 8: Project scoping
        print("\n✓ Test 8: Testing project scoping...")
        db.create_queue_item("/project/b", "docs/plan_b.md", "Feature B", 0, temp_db)
        items_a = db.list_queue_items("/project/a", temp_db)
        items_b = db.list_queue_items("/project/b", temp_db)
        assert len(items_b) == 1, f"Expected 1 item in project B, got {len(items_b)}"
        print(f"  Project A: {len(items_a)} items, Project B: {len(items_b)} items")
        print("  PASSED: Projects properly scoped")

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)

    finally:
        # Cleanup
        os.unlink(temp_db)

if __name__ == "__main__":
    test_queue_items()

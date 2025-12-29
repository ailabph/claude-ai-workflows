#!/usr/bin/env python3
"""
Manual test for extract_feature_from_plan functionality.
"""

import sys
import tempfile
import os
from pathlib import Path

# Add orchestrator-auto to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_auto.parser import extract_feature_from_plan

def test_feature_extraction():
    """Test feature extraction functionality."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Test 1: YAML frontmatter
        print("✓ Test 1: YAML frontmatter extraction...")
        yaml_file = tmppath / "yaml-test.md"
        yaml_file.write_text("""---
feature: User Authentication System
---

# Plan
Content here.
""")
        result = extract_feature_from_plan(str(yaml_file))
        assert result == "User Authentication System", f"Expected 'User Authentication System', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 2: Feature header
        print("\n✓ Test 2: # Feature: header extraction...")
        feature_file = tmppath / "feature-test.md"
        feature_file.write_text("""# Feature: Payment Gateway Integration

## Overview
Integrate payment gateway.
""")
        result = extract_feature_from_plan(str(feature_file))
        assert result == "Payment Gateway Integration", f"Expected 'Payment Gateway Integration', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 3: Implementation Plan header
        print("\n✓ Test 3: # Implementation Plan: header extraction...")
        impl_file = tmppath / "impl-test.md"
        impl_file.write_text("""# Implementation Plan: API Rate Limiting

## Description
Add rate limiting.
""")
        result = extract_feature_from_plan(str(impl_file))
        assert result == "API Rate Limiting", f"Expected 'API Rate Limiting', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 4: Plain H1 title
        print("\n✓ Test 4: Plain H1 title extraction...")
        h1_file = tmppath / "h1-test.md"
        h1_file.write_text("""# Database Migration Tools

## Overview
Tools for migrations.
""")
        result = extract_feature_from_plan(str(h1_file))
        assert result == "Database Migration Tools", f"Expected 'Database Migration Tools', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 5: Filename fallback (no headers)
        print("\n✓ Test 5: Filename fallback (no headers)...")
        no_header_file = tmppath / "user-profile-feature.md"
        no_header_file.write_text("""Some content without headers.

## Milestone 1
Details here.
""")
        result = extract_feature_from_plan(str(no_header_file))
        assert result == "user profile feature", f"Expected 'user profile feature', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 6: Missing file (filename fallback)
        print("\n✓ Test 6: Missing file (filename fallback)...")
        missing_file = tmppath / "nonexistent-plan.md"
        result = extract_feature_from_plan(str(missing_file))
        assert result == "nonexistent plan", f"Expected 'nonexistent plan', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 7: Strip "Implementation Plan" suffix
        print("\n✓ Test 7: Strip 'Implementation Plan' suffix...")
        suffix_file = tmppath / "suffix-test.md"
        suffix_file.write_text("""# User Dashboard - Implementation Plan

## Overview
Dashboard features.
""")
        result = extract_feature_from_plan(str(suffix_file))
        assert result == "User Dashboard", f"Expected 'User Dashboard', got '{result}'"
        assert "Implementation Plan" not in result
        print(f"  Result: '{result}' ✓")

        # Test 8: Case insensitivity
        print("\n✓ Test 8: Case insensitive matching...")
        case_file = tmppath / "case-test.md"
        case_file.write_text("""# FEATURE: Case Test

Content.
""")
        result = extract_feature_from_plan(str(case_file))
        assert result == "Case Test", f"Expected 'Case Test', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 9: Priority order (YAML > Feature > Implementation Plan > H1)
        print("\n✓ Test 9: Priority order (YAML wins)...")
        priority_file = tmppath / "priority-test.md"
        priority_file.write_text("""---
feature: YAML Priority
---

# Feature: Header Priority

# Plain H1 Title
""")
        result = extract_feature_from_plan(str(priority_file))
        assert result == "YAML Priority", f"Expected 'YAML Priority', got '{result}'"
        print(f"  Result: '{result}' ✓")

        # Test 10: Real-world example from actual plan
        print("\n✓ Test 10: Real-world plan format...")
        real_file = tmppath / "PLAN_queue_feature.md"
        real_file.write_text("""# Plan: Plan Queue Feature (GO-Ready)

Queue multiple plan files for sequential execution.

## Feature Description
Add --queue mode.
""")
        result = extract_feature_from_plan(str(real_file))
        assert "Plan Queue Feature" in result
        print(f"  Result: '{result}' ✓")

        print("\n" + "=" * 60)
        print("✓ ALL FEATURE EXTRACTION TESTS PASSED!")
        print("=" * 60)

if __name__ == "__main__":
    test_feature_extraction()

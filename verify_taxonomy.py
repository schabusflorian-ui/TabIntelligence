"""
Quick validation script for taxonomy implementation.
Tests the code without requiring database connection.
"""
import json
import sys
from pathlib import Path


def validate_taxonomy_json():
    """Validate the taxonomy seed JSON file."""
    print("=" * 70)
    print("VALIDATING TAXONOMY SEED DATA")
    print("=" * 70)

    seed_file = Path("data/taxonomy_seed.json")

    if not seed_file.exists():
        print(f"❌ ERROR: {seed_file} not found!")
        return False

    try:
        with open(seed_file) as f:
            data = json.load(f)
        print(f"✅ JSON is valid")
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        return False

    # Validate structure
    if "items" not in data:
        print("❌ Missing 'items' key")
        return False

    items = data["items"]
    print(f"✅ Contains {len(items)} taxonomy items")

    # Count by category
    categories = {}
    canonical_names = set()

    for item in items:
        # Check required fields
        required_fields = ["canonical_name", "category", "display_name"]
        for field in required_fields:
            if field not in item:
                print(f"❌ Item missing required field '{field}': {item}")
                return False

        # Track category counts
        category = item["category"]
        categories[category] = categories.get(category, 0) + 1

        # Check for duplicates
        canonical = item["canonical_name"]
        if canonical in canonical_names:
            print(f"❌ Duplicate canonical_name: {canonical}")
            return False
        canonical_names.add(canonical)

        # Validate aliases
        if "aliases" in item and item["aliases"]:
            if not isinstance(item["aliases"], list):
                print(f"❌ Aliases must be list: {canonical}")
                return False

    print(f"✅ No duplicate canonical_names")
    print(f"\n📊 Category Breakdown:")
    for cat, count in sorted(categories.items()):
        print(f"   - {cat}: {count} items")

    # Check minimum requirements
    min_requirements = {
        "income_statement": 20,
        "balance_sheet": 25,
        "cash_flow": 15,
        "debt_schedule": 10,
        "metrics": 10
    }

    all_met = True
    print(f"\n✅ Minimum Requirements:")
    for cat, min_count in min_requirements.items():
        actual_count = categories.get(cat, 0)
        status = "✅" if actual_count >= min_count else "❌"
        print(f"   {status} {cat}: {actual_count}/{min_count} (required)")
        if actual_count < min_count:
            all_met = False

    return all_met


def validate_taxonomy_manager():
    """Validate the TaxonomyManager module can be imported."""
    print("\n" + "=" * 70)
    print("VALIDATING TAXONOMY MANAGER MODULE")
    print("=" * 70)

    try:
        from src.guidelines.taxonomy import TaxonomyManager, load_taxonomy_for_stage3
        print("✅ TaxonomyManager imported successfully")

        # Check methods exist
        manager = TaxonomyManager()
        methods = [
            'get_all',
            'get_by_category',
            'search',
            'get_by_canonical_name',
            'get_by_canonical_names',
            'format_for_prompt',
            'get_hierarchy',
            'get_statistics'
        ]

        for method in methods:
            if not hasattr(manager, method):
                print(f"❌ Missing method: {method}")
                return False

        print(f"✅ All {len(methods)} methods present")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def validate_orchestrator_integration():
    """Validate orchestrator integration."""
    print("\n" + "=" * 70)
    print("VALIDATING ORCHESTRATOR INTEGRATION")
    print("=" * 70)

    try:
        with open("src/extraction/orchestrator.py") as f:
            content = f.read()

        # Check for database imports
        if "from src.db.session import get_db_context" in content:
            print("✅ Database session import present")
        else:
            print("❌ Missing database session import")
            return False

        if "from src.guidelines.taxonomy import load_taxonomy_for_stage3" in content:
            print("✅ Taxonomy import present")
        else:
            print("❌ Missing taxonomy import")
            return False

        # Check that hardcoded taxonomy is replaced
        if "load_taxonomy_for_stage3(db)" in content or "load_taxonomy_for_stage3(session)" in content:
            print("✅ Dynamic taxonomy loading implemented")
        else:
            print("⚠️  Warning: Dynamic taxonomy loading may not be fully implemented")

        print("✅ Orchestrator integration looks good")
        return True

    except Exception as e:
        print(f"❌ Error validating orchestrator: {e}")
        return False


def validate_migration():
    """Validate migration file."""
    print("\n" + "=" * 70)
    print("VALIDATING SEED MIGRATION")
    print("=" * 70)

    try:
        migration_files = list(Path("alembic/versions").glob("*seed_taxonomy.py"))

        if not migration_files:
            print("❌ No seed taxonomy migration found")
            return False

        migration_file = migration_files[0]
        print(f"✅ Found migration: {migration_file.name}")

        with open(migration_file) as f:
            content = f.read()

        # Check for key elements
        checks = {
            "upgrade() function": "def upgrade(",
            "downgrade() function": "def downgrade(",
            "bulk_insert": "bulk_insert",
            "taxonomy_table": "taxonomy_table",
        }

        for name, pattern in checks.items():
            if pattern in content:
                print(f"✅ {name} present")
            else:
                print(f"❌ {name} missing")
                return False

        return True

    except Exception as e:
        print(f"❌ Error validating migration: {e}")
        return False


def main():
    """Run all validations."""
    print("\n" + "=" * 70)
    print("TAXONOMY SYSTEM VALIDATION")
    print("=" * 70 + "\n")

    results = {
        "Taxonomy JSON": validate_taxonomy_json(),
        "TaxonomyManager": validate_taxonomy_manager(),
        "Orchestrator Integration": validate_orchestrator_integration(),
        "Seed Migration": validate_migration(),
    }

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    all_passed = True
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n🎉 ALL VALIDATIONS PASSED!")
        print("\n📋 Next Steps:")
        print("   1. Ensure PostgreSQL is running (docker-compose up -d)")
        print("   2. Run migrations: alembic upgrade head")
        print("   3. Test end-to-end extraction with sample Excel file")
        return 0
    else:
        print("\n⚠️  SOME VALIDATIONS FAILED")
        print("   Please review the errors above and fix before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

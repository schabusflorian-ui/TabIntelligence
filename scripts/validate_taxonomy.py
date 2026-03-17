#!/usr/bin/env python3
"""
Taxonomy Validation Script

Comprehensive validation of taxonomy integrity including:
- Schema completeness
- Orphaned parent references
- Circular reference detection
- Hierarchy depth analysis
- Cross-category parent validation
- Duplicate aliases
- Derivation formula validity
- OCR variant quality
- Format example validity
- Industry tag consistency
- Accounting identities
- Category distribution

Usage:
    python scripts/validate_taxonomy.py
    python scripts/validate_taxonomy.py --path data/taxonomy.json
"""

import argparse
import json
import os
import re
import sys

# Allow importing from src/ when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.taxonomy_constants import VALID_CATEGORIES  # noqa: E402


class TaxonomyValidator:
    def __init__(self, taxonomy_path: str = "data/taxonomy.json"):
        with open(taxonomy_path, "r") as f:
            self.data = json.load(f)

        # Flatten categories dict into a single items list
        self.all_items = []
        for category, cat_items in self.data.get("categories", {}).items():
            for item in cat_items:
                item.setdefault("category", category)
                self.all_items.append(item)

        self.items = {item["canonical_name"]: item for item in self.all_items}
        self.errors = []
        self.warnings = []

    def validate_all(self):
        """Run all validation checks."""
        print("=" * 70)
        print("TAXONOMY VALIDATION REPORT")
        print("=" * 70)
        print(f"Version: {self.data.get('version', 'unknown')}")
        print(f"Total items: {len(self.all_items)}")
        print(f"Categories: {len(self.data.get('categories', {}))}")
        print()

        self.check_json_schema()
        self.check_category_distribution()
        self.check_schema_completeness()
        self.check_valid_categories()
        self.check_orphaned_parents()
        self.check_circular_references()
        self.check_hierarchy_depth()
        self.check_cross_category_parents()
        self.check_duplicate_aliases()
        self.check_duplicate_canonical_names()
        self.check_derivation_formulas()
        self.check_ocr_variants()
        self.check_format_examples()
        self.check_industry_tags()
        self.check_accounting_identities()
        self.check_cross_item_validation()

        # Print summary
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        if not self.errors and not self.warnings:
            print("All checks passed!")
        else:
            if self.errors:
                print(f"{len(self.errors)} error(s) found:")
                for error in self.errors:
                    print(f"   - {error}")
            if self.warnings:
                print(f"{len(self.warnings)} warning(s) found:")
                for warning in self.warnings[:10]:
                    print(f"   - {warning}")
                if len(self.warnings) > 10:
                    print(f"   ... and {len(self.warnings) - 10} more warnings")

        return len(self.errors) == 0

    def check_json_schema(self):
        """Validate against JSON Schema (if jsonschema is installed)."""
        print("\n0. JSON SCHEMA VALIDATION")
        print("-" * 70)

        try:
            import jsonschema
        except ImportError:
            print("   SKIP: jsonschema not installed (pip install jsonschema)")
            return

        schema_path = os.path.join(os.path.dirname(__file__), "..", "data", "taxonomy.schema.json")
        if not os.path.exists(schema_path):
            print("   SKIP: data/taxonomy.schema.json not found")
            return

        with open(schema_path, "r") as f:
            schema = json.load(f)

        try:
            jsonschema.validate(self.data, schema)
            print(f"   OK: taxonomy.json validates against JSON Schema")
        except jsonschema.ValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
            self.errors.append(f"JSON Schema: {e.message} (at {path})")
            print(f"   FAIL: {e.message}")

    def check_category_distribution(self):
        """Report category distribution."""
        print("\n1. CATEGORY DISTRIBUTION")
        print("-" * 70)

        category_counts = {}
        for item in self.all_items:
            cat = item.get("category", "UNKNOWN")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        for cat in sorted(category_counts.keys()):
            count = category_counts[cat]
            print(f"   {cat}: {count} items")

    def check_schema_completeness(self):
        """Verify all required fields are present."""
        print("\n2. SCHEMA COMPLETENESS CHECK")
        print("-" * 70)

        required_fields = [
            "canonical_name",
            "category",
            "display_name",
            "aliases",
            "definition",
            "typical_sign",
        ]
        missing_fields = []

        for item in self.all_items:
            for field in required_fields:
                if field not in item:
                    missing_fields.append(f"{item.get('canonical_name', '???')}: missing '{field}'")

        if missing_fields:
            self.errors.extend(missing_fields)
            print(f"   FAIL: {len(missing_fields)} items missing required fields")
        else:
            print(f"   OK: All {len(self.all_items)} items have required fields")

    def check_valid_categories(self):
        """Verify all categories are in the valid set."""
        print("\n3. VALID CATEGORIES CHECK")
        print("-" * 70)

        invalid = []
        for item in self.all_items:
            cat = item.get("category")
            if cat not in VALID_CATEGORIES:
                invalid.append(f"{item['canonical_name']}: invalid category '{cat}'")

        if invalid:
            self.errors.extend(invalid)
            print(f"   FAIL: {len(invalid)} items have invalid categories")
        else:
            print(f"   OK: All items use valid categories")

    def check_orphaned_parents(self):
        """Check for orphaned parent references."""
        print("\n4. ORPHANED PARENT REFERENCES CHECK")
        print("-" * 70)

        canonical_names = set(self.items.keys())
        orphaned = []

        for item in self.all_items:
            parent = item.get("parent_canonical")
            if parent and parent not in canonical_names:
                orphaned.append(f"{item['canonical_name']} -> {parent} (does not exist)")

        if orphaned:
            self.errors.extend(orphaned)
            print(f"   FAIL: {len(orphaned)} orphaned parent references")
            for o in orphaned[:5]:
                print(f"      {o}")
        else:
            items_with_parents = sum(
                1 for item in self.all_items if item.get("parent_canonical")
            )
            print(f"   OK: All {items_with_parents} parent references are valid")

    def check_circular_references(self):
        """Detect circular parent references."""
        print("\n5. CIRCULAR REFERENCE CHECK")
        print("-" * 70)

        circular = []
        for item in self.all_items:
            visited = set()
            current = item["canonical_name"]
            while current:
                if current in visited:
                    circular.append(
                        f"{item['canonical_name']}: circular chain detected at '{current}'"
                    )
                    break
                visited.add(current)
                parent_item = self.items.get(current)
                current = parent_item.get("parent_canonical") if parent_item else None

        if circular:
            self.errors.extend(circular)
            print(f"   FAIL: {len(circular)} circular references detected")
        else:
            print(f"   OK: No circular references")

    def check_hierarchy_depth(self):
        """Analyze hierarchy depth per item."""
        print("\n6. HIERARCHY DEPTH ANALYSIS")
        print("-" * 70)

        max_depth = 0
        depth_counts = {}

        for item in self.all_items:
            depth = 0
            current = item.get("parent_canonical")
            visited = set()
            while current and current in self.items and current not in visited:
                visited.add(current)
                depth += 1
                current = self.items[current].get("parent_canonical")

            depth_counts[depth] = depth_counts.get(depth, 0) + 1
            max_depth = max(max_depth, depth)

        print(f"   Max depth: {max_depth}")
        for d in sorted(depth_counts.keys()):
            print(f"   Depth {d}: {depth_counts[d]} items")

        if max_depth > 4:
            self.warnings.append(f"Hierarchy depth {max_depth} exceeds recommended max of 4")

    def check_cross_category_parents(self):
        """Check that parent items are in the same category."""
        print("\n7. CROSS-CATEGORY PARENT CHECK")
        print("-" * 70)

        cross_cat = []
        for item in self.all_items:
            parent_name = item.get("parent_canonical")
            if parent_name and parent_name in self.items:
                parent = self.items[parent_name]
                if item["category"] != parent.get("category"):
                    cross_cat.append(
                        f"{item['canonical_name']} ({item['category']}) -> "
                        f"{parent_name} ({parent.get('category')})"
                    )

        if cross_cat:
            for cc in cross_cat[:5]:
                self.warnings.append(f"Cross-category parent: {cc}")
            print(f"   WARNING: {len(cross_cat)} cross-category parent references")
        else:
            print(f"   OK: All parent references are within the same category")

    def check_duplicate_aliases(self):
        """Check for duplicate aliases across items."""
        print("\n8. DUPLICATE ALIASES CHECK")
        print("-" * 70)

        alias_to_items = {}
        for item in self.all_items:
            canonical = item["canonical_name"]
            for alias in item.get("aliases", []):
                alias_lower = alias.lower()
                if alias_lower not in alias_to_items:
                    alias_to_items[alias_lower] = []
                alias_to_items[alias_lower].append(canonical)

        duplicates = {alias: items for alias, items in alias_to_items.items() if len(items) > 1}

        if duplicates:
            for alias, items in list(duplicates.items())[:5]:
                self.warnings.append(f"Alias '{alias}' used by: {', '.join(items)}")
            print(f"   WARNING: {len(duplicates)} duplicate aliases found (may be intentional)")
        else:
            print("   OK: No duplicate aliases found")

    def check_duplicate_canonical_names(self):
        """Check for duplicate canonical names."""
        print("\n9. DUPLICATE CANONICAL NAMES CHECK")
        print("-" * 70)

        canonical_names = [item["canonical_name"] for item in self.all_items]
        seen = set()
        duplicates = set()
        for name in canonical_names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)

        if duplicates:
            self.errors.extend([f"Duplicate canonical_name: {name}" for name in duplicates])
            print(f"   FAIL: {len(duplicates)} duplicate canonical names")
        else:
            print(f"   OK: All {len(canonical_names)} canonical names are unique")

    def check_derivation_formulas(self):
        """Validate derivation formulas reference existing items."""
        print("\n10. DERIVATION FORMULAS CHECK")
        print("-" * 70)

        derivations = []
        invalid_refs = []

        for item in self.all_items:
            validation_rules = item.get("validation_rules", {})
            if not isinstance(validation_rules, dict):
                continue
            derivation = validation_rules.get("derivation")

            if derivation:
                derivations.append((item["canonical_name"], derivation))

                # Extract potential canonical names from derivation
                potential_refs = re.findall(r"\b([a-z][a-z_]+)\b", derivation)
                keywords = {"and", "or", "not", "if", "else", "sum", "abs", "max", "min"}
                for ref in potential_refs:
                    if ref not in keywords and ref not in self.items:
                        invalid_refs.append(
                            f"{item['canonical_name']}: derivation references "
                            f"unknown item '{ref}'"
                        )

        print(f"   Found {len(derivations)} derivation formulas")
        if invalid_refs:
            for ref in invalid_refs[:5]:
                self.warnings.append(ref)
            print(f"   WARNING: {len(invalid_refs)} potentially invalid references")
        else:
            print(f"   OK: All derivation references valid")

    def check_ocr_variants(self):
        """Check OCR variants quality."""
        print("\n11. OCR VARIANTS CHECK")
        print("-" * 70)

        items_with_ocr = sum(1 for item in self.all_items if "ocr_variants" in item)
        total_variants = sum(len(item.get("ocr_variants", [])) for item in self.all_items)

        print(f"   {items_with_ocr}/{len(self.all_items)} items have OCR variants")
        print(f"   {total_variants} total OCR variants")

        for item in self.all_items:
            ocr_variants = item.get("ocr_variants", [])
            display_name = item.get("display_name", "")

            for variant in ocr_variants:
                if variant.lower() == display_name.lower():
                    self.warnings.append(
                        f"{item['canonical_name']}: OCR variant '{variant}' identical to display_name"
                    )

    def check_format_examples(self):
        """Validate format examples."""
        print("\n12. FORMAT EXAMPLES CHECK")
        print("-" * 70)

        items_with_examples = sum(1 for item in self.all_items if "format_examples" in item)
        total_examples = sum(len(item.get("format_examples", [])) for item in self.all_items)

        print(f"   {items_with_examples}/{len(self.all_items)} items have format examples")
        print(f"   {total_examples} total format examples")

        for item in self.all_items:
            examples = item.get("format_examples", [])
            for i, example in enumerate(examples):
                if not isinstance(example, dict):
                    self.errors.append(f"{item['canonical_name']}: format_examples[{i}] not a dict")
                elif "value" not in example or "context" not in example:
                    self.errors.append(
                        f"{item['canonical_name']}: format_examples[{i}] missing 'value' or 'context'"
                    )

    def check_industry_tags(self):
        """Validate industry tags."""
        print("\n13. INDUSTRY TAGS CHECK")
        print("-" * 70)

        items_with_tags = sum(1 for item in self.all_items if "industry_tags" in item)
        all_tags = set()

        for item in self.all_items:
            tags = item.get("industry_tags", [])
            all_tags.update(tags)

        print(f"   {items_with_tags}/{len(self.all_items)} items have industry tags")
        print(f"   {len(all_tags)} unique industry tags: {sorted(all_tags)}")

    def check_accounting_identities(self):
        """Check key accounting identities exist."""
        print("\n14. ACCOUNTING IDENTITIES CHECK")
        print("-" * 70)

        identities = [
            ("total_assets", "current_assets + non_current_assets"),
            ("total_liabilities", "current_liabilities + non_current_liabilities"),
            ("total_equity", "total_assets - total_liabilities"),
            ("gross_profit", "revenue - cogs"),
            ("ebit", "ebitda - depreciation - amortization"),
            ("fcf", "cfo - capex"),
        ]

        missing = []
        for item_name, formula in identities:
            if item_name not in self.items:
                missing.append(item_name)

        if missing:
            for m in missing:
                self.warnings.append(f"Key accounting item missing: {m}")
            print(f"   WARNING: {len(missing)} key accounting items missing: {', '.join(missing)}")
        else:
            print("   OK: All key accounting identity items exist")

    def check_cross_item_validation(self):
        """Check cross-item validation rule structure."""
        print("\n15. CROSS-ITEM VALIDATION RULES CHECK")
        print("-" * 70)

        items_with_cross_val = 0
        total_rules = 0

        for item in self.all_items:
            validation_rules = item.get("validation_rules", {})
            if not isinstance(validation_rules, dict):
                continue

            cross_val = validation_rules.get("cross_item_validation", {})
            if not isinstance(cross_val, dict):
                continue

            if cross_val:
                items_with_cross_val += 1

            relationships = cross_val.get("relationships", [])
            if isinstance(relationships, list):
                total_rules += len(relationships)

                for rel in relationships:
                    if isinstance(rel, dict) and "rule" not in rel:
                        self.errors.append(
                            f"{item['canonical_name']}: relationship missing 'rule' field"
                        )

        print(f"   {items_with_cross_val} items have cross-item validation rules")
        print(f"   {total_rules} total cross-item validation relationships")


def main():
    parser = argparse.ArgumentParser(description="Validate taxonomy.json integrity")
    parser.add_argument(
        "--path",
        default="data/taxonomy.json",
        help="Path to taxonomy JSON file (default: data/taxonomy.json)",
    )
    args = parser.parse_args()

    validator = TaxonomyValidator(args.path)
    success = validator.validate_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

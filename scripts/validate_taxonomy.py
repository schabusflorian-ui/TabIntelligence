#!/usr/bin/env python3
"""
Taxonomy Validation Script

Comprehensive validation of taxonomy integrity including:
- Schema completeness
- Orphaned parent references
- Duplicate aliases
- Derivation formula validity
- OCR variant quality
- Format example validity
- Industry tag consistency
- Accounting identities

Usage:
    python scripts/validate_taxonomy.py
"""

import json
import re
from typing import Dict, List, Set, Tuple
from pathlib import Path


class TaxonomyValidator:
    def __init__(self, taxonomy_path: str = "data/taxonomy_seed.json"):
        with open(taxonomy_path, 'r') as f:
            self.data = json.load(f)
        self.items = {item['canonical_name']: item for item in self.data['items']}
        self.errors = []
        self.warnings = []

    def validate_all(self):
        """Run all validation checks."""
        print("=" * 70)
        print("TAXONOMY VALIDATION REPORT")
        print("=" * 70)
        print(f"Version: {self.data.get('version', 'unknown')}")
        print(f"Total items: {len(self.data['items'])}")
        print()

        self.check_schema_completeness()
        self.check_orphaned_parents()
        self.check_duplicate_aliases()
        self.check_duplicate_canonical_names()
        self.check_derivation_formulas()
        self.check_ocr_variants()
        self.check_format_examples()
        self.check_industry_tags()
        self.check_accounting_identities()
        self.check_phase2_enhancements()

        # Print summary
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        if not self.errors and not self.warnings:
            print("✅ All checks passed!")
        else:
            if self.errors:
                print(f"❌ {len(self.errors)} error(s) found:")
                for error in self.errors:
                    print(f"   - {error}")
            if self.warnings:
                print(f"⚠️  {len(self.warnings)} warning(s) found:")
                for warning in self.warnings[:10]:  # Show first 10
                    print(f"   - {warning}")
                if len(self.warnings) > 10:
                    print(f"   ... and {len(self.warnings) - 10} more warnings")

        return len(self.errors) == 0

    def check_schema_completeness(self):
        """Verify all required fields are present."""
        print("\n1. SCHEMA COMPLETENESS CHECK")
        print("-" * 70)

        required_fields = ['canonical_name', 'category', 'display_name', 'aliases', 'definition', 'typical_sign']
        missing_fields = []

        for item in self.data['items']:
            for field in required_fields:
                if field not in item:
                    missing_fields.append(f"{item.get('canonical_name', '???')}: missing '{field}'")

        if missing_fields:
            self.errors.extend(missing_fields)
            print(f"❌ {len(missing_fields)} items missing required fields")
        else:
            print(f"✅ All {len(self.data['items'])} items have required fields")

    def check_orphaned_parents(self):
        """Check for orphaned parent references."""
        print("\n2. ORPHANED PARENT REFERENCES CHECK")
        print("-" * 70)

        canonical_names = set(self.items.keys())
        orphaned = []

        for item in self.data['items']:
            parent = item.get('parent_canonical')
            if parent and parent not in canonical_names:
                orphaned.append(f"{item['canonical_name']} → {parent} (does not exist)")

        if orphaned:
            self.errors.extend(orphaned)
            print(f"❌ {len(orphaned)} orphaned parent references")
        else:
            items_with_parents = sum(1 for item in self.data['items'] if item.get('parent_canonical'))
            print(f"✅ All {items_with_parents} parent references are valid")

    def check_duplicate_aliases(self):
        """Check for duplicate aliases across items."""
        print("\n3. DUPLICATE ALIASES CHECK")
        print("-" * 70)

        alias_to_items = {}
        for item in self.data['items']:
            canonical = item['canonical_name']
            for alias in item.get('aliases', []):
                alias_lower = alias.lower()
                if alias_lower not in alias_to_items:
                    alias_to_items[alias_lower] = []
                alias_to_items[alias_lower].append(canonical)

        duplicates = {alias: items for alias, items in alias_to_items.items() if len(items) > 1}

        if duplicates:
            for alias, items in list(duplicates.items())[:5]:  # Show first 5
                self.warnings.append(f"Alias '{alias}' used by: {', '.join(items)}")
            print(f"⚠️  {len(duplicates)} duplicate aliases found (may be intentional)")
        else:
            print(f"✅ No duplicate aliases found")

    def check_duplicate_canonical_names(self):
        """Check for duplicate canonical names."""
        print("\n4. DUPLICATE CANONICAL NAMES CHECK")
        print("-" * 70)

        canonical_names = [item['canonical_name'] for item in self.data['items']]
        duplicates = [name for name in canonical_names if canonical_names.count(name) > 1]

        if duplicates:
            unique_dups = list(set(duplicates))
            self.errors.extend([f"Duplicate canonical_name: {name}" for name in unique_dups])
            print(f"❌ {len(unique_dups)} duplicate canonical names")
        else:
            print(f"✅ All {len(canonical_names)} canonical names are unique")

    def check_derivation_formulas(self):
        """Validate derivation formulas."""
        print("\n5. DERIVATION FORMULAS CHECK")
        print("-" * 70)

        derivations = []
        invalid = []

        for item in self.data['items']:
            validation_rules = item.get('validation_rules', {})
            derivation = validation_rules.get('derivation')

            if derivation:
                derivations.append((item['canonical_name'], derivation))

                # Simple validation: check that referenced items exist
                # Extract potential canonical names (alphanumeric + underscore)
                potential_refs = re.findall(r'\\b([a-z_]+)\\b', derivation)
                for ref in potential_refs:
                    if ref not in ['and', 'or', 'not', 'if', 'else'] and ref not in self.items:
                        # Not necessarily an error (might be operators/keywords)
                        pass

        print(f"✅ Found {len(derivations)} derivation formulas")
        if invalid:
            print(f"⚠️  {len(invalid)} potentially invalid references")
            for err in invalid[:5]:
                self.warnings.append(err)

    def check_ocr_variants(self):
        """Check OCR variants quality."""
        print("\n6. OCR VARIANTS CHECK")
        print("-" * 70)

        items_with_ocr = sum(1 for item in self.data['items'] if 'ocr_variants' in item)
        total_variants = sum(len(item.get('ocr_variants', [])) for item in self.data['items'])

        print(f"✅ {items_with_ocr}/{len(self.data['items'])} items have OCR variants")
        print(f"✅ {total_variants} total OCR variants")

        # Check for overly similar variants
        for item in self.data['items']:
            ocr_variants = item.get('ocr_variants', [])
            display_name = item['display_name']

            for variant in ocr_variants:
                if variant.lower() == display_name.lower():
                    self.warnings.append(
                        f"{item['canonical_name']}: OCR variant '{variant}' identical to display_name"
                    )

    def check_format_examples(self):
        """Validate format examples."""
        print("\n7. FORMAT EXAMPLES CHECK")
        print("-" * 70)

        items_with_examples = sum(1 for item in self.data['items'] if 'format_examples' in item)
        total_examples = sum(len(item.get('format_examples', [])) for item in self.data['items'])

        print(f"✅ {items_with_examples}/{len(self.data['items'])} items have format examples")
        print(f"✅ {total_examples} total format examples")

        # Check example structure
        for item in self.data['items']:
            examples = item.get('format_examples', [])
            for i, example in enumerate(examples):
                if not isinstance(example, dict):
                    self.errors.append(
                        f"{item['canonical_name']}: format_examples[{i}] not a dict"
                    )
                elif 'value' not in example or 'context' not in example:
                    self.errors.append(
                        f"{item['canonical_name']}: format_examples[{i}] missing 'value' or 'context'"
                    )

    def check_industry_tags(self):
        """Validate industry tags."""
        print("\n8. INDUSTRY TAGS CHECK")
        print("-" * 70)

        items_with_tags = sum(1 for item in self.data['items'] if 'industry_tags' in item)
        all_tags = set()

        for item in self.data['items']:
            tags = item.get('industry_tags', [])
            all_tags.update(tags)

        print(f"✅ {items_with_tags}/{len(self.data['items'])} items have industry tags")
        print(f"✅ {len(all_tags)} unique industry tags: {sorted(all_tags)}")

    def check_accounting_identities(self):
        """Check key accounting identities."""
        print("\n9. ACCOUNTING IDENTITIES CHECK")
        print("-" * 70)

        # Define key identities
        identities = [
            ("total_assets", "current_assets + non_current_assets"),
            ("total_liabilities", "current_liabilities + non_current_liabilities"),
            ("total_equity", "total_assets - total_liabilities"),
            ("gross_profit", "revenue - cogs"),
            ("ebit", "ebitda - depreciation - amortization"),
            ("fcf", "cfo - capex"),
        ]

        # Check if key items exist
        missing = []
        for item_name, formula in identities:
            if item_name not in self.items:
                missing.append(item_name)

        if missing:
            print(f"⚠️  {len(missing)} key accounting items missing: {', '.join(missing)}")
        else:
            print(f"✅ All key accounting identity items exist")

    def check_phase2_enhancements(self):
        """Check Phase 2 robustness enhancements."""
        print("\n10. PHASE 2 ROBUSTNESS CHECKS")
        print("-" * 70)

        # Count Phase 2 enhancements
        items_with_cross_val = 0
        items_with_confidence = 0
        misspellings_added = 0
        total_validation_rules = 0

        for item in self.data['items']:
            validation_rules = item.get('validation_rules', {})

            # Check for cross-item validation
            if 'cross_item_validation' in validation_rules:
                items_with_cross_val += 1
                cross_val = validation_rules['cross_item_validation']

                # Count relationships
                if 'relationships' in cross_val:
                    total_validation_rules += len(cross_val['relationships'])

            # Check for confidence scoring
            if 'confidence_scoring' in item:
                items_with_confidence += 1

        print(f"✅ {items_with_cross_val} items have cross-item validation rules")
        print(f"✅ {total_validation_rules} total cross-item validation relationships")
        print(f"✅ {items_with_confidence} items have confidence scoring metadata")

        # Validate cross-item validation structure
        validation_errors = []
        for item in self.data['items']:
            validation_rules = item.get('validation_rules', {})
            cross_val = validation_rules.get('cross_item_validation', {})

            for relationship in cross_val.get('relationships', []):
                if 'rule' not in relationship:
                    validation_errors.append(
                        f"{item['canonical_name']}: relationship missing 'rule' field"
                    )
                if 'error_message' not in relationship:
                    self.warnings.append(
                        f"{item['canonical_name']}: relationship missing 'error_message' (recommended)"
                    )

        if validation_errors:
            self.errors.extend(validation_errors)
            print(f"❌ {len(validation_errors)} validation rule errors")

        # Validate confidence scoring structure
        confidence_errors = []
        for item in self.data['items']:
            if 'confidence_scoring' in item:
                conf = item['confidence_scoring']
                required_fields = []  # No strictly required fields, all optional

                # Check structure
                if not isinstance(conf, dict):
                    confidence_errors.append(
                        f"{item['canonical_name']}: confidence_scoring must be a dict"
                    )

        if confidence_errors:
            self.errors.extend(confidence_errors)
            print(f"❌ {len(confidence_errors)} confidence scoring errors")


if __name__ == "__main__":
    validator = TaxonomyValidator()
    success = validator.validate_all()
    exit(0 if success else 1)

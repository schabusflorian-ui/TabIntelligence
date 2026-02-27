#!/usr/bin/env python3
"""
Proof of Concept: Guided Extraction with Claude

Usage:
    python scripts/poc_guided_extraction.py <excel_file>
    python scripts/poc_guided_extraction.py tests/fixtures/sample_model.xlsx
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/poc_guided_extraction.py <excel_file>")
        print("\nThis script tests Claude's guided extraction on an Excel file.")
        print("\nIf you don't have a test file, run:")
        print("  python scripts/create_test_model.py")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        print("1. Get your key from console.anthropic.com")
        print("2. Add to .env file: ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)
    
    print(f"Testing guided extraction on: {file_path}")
    print("=" * 60)
    
    # Read file
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    
    print(f"File size: {len(file_bytes):,} bytes")
    print()
    
    # Run extraction
    from src.extraction.orchestrator import extract
    
    result = await extract(file_bytes, file_id="test-123", entity_id="test-entity")
    
    # Print results
    print("\n" + "=" * 60)
    print("EXTRACTION RESULTS")
    print("=" * 60)
    
    print(f"\nSheets found: {len(result['sheets'])}")
    for sheet in result['sheets']:
        print(f"  - {sheet}")
    
    print(f"\nTriage results:")
    for t in result['triage']:
        tier = t.get('tier', '?')
        decision = t.get('decision', '?')
        print(f"  - {t['sheet_name']}: Tier {tier} ({decision})")
    
    print(f"\nLine items extracted: {len(result['line_items'])}")
    
    # Show sample of mapped items
    mapped = [li for li in result['line_items'] if li['canonical_name'] != 'unmapped']
    print(f"Successfully mapped: {len(mapped)}")
    
    if mapped:
        print("\nSample mappings:")
        for item in mapped[:10]:
            print(f"  {item['original_label'][:30]:30} → {item['canonical_name']:20} ({item['confidence']:.0%})")
    
    # Show unmapped
    unmapped = [li for li in result['line_items'] if li['canonical_name'] == 'unmapped']
    if unmapped:
        print(f"\nUnmapped items ({len(unmapped)}):")
        for item in unmapped[:5]:
            print(f"  - {item['original_label']}")
    
    print(f"\n" + "=" * 60)
    print(f"COST SUMMARY")
    print(f"=" * 60)
    print(f"Tokens used: {result['tokens_used']:,}")
    print(f"Estimated cost: ${result['cost_usd']:.4f}")
    
    # Save full results
    output_path = Path(file_path).stem + "_extraction.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nFull results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

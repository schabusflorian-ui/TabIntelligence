"""
Taxonomy Manager - Agent 4: Guidelines Manager

Provides access to the canonical financial taxonomy for extraction guidance.
Supports querying, searching, and formatting taxonomy for Claude prompts.
"""
from typing import List, Optional, Dict, Any
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func

from src.db.models import Taxonomy
from src.core.logging import get_logger

logger = get_logger(__name__)


class TaxonomyManager:
    """
    Agent 4: Guidelines Manager - Taxonomy Operations.

    Provides high-level API for accessing and querying the canonical
    financial taxonomy from the database.
    """

    def get_all(self, session: Session) -> List[Taxonomy]:
        """
        Retrieve all taxonomy items ordered by category, then canonical_name.

        Args:
            session: Database session

        Returns:
            List of all Taxonomy objects sorted by category and name

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                all_items = manager.get_all(db)
                print(f"Total taxonomy items: {len(all_items)}")
        """
        logger.debug("Fetching all taxonomy items")

        stmt = select(Taxonomy).order_by(Taxonomy.category, Taxonomy.canonical_name)
        result = session.execute(stmt)
        items = list(result.scalars().all())

        logger.info(f"Retrieved {len(items)} taxonomy items")
        return items

    def get_by_category(
        self, session: Session, category: str
    ) -> List[Taxonomy]:
        """
        Get taxonomy items for a specific category.

        Args:
            session: Database session
            category: Category to filter by (e.g., 'income_statement', 'balance_sheet')

        Returns:
            List of Taxonomy objects in the specified category

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                income_items = manager.get_by_category(db, "income_statement")
                print(f"Income statement items: {len(income_items)}")
        """
        logger.debug(f"Fetching taxonomy items for category: {category}")

        stmt = (
            select(Taxonomy)
            .where(Taxonomy.category == category)
            .order_by(Taxonomy.canonical_name)
        )
        result = session.execute(stmt)
        items = list(result.scalars().all())

        logger.info(f"Retrieved {len(items)} items for category '{category}'")
        return items

    def search(self, session: Session, query: str) -> List[Taxonomy]:
        """
        Search taxonomy by name or alias (case-insensitive).

        Searches across canonical_name, display_name, and aliases JSON array.

        Args:
            session: Database session
            query: Search term (case-insensitive)

        Returns:
            List of matching Taxonomy objects

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                # Search for "sales" - will find "revenue" via alias
                results = manager.search(db, "sales")
                for item in results:
                    print(f"{item.canonical_name}: {item.display_name}")
        """
        logger.debug(f"Searching taxonomy for: '{query}'")

        query_lower = query.lower()

        # Search in canonical_name, display_name, and aliases JSON array
        # For aliases (JSON column), cast to text and use ILIKE for substring matching
        stmt = select(Taxonomy).where(
            or_(
                func.lower(Taxonomy.canonical_name).contains(query_lower),
                func.lower(Taxonomy.display_name).contains(query_lower),
                func.cast(Taxonomy.aliases, sa.Text).ilike(f"%{query_lower}%"),
            )
        )

        result = session.execute(stmt)
        items = list(result.scalars().all())

        logger.info(f"Found {len(items)} taxonomy items matching '{query}'")
        return items

    def get_by_canonical_name(
        self, session: Session, canonical_name: str
    ) -> Optional[Taxonomy]:
        """
        Get specific taxonomy item by canonical name.

        Args:
            session: Database session
            canonical_name: Exact canonical name to look up

        Returns:
            Taxonomy object if found, None otherwise

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                revenue = manager.get_by_canonical_name(db, "revenue")
                if revenue:
                    print(f"Found: {revenue.display_name}")
                    print(f"Aliases: {revenue.aliases}")
        """
        logger.debug(f"Fetching taxonomy item: {canonical_name}")

        stmt = select(Taxonomy).where(Taxonomy.canonical_name == canonical_name)
        result = session.execute(stmt)
        item = result.scalar_one_or_none()

        if item:
            logger.debug(f"Found taxonomy item: {canonical_name}")
        else:
            logger.warning(f"Taxonomy item not found: {canonical_name}")

        return item

    def get_by_canonical_names(
        self, session: Session, canonical_names: List[str]
    ) -> List[Taxonomy]:
        """
        Get multiple taxonomy items by canonical names (batch lookup).

        Args:
            session: Database session
            canonical_names: List of canonical names to look up

        Returns:
            List of Taxonomy objects found (may be shorter than input list)

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                items = manager.get_by_canonical_names(
                    db, ["revenue", "cogs", "gross_profit"]
                )
        """
        logger.debug(f"Fetching {len(canonical_names)} taxonomy items")

        stmt = select(Taxonomy).where(
            Taxonomy.canonical_name.in_(canonical_names)
        )
        result = session.execute(stmt)
        items = list(result.scalars().all())

        logger.info(f"Found {len(items)}/{len(canonical_names)} taxonomy items")
        return items

    def format_for_prompt(
        self, session: Session, category: Optional[str] = None
    ) -> str:
        """
        Format taxonomy for Claude prompt.

        Creates a condensed string representation suitable for including
        in extraction prompts. Groups items by category and lists
        canonical names.

        Args:
            session: Database session
            category: Optional category filter. If None, returns all categories.

        Returns:
            Formatted string like:
            '''
            Income Statement: revenue, cogs, gross_profit, opex, sga, ...
            Balance Sheet: cash, accounts_receivable, inventory, ...
            Cash Flow: cfo, capex, cfi, cff, fcf, net_change_cash
            '''

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                # Get all taxonomy formatted
                prompt_text = manager.format_for_prompt(db)
                # Or get just one category
                bs_text = manager.format_for_prompt(db, "balance_sheet")
        """
        logger.debug(f"Formatting taxonomy for prompt (category={category})")

        if category:
            items = self.get_by_category(session, category)
            categories = {category: items}
        else:
            all_items = self.get_all(session)
            # Group by category
            categories: Dict[str, List[Taxonomy]] = {}
            for item in all_items:
                if item.category not in categories:
                    categories[item.category] = []
                categories[item.category].append(item)

        # Format as prompt text
        lines = []
        category_names = {
            "income_statement": "Income Statement",
            "balance_sheet": "Balance Sheet",
            "cash_flow": "Cash Flow",
            "debt_schedule": "Debt Schedule",
            "depreciation_amortization": "Depreciation & Amortization",
            "working_capital": "Working Capital",
            "assumptions": "Assumptions",
            "metrics": "Metrics",
        }

        # Sort categories for consistent output
        sorted_categories = sorted(categories.keys())

        for cat in sorted_categories:
            items = categories[cat]
            display_name = category_names.get(cat, cat.replace("_", " ").title())
            canonical_names = [item.canonical_name for item in items]
            line = f"{display_name}: {', '.join(canonical_names)}"
            lines.append(line)

        result = "\n".join(lines)
        logger.debug(f"Formatted {len(lines)} category lines for prompt")
        return result

    def get_hierarchy(
        self, session: Session, category: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get taxonomy with hierarchical parent-child relationships.

        Returns nested structure showing parent-child relationships
        using the parent_canonical field.

        Args:
            session: Database session
            category: Optional category filter

        Returns:
            Dictionary mapping top-level canonical names to their metadata
            and children:
            {
                'revenue': {
                    'item': <Taxonomy object>,
                    'children': [<product_revenue>, <service_revenue>, ...]
                },
                'cogs': {
                    'item': <Taxonomy object>,
                    'children': [<material_costs>, <labor_costs>, ...]
                }
            }

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                hierarchy = manager.get_hierarchy(db, "income_statement")
                for parent_name, data in hierarchy.items():
                    print(f"{parent_name}:")
                    for child in data['children']:
                        print(f"  - {child.canonical_name}")
        """
        logger.debug(f"Building taxonomy hierarchy (category={category})")

        items = (
            self.get_by_category(session, category)
            if category
            else self.get_all(session)
        )

        # Build hierarchy
        hierarchy: Dict[str, Dict[str, Any]] = {}
        items_by_name = {item.canonical_name: item for item in items}

        # First pass: identify top-level items (no parent)
        for item in items:
            if item.parent_canonical is None:
                hierarchy[item.canonical_name] = {
                    "item": item,
                    "children": [],
                }

        # Second pass: attach children to parents
        for item in items:
            if item.parent_canonical and item.parent_canonical in hierarchy:
                hierarchy[item.parent_canonical]["children"].append(item)

        logger.info(f"Built hierarchy with {len(hierarchy)} top-level items")
        return hierarchy

    def get_statistics(self, session: Session) -> Dict[str, Any]:
        """
        Get taxonomy statistics (counts by category, etc.).

        Args:
            session: Database session

        Returns:
            Dictionary with taxonomy statistics:
            {
                'total_items': 110,
                'categories': {
                    'income_statement': 30,
                    'balance_sheet': 35,
                    ...
                }
            }

        Example:
            with get_db_context() as db:
                manager = TaxonomyManager()
                stats = manager.get_statistics(db)
                print(f"Total items: {stats['total_items']}")
                for cat, count in stats['categories'].items():
                    print(f"{cat}: {count}")
        """
        logger.debug("Calculating taxonomy statistics")

        all_items = self.get_all(session)

        # Count by category
        category_counts: Dict[str, int] = {}
        for item in all_items:
            category_counts[item.category] = category_counts.get(item.category, 0) + 1

        stats = {
            "total_items": len(all_items),
            "categories": category_counts,
        }

        logger.info(f"Taxonomy statistics: {stats['total_items']} total items")
        return stats


# Convenience function for Stage 3 mapping
def load_taxonomy_for_stage3(session: Session) -> str:
    """
    Load and format taxonomy for Stage 3 mapping prompt.

    This is a convenience function that creates a TaxonomyManager
    and formats the complete taxonomy for use in extraction prompts.

    Args:
        session: Database session

    Returns:
        Formatted taxonomy string ready for Claude prompt

    Example:
        from src.db.session import get_db_context
        from src.guidelines.taxonomy import load_taxonomy_for_stage3

        with get_db_context() as db:
            taxonomy_text = load_taxonomy_for_stage3(db)
            prompt = f'''
            Map these financial line items to canonical names.

            CANONICAL TAXONOMY (use these exact names):
            {taxonomy_text}

            Line items to map: ...
            '''
    """
    logger.debug("Loading taxonomy for Stage 3 mapping")

    manager = TaxonomyManager()
    taxonomy_text = manager.format_for_prompt(session)

    logger.info("Taxonomy loaded successfully for Stage 3")
    return taxonomy_text

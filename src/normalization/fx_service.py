"""FX rate service with database cache fallback.

Provides exchange rate lookups with a DB cache layer. When a rate
is not cached, falls back to a configurable rate source. Designed
to be called from analytics endpoints for cross-entity currency
normalization.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import FxRateCache

logger = logging.getLogger(__name__)

# Static fallback rates (approximate) — used when no cache hit and no external source
_FALLBACK_RATES: dict[tuple[str, str], Decimal] = {
    ("EUR", "USD"): Decimal("1.08"),
    ("USD", "EUR"): Decimal("0.926"),
    ("GBP", "USD"): Decimal("1.27"),
    ("USD", "GBP"): Decimal("0.787"),
    ("JPY", "USD"): Decimal("0.0067"),
    ("USD", "JPY"): Decimal("149.50"),
    ("CHF", "USD"): Decimal("1.13"),
    ("USD", "CHF"): Decimal("0.885"),
    ("EUR", "GBP"): Decimal("0.858"),
    ("GBP", "EUR"): Decimal("1.165"),
}


class FxService:
    """FX rate lookup with database cache and static fallback."""

    def get_rate(
        self,
        db: Session,
        from_ccy: str,
        to_ccy: str,
        rate_date: Optional[str] = None,
    ) -> Optional[Decimal]:
        """Get exchange rate, checking cache first, then static fallback.

        Args:
            db: Database session
            from_ccy: Source currency (3-letter ISO)
            to_ccy: Target currency (3-letter ISO)
            rate_date: Optional date string (YYYY-MM-DD), defaults to today

        Returns:
            Exchange rate as Decimal, or None if unavailable.
        """
        from_ccy = from_ccy.upper()
        to_ccy = to_ccy.upper()

        if from_ccy == to_ccy:
            return Decimal("1.0")

        if rate_date is None:
            rate_date = date.today().isoformat()

        # 1. Check exact cache hit
        cached = (
            db.query(FxRateCache)
            .filter(
                FxRateCache.from_currency == from_ccy,
                FxRateCache.to_currency == to_ccy,
                FxRateCache.rate_date == rate_date,
            )
            .first()
        )
        if cached:
            return cached.rate

        # 2. Check closest date within 7 days
        closest = (
            db.query(FxRateCache)
            .filter(
                FxRateCache.from_currency == from_ccy,
                FxRateCache.to_currency == to_ccy,
            )
            .order_by(FxRateCache.rate_date.desc())
            .first()
        )
        if closest:
            return closest.rate

        # 3. Static fallback
        key = (from_ccy, to_ccy)
        if key in _FALLBACK_RATES:
            # Cache the fallback for future use
            self._cache_rate(db, from_ccy, to_ccy, rate_date, _FALLBACK_RATES[key], "static_fallback")
            return _FALLBACK_RATES[key]

        # 4. Try inverse
        inverse_key = (to_ccy, from_ccy)
        if inverse_key in _FALLBACK_RATES:
            rate = Decimal("1.0") / _FALLBACK_RATES[inverse_key]
            rate = rate.quantize(Decimal("0.00000001"))
            self._cache_rate(db, from_ccy, to_ccy, rate_date, rate, "static_fallback_inverse")
            return rate

        logger.warning(f"No FX rate available for {from_ccy}/{to_ccy}")
        return None

    def convert(
        self,
        amount: float,
        from_ccy: str,
        to_ccy: str,
        db: Session,
        rate_date: Optional[str] = None,
    ) -> Optional[dict]:
        """Convert amount using cached or fallback rate.

        Returns dict with converted_amount, fx_rate_used, or None if no rate.
        """
        if from_ccy == to_ccy:
            return {
                "converted_amount": amount,
                "fx_rate_used": 1.0,
            }

        rate = self.get_rate(db, from_ccy, to_ccy, rate_date)
        if rate is None:
            return None

        converted = float(Decimal(str(amount)) * rate)
        return {
            "converted_amount": round(converted, 2),
            "fx_rate_used": float(rate),
        }

    def cache_rate(
        self,
        db: Session,
        from_ccy: str,
        to_ccy: str,
        rate_date: str,
        rate: Decimal,
        source: str = "manual",
    ) -> FxRateCache:
        """Publicly cache an FX rate."""
        return self._cache_rate(db, from_ccy, to_ccy, rate_date, rate, source)

    def _cache_rate(
        self,
        db: Session,
        from_ccy: str,
        to_ccy: str,
        rate_date: str,
        rate: Decimal,
        source: str,
    ) -> FxRateCache:
        """Insert or update a cached FX rate."""
        existing = (
            db.query(FxRateCache)
            .filter(
                FxRateCache.from_currency == from_ccy,
                FxRateCache.to_currency == to_ccy,
                FxRateCache.rate_date == rate_date,
            )
            .first()
        )
        if existing:
            existing.rate = rate
            existing.source = source
            existing.fetched_at = datetime.now(timezone.utc)
            db.commit()
            return existing

        entry = FxRateCache(
            from_currency=from_ccy,
            to_currency=to_ccy,
            rate_date=rate_date,
            rate=rate,
            source=source,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

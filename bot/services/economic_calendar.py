"""
Economic Calendar Service - Provides real economic event data for News Protection.

Sources:
1. LOCAL_EVENTS - Hardcoded major events (FOMC, CPI, NFP) for 2024-2025
2. Forex Factory RSS - Live calendar feed
3. Heuristics - Backup pattern-based detection

Author: ASE BOT Trading System
Version: 1.0
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import re
from functools import lru_cache

logger = logging.getLogger(__name__)


class EventImpact(Enum):
    """Economic event impact level."""
    HIGH = "high"      # Red - Major market mover
    MEDIUM = "medium"  # Orange - Moderate impact
    LOW = "low"        # Yellow - Minor impact


@dataclass
class EconomicEvent:
    """Represents an economic calendar event."""
    name: str
    datetime_utc: datetime
    impact: EventImpact
    currency: str = "USD"
    forecast: Optional[str] = None
    previous: Optional[str] = None
    
    def minutes_until(self, now: datetime = None) -> float:
        """Calculate minutes until this event."""
        if now is None:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        delta = self.datetime_utc - now
        return delta.total_seconds() / 60


# =============================================================================
# LOCAL EVENTS DATABASE 2024-2025
# =============================================================================

# FOMC Meeting Dates 2024-2025 (announcement at 19:00 UTC / 14:00 EST)
FOMC_DATES_2024_2025 = [
    # 2024 (remaining)
    datetime(2024, 12, 18, 19, 0, tzinfo=timezone.utc),
    # 2025
    datetime(2025, 1, 29, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 3, 19, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 5, 7, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 6, 18, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 7, 30, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 9, 17, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 10, 29, 19, 0, tzinfo=timezone.utc),
    datetime(2025, 12, 17, 19, 0, tzinfo=timezone.utc),
]

# CPI Release Dates 2024-2025 (release at 13:30 UTC / 8:30 EST)
CPI_DATES_2024_2025 = [
    # 2024 (remaining)
    datetime(2024, 12, 11, 13, 30, tzinfo=timezone.utc),
    # 2025
    datetime(2025, 1, 15, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 2, 12, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 3, 12, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 4, 10, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 5, 13, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 6, 11, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 7, 10, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 8, 12, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 9, 10, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 10, 10, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 11, 12, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 12, 10, 13, 30, tzinfo=timezone.utc),
]

# NFP (Non-Farm Payrolls) - First Friday of each month at 13:30 UTC
NFP_DATES_2024_2025 = [
    # 2024 (remaining)
    datetime(2024, 12, 6, 13, 30, tzinfo=timezone.utc),
    # 2025
    datetime(2025, 1, 10, 13, 30, tzinfo=timezone.utc),  # Second Friday (holiday adjustment)
    datetime(2025, 2, 7, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 3, 7, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 4, 4, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 5, 2, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 6, 6, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 7, 3, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 8, 1, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 9, 5, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 10, 3, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 11, 7, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 12, 5, 13, 30, tzinfo=timezone.utc),
]

# PPI (Producer Price Index) - Usually day after CPI at 13:30 UTC
PPI_DATES_2024_2025 = [
    # 2024 (remaining)
    datetime(2024, 12, 12, 13, 30, tzinfo=timezone.utc),
    # 2025
    datetime(2025, 1, 14, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 2, 13, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 3, 13, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 4, 11, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 5, 15, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 6, 12, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 7, 15, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 8, 14, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 9, 11, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 10, 14, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 11, 13, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 12, 11, 13, 30, tzinfo=timezone.utc),
]

# Retail Sales - Usually ~15th of month at 13:30 UTC
RETAIL_SALES_DATES_2025 = [
    datetime(2025, 1, 16, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 2, 14, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 3, 17, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 4, 16, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 5, 15, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 6, 17, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 7, 16, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 8, 14, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 9, 16, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 10, 16, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 11, 14, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 12, 16, 13, 30, tzinfo=timezone.utc),
]

# GDP Releases (Advance, Preliminary, Final) - Various dates
GDP_DATES_2025 = [
    datetime(2025, 1, 30, 13, 30, tzinfo=timezone.utc),   # Q4 2024 Advance
    datetime(2025, 2, 27, 13, 30, tzinfo=timezone.utc),   # Q4 2024 Second
    datetime(2025, 3, 27, 13, 30, tzinfo=timezone.utc),   # Q4 2024 Final
    datetime(2025, 4, 30, 13, 30, tzinfo=timezone.utc),   # Q1 2025 Advance
    datetime(2025, 5, 29, 13, 30, tzinfo=timezone.utc),   # Q1 2025 Second
    datetime(2025, 6, 26, 13, 30, tzinfo=timezone.utc),   # Q1 2025 Final
    datetime(2025, 7, 30, 13, 30, tzinfo=timezone.utc),   # Q2 2025 Advance
    datetime(2025, 8, 28, 13, 30, tzinfo=timezone.utc),   # Q2 2025 Second
    datetime(2025, 9, 25, 13, 30, tzinfo=timezone.utc),   # Q2 2025 Final
    datetime(2025, 10, 30, 13, 30, tzinfo=timezone.utc),  # Q3 2025 Advance
    datetime(2025, 11, 26, 13, 30, tzinfo=timezone.utc),  # Q3 2025 Second
    datetime(2025, 12, 23, 13, 30, tzinfo=timezone.utc),  # Q3 2025 Final
]

# PCE (Personal Consumption Expenditures) - Fed's preferred inflation gauge
PCE_DATES_2025 = [
    datetime(2025, 1, 31, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 2, 28, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 3, 28, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 4, 30, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 5, 30, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 6, 27, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 7, 31, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 8, 29, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 9, 26, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 10, 31, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 11, 26, 13, 30, tzinfo=timezone.utc),
    datetime(2025, 12, 24, 13, 30, tzinfo=timezone.utc),
]


def _build_local_events() -> List[EconomicEvent]:
    """Build list of all local economic events."""
    events = []
    
    # FOMC - Highest impact
    for dt in FOMC_DATES_2024_2025:
        events.append(EconomicEvent(
            name="FOMC Interest Rate Decision",
            datetime_utc=dt,
            impact=EventImpact.HIGH,
            currency="USD"
        ))
    
    # CPI - High impact
    for dt in CPI_DATES_2024_2025:
        events.append(EconomicEvent(
            name="CPI (Consumer Price Index)",
            datetime_utc=dt,
            impact=EventImpact.HIGH,
            currency="USD"
        ))
    
    # NFP - High impact
    for dt in NFP_DATES_2024_2025:
        events.append(EconomicEvent(
            name="NFP (Non-Farm Payrolls)",
            datetime_utc=dt,
            impact=EventImpact.HIGH,
            currency="USD"
        ))
    
    # PPI - Medium-High impact
    for dt in PPI_DATES_2024_2025:
        events.append(EconomicEvent(
            name="PPI (Producer Price Index)",
            datetime_utc=dt,
            impact=EventImpact.MEDIUM,
            currency="USD"
        ))
    
    # Retail Sales - Medium impact
    for dt in RETAIL_SALES_DATES_2025:
        events.append(EconomicEvent(
            name="Retail Sales",
            datetime_utc=dt,
            impact=EventImpact.MEDIUM,
            currency="USD"
        ))
    
    # GDP - High impact
    for dt in GDP_DATES_2025:
        events.append(EconomicEvent(
            name="GDP Release",
            datetime_utc=dt,
            impact=EventImpact.HIGH,
            currency="USD"
        ))
    
    # PCE - High impact (Fed's preferred measure)
    for dt in PCE_DATES_2025:
        events.append(EconomicEvent(
            name="PCE Price Index",
            datetime_utc=dt,
            impact=EventImpact.HIGH,
            currency="USD"
        ))
    
    return sorted(events, key=lambda e: e.datetime_utc)


# Pre-build local events cache
LOCAL_EVENTS: List[EconomicEvent] = _build_local_events()


class EconomicCalendarService:
    """
    Service for fetching economic calendar events.
    
    Priority:
    1. Local hardcoded events (most reliable)
    2. Forex Factory RSS feed (live data)
    3. Pattern-based heuristics (fallback)
    """
    
    # Forex Factory RSS URL
    FOREX_FACTORY_RSS = "https://www.forexfactory.com/ffcal_week_this.xml"
    
    # Cache settings
    CACHE_TTL_SECONDS = 300  # 5 minutes
    REQUEST_TIMEOUT = 10  # seconds
    
    def __init__(self):
        self._cache: List[EconomicEvent] = []
        self._cache_timestamp: Optional[datetime] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def get_upcoming_event(
        self, 
        minutes_ahead: int = 30,
        min_impact: EventImpact = EventImpact.HIGH
    ) -> Optional[Tuple[str, float]]:
        """
        Get the next upcoming economic event within the time window.
        
        Args:
            minutes_ahead: Look ahead window in minutes
            min_impact: Minimum event impact level to consider
            
        Returns:
            Tuple of (event_name, minutes_until) or None
        """
        now = datetime.now(timezone.utc)
        
        # 1. Check local events first (most reliable)
        event = self._check_local_events(now, minutes_ahead, min_impact)
        if event:
            return event
        
        # 2. Check cached external events
        event = self._check_cached_events(now, minutes_ahead, min_impact)
        if event:
            return event
        
        return None
    
    async def get_upcoming_event_async(
        self, 
        minutes_ahead: int = 30,
        min_impact: EventImpact = EventImpact.HIGH
    ) -> Optional[Tuple[str, float]]:
        """
        Async version that also fetches from external sources.
        
        Args:
            minutes_ahead: Look ahead window in minutes
            min_impact: Minimum event impact level to consider
            
        Returns:
            Tuple of (event_name, minutes_until) or None
        """
        now = datetime.now(timezone.utc)
        
        # 1. Check local events first (most reliable)
        event = self._check_local_events(now, minutes_ahead, min_impact)
        if event:
            return event
        
        # 2. Try to refresh cache from external source
        await self._refresh_cache_if_needed()
        
        # 3. Check cached external events
        event = self._check_cached_events(now, minutes_ahead, min_impact)
        if event:
            return event
        
        return None
    
    def _check_local_events(
        self, 
        now: datetime, 
        minutes_ahead: int,
        min_impact: EventImpact
    ) -> Optional[Tuple[str, float]]:
        """Check hardcoded local events."""
        impact_priority = {
            EventImpact.HIGH: 3,
            EventImpact.MEDIUM: 2,
            EventImpact.LOW: 1
        }
        min_priority = impact_priority.get(min_impact, 1)
        
        for event in LOCAL_EVENTS:
            # Skip low impact events if minimum is higher
            if impact_priority.get(event.impact, 0) < min_priority:
                continue
            
            minutes_until = event.minutes_until(now)
            
            # Event is in the past
            if minutes_until < 0:
                continue
            
            # Event is within our window
            if 0 < minutes_until <= minutes_ahead:
                return (event.name, minutes_until)
            
            # Events are sorted, so if we're past the window, stop
            if minutes_until > minutes_ahead:
                break
        
        return None
    
    def _check_cached_events(
        self, 
        now: datetime, 
        minutes_ahead: int,
        min_impact: EventImpact
    ) -> Optional[Tuple[str, float]]:
        """Check cached external events."""
        if not self._cache:
            return None
        
        impact_priority = {
            EventImpact.HIGH: 3,
            EventImpact.MEDIUM: 2,
            EventImpact.LOW: 1
        }
        min_priority = impact_priority.get(min_impact, 1)
        
        for event in self._cache:
            if impact_priority.get(event.impact, 0) < min_priority:
                continue
            
            minutes_until = event.minutes_until(now)
            
            if 0 < minutes_until <= minutes_ahead:
                return (event.name, minutes_until)
        
        return None
    
    async def _refresh_cache_if_needed(self):
        """Refresh cache from external source if expired."""
        now = datetime.now(timezone.utc)
        
        # Check if cache is still valid
        if self._cache_timestamp:
            age = (now - self._cache_timestamp).total_seconds()
            if age < self.CACHE_TTL_SECONDS:
                return  # Cache is fresh
        
        # Try to fetch from Forex Factory
        try:
            events = await self._fetch_forex_factory()
            if events:
                self._cache = events
                self._cache_timestamp = now
                logger.debug(f"📅 Economic calendar cache refreshed: {len(events)} events")
        except Exception as e:
            logger.debug(f"Failed to refresh economic calendar: {e}")
    
    async def _fetch_forex_factory(self) -> List[EconomicEvent]:
        """
        Fetch economic events from Forex Factory.
        
        Note: Forex Factory doesn't have a public API, so this uses their RSS feed
        which has limited data. For production, consider:
        - Investing.com API
        - TradingView webhook
        - Paid economic calendar API
        """
        try:
            session = await self._get_session()
            
            async with session.get(self.FOREX_FACTORY_RSS) as response:
                if response.status != 200:
                    return []
                
                content = await response.text()
                return self._parse_forex_factory_xml(content)
                
        except asyncio.TimeoutError:
            logger.debug("Forex Factory request timed out")
            return []
        except Exception as e:
            logger.debug(f"Error fetching Forex Factory: {e}")
            return []
    
    def _parse_forex_factory_xml(self, xml_content: str) -> List[EconomicEvent]:
        """Parse Forex Factory XML/RSS feed."""
        events = []
        
        try:
            # Simple regex parsing (avoid heavy XML dependencies)
            # Pattern for event items
            item_pattern = r'<event>(.*?)</event>'
            title_pattern = r'<title>(.*?)</title>'
            date_pattern = r'<date>(.*?)</date>'
            time_pattern = r'<time>(.*?)</time>'
            impact_pattern = r'<impact>(.*?)</impact>'
            currency_pattern = r'<country>(.*?)</country>'
            
            items = re.findall(item_pattern, xml_content, re.DOTALL)
            
            for item in items:
                try:
                    title_match = re.search(title_pattern, item)
                    date_match = re.search(date_pattern, item)
                    time_match = re.search(time_pattern, item)
                    impact_match = re.search(impact_pattern, item)
                    currency_match = re.search(currency_pattern, item)
                    
                    if not all([title_match, date_match]):
                        continue
                    
                    title = title_match.group(1).strip()
                    date_str = date_match.group(1).strip()
                    time_str = time_match.group(1).strip() if time_match else "00:00"
                    impact_str = impact_match.group(1).strip().lower() if impact_match else "low"
                    currency = currency_match.group(1).strip() if currency_match else "USD"
                    
                    # Parse impact
                    if 'high' in impact_str or 'red' in impact_str:
                        impact = EventImpact.HIGH
                    elif 'medium' in impact_str or 'orange' in impact_str:
                        impact = EventImpact.MEDIUM
                    else:
                        impact = EventImpact.LOW
                    
                    # Parse datetime
                    # Forex Factory uses various formats, try common ones
                    dt = self._parse_ff_datetime(date_str, time_str)
                    if dt:
                        events.append(EconomicEvent(
                            name=title,
                            datetime_utc=dt,
                            impact=impact,
                            currency=currency
                        ))
                        
                except Exception as e:
                    logger.debug(f"Failed to parse FF event: {e}")
                    continue
            
            return sorted(events, key=lambda e: e.datetime_utc)
            
        except Exception as e:
            logger.debug(f"Error parsing Forex Factory XML: {e}")
            return []
    
    def _parse_ff_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse Forex Factory date/time strings."""
        try:
            # Common formats
            formats = [
                "%m-%d-%Y %H:%M",
                "%Y-%m-%d %H:%M",
                "%d-%m-%Y %H:%M",
                "%m/%d/%Y %H:%M",
            ]
            
            datetime_str = f"{date_str} {time_str}"
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(datetime_str, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def get_events_for_date(self, target_date: datetime) -> List[EconomicEvent]:
        """Get all events for a specific date."""
        events = []
        
        for event in LOCAL_EVENTS:
            if event.datetime_utc.date() == target_date.date():
                events.append(event)
        
        return events
    
    def get_high_impact_events_this_week(self) -> List[EconomicEvent]:
        """Get all high impact events for the current week."""
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        
        events = []
        for event in LOCAL_EVENTS:
            if (week_start <= event.datetime_utc < week_end and 
                event.impact == EventImpact.HIGH):
                events.append(event)
        
        return events


# Singleton instance
_calendar_service: Optional[EconomicCalendarService] = None


def get_economic_calendar() -> EconomicCalendarService:
    """Get the singleton calendar service instance."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = EconomicCalendarService()
    return _calendar_service


async def get_upcoming_economic_event(
    minutes_ahead: int = 30,
    min_impact: str = "high"
) -> Optional[Tuple[str, float]]:
    """
    Convenience function to get upcoming economic event.
    
    Args:
        minutes_ahead: Look ahead window in minutes
        min_impact: "high", "medium", or "low"
        
    Returns:
        Tuple of (event_name, minutes_until) or None
    """
    impact_map = {
        "high": EventImpact.HIGH,
        "medium": EventImpact.MEDIUM,
        "low": EventImpact.LOW
    }
    
    calendar = get_economic_calendar()
    return await calendar.get_upcoming_event_async(
        minutes_ahead=minutes_ahead,
        min_impact=impact_map.get(min_impact.lower(), EventImpact.HIGH)
    )


# Quick test
if __name__ == "__main__":
    async def test():
        print("📅 Economic Calendar Test")
        print("=" * 50)
        
        calendar = get_economic_calendar()
        
        # Get this week's high impact events
        events = calendar.get_high_impact_events_this_week()
        print(f"\n🔴 High Impact Events This Week ({len(events)}):")
        for event in events:
            print(f"  - {event.name}: {event.datetime_utc.strftime('%Y-%m-%d %H:%M UTC')}")
        
        # Check for upcoming event
        result = await get_upcoming_economic_event(minutes_ahead=60)
        if result:
            name, minutes = result
            print(f"\n⚠️ UPCOMING EVENT: {name} in {minutes:.0f} minutes!")
        else:
            print("\n✅ No high-impact events in the next 60 minutes")
        
        await calendar.close()
    
    asyncio.run(test())

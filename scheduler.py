"""
Scheduler: determine whether today is within the run window after a 13F deadline.

13F deadlines are 45 days after each quarter end. The scraper runs
2-3 days after each deadline to catch late filers — i.e. the window is
[deadline + 2, deadline + 5].

Also provides a GitHub Actions cron schedule as a convenience reference.
"""

from datetime import date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# 45 days after quarter-end gives these approximate dates (adjusted for weekends
# by SEC rules). Hard-code 2026 and add a helper to compute future years.
DEADLINES_2026 = [
    date(2026, 2, 17),  # Q4 2025
    date(2026, 5, 15),  # Q1 2026
    date(2026, 8, 14),  # Q2 2026
    date(2026, 11, 16),  # Q3 2026
]

# Days after deadline to start/stop running
RUN_WINDOW_START = 2
RUN_WINDOW_END = 5


def _compute_deadline(year: int, quarter: int) -> date:
    """Compute the approximate 13F deadline (45 days after quarter end)."""
    quarter_end_month = quarter * 3
    # Last day of quarter-end month
    if quarter_end_month == 12:
        qe = date(year, 12, 31)
    else:
        qe = date(year, quarter_end_month + 1, 1) - timedelta(days=1)
    raw = qe + timedelta(days=45)
    # If deadline falls on a weekend, push to Monday
    while raw.weekday() >= 5:
        raw += timedelta(days=1)
    return raw


def get_deadlines(year: int):
    return [_compute_deadline(year, q) for q in range(1, 5)]


def should_run(today: Optional[date] = None) -> tuple[bool, Optional[date]]:
    """Return (True, deadline) if today is within the run window for any deadline."""
    if today is None:
        today = date.today()

    year = today.year
    candidates = DEADLINES_2026 if year == 2026 else get_deadlines(year)
    # Also check adjacent year in case we're near a year boundary
    candidates += get_deadlines(year - 1) + get_deadlines(year + 1)

    for deadline in candidates:
        delta = (today - deadline).days
        if RUN_WINDOW_START <= delta <= RUN_WINDOW_END:
            logger.info("Today (%s) is day +%d after deadline %s — running.", today, delta, deadline)
            return True, deadline

    logger.info("Today (%s) is not within any run window — skipping.", today)
    return False, None


GITHUB_ACTIONS_CRON = """\
# .github/workflows/run-13f.yml  (on.schedule section)
# Runs at 9am UTC on the target dates (3 days after each 2026 deadline)
- cron: '0 9 20 2 *'   # Q4 2025: Feb 20 2026
- cron: '0 9 18 5 *'   # Q1 2026: May 18 2026
- cron: '0 9 17 8 *'   # Q2 2026: Aug 17 2026
- cron: '0 9 19 11 *'  # Q3 2026: Nov 19 2026
"""

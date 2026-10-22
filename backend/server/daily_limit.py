# SPDX-License-Identifier: AGPL-3.0-only
"""Free checks per IP address per day (owner decision, 2026-10-09: 3).

Every endpoint that runs the model counts against one allowance per client
IP: /ocr, /analyze-vl, /report-python and /api/v2/reports. Only a check that
produced a result counts; a refusal (busy, too big, no handwriting) does not.
The day turns over at midnight India time. Counts live in memory, so a
restart of the analyser starts the day afresh.

Not counted:
  * a Pro access key (the caller passes ``exempt=True``);
  * private and loopback addresses: CI, local tools and the docker network,
    which no visitor arrives from through Cloudflare and nginx;
  * the addresses in VAHINI_DAILY_LIMIT_EXEMPT (comma separated), for the
    server's own stage checks.

The client address is X-Real-IP, which nginx sets from the address it
restored from Cloudflare, and only when the request itself comes from a
private address (the proxy). A request straight from a public address is
counted by that address, so the header cannot be forged from outside.

VAHINI_DAILY_SCANS_PER_IP sets the allowance; 0 turns the limit off.
"""

import ipaddress
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from starlette.exceptions import HTTPException

IST = timezone(timedelta(hours=5, minutes=30))


def _is_ip(addr):
    try:
        ipaddress.ip_address(addr)
    except ValueError:
        return False
    return True


def _private(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


class DailyLimit:
    """Per-IP daily allowance of free checks."""

    def __init__(self, limit=None, exempt=None, clock=time.time):
        if limit is None:
            limit = int(os.environ.get("VAHINI_DAILY_SCANS_PER_IP", "3"))
        if exempt is None:
            exempt = os.environ.get("VAHINI_DAILY_LIMIT_EXEMPT", "")
        self.limit = max(0, limit)
        self.exempt = {a.strip() for a in exempt.split(",") if a.strip()}
        self.clock = clock
        self.counts = {}
        self.lock = threading.Lock()

    def _day(self):
        return datetime.fromtimestamp(self.clock(), IST).date()

    def client(self, request):
        """The address to count, or None when the request is not counted."""
        peer = request.client.host if request.client else ""
        if not _is_ip(peer):
            return None  # an in-process test client, never a network peer
        real = request.headers.get("x-real-ip", "").strip()
        addr = real if real and _private(peer) else peer
        if not _is_ip(addr) or _private(addr) or addr in self.exempt:
            return None
        return addr

    def seconds_to_midnight(self):
        now = datetime.fromtimestamp(self.clock(), IST)
        nxt = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return max(1, int((nxt - now).total_seconds()))

    def check(self, request, exempt=False):
        """Raise 429 when the address has used today's checks.

        Returns the address to charge after a successful check, or None."""
        if not self.limit or exempt:
            return None
        addr = self.client(request)
        if addr is None:
            return None
        with self.lock:
            day, used = self.counts.get(addr, (self._day(), 0))
            if day != self._day():
                used = 0
            if used >= self.limit:
                raise HTTPException(
                    429,
                    {
                        "error_code": "daily_limit",
                        "error": (
                            f"Today's {self.limit} free checks from this"
                            " connection are used. Come back tomorrow."
                        ),
                        "limit": self.limit,
                    },
                    headers={
                        "Retry-After": str(self.seconds_to_midnight()),
                        "Cache-Control": "no-store",
                    },
                )
        return addr

    def spend(self, addr):
        """Count one finished check for the address returned by check()."""
        if addr is None:
            return
        with self.lock:
            today = self._day()
            day, used = self.counts.get(addr, (today, 0))
            self.counts[addr] = (today, (used if day == today else 0) + 1)
            # Forget earlier days so the table holds one day of addresses.
            if len(self.counts) > 10000:
                self.counts = {
                    a: v for a, v in self.counts.items() if v[0] == today
                }


LIMIT = DailyLimit()

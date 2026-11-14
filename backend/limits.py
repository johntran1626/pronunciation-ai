"""Rate limits for NEW text-to-speech clips (cached clips are free, so they are never counted).

Two rules, both checked before Azure is called:
  1. per client: at most `per_client` new clips in any `window_s` seconds (a "sliding window": we keep the time
     of each recent request and forget the ones older than the window). Stops one visitor spamming Custom mode.
  2. for everyone together: at most `daily_chars` characters of new speech per UTC day. This is the spending cap:
     Azure bills per character, so a character budget is a money budget.

Counts live in memory: a server restart resets them. That's fine on Azure's free tier (F0), which refuses rather
than bills past its monthly quota; on a paid tier we'd store the daily count on disk (TODO before a paid tier).
"""
import threading
import time
from collections import defaultdict, deque

DAY_S = 86_400


class TTSLimiter:
    def __init__(self, per_client=10, window_s=60, daily_chars=15_000, clock=time.time):
        # 15,000/day x 30 days = 450,000 characters/month, under the F0 free 500,000 for neural voices.
        self.per_client, self.window_s, self.daily_chars = per_client, window_s, daily_chars
        self.clock = clock
        self.recent = defaultdict(deque)   # client -> times of its recent allowed requests, oldest first
        self.day, self.chars = None, 0     # which UTC day we're counting, and characters used in it
        self.lock = threading.Lock()       # requests run in parallel threads; counts must not race

    def allow(self, client, n_chars):
        """(True, 0) and the request is counted, or (False, seconds to wait) and nothing is counted."""
        with self.lock:
            now = self.clock()
            self._roll_day(now)
            times = self.recent[client]
            while times and times[0] <= now - self.window_s:   # forget requests older than the window
                times.popleft()
            if len(times) >= self.per_client:
                return False, max(1, int(times[0] + self.window_s - now + 0.999))  # until the oldest ages out
            if self.chars + n_chars > self.daily_chars:
                return False, max(1, int((self.day + 1) * DAY_S - now + 0.999))   # until UTC midnight
            times.append(now)
            self.chars += n_chars
            return True, 0

    def used_today(self):
        with self.lock:
            self._roll_day(self.clock())
            return self.chars

    def _roll_day(self, now):
        day = int(now // DAY_S)            # UTC day number (time.time() counts from midnight UTC, 1 Jan 1970)
        if day != self.day:
            self.day, self.chars = day, 0

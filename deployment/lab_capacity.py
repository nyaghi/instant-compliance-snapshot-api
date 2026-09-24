"""Private, single-instance lab admission. No registry or status implementation.

The shared pool reserves capacity for registration requests AND discovery browser
tasks. Fairness is by organization within this authenticated lab, not a customer
authorization model. This is deliberately NOT a durable/distributed job queue.
"""
from collections import Counter, deque
from contextvars import ContextVar
from dataclasses import dataclass
import threading
import time

REQUEST_GROUP = ContextVar('lab_request_group', default='unattributed')
REQUEST_TIMING = ContextVar('lab_request_timing', default=None)


@dataclass(eq=False)
class Ticket:
    group: str
    category: str
    started: float


class FairCapacity:
    def __init__(self, slots, max_waiters=256, category_limits=None):
        if slots < 1 or max_waiters < 1:
            raise ValueError('Capacity must be positive')
        self.slots, self.max_waiters = slots, max_waiters
        self.category_limits = category_limits or {}
        if any(v < 1 or v > slots for v in self.category_limits.values()):
            raise ValueError('Invalid category capacity')
        self.cv = threading.Condition()
        self.pending = {}
        self.order = deque()
        self.active = set()
        self.by_group, self.by_category = Counter(), Counter()
        self.counts = Counter()
        self.recent = deque(maxlen=512)

    def _eligible(self, ticket):
        return self.by_category[ticket.category] < self.category_limits.get(ticket.category, self.slots)

    def _chosen(self):
        # Prefer the organization with least active work, then round-robin.
        candidates = [(self.by_group[g], i, t) for i, g in enumerate(self.order)
                      for t in self.pending[g] if self._eligible(t)]
        return min(candidates, key=lambda item: item[:2])[2] if candidates else None

    def _remove(self, ticket):
        group = ticket.group
        self.pending[group].remove(ticket)
        self.order.remove(group)
        if self.pending[group]:
            self.order.append(group)
        else:
            del self.pending[group]

    def acquire(self, group, category, timeout, canceled=None):
        now = time.monotonic()
        ticket = Ticket(group, category, now)
        deadline = now + max(0, timeout)
        with self.cv:
            if sum(map(len, self.pending.values())) >= self.max_waiters:
                self.counts['queue_full'] += 1
                return None
            if group not in self.pending:
                self.pending[group] = deque()
                self.order.append(group)
            self.pending[group].append(ticket)
            self.counts['peak_waiters'] = max(self.counts['peak_waiters'], sum(map(len, self.pending.values())))
            first = True
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if canceled and canceled():
                        self.counts['canceled_before_start'] += 1
                        return None
                    if (remaining > 0 or first) and len(self.active) < self.slots and self._chosen() is ticket:
                        self.active.add(ticket)
                        self.by_group[group] += 1
                        self.by_category[category] += 1
                        self.counts['admitted'] += 1
                        self.counts['peak_active'] = max(self.counts['peak_active'], len(self.active))
                        waited = time.monotonic() - now
                        self.recent.append({'event': 'admitted', 'category': category, 'queue_seconds': waited})
                        timing = REQUEST_TIMING.get()
                        if timing is not None and category == 'registration':
                            timing['queue_seconds'] = waited
                        return ticket
                    if remaining <= 0:
                        self.counts['queue_expired'] += 1
                        return None
                    first = False
                    self.cv.wait(min(remaining, .1 if canceled else 1.0))
            finally:
                self._remove(ticket)
                self.cv.notify_all()

    def release(self, ticket):
        with self.cv:
            if ticket not in self.active:
                raise ValueError('Unknown or already released capacity ticket')
            self.active.remove(ticket)
            self.by_group[ticket.group] -= 1
            if not self.by_group[ticket.group]: del self.by_group[ticket.group]
            self.by_category[ticket.category] -= 1
            self.counts['completed'] += 1
            self.cv.notify_all()

    def snapshot(self):
        with self.cv:
            return {'scope': 'single_instance', 'slots': self.slots,
                    'active': len(self.active), 'queued': sum(map(len, self.pending.values())),
                    'waiting_organizations': len(self.pending), 'max_waiters': self.max_waiters,
                    'active_by_category': dict(self.by_category), 'counts': dict(self.counts),
                    'recent': list(self.recent)}


class AdmissionSemaphore:
    """Same acquire/release contract used by the unchanged master handler."""
    def __init__(self, pool, category):
        self.pool, self.category = pool, category
        self.local = threading.local()

    def acquire(self, blocking=True, timeout=None):
        if getattr(self.local, 'ticket', None) is not None:
            raise RuntimeError('Capacity must not be acquired twice on the same thread')
        ticket = self.pool.acquire(REQUEST_GROUP.get(), self.category,
                                   0 if not blocking else (150 if timeout is None else timeout))
        self.local.ticket = ticket
        return ticket is not None

    def release(self):
        ticket = getattr(self.local, 'ticket', None)
        if ticket is None: raise ValueError('No capacity ticket to release')
        self.pool.release(ticket)
        self.local.ticket = None


def install(master, slots):
    if master.MAX_BROWSER_LOOKUPS < slots:
        raise RuntimeError('Inner browser slots cannot be below admitted capacity')
    pool = FairCapacity(slots, category_limits={'discovery_browser': min(4, slots)})
    master.SINGLE_STATE_REQUEST_SEMAPHORE = AdmissionSemaphore(pool, 'registration')
    master.IDENTITY_BROWSER_SLOTS = AdmissionSemaphore(pool, 'discovery_browser')
    # Discovery's executor preserves ContextVars in the current master. Set a
    # group at this boundary as well so internal callers never lose fairness.
    original = master.identity_browser_names
    def identity_browser_names(source, ein, deadline):
        token = REQUEST_GROUP.set('lab:' + master.canonical_ein_digits(ein))
        try: return original(source, ein, deadline)
        finally: REQUEST_GROUP.reset(token)
    master.identity_browser_names = identity_browser_names
    return pool

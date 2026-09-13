import threading
import time


class MatchStore:
    """
    Thread-safe in-memory store for normalized records waiting
    for economic matching.

    Arrival times are tracked separately so the public getters
    continue returning CanonicalTrade / CanonicalPnl objects.
    """

    def __init__(self):
        self.executions = []
        self.confirmations = []
        self.pnl_records = []

        self.execution_received_at = {}
        self.confirmation_received_at = {}
        self.pnl_received_at = {}

        self.lock = threading.Lock()

    def add_execution(self, execution):
        with self.lock:
            self.executions.append(execution)
            self.execution_received_at[id(execution)] = time.monotonic()

    def add_confirmation(self, confirmation):
        with self.lock:
            self.confirmations.append(confirmation)
            self.confirmation_received_at[id(confirmation)] = time.monotonic()

    def add_pnl(self, pnl):
        with self.lock:
            self.pnl_records.append(pnl)
            self.pnl_received_at[id(pnl)] = time.monotonic()

    def get_executions(self):
        with self.lock:
            return list(self.executions)

    def get_confirmations(self):
        with self.lock:
            return list(self.confirmations)

    def get_pnl_records(self):
        with self.lock:
            return list(self.pnl_records)

    def remove_execution(self, execution):
        with self.lock:
            if execution in self.executions:
                self.executions.remove(execution)

            self.execution_received_at.pop(
                id(execution),
                None
            )

    def remove_executions(self, executions):
        with self.lock:
            for execution in executions:
                if execution in self.executions:
                    self.executions.remove(execution)

                self.execution_received_at.pop(
                    id(execution),
                    None
                )

    def remove_confirmation(self, confirmation):
        with self.lock:
            if confirmation in self.confirmations:
                self.confirmations.remove(confirmation)

            self.confirmation_received_at.pop(
                id(confirmation),
                None
            )

    def remove_pnl(self, pnl):
        with self.lock:
            if pnl in self.pnl_records:
                self.pnl_records.remove(pnl)

            self.pnl_received_at.pop(
                id(pnl),
                None
            )

    def get_stale_executions(self, timeout_seconds):
        now = time.monotonic()

        with self.lock:
            return [
                execution
                for execution in self.executions
                if (
                    now
                    - self.execution_received_at.get(
                        id(execution),
                        now
                    )
                    >= timeout_seconds
                )
            ]

    def get_stale_confirmations(self, timeout_seconds):
        now = time.monotonic()

        with self.lock:
            return [
                confirmation
                for confirmation in self.confirmations
                if (
                    now
                    - self.confirmation_received_at.get(
                        id(confirmation),
                        now
                    )
                    >= timeout_seconds
                )
            ]

    def execution_count(self):
        with self.lock:
            return len(self.executions)

    def confirmation_count(self):
        with self.lock:
            return len(self.confirmations)

    def pnl_count(self):
        with self.lock:
            return len(self.pnl_records)
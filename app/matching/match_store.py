import threading


class MatchStore:
    """
    Temporary in-memory store for normalized records
    that have not yet been fully matched/reconciled.
    """

    def __init__(self):
        self.executions = []
        self.confirmations = []
        self.pnl_records = []

        # Consumers run in separate threads, so protect shared state.
        self.lock = threading.Lock()

    def add_execution(self, execution):
        with self.lock:
            self.executions.append(execution)

    def add_confirmation(self, confirmation):
        with self.lock:
            self.confirmations.append(confirmation)

    def add_pnl(self, pnl):
        with self.lock:
            self.pnl_records.append(pnl)

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

    def remove_executions(self, executions):
        with self.lock:
            for execution in executions:
                if execution in self.executions:
                    self.executions.remove(execution)

    def remove_confirmation(self, confirmation):
        with self.lock:
            if confirmation in self.confirmations:
                self.confirmations.remove(confirmation)

    def remove_pnl(self, pnl):
        with self.lock:
            if pnl in self.pnl_records:
                self.pnl_records.remove(pnl)

    def execution_count(self):
        with self.lock:
            return len(self.executions)

    def confirmation_count(self):
        with self.lock:
            return len(self.confirmations)

    def pnl_count(self):
        with self.lock:
            return len(self.pnl_records)
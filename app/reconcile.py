import threading
import time
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from .utils import parse_timestamp, is_within_tolerance, is_timestamp_within_drift

Base = declarative_base()


class ReconciliationResult(Base):
    """
    Stores the latest reconciliation result for each trade.
    Raw source records are kept as JSON for auditability.
    """
    __tablename__ = "reconciliation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, unique=True, nullable=False)
    ticker = Column(String)
    status = Column(String, nullable=False)
    execution_data = Column(SQLiteJSON)
    confirmation_data = Column(SQLiteJSON)
    pnl_data = Column(SQLiteJSON)
    mismatch_details = Column(SQLiteJSON)
    reconciliation_timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ReconciliationResult(trade_id='{self.trade_id}', status='{self.status}')>"


class ReconciliationEngine:
    """
    Receives execution, broker confirmation, and P&L messages,
    groups them by trade_id, reconciles the records, and saves results.
    """

    def __init__(self, db_url="sqlite:///./reports/reconciliation.db", db_session=None):
        # Temporary in-memory storage for messages waiting on their matching records.
        self.trade_store = {}
        self.trade_store_lock = threading.Lock()

        # Create the reconciliation database and table if they do not exist.
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)

        # Tests can inject their own DB session. Production creates one here.
        if db_session:
            self.session = db_session
        else:
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

        self.db_session = self.session
        print(f"ReconciliationEngine initialized with DB: {db_url}")

        # Prometheus metric collectors are injected later by the application.
        self.total_trades_counter = None
        self.matched_trades_counter = None
        self.mismatched_trades_counter = None
        self.in_memory_store_size_gauge = None
        self.reconciliation_latency_histogram = None

    def set_metrics_collectors(
        self,
        total_trades_counter,
        matched_trades_counter,
        mismatched_trades_counter,
        in_memory_store_size_gauge,
        reconciliation_latency_histogram
    ):
        """Attach Prometheus metric collectors to the reconciliation engine."""
        self.total_trades_counter = total_trades_counter
        self.matched_trades_counter = matched_trades_counter
        self.mismatched_trades_counter = mismatched_trades_counter
        self.in_memory_store_size_gauge = in_memory_store_size_gauge
        self.reconciliation_latency_histogram = reconciliation_latency_histogram

    def process_message(self, topic: str, message: dict):
        """
        Store each Kafka message under its trade_id.
        Reconciliation is attempted whenever a new source record arrives.
        """
        trade_id = message.get("trade_id")

        if not trade_id:
            print(f"Warning: Message from topic {topic} missing trade_id: {message}")
            return

        trade_id = str(trade_id)

        # Lock protects the shared trade_store because multiple consumers may write to it.
        with self.trade_store_lock:
            if trade_id not in self.trade_store:
                self.trade_store[trade_id] = {
                    "execution": None,
                    "confirmation": None,
                    "pnl": None,
                    "status": "PENDING",
                    "start_time": time.time()
                }

                if self.in_memory_store_size_gauge:
                    self.in_memory_store_size_gauge.inc()

            # Map each Kafka topic to the appropriate record type.
            if topic == "executions":
                self.trade_store[trade_id]["execution"] = message
            elif topic == "confirmations":
                self.trade_store[trade_id]["confirmation"] = message
            elif topic == "pnl_snapshot":
                self.trade_store[trade_id]["pnl"] = message
            else:
                print(f"Unknown topic: {topic} for trade_id {trade_id}")
                return

            self._attempt_reconciliation(trade_id)

    def _attempt_reconciliation(self, trade_id: str):
        """
        Execution and confirmation are required for reconciliation.
        P&L is optional because it may arrive later.
        """
        trade_data = self.trade_store.get(trade_id)

        if not trade_data:
            print(f"Trade {trade_id} not found in store for reconciliation")
            return

        execution = trade_data.get("execution")
        confirmation = trade_data.get("confirmation")
        pnl = trade_data.get("pnl")

        if execution and confirmation:
            self._perform_reconciliation_and_save(
                trade_id,
                execution,
                confirmation,
                pnl
            )
        else:
            print(f"Trade {trade_id} not ready. Missing execution or confirmation.")

    def _perform_reconciliation_and_save(
        self,
        trade_id: str,
        execution: dict,
        confirmation: dict,
        pnl: dict = None
    ):
        """
        Compare economically important fields between internal execution,
        broker confirmation, and optional P&L records.
        """
        mismatches = []
        is_matched = True

        if self.total_trades_counter:
            self.total_trades_counter.inc()

        # ---------------------------------------------------------
        # Quantity reconciliation
        # Quantity is expected to match exactly.
        # ---------------------------------------------------------
        execution_qty = execution.get("quantity")
        confirmation_qty = confirmation.get("quantity")

        if execution_qty is None or confirmation_qty is None:
            mismatches.append({
                "field": "quantity",
                "execution": execution_qty,
                "confirmation": confirmation_qty,
                "reason": "Quantity missing"
            })
            is_matched = False

        elif not is_within_tolerance(
            float(execution_qty),
            float(confirmation_qty),
            tolerance=0.0
        ):
            mismatches.append({
                "field": "quantity",
                "execution": execution_qty,
                "confirmation": confirmation_qty,
                "reason": "Quantity mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Price reconciliation
        # A small tolerance allows minor rounding differences.
        # ---------------------------------------------------------
        execution_price = execution.get("price")
        confirmation_price = confirmation.get("price")

        if execution_price is None or confirmation_price is None:
            mismatches.append({
                "field": "price",
                "execution": execution_price,
                "confirmation": confirmation_price,
                "reason": "Price missing"
            })
            is_matched = False

        elif not is_within_tolerance(
            float(execution_price),
            float(confirmation_price),
            tolerance=0.005
        ):
            mismatches.append({
                "field": "price",
                "execution": execution_price,
                "confirmation": confirmation_price,
                "reason": "Price mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Timestamp reconciliation
        # New data uses "timestamp", but fallback fields support
        # older Kafka messages still present in the topic.
        # ---------------------------------------------------------
        exec_timestamp = (
            execution.get("timestamp")
            or execution.get("execution_timestamp")
        )

        conf_timestamp = (
            confirmation.get("timestamp")
            or confirmation.get("execution_timestamp")
            or confirmation.get("broker_timestamp")
        )

        if exec_timestamp is None or conf_timestamp is None:
            mismatches.append({
                "field": "timestamp",
                "execution": exec_timestamp,
                "confirmation": conf_timestamp,
                "reason": "Timestamp missing"
            })
            is_matched = False

        else:
            try:
                exec_ts = parse_timestamp(exec_timestamp)
                conf_ts = parse_timestamp(conf_timestamp)

                # Allow small timing differences between internal and broker systems.
                if not is_timestamp_within_drift(
                    exec_ts,
                    conf_ts,
                    drift_ms=100
                ):
                    mismatches.append({
                        "field": "timestamp",
                        "execution": exec_timestamp,
                        "confirmation": conf_timestamp,
                        "reason": "Timestamp drift beyond 100ms"
                    })
                    is_matched = False

            except (ValueError, TypeError) as e:
                mismatches.append({
                    "field": "timestamp",
                    "execution": exec_timestamp,
                    "confirmation": conf_timestamp,
                    "reason": f"Timestamp parsing error: {e}"
                })
                is_matched = False

        # ---------------------------------------------------------
        # Instrument reconciliation
        # ISIN is preferred because broker and internal ticker
        # representations may differ, e.g. 7203 vs 7203.T.
        # ---------------------------------------------------------
        execution_isin = execution.get("isin")
        confirmation_isin = confirmation.get("isin")

        if execution_isin and confirmation_isin:
            if execution_isin != confirmation_isin:
                mismatches.append({
                    "field": "isin",
                    "execution": execution_isin,
                    "confirmation": confirmation_isin,
                    "reason": "Instrument mismatch"
                })
                is_matched = False

        else:
            execution_ticker = execution.get("ticker")
            confirmation_ticker = confirmation.get("ticker")

            if execution_ticker != confirmation_ticker:
                mismatches.append({
                    "field": "ticker",
                    "execution": execution_ticker,
                    "confirmation": confirmation_ticker,
                    "reason": "Ticker mismatch"
                })
                is_matched = False

        # ---------------------------------------------------------
        # Currency reconciliation
        # A trade should normally have the same transaction currency
        # across the internal execution and broker confirmation.
        # ---------------------------------------------------------
        execution_currency = execution.get("trade_currency")
        confirmation_currency = confirmation.get("trade_currency")

        if (
            execution_currency
            and confirmation_currency
            and execution_currency != confirmation_currency
        ):
            mismatches.append({
                "field": "trade_currency",
                "execution": execution_currency,
                "confirmation": confirmation_currency,
                "reason": "Trade currency mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Settlement date reconciliation
        # Ensures both systems expect the trade to settle on the same day.
        # ---------------------------------------------------------
        execution_settlement = execution.get("settlement_date")
        confirmation_settlement = confirmation.get("settlement_date")

        if (
            execution_settlement
            and confirmation_settlement
            and execution_settlement != confirmation_settlement
        ):
            mismatches.append({
                "field": "settlement_date",
                "execution": execution_settlement,
                "confirmation": confirmation_settlement,
                "reason": "Settlement date mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # P&L consistency check
        #
        # net_pnl should approximately equal:
        # realized + unrealized + FX P&L - fees
        #
        # P&L may arrive later, so this check only runs when available.
        # ---------------------------------------------------------
        if pnl:
            net_pnl = pnl.get("net_pnl")
            realized_pnl = pnl.get("realized_pnl", 0.0)
            unrealized_pnl = pnl.get("unrealized_pnl", 0.0)
            fx_pnl = pnl.get("fx_pnl", 0.0)
            total_fees = pnl.get("total_fees", 0.0)

            if net_pnl is not None:
                try:
                    reported_net_pnl = float(net_pnl)
                    realized = float(realized_pnl or 0.0)
                    unrealized = float(unrealized_pnl or 0.0)
                    fx = float(fx_pnl or 0.0)
                    fees = float(total_fees or 0.0)

                    calculated_net_pnl = realized + unrealized + fx - fees

                    if not is_within_tolerance(
                        calculated_net_pnl,
                        reported_net_pnl,
                        tolerance=1.0
                    ):
                        mismatches.append({
                            "field": "net_pnl",
                            "calculated": round(calculated_net_pnl, 2),
                            "reported": reported_net_pnl,
                            "reason": "P&L consistency check failed"
                        })
                        is_matched = False

                except (ValueError, TypeError) as e:
                    mismatches.append({
                        "field": "pnl_calculation_error",
                        "reason": f"Error converting P&L values: {e}"
                    })
                    is_matched = False

        # Final reconciliation status after all checks are completed.
        status = "MATCHED" if is_matched else "MISMATCHED"
        print(f"Reconciliation for Trade {trade_id}: Status = {status}")

        if mismatches:
            print(f"Mismatches: {mismatches}")

            if self.mismatched_trades_counter:
                self.mismatched_trades_counter.inc()

        else:
            if self.matched_trades_counter:
                self.matched_trades_counter.inc()

        # Measure time from the first received message until reconciliation.
        if (
            "start_time" in self.trade_store[trade_id]
            and self.reconciliation_latency_histogram
        ):
            latency = time.time() - self.trade_store[trade_id]["start_time"]
            self.reconciliation_latency_histogram.observe(latency)

        # ---------------------------------------------------------
        # Persist the latest reconciliation result to SQLite.
        # Existing trade records are updated instead of duplicated.
        # ---------------------------------------------------------
        session = self.session

        try:
            existing = (
                session.query(ReconciliationResult)
                .filter_by(trade_id=trade_id)
                .first()
            )

            if existing:
                existing.ticker = execution.get("ticker", "N/A")
                existing.status = status
                existing.execution_data = execution
                existing.confirmation_data = confirmation
                existing.pnl_data = pnl
                existing.mismatch_details = mismatches
                existing.reconciliation_timestamp = datetime.utcnow()

                print(f"Updated trade {trade_id} in DB.")

            else:
                new_result = ReconciliationResult(
                    trade_id=trade_id,
                    ticker=execution.get("ticker", "N/A"),
                    status=status,
                    execution_data=execution,
                    confirmation_data=confirmation,
                    pnl_data=pnl,
                    mismatch_details=mismatches
                )

                session.add(new_result)
                print(f"Inserted trade {trade_id} into DB.")

            session.commit()

        except Exception as e:
            session.rollback()
            print(f"DB error for trade {trade_id}: {e}")
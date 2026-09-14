import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from .utils import is_within_tolerance, is_timestamp_within_drift
from .matching.match_store import MatchStore
from .matching.group_matcher import find_match


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
    break_type = Column(String)
    execution_data = Column(SQLiteJSON)
    confirmation_data = Column(SQLiteJSON)
    pnl_data = Column(SQLiteJSON)
    mismatch_details = Column(SQLiteJSON)
    reconciliation_timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ReconciliationResult(trade_id='{self.trade_id}', status='{self.status}')>"


class ReconciliationEngine:
    """
    Receives normalized execution, confirmation, and P&L objects,
    groups them by trade_id, reconciles them, and persists the result.
    """

    def __init__(self, db_url="sqlite:///./reports/reconciliation.db", db_session=None):
        # New economic matching store.
        self.match_store = MatchStore()
        
        # Completed economic matches.
        self.completed_matches = {}
        
        # Source trade ID -> canonical reconciliation ID.
        self.reconciliation_aliases = {}
        

        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)

        if db_session:
            self.session = db_session
        else:
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

        self.db_session = self.session
        print(f"ReconciliationEngine initialized with DB: {db_url}")

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
        """Attach Prometheus metric collectors."""
        self.total_trades_counter = total_trades_counter
        self.matched_trades_counter = matched_trades_counter
        self.mismatched_trades_counter = mismatched_trades_counter
        self.in_memory_store_size_gauge = in_memory_store_size_gauge
        self.reconciliation_latency_histogram = reconciliation_latency_histogram

    def _get(self, obj, field, default=None):
        """
        Transitional helper.

        Supports both:
        - Canonical dataclass objects: execution.price
        - Legacy dictionaries: execution["price"]

        This lets old tests continue working during migration.
        """
        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(field, default)

        return getattr(obj, field, default)

    def _serialize(self, obj):
        """
        Convert canonical objects into JSON-safe dictionaries
        before storing them in SQLite.
        """
        if obj is None:
            return None

        # Prefer original raw source data for auditability.
        raw_data = self._get(obj, "raw_data")

        if raw_data:
            return raw_data

        if isinstance(obj, dict):
            return obj

        if is_dataclass(obj):
            data = asdict(obj)

            # datetime cannot be written directly to JSON.
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()

            return data

        return {"value": str(obj)}

    def process_message(self, topic: str, message):
        """
        Store normalized records by trade_id.

        Messages should normally be CanonicalTrade or CanonicalPnl
        objects after passing through the normalization layer.
        """
        trade_id = self._get( message, "trade_id" )

        if not trade_id:
            print( f"Warning: Message from topic {topic} missing trade_id: {message}" )
            return

        trade_id = str(trade_id)
        # ---------------------------------------------------------
        # Execution arrives
        # Store it until a broker confirmation can match against it.
        # ---------------------------------------------------------
        if topic == "executions":
            self.match_store.add_execution(message)

            print( f"Stored pending execution {trade_id}. Pending executions: {self.match_store.execution_count()}" )
            # A confirmation may already be waiting.
            self._try_match_pending_confirmations()

        # ---------------------------------------------------------
        # Confirmation arrives
        # Try to find either:
        # 1. one execution
        # 2. an aggregation of multiple executions
        # ---------------------------------------------------------
        
        elif topic == "confirmations":
            self.match_store.add_confirmation(message)
            print( f"Stored pending confirmation {trade_id}." )

            self._try_match_confirmation(message)

        # ---------------------------------------------------------
        # P&L arrives
        # Keep it pending for later association.
        # ---------------------------------------------------------
        elif topic == "pnl_snapshot":
            self.match_store.add_pnl(message)
            print( f"Stored pending P&L {trade_id}. Pending P&L records: {self.match_store.pnl_count()}" )
            
            self._try_attach_pnl(message)
        else:
            print( f"Unknown topic: {topic} for trade_id {trade_id}" )
            
    def _perform_reconciliation_and_save( self, trade_id: str, execution, confirmation, pnl=None ):
        """
        Compare canonical economic fields.

        Source-specific differences such as 7203 vs 7203.T
        should already have been resolved by normalization.
        """
        mismatches = []
        is_matched = True

        if self.total_trades_counter:
            self.total_trades_counter.inc()

        # ---------------------------------------------------------
        # Instrument identity
        # Both source records should now contain the same canonical
        # instrument_id regardless of their original ticker format.
        # ---------------------------------------------------------
        execution_instrument = self._get(execution, "instrument_id")
        confirmation_instrument = self._get(confirmation, "instrument_id")

        if not execution_instrument or not confirmation_instrument:
            mismatches.append({
                "field": "instrument_id",
                "execution": execution_instrument,
                "confirmation": confirmation_instrument,
                "reason": "Canonical instrument identity missing"
            })
            is_matched = False

        elif execution_instrument != confirmation_instrument:
            mismatches.append({
                "field": "instrument_id",
                "execution": execution_instrument,
                "confirmation": confirmation_instrument,
                "reason": "Instrument mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Quantity
        # ---------------------------------------------------------
        execution_qty = self._get(execution, "quantity")
        confirmation_qty = self._get(confirmation, "quantity")

        if execution_qty is None or confirmation_qty is None:
            mismatches.append({
                "field": "quantity",
                "execution": execution_qty,
                "confirmation": confirmation_qty,
                "reason": "Quantity missing"
            })
            is_matched = False

        elif not is_within_tolerance(
            execution_qty,
            confirmation_qty,
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
        # Price
        # Small differences are allowed for rounding.
        # ---------------------------------------------------------
        execution_price = self._get(execution, "price")
        confirmation_price = self._get(confirmation, "price")

        if execution_price is None or confirmation_price is None:
            mismatches.append({
                "field": "price",
                "execution": execution_price,
                "confirmation": confirmation_price,
                "reason": "Price missing"
            })
            is_matched = False

        elif not is_within_tolerance(
            execution_price,
            confirmation_price,
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
        # Side
        # BUY must reconcile against BUY and SELL against SELL.
        # ---------------------------------------------------------
        execution_side = self._get(execution, "side")
        confirmation_side = self._get(confirmation, "side")

        if (
            execution_side
            and confirmation_side
            and execution_side != confirmation_side
        ):
            mismatches.append({
                "field": "side",
                "execution": execution_side,
                "confirmation": confirmation_side,
                "reason": "Trade side mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Timestamp
        # Timestamp aliases have already been handled by normalization.
        # Reconciliation only compares canonical datetime values.
        # ---------------------------------------------------------
        execution_timestamp = self._get(execution, "timestamp")
        confirmation_timestamp = self._get(confirmation, "timestamp")

        if execution_timestamp is None or confirmation_timestamp is None:
            mismatches.append({
                "field": "timestamp",
                "execution": str(execution_timestamp),
                "confirmation": str(confirmation_timestamp),
                "reason": "Timestamp missing"
            })
            is_matched = False

        elif not is_timestamp_within_drift(
            execution_timestamp,
            confirmation_timestamp,
            drift_ms=100
        ):
            mismatches.append({
                "field": "timestamp",
                "execution": execution_timestamp.isoformat()
                
                if isinstance(execution_timestamp, datetime)
                else str(execution_timestamp),
                "confirmation": confirmation_timestamp.isoformat()
                
                if isinstance(confirmation_timestamp, datetime)
                else str(confirmation_timestamp),
                "reason": "Timestamp drift beyond 100ms"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Currency
        # Raw "trade_currency" has already been normalized to "currency".
        # ---------------------------------------------------------
        execution_currency = self._get(execution, "currency")
        confirmation_currency = self._get(confirmation, "currency")

        if (
            execution_currency
            and confirmation_currency
            and execution_currency != confirmation_currency
        ):
            mismatches.append({
                "field": "currency",
                "execution": execution_currency,
                "confirmation": confirmation_currency,
                "reason": "Trade currency mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # Settlement date
        # ---------------------------------------------------------
        execution_settlement = self._get(execution, "settlement_date")
        confirmation_settlement = self._get(confirmation, "settlement_date")

        if ( execution_settlement and confirmation_settlement and execution_settlement != confirmation_settlement ):
            mismatches.append({
                "field": "settlement_date",
                "execution": execution_settlement,
                "confirmation": confirmation_settlement,
                "reason": "Settlement date mismatch"
            })
            is_matched = False

        # ---------------------------------------------------------
        # P&L consistency
        #
        # net_pnl =
        # realized_pnl + unrealized_pnl + fx_pnl - total_fees
        # ---------------------------------------------------------
        if pnl:
            net_pnl = self._get(pnl, "net_pnl")
            realized_pnl = self._get(pnl, "realized_pnl", 0.0)
            unrealized_pnl = self._get(pnl, "unrealized_pnl", 0.0)
            fx_pnl = self._get(pnl, "fx_pnl", 0.0)
            total_fees = self._get(pnl, "total_fees", 0.0)

            if net_pnl is not None:
                try:
                    reported_net_pnl = float(net_pnl)
                    realized = float(realized_pnl or 0.0)
                    unrealized = float(unrealized_pnl or 0.0)
                    fx = float(fx_pnl or 0.0)
                    fees = float(total_fees or 0.0)

                    calculated_net_pnl = (
                        realized
                        + unrealized
                        + fx
                        - fees
                    )

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

        status = "MATCHED" if is_matched else "MISMATCHED"
        break_type = self._classify_break(mismatches)

        print(f"Reconciliation for Trade {trade_id}: Status = {status}")

        if mismatches:
            print(f"Mismatches: {mismatches}")

            if self.mismatched_trades_counter:
                self.mismatched_trades_counter.inc()

        else:
            if self.matched_trades_counter:
                self.matched_trades_counter.inc()

        # Persist the reconciliation result.
        self._save_result(
            trade_id,
            execution,
            confirmation,
            pnl,
            status,
            break_type,
            mismatches
        )

    def _save_result( self, trade_id, execution, confirmation, pnl, status, break_type, mismatches ):
        """
        Store raw source records in SQLite while reconciliation operates
        on normalized canonical objects.
        """
        session = self.session

        execution_data = self._serialize(execution)
        confirmation_data = self._serialize(confirmation)
        pnl_data = self._serialize(pnl)

        ticker = ( self._get( execution, "ticker" ) 
                or self._get( confirmation, "ticker" ) 
                or "N/A" )

        try:
            existing = (
                session.query(ReconciliationResult)
                .filter_by(trade_id=trade_id)
                .first()
            )

            if existing:
                existing.ticker = ticker
                existing.status = status
                existing.execution_data = execution_data
                existing.confirmation_data = confirmation_data
                existing.pnl_data = pnl_data
                existing.break_type = break_type
                existing.mismatch_details = mismatches
                existing.reconciliation_timestamp = datetime.utcnow()

                print(f"Updated trade {trade_id} in DB.")

            else:
                new_result = ReconciliationResult(
                    trade_id=trade_id,
                    ticker=ticker,
                    status=status,
                    execution_data=execution_data,
                    confirmation_data=confirmation_data,
                    pnl_data=pnl_data,
                    break_type=break_type,
                    mismatch_details=mismatches
                )

                session.add(new_result)
                print(f"Inserted trade {trade_id} into DB.")

            session.commit()

        except Exception as e:
            session.rollback()
            print(f"DB error for trade {trade_id}: {e}")
            
            
    def _try_match_confirmation(self, confirmation):
        """
        Try to match a broker confirmation against pending executions.
        """

        executions = self.match_store.get_executions()

        if not executions:
            print(
                f"No pending executions available for "
                f"confirmation {self._get(confirmation, 'trade_id')}"
            )
            return

        result = find_match(
            executions,
            confirmation,
            threshold=80,
            max_group_size=3
        )

        match_type = result["match_type"]

        if match_type == "UNMATCHED":
            print(
                f"No economic match found for confirmation "
                f"{self._get(confirmation, 'trade_id')}"
            )
            return

        matched_executions = result["executions"]

        if match_type == "ONE_TO_ONE":
            execution_for_reconciliation = (
                matched_executions[0]
            )

        elif match_type == "MANY_TO_ONE":
            execution_for_reconciliation = (
                result["aggregated_execution"]
            )

        else:
            return

        print(
            f"Trade match found: "
            f"type={match_type}, "
            f"score={result['score']}"
        )

        # Remove records from pending store once matched.
        self.match_store.remove_executions(
            matched_executions
        )

        self.match_store.remove_confirmation(
            confirmation
        )

        # Try to attach P&L if one exists.
        pnl = self._find_pnl_for_match(
            execution_for_reconciliation
        )

        # When a match is found, save the matched pair before calling reconciliation
        reconciliation_id = self._build_reconciliation_id(execution_for_reconciliation)
        
        if not reconciliation_id:
            print( "Unable to create reconciliation ID " "for matched trade." )
            return

        self._register_completed_match( reconciliation_id, execution_for_reconciliation, confirmation )

        self._perform_reconciliation_and_save( reconciliation_id, execution_for_reconciliation, confirmation, pnl )
        
        
        # Keep the matched pair available in case P&L arrives later.
        self._register_completed_match(
            reconciliation_id,
            execution_for_reconciliation,
            confirmation
        )

        self._perform_reconciliation_and_save(
            reconciliation_id,
            execution_for_reconciliation,
            confirmation,
            pnl
        )
                

    def _try_match_pending_confirmations(self):
        """
        Re-run matching when a new execution arrives.

        This handles the case where the broker confirmation
        arrived before the internal execution.
        """

        confirmations = (
            self.match_store.get_confirmations()
        )

        for confirmation in confirmations:
            self._try_match_confirmation(
                confirmation
            )
            
            
    def _find_pnl_for_match(self, execution):
        """
        Initial P&L association logic.

        Prefer same trade_id. More advanced economic
        association will be added later.
        """

        execution_trade_id = self._get(
            execution,
            "trade_id"
        )

        for pnl in self.match_store.get_pnl_records():
            pnl_trade_id = self._get(
                pnl,
                "trade_id"
            )

            if pnl_trade_id == execution_trade_id:
                self.match_store.remove_pnl(pnl)
                return pnl

        return None
    
    def _try_attach_pnl(self, pnl):
        """
        Attach late-arriving P&L using any known source trade ID.

        The P&L trade ID is first resolved through the alias map
        to TradeRecon's canonical reconciliation ID.
        """
        pnl_trade_id = self._get( pnl, "trade_id" )

        if not pnl_trade_id:
            print( "P&L record has no trade_id; " "cannot associate it yet." )
            return

        pnl_trade_id = str( pnl_trade_id )

        # Convert source-system ID into TradeRecon's
        # canonical reconciliation ID.
        reconciliation_id = ( self.reconciliation_aliases.get( pnl_trade_id ) )

        if not reconciliation_id:
            print( f"No reconciliation alias found for P&L {pnl_trade_id}" )
            return

        match = self.completed_matches.get( reconciliation_id )

        if not match:
            print( f"No completed match found for reconciliation {reconciliation_id}" )
            return

        execution = match["execution"]
        confirmation = match["confirmation"]

        self.match_store.remove_pnl( pnl )

        self._perform_reconciliation_and_save(
            reconciliation_id,
            execution,
            confirmation,
            pnl
        )

        print( f"Late P&L {pnl_trade_id} attached to reconciliation {reconciliation_id}" )
        
        
    def _register_completed_match(self, reconciliation_id, execution, confirmation):
        """
        Store an already matched execution/confirmation pair so
        late-arriving P&L can be associated later.
        """
        reconciliation_id = str(reconciliation_id)


        self.completed_matches[reconciliation_id] = {
            "execution": execution,
            "confirmation": confirmation
        }
        
        # Canonical ID points to itself.
        self.reconciliation_aliases[reconciliation_id] = reconciliation_id
        
        # Register all internal execution IDs.
        for execution_id in self._get_component_trade_ids(execution):
            self.reconciliation_aliases[execution_id] = reconciliation_id

        # Register broker confirmation ID.
        confirmation_id = self._get( confirmation, "trade_id" )

        if confirmation_id:
            self.reconciliation_aliases[str(confirmation_id)] = reconciliation_id
        
        
    def _get_component_trade_ids(self, execution):
        """
        Return all internal execution IDs represented by a canonical trade.

        For a normal one-to-one trade this returns one ID.
        For an aggregated trade it returns all component execution IDs.
        """

        raw_data = self._get(
            execution,
            "raw_data",
            {}
        ) or {}

        component_ids = raw_data.get(
            "component_trade_ids"
        )

        if component_ids:
            return [
                str(trade_id)
                for trade_id in component_ids
                if trade_id
            ]

        trade_id = self._get(
            execution,
            "trade_id"
        )

        return [str(trade_id)] if trade_id else []

    def _build_reconciliation_id(self, execution):
        """
        Build TradeRecon's canonical ID for the economic trade.

        One execution:
            T001

        Aggregated executions:
            T001+T002
        """

        component_ids = self._get_component_trade_ids(
            execution
        )

        if component_ids:
            return "+".join(component_ids)

        trade_id = self._get(
            execution,
            "trade_id"
        )

        return (
            str(trade_id)
            if trade_id
            else None
        )


    def process_stale_records( self, timeout_seconds=30 ):
        """
        Convert records that have remained unmatched beyond the
        configured timeout into explicit reconciliation breaks.
        """

        stale_executions = (
            self.match_store.get_stale_executions(
                timeout_seconds
            )
        )

        stale_confirmations = (
            self.match_store.get_stale_confirmations(
                timeout_seconds
            )
        )

        for execution in stale_executions:
            trade_id = self._get(
                execution,
                "trade_id"
            )

            print(
                f"Execution {trade_id} exceeded "
                f"{timeout_seconds}s matching timeout."
            )

            self._save_unmatched_break(
                execution=execution,
                confirmation=None,
                break_type="MISSING_CONFIRMATION"
            )

            self.match_store.remove_execution(
                execution
            )

        for confirmation in stale_confirmations:
            trade_id = self._get(
                confirmation,
                "trade_id"
            )

            print(
                f"Confirmation {trade_id} exceeded "
                f"{timeout_seconds}s matching timeout."
            )

            self._save_unmatched_break(
                execution=None,
                confirmation=confirmation,
                break_type="MISSING_EXECUTION"
            )

            self.match_store.remove_confirmation(
                confirmation
            )
            
            
    def _save_unmatched_break( self, execution=None, confirmation=None, break_type="UNMATCHED" ):
        """
        Persist an unmatched record as an explicit trade break.
        """

        record = execution or confirmation

        if record is None:
            return

        trade_id = self._get(
            record,
            "trade_id"
        )

        if not trade_id:
            print(
                f"Cannot persist {break_type}: "
                f"record has no trade_id."
            )
            return

        trade_id = str(trade_id)

        mismatches = [{
            "field": "matching",
            "reason": break_type
        }]

        if self.total_trades_counter:
            self.total_trades_counter.inc()

        if self.mismatched_trades_counter:
            self.mismatched_trades_counter.inc()

        self._save_result(
            trade_id=trade_id,
            execution=execution,
            confirmation=confirmation,
            pnl=None,
            status="MISMATCHED",
            break_type=break_type,
            mismatches=mismatches
        )

        print(
            f"Trade {trade_id} aged out: "
            f"{break_type}"
        )
        
    def _classify_break(self, mismatches):
        """
        Convert detailed mismatch records into one high-level break type.
        """

        if not mismatches:
            return None

        break_types = set()

        field_mapping = {
            "instrument_id": "INSTRUMENT_BREAK",
            "quantity": "QUANTITY_BREAK",
            "price": "PRICE_BREAK",
            "side": "SIDE_BREAK",
            "timestamp": "TIMESTAMP_BREAK",
            "currency": "CURRENCY_BREAK",
            "settlement_date": "SETTLEMENT_BREAK",
            "net_pnl": "PNL_BREAK",
            "pnl_calculation_error": "PNL_BREAK"
        }

        for mismatch in mismatches:
            reason = mismatch.get("reason")

            if reason in {
                "MISSING_EXECUTION",
                "MISSING_CONFIRMATION"
            }:
                break_types.add(reason)
                continue

            field = mismatch.get("field")

            break_type = field_mapping.get(field)

            if break_type:
                break_types.add(break_type)

        if not break_types:
            return "OTHER_BREAK"

        if len(break_types) > 1:
            return "MULTIPLE_BREAKS"

        return next(iter(break_types))
    
    
    def get_pending_records(self):
        """
        Return the current live matching queue for the UI.
        """

        pending = []

        for execution in self.match_store.get_executions():
            pending.append({
                "record_type": "EXECUTION",
                "trade_id": self._get(execution, "trade_id"),
                "ticker": self._get(execution, "ticker"),
                "side": self._get(execution, "side"),
                "quantity": self._get(execution, "quantity"),
                "price": self._get(execution, "price"),
                "account_id": self._get(execution, "account_id"),
                "status": "PENDING",
                "waiting_for": "CONFIRMATION"
            })

        for confirmation in self.match_store.get_confirmations():
            pending.append({
                "record_type": "CONFIRMATION",
                "trade_id": self._get(confirmation, "trade_id"),
                "ticker": self._get(confirmation, "ticker"),
                "side": self._get(confirmation, "side"),
                "quantity": self._get(confirmation, "quantity"),
                "price": self._get(confirmation, "price"),
                "account_id": self._get(confirmation, "account_id"),
                "status": "PENDING",
                "waiting_for": "EXECUTION"
            })

        return pending
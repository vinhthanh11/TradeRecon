import math
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .reconcile import ReconciliationResult, Base


class ReportGenerator:
    def __init__(
        self,
        db_url="sqlite:///./reports/reconciliation.db",
        template_dir="./reports/templates",
    ):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.report_output_dir = "./reports"
        os.makedirs(self.report_output_dir, exist_ok=True)
        print(
            f"ReportGenerator initialized. DB: {db_url}, "
            f"Templates: {template_dir}"
        )

    def _get_session(self):
        return self.Session()

    @staticmethod
    def _safe_get(data, key, default=None):
        if not isinstance(data, dict):
            return default
        return data.get(key, default)

    @staticmethod
    def _format_number(value, decimals=4):
        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        try:
            number = float(value)
        except (TypeError, ValueError):
            return value

        if math.isnan(number):
            return None

        if number.is_integer():
            return f"{int(number):,}"

        return f"{number:,.{decimals}f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_money(value):
        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        try:
            number = float(value)
        except (TypeError, ValueError):
            return value

        if math.isnan(number):
            return None

        return f"{number:,.2f}"

    @staticmethod
    def _format_timestamp(value):
        if not value:
            return None

        text = str(value)

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except (ValueError, TypeError):
            return text

    @staticmethod
    def _component_ids(data):
        if not isinstance(data, dict):
            return []

        candidates = [
            data.get("component_trade_ids"),
            data.get("component_ids"),
        ]

        raw_data = data.get("raw_data")
        if isinstance(raw_data, dict):
            candidates.extend([
                raw_data.get("component_trade_ids"),
                raw_data.get("component_ids"),
            ])

        for value in candidates:
            if isinstance(value, list):
                return [str(v) for v in value if v is not None]

        return []

    def _infer_match_type(self, execution_data, confirmation_data):
        execution_components = self._component_ids(execution_data)
        confirmation_components = self._component_ids(confirmation_data)

        execution_count = len(execution_components) if execution_components else (
            1 if execution_data else 0
        )
        confirmation_count = len(confirmation_components) if confirmation_components else (
            1 if confirmation_data else 0
        )

        if execution_count > 1 and confirmation_count > 1:
            return "MANY_TO_MANY"
        if execution_count > 1 and confirmation_count == 1:
            return "MANY_TO_ONE"
        if execution_count == 1 and confirmation_count > 1:
            return "ONE_TO_MANY"
        if execution_count == 1 and confirmation_count == 1:
            return "ONE_TO_ONE"
        if execution_count and not confirmation_count:
            return "UNMATCHED_EXECUTION"
        if confirmation_count and not execution_count:
            return "UNMATCHED_CONFIRMATION"

        return "UNKNOWN"

    @staticmethod
    def _build_mismatch_summary(details):
        if not details:
            return "—"

        messages = []

        for detail in details:
            if not isinstance(detail, dict):
                messages.append(str(detail))
                continue

            field = detail.get("field", "unknown")
            reason = detail.get("reason", "Mismatch")
            execution = detail.get("execution")
            confirmation = detail.get("confirmation")

            if execution is not None or confirmation is not None:
                messages.append(
                    f"{field}: {reason} "
                    f"(execution={execution!s}, confirmation={confirmation!s})"
                )
            else:
                messages.append(f"{field}: {reason}")

        return " | ".join(messages)

    @staticmethod
    def _detect_break_type(result, mismatch_details):
        explicit_break_type = getattr(result, "break_type", None)
        if explicit_break_type:
            return explicit_break_type

        if not mismatch_details:
            return None

        break_map = {
            "instrument_id": "INSTRUMENT_BREAK",
            "quantity": "QUANTITY_BREAK",
            "price": "PRICE_BREAK",
            "side": "SIDE_BREAK",
            "timestamp": "TIMESTAMP_BREAK",
            "currency": "CURRENCY_BREAK",
            "settlement_date": "SETTLEMENT_BREAK",
            "net_pnl": "PNL_BREAK",
            "pnl_calculation_error": "PNL_BREAK",
        }

        detected = []

        for detail in mismatch_details:
            if not isinstance(detail, dict):
                continue

            reason = str(detail.get("reason", ""))
            field = detail.get("field")

            if reason in {"MISSING_EXECUTION", "MISSING_CONFIRMATION"}:
                detected.append(reason)
            elif field in break_map:
                detected.append(break_map[field])

        unique = list(dict.fromkeys(detected))

        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            return "MULTIPLE_BREAKS"

        return "OTHER_BREAK"

    def fetch_all_reconciliation_results(self) -> pd.DataFrame:
        session = self._get_session()

        try:
            results = session.query(ReconciliationResult).all()
            data = []

            for r in results:
                execution_data = r.execution_data or {}
                confirmation_data = r.confirmation_data or {}
                pnl_data = r.pnl_data or {}
                mismatch_details = (
                    r.mismatch_details
                    if r.mismatch_details is not None
                    else []
                )

                execution_components = self._component_ids(execution_data)
                confirmation_components = self._component_ids(confirmation_data)

                row = {
                    "id": r.id,
                    "trade_id": r.trade_id,
                    "ticker": r.ticker,
                    "status": r.status,
                    "break_type": self._detect_break_type(
                        r, mismatch_details
                    ),
                    "match_type": self._infer_match_type(
                        execution_data,
                        confirmation_data,
                    ),
                    "execution_components": execution_components,
                    "confirmation_components": confirmation_components,
                    "reconciliation_timestamp": self._format_timestamp(
                        r.reconciliation_timestamp.isoformat()
                        if r.reconciliation_timestamp
                        else None
                    ),
                    "execution_qty": self._safe_get(
                        execution_data, "quantity"
                    ),
                    "execution_qty_display": self._format_number(
                        self._safe_get(execution_data, "quantity"),
                        decimals=2,
                    ),
                    "execution_price": self._safe_get(
                        execution_data, "price"
                    ),
                    "execution_price_display": self._format_number(
                        self._safe_get(execution_data, "price"),
                        decimals=4,
                    ),
                    "execution_timestamp": self._format_timestamp(
                        self._safe_get(execution_data, "timestamp")
                    ),
                    "confirmation_qty": self._safe_get(
                        confirmation_data, "quantity"
                    ),
                    "confirmation_qty_display": self._format_number(
                        self._safe_get(confirmation_data, "quantity"),
                        decimals=2,
                    ),
                    "confirmation_price": self._safe_get(
                        confirmation_data, "price"
                    ),
                    "confirmation_price_display": self._format_number(
                        self._safe_get(confirmation_data, "price"),
                        decimals=4,
                    ),
                    "confirmation_timestamp": self._format_timestamp(
                        self._safe_get(confirmation_data, "timestamp")
                    ),
                    "net_pnl": self._safe_get(pnl_data, "net_pnl"),
                    "net_pnl_display": self._format_money(
                        self._safe_get(pnl_data, "net_pnl")
                    ),
                    "commission": self._safe_get(
                        confirmation_data, "commission"
                    ),
                    "commission_display": self._format_money(
                        self._safe_get(confirmation_data, "commission")
                    ),
                    "mismatch_details": mismatch_details,
                    "mismatch_summary": self._build_mismatch_summary(
                        mismatch_details
                    ),
                }

                data.append(row)

            return pd.DataFrame(data)

        except Exception as e:
            print(f"Error fetching reconciliation results: {e}")
            return pd.DataFrame()

        finally:
            session.close()

    def get_reconciliation_status(self):
        """
        JSON-friendly payload for /api/reconciliation_status.
        Removes pandas NaN and includes display/enrichment fields.
        """
        df = self.fetch_all_reconciliation_results()

        if df.empty:
            return []

        records = df.to_dict(orient="records")

        def clean(value):
            if isinstance(value, dict):
                return {
                    key: clean(item)
                    for key, item in value.items()
                }

            if isinstance(value, list):
                return [
                    clean(item)
                    for item in value
                ]

            try:
                if pd.isna(value):
                    return None
            except (TypeError, ValueError):
                pass

            return value

        return [
            clean(record)
            for record in records
        ]

    def generate_html_report(self, filename: str = None) -> str:
        df = self.fetch_all_reconciliation_results()
        template = self.env.get_template("report.html")

        report_data = (
            df.to_dict(orient="records")
            if not df.empty
            else []
        )

        matched_trades = [
            trade
            for trade in report_data
            if trade.get("status") == "MATCHED"
        ]

        mismatched_trades = [
            trade
            for trade in report_data
            if trade.get("status") == "MISMATCHED"
        ]

        grouped_match_count = sum(
            1
            for trade in matched_trades
            if trade.get("match_type") in {
                "MANY_TO_ONE",
                "ONE_TO_MANY",
                "MANY_TO_MANY",
            }
        )

        html_content = template.render(
            report_timestamp=datetime.now().isoformat(timespec="seconds"),
            total_trades=len(report_data),
            matched_count=len(matched_trades),
            mismatched_count=len(mismatched_trades),
            grouped_match_count=grouped_match_count,
            matched_trades=matched_trades,
            mismatched_trades=mismatched_trades,
        )

        if filename:
            filepath = os.path.join(
                self.report_output_dir,
                filename,
            )

            with open(
                filepath,
                "w",
                encoding="utf-8",
            ) as file:
                file.write(html_content)

            print(
                f"HTML report saved to {filepath}"
            )

        return html_content

    def generate_csv_report(
        self,
        filename: str = "reconciliation_report.csv",
    ):
        df = self.fetch_all_reconciliation_results()

        filepath = os.path.join(
            self.report_output_dir,
            filename,
        )

        df.to_csv(
            filepath,
            index=False,
        )

        print(
            f"CSV report saved to {filepath}"
        )

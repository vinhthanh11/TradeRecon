import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


SCENARIO_WEIGHTS = {
    "MATCHED": 65,
    "PRICE_BREAK": 8,
    "QUANTITY_BREAK": 7,
    "TIMESTAMP_BREAK": 6,
    "SETTLEMENT_BREAK": 4,
    "MISSING_CONFIRMATION": 4,
    "MISSING_EXECUTION": 3,
    "PNL_BREAK": 3,
}


def choose_scenario():
    return random.choices(
        population=list(SCENARIO_WEIGHTS.keys()),
        weights=list(SCENARIO_WEIGHTS.values()),
        k=1
    )[0]


def generate_trade_data(
    output_dir="berlin",
    num_trades=50,
    seed=42
):
    random.seed(seed)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    executions_file = output_path / "executions.csv"
    broker_file = output_path / "broker_confirmations.csv"
    pnl_file = output_path / "pnl_snapshot.csv"
    expected_file = output_path / "expected_results.csv"

    instruments = [
        {
            "ticker": "AAPL",
            "broker_ticker": "AAPL",
            "isin": "US0378331005",
            "exchange": "NASDAQ",
            "venue_mic": "XNAS",
            "country": "US",
            "currency": "USD",
            "base_price": 190.50,
        },
        {
            "ticker": "MSFT",
            "broker_ticker": "MSFT",
            "isin": "US5949181045",
            "exchange": "NASDAQ",
            "venue_mic": "XNAS",
            "country": "US",
            "currency": "USD",
            "base_price": 420.00,
        },
        {
            "ticker": "7203",
            "broker_ticker": "7203.T",
            "isin": "JP3633400001",
            "exchange": "Tokyo Stock Exchange",
            "venue_mic": "XTKS",
            "country": "JP",
            "currency": "JPY",
            "base_price": 2850.00,
        },
        {
            "ticker": "HSBA",
            "broker_ticker": "HSBA.L",
            "isin": "GB0005405286",
            "exchange": "London Stock Exchange",
            "venue_mic": "XLON",
            "country": "GB",
            "currency": "GBP",
            "base_price": 7.25,
        },
        {
            "ticker": "SAP",
            "broker_ticker": "SAP.DE",
            "isin": "DE0007164600",
            "exchange": "Xetra",
            "venue_mic": "XETR",
            "country": "DE",
            "currency": "EUR",
            "base_price": 205.00,
        },
    ]

    fx_rates = {
        "USD": 1.0,
        "EUR": 1.17,
        "GBP": 1.36,
        "JPY": 0.0068,
    }

    execution_headers = [
        "trade_id", "order_id", "execution_id", "account_id",
        "portfolio_id", "side", "ticker", "isin",
        "security_type", "quantity", "price", "trade_currency",
        "notional", "exchange", "venue_mic", "market_country",
        "timestamp", "settlement_date", "fx_rate", "source_system",
    ]

    broker_headers = [
        "trade_id", "broker_trade_id", "broker_execution_id",
        "order_id", "account_id", "side", "ticker", "isin",
        "security_type", "quantity", "price", "gross_notional",
        "trade_currency", "exchange", "venue_mic", "market_country",
        "broker_name", "timestamp", "settlement_date", "fx_rate",
        "commission", "exchange_fee", "clearing_fee", "tax",
        "stamp_duty", "total_fees", "net_settlement_amount",
        "confirmation_status", "source_system",
    ]

    pnl_headers = [
        "trade_id", "account_id", "portfolio_id", "ticker", "isin",
        "side", "quantity", "trade_price", "mark_price",
        "trade_currency", "base_currency", "fx_rate",
        "gross_notional", "market_value", "realized_pnl",
        "unrealized_pnl", "fx_pnl", "total_fees",
        "net_pnl", "pnl_currency", "timestamp",
        "pricing_source", "source_system",
    ]

    expected_headers = [
        "trade_id",
        "scenario",
        "expected_status",
        "expected_break_type",
    ]

    executions = []
    confirmations = []
    pnl_snapshots = []
    expected_results = []

    base_time = datetime(2026, 9, 12, 10, 0, 0)

    for i in range(1, num_trades + 1):

        scenario = choose_scenario()
        instrument = random.choice(instruments)

        trade_id = f"T{i:04d}"
        order_id = f"O{i:05d}"
        execution_id = f"E{i:06d}"

        broker_trade_id = f"BT{i:06d}"
        broker_execution_id = f"BE{i:06d}"

        account_id = random.choice([
            "ACC001",
            "ACC002",
            "ACC003"
        ])

        portfolio_id = random.choice([
            "PORT_US",
            "PORT_GLOBAL",
            "PORT_ARB"
        ])

        side = random.choice([
            "BUY",
            "SELL"
        ])

        quantity = random.choice([
            50,
            100,
            200,
            500,
            1000
        ])

        price = round(
            instrument["base_price"]
            * (1 + random.uniform(-0.01, 0.01)),
            4
        )

        currency = instrument["currency"]
        fx_rate = fx_rates[currency]

        notional = round(
            quantity * price,
            2
        )

        execution_timestamp = (
            base_time
            + timedelta(
                seconds=random.randint(0, 3600),
                milliseconds=random.randint(0, 150)
            )
        )

        # Normal trades stay inside 100ms tolerance.
        broker_timestamp = (
            execution_timestamp
            + timedelta(
                milliseconds=random.randint(-75, 75)
            )
        )

        trade_date = execution_timestamp.date()

        settlement_date = (
            trade_date
            + timedelta(days=2)
        )

        broker_quantity = quantity
        broker_price = round(
            price
            + random.choice([
                0,
                0,
                0.0001,
                -0.0001
            ]),
            4
        )

        broker_settlement_date = settlement_date

        # =====================================================
        # RANDOM SCENARIO MUTATIONS
        # =====================================================

        if scenario == "PRICE_BREAK":
            broker_price = round(
                price
                + random.choice([
                    0.10,
                    0.25,
                    0.50,
                    -0.10,
                    -0.25
                ]),
                4
            )

        elif scenario == "QUANTITY_BREAK":
            broker_quantity = random.choice([
                max(1, quantity // 2),
                quantity + 50,
                quantity + 100
            ])

        elif scenario == "TIMESTAMP_BREAK":
            broker_timestamp = (
                execution_timestamp
                + timedelta(
                    milliseconds=random.randint(
                        250,
                        1200
                    )
                )
            )

        elif scenario == "SETTLEMENT_BREAK":
            broker_settlement_date = (
                settlement_date
                + timedelta(days=1)
            )

        # =====================================================
        # FEES
        # =====================================================

        commission = round(
            max(
                0.50,
                broker_quantity * 0.002
            ),
            2
        )

        exchange_fee = round(
            broker_quantity * 0.0005,
            2
        )

        clearing_fee = round(
            broker_quantity * 0.0002,
            2
        )

        tax = 0.0
        stamp_duty = 0.0

        broker_notional = round(
            broker_quantity * broker_price,
            2
        )

        if (
            instrument["country"] == "GB"
            and side == "BUY"
        ):
            stamp_duty = round(
                broker_notional * 0.005,
                2
            )

        total_fees = round(
            commission
            + exchange_fee
            + clearing_fee
            + tax
            + stamp_duty,
            2
        )

        if side == "BUY":
            net_settlement_amount = round(
                broker_notional
                + total_fees,
                2
            )
        else:
            net_settlement_amount = round(
                broker_notional
                - total_fees,
                2
            )

        # =====================================================
        # P&L
        # =====================================================

        mark_price = round(
            price
            * (
                1
                + random.uniform(
                    -0.02,
                    0.02
                )
            ),
            4
        )

        market_value = round(
            quantity * mark_price,
            2
        )

        direction = (
            1
            if side == "BUY"
            else -1
        )

        unrealized_pnl_local = round(
            (
                mark_price
                - price
            )
            * quantity
            * direction,
            2
        )

        unrealized_pnl = round(
            unrealized_pnl_local
            * fx_rate,
            2
        )

        realized_pnl = 0.0

        if currency != "USD":
            fx_pnl = round(
                random.uniform(
                    -10,
                    10
                ),
                2
            )
        else:
            fx_pnl = 0.0

        fees_usd = round(
            total_fees
            * fx_rate,
            2
        )

        net_pnl = round(
            realized_pnl
            + unrealized_pnl
            + fx_pnl
            - fees_usd,
            2
        )

        if scenario == "PNL_BREAK":
            net_pnl = round(
                net_pnl
                + random.choice([
                    10,
                    25,
                    50,
                    -10,
                    -25
                ]),
                2
            )

        pnl_timestamp = datetime.combine(
            trade_date,
            datetime.min.time()
        ).replace(
            hour=16,
            minute=0,
            second=0
        )

        # =====================================================
        # EXECUTION RECORD
        # =====================================================

        execution_record = {
            "trade_id": trade_id,
            "order_id": order_id,
            "execution_id": execution_id,
            "account_id": account_id,
            "portfolio_id": portfolio_id,
            "side": side,
            "ticker": instrument["ticker"],
            "isin": instrument["isin"],
            "security_type": "COMMON_STOCK",
            "quantity": quantity,
            "price": price,
            "trade_currency": currency,
            "notional": notional,
            "exchange": instrument["exchange"],
            "venue_mic": instrument["venue_mic"],
            "market_country": instrument["country"],
            "timestamp": execution_timestamp.isoformat(
                timespec="milliseconds"
            ),
            "settlement_date": settlement_date.isoformat(),
            "fx_rate": fx_rate,
            "source_system": "OMS",
        }

        # =====================================================
        # BROKER RECORD
        # =====================================================

        confirmation_record = {
            "trade_id": trade_id,
            "broker_trade_id": broker_trade_id,
            "broker_execution_id": broker_execution_id,
            "order_id": order_id,
            "account_id": account_id,
            "side": side,
            "ticker": instrument["broker_ticker"],
            "isin": instrument["isin"],
            "security_type": "COMMON_STOCK",
            "quantity": broker_quantity,
            "price": broker_price,
            "gross_notional": broker_notional,
            "trade_currency": currency,
            "exchange": instrument["exchange"],
            "venue_mic": instrument["venue_mic"],
            "market_country": instrument["country"],
            "broker_name": random.choice([
                "Broker_A",
                "Broker_B",
                "Broker_C"
            ]),
            "timestamp": broker_timestamp.isoformat(
                timespec="milliseconds"
            ),
            "settlement_date": broker_settlement_date.isoformat(),
            "fx_rate": fx_rate,
            "commission": commission,
            "exchange_fee": exchange_fee,
            "clearing_fee": clearing_fee,
            "tax": tax,
            "stamp_duty": stamp_duty,
            "total_fees": total_fees,
            "net_settlement_amount": net_settlement_amount,
            "confirmation_status": "CONFIRMED",
            "source_system": "BROKER",
        }

        # =====================================================
        # P&L RECORD
        # =====================================================

        pnl_record = {
            "trade_id": trade_id,
            "account_id": account_id,
            "portfolio_id": portfolio_id,
            "ticker": instrument["ticker"],
            "isin": instrument["isin"],
            "side": side,
            "quantity": quantity,
            "trade_price": price,
            "mark_price": mark_price,
            "trade_currency": currency,
            "base_currency": "USD",
            "fx_rate": fx_rate,
            "gross_notional": notional,
            "market_value": market_value,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "fx_pnl": fx_pnl,
            "total_fees": fees_usd,
            "net_pnl": net_pnl,
            "pnl_currency": "USD",
            "timestamp": pnl_timestamp.isoformat(
                timespec="seconds"
            ),
            "pricing_source": "MARKET_DATA",
            "source_system": "PNL_ENGINE",
        }

        # =====================================================
        # DECIDE WHICH RECORDS ACTUALLY EXIST
        # =====================================================

        if scenario != "MISSING_EXECUTION":
            executions.append(
                execution_record
            )

        if scenario != "MISSING_CONFIRMATION":
            confirmations.append(
                confirmation_record
            )

        pnl_snapshots.append(
            pnl_record
        )

        # =====================================================
        # EXPECTED RESULT
        # =====================================================

        if scenario == "MATCHED":
            expected_status = "MATCHED"
            expected_break = ""

        else:
            expected_status = "MISMATCHED"
            expected_break = scenario

        expected_results.append({
            "trade_id": trade_id,
            "scenario": scenario,
            "expected_status": expected_status,
            "expected_break_type": expected_break,
        })

    # =========================================================
    # CSV WRITER
    # =========================================================

    def write_csv(
        filename,
        headers,
        rows
    ):
        with open(
            filename,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=headers
            )

            writer.writeheader()
            writer.writerows(rows)

    write_csv(
        executions_file,
        execution_headers,
        executions
    )

    write_csv(
        broker_file,
        broker_headers,
        confirmations
    )

    write_csv(
        pnl_file,
        pnl_headers,
        pnl_snapshots
    )

    write_csv(
        expected_file,
        expected_headers,
        expected_results
    )

    # =========================================================
    # SUMMARY
    # =========================================================

    scenario_counts = {}

    for result in expected_results:
        scenario = result["scenario"]

        scenario_counts[scenario] = (
            scenario_counts.get(
                scenario,
                0
            )
            + 1
        )

    print(
        f"\nGenerated {num_trades} simulated trades."
    )

    print(
        f"Executions: {len(executions)}"
    )

    print(
        f"Confirmations: {len(confirmations)}"
    )

    print(
        f"P&L snapshots: {len(pnl_snapshots)}"
    )

    print("\nScenario distribution:")

    for scenario, count in sorted(
        scenario_counts.items()
    ):
        print(
            f"  {scenario:<22} {count}"
        )

    print("\nFiles:")
    print(executions_file)
    print(broker_file)
    print(pnl_file)
    print(expected_file)


if __name__ == "__main__":
    generate_trade_data(
        output_dir="berlin",
        num_trades=100,
        seed=42
    )
# TradeRecon Architecture Upgrade (Berlin Release)

## Overview

TradeRecon is evolving from a simple row-by-row reconciliation demo into a more extensible trade reconciliation framework that can handle different trade representations, broker-specific formats, international instruments, partial fills, aggregation, and more complex matching logic.

The original version of TradeRecon worked well when execution, broker confirmation, and P&L records shared a simple and consistent schema. As the data model expanded to include fields such as ISIN, exchange, currency, settlement date, fees, and different ticker representations, the reconciliation logic needed to become more modular.

This upgrade introduces a normalization and canonical trade representation layer so that source systems can remain different while TradeRecon compares them in a consistent internal format.

## Goal of the Upgrade

The main goal is to separate three concerns that were previously mixed together inside `reconcile.py`:

1. **Source-specific representation**

   * Different systems may use different field names or instrument identifiers.
   * Example: `7203` internally and `7203.T` at the broker.

2. **Trade identity and matching**

   * Two records may represent the same economic trade even if their IDs or row structure are different.
   * Example: two internal fills may correspond to one aggregated broker confirmation.

3. **Reconciliation**

   * Once records are normalized and matched, TradeRecon can compare quantity, price, timestamp, settlement date, currency, P&L, and other fields.

The intended architecture is:

```text
Raw Source Data
      ↓
Normalization
      ↓
Instrument Mapping
      ↓
Canonical Trade Representation
      ↓
Trade Matching / Aggregation
      ↓
Reconciliation
      ↓
Database / Reports / Monitoring
```

The key principle is:

```text
Raw data can be different.
Canonical data should not be.
```

## Why This Upgrade Is Needed

The original architecture assumed that records from different systems had nearly identical structures.

For example:

```text
Execution
trade_id
ticker
quantity
price
timestamp

Confirmation
trade_id
ticker
quantity
price
timestamp
```

This allowed direct comparisons such as:

```python
execution["price"]
confirmation["price"]
```

That approach becomes fragile when different systems represent the same trade differently.

For example:

```text
Internal execution
ticker = 7203
ISIN   = JP3633400001

Broker confirmation
ticker = 7203.T
ISIN   = JP3633400001
```

A simple ticker comparison would incorrectly identify this as a mismatch.

The upgraded architecture instead identifies the underlying instrument first and then performs reconciliation using a normalized representation.

## Current Architecture

The current TradeRecon flow is approximately:

```text
CSV
 ↓
Kafka Producer
 ↓
Kafka Consumer
 ↓
reconcile.py
 ↓
SQLite
 ↓
Reports / Grafana / Prometheus
```

Most reconciliation logic currently lives inside `reconcile.py`.

This works well for basic one-to-one trade reconciliation, but adding more special cases directly into the same file would eventually make the reconciliation engine difficult to maintain.

## Proposed Architecture

The upgraded structure introduces three new layers:

* `normalization/`
* `reference/`
* `matching/`

The proposed project structure is:

```text
TradeRecon/
├── app/
│   ├── __init__.py
│   ├── consumer.py
│   ├── reconcile.py
│   ├── report_generator.py
│   ├── utils.py
│   ├── main.py
│   │
│   ├── normalization/
│   │   ├── __init__.py
│   │   ├── execution_normalizer.py
│   │   ├── confirmation_normalizer.py
│   │   ├── pnl_normalizer.py
│   │   └── canonical_trade.py
│   │
│   ├── reference/
│   │   ├── __init__.py
│   │   ├── instrument_mapper.py
│   │   └── instrument_reference.py
│   │
│   └── matching/
│       ├── __init__.py
│       ├── trade_matcher.py
│       └── aggregation.py
│
├── kafka/
│   └── producer.py
│
├── data/
│   ├── executions.csv
│   ├── broker_confirmations.csv
│   ├── pnl_snapshot.csv
│   │
│   └── reference/
│       └── instruments.csv
│
├── reports/
│   └── templates/
│       └── report.html
│
├── tests/
│   ├── test_reconciliation.py
│   ├── test_normalization.py
│   ├── test_instrument_mapping.py
│   └── test_trade_matching.py
│
├── prometheus/
│   └── prometheus.yml
│
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── datasource.yml
│   │   └── dashboards/
│   │       └── dashboard.yml
│   └── dashboards/
│       └── traderecon_dashboard.json
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## New Components

### `normalization/`

The normalization layer converts raw source messages into a consistent internal representation.

Each source can keep its own format, while the rest of the application receives standardized fields.

Example:

```text
Broker ticker: 7203.T
Internal ticker: 7203
Canonical instrument: JP3633400001
```

#### `execution_normalizer.py`

Normalizes execution records coming from the internal OMS or execution feed.

Responsibilities may include:

```text
field-name normalization
timestamp normalization
currency normalization
instrument lookup
missing-field handling
source metadata
```

#### `confirmation_normalizer.py`

Normalizes broker confirmation records.

This is where broker-specific field names and representations should be handled rather than placing those rules directly inside `reconcile.py`.

#### `pnl_normalizer.py`

Normalizes P&L records and creates consistent fields for:

```text
realized P&L
unrealized P&L
FX P&L
fees
net P&L
valuation timestamp
```

#### `canonical_trade.py`

Defines TradeRecon's internal representation of a trade.

A simplified canonical object may contain:

```python
trade_id
instrument_id
ticker
side
quantity
price
currency
timestamp
settlement_date
source
```

The canonical representation becomes the common language between normalization, matching, and reconciliation.

## Instrument Reference Layer

### `reference/instrument_mapper.py`

The instrument mapper resolves different identifiers to the same security.

Example:

```text
7203
7203.T
JP3633400001

→ Toyota Motor Corporation
→ Canonical ID: JP3633400001
```

This allows TradeRecon to distinguish between a representation difference and a true instrument mismatch.

### `data/reference/instruments.csv`

A reference table can store mappings such as:

```csv
canonical_ticker,isin,cusip,sedol,broker_ticker,exchange,mic,currency
AAPL,US0378331005,037833100,2046251,AAPL,NASDAQ,XNAS,USD
7203,JP3633400001,,,7203.T,Tokyo Stock Exchange,XTKS,JPY
HSBA,GB0005405286,,,HSBA.L,London Stock Exchange,XLON,GBP
SAP,DE0007164600,,,SAP.DE,Xetra,XETR,EUR
```

The reference layer can later be expanded to support additional identifier types and broker-specific mappings.

## Matching Layer

### `matching/trade_matcher.py`

The trade matcher determines whether records from different systems represent the same economic trade.

The current project mainly matches records using:

```text
trade_id
```

The upgraded version can eventually use multiple attributes:

```text
instrument
side
quantity
price
timestamp
account
currency
settlement date
```

This allows TradeRecon to handle cases where internal and broker trade IDs differ.

A future matching score could look like:

```text
Instrument match          +40
Quantity match            +20
Side match                +10
Price within tolerance    +15
Timestamp within tolerance +15
--------------------------------
Total                     100
```

### `matching/aggregation.py`

Aggregation handles cases where one system represents a trade differently from another.

Example:

```text
Internal executions

BUY 100 @ 190.10
BUY 100 @ 190.30
```

Broker confirmation:

```text
BUY 200 @ 190.20
```

The aggregation layer can calculate:

```text
Total quantity = 200
VWAP           = 190.20
```

and compare the aggregated internal execution against the broker confirmation.

This creates the foundation for:

```text
one-to-one matching
one-to-many matching
many-to-one matching
partial fills
aggregated confirmations
```

## Reconciliation Engine

`reconcile.py` remains the core reconciliation engine, but its responsibility becomes narrower.

Instead of understanding every source format and every broker-specific edge case, it should primarily compare normalized records.

Examples of reconciliation checks include:

```text
quantity
price
timestamp drift
instrument identity
trade currency
settlement date
fees
net P&L
```

The intended long-term flow is:

```python
execution = normalize_execution(raw_execution)
confirmation = normalize_confirmation(raw_confirmation)

match = match_trades(
    execution,
    confirmation
)

result = reconcile(
    execution,
    confirmation,
    pnl
)
```

This keeps `reconcile.py` focused on reconciliation instead of becoming a collection of source-specific exceptions.

## Trade Representation Examples

The upgraded architecture is intended to support cases such as:

### Different ticker representations

```text
Internal:
7203

Broker:
7203.T

Canonical:
JP3633400001
```

### Different trade IDs

```text
Internal trade ID:
T12345

Broker trade ID:
BRK99881
```

TradeRecon can still identify them as the same trade using instrument, side, quantity, price, account, and timestamp.

### Partial fills

```text
Internal:
100 shares
100 shares

Broker:
200 shares
```

The aggregation layer combines the internal fills before reconciliation.

### International securities

TradeRecon can reconcile trades across markets with fields such as:

```text
ISIN
MIC
currency
FX rate
settlement date
stamp duty
broker fees
exchange fees
```

## What Stays the Same

This upgrade does not replace the existing project.

The following remain core components:

```text
Kafka ingestion
Docker environment
SQLite reconciliation database
Prometheus metrics
Grafana dashboards
report generation
existing CSV input feeds
current reconciliation logic
```

The new architecture adds layers around the existing reconciliation engine so that future complexity can be introduced without continuously expanding a single file.

## Development Plan

The upgrade can be implemented incrementally.

### Phase 1 — Normalization and Instrument Mapping

Add:

```text
app/normalization/
app/reference/
data/reference/instruments.csv
```

Initial goal:

```text
Raw Execution
Raw Confirmation
      ↓
Normalized representation
      ↓
Current reconciliation engine
```

This phase should support:

```text
different ticker formats
ISIN-based instrument matching
timestamp normalization
currency normalization
missing fields
broker-specific field names
```

### Phase 2 — Trade Matching and Aggregation

Add:

```text
app/matching/trade_matcher.py
app/matching/aggregation.py
```

Support:

```text
different trade IDs
partial fills
one-to-many matches
many-to-one matches
VWAP aggregation
match scoring
```

### Phase 3 — Product-Specific and Advanced Rules

Future modules may include:

```text
special_cases/
├── equities.py
├── options.py
├── fixed_income.py
├── fx.py
└── swaps.py
```

Potential future capabilities include:

```text
option contract normalization
bond identifiers
FX pair normalization
corporate action adjustments
broker-specific reconciliation rules
trade lifecycle events
real-time break alerts
portfolio-level reconciliation
```

## Testing Strategy

Each new layer should be tested independently.

### Normalization tests

Verify that different source representations produce the same canonical trade.

Example:

```text
7203
7203.T
JP3633400001

→ same instrument
```

### Matching tests

Test:

```text
one-to-one
one-to-many
many-to-one
different trade IDs
partial fills
timestamp tolerances
```

### Reconciliation tests

Continue validating:

```text
quantity
price
currency
settlement date
P&L
fees
timestamp drift
```

## Long-Term Direction

The goal of TradeRecon is not simply to compare two CSV rows.

The longer-term objective is to model how a real post-trade reconciliation system handles multiple representations of the same economic event.

The architecture is therefore moving from:

```text
Compare Row A with Row B
```

toward:

```text
Ingest
   ↓
Understand
   ↓
Normalize
   ↓
Identify
   ↓
Match
   ↓
Reconcile
   ↓
Classify breaks
   ↓
Report and monitor
```

This provides a stronger foundation for increasingly complex trade workflows while keeping each component understandable, testable, and independently extensible.

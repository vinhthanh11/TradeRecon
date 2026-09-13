import csv
from pathlib import Path


class InstrumentMapper:
    def __init__(self, reference_file="data/instruments.csv"):
        self.by_isin = {}
        self.by_ticker = {}

        self._load_reference(reference_file)

    def _load_reference(self, reference_file):
        path = Path(reference_file)

        with path.open( newline="", encoding="utf-8" ) as file:

            reader = csv.DictReader(file)

            for row in reader:
                isin = row.get("isin")
                canonical_ticker = row.get( "canonical_ticker" )
                broker_ticker = row.get( "broker_ticker" )

                if isin:
                    self.by_isin[isin] = row

                if canonical_ticker:
                    self.by_ticker[ canonical_ticker ] = row

                if broker_ticker:
                    self.by_ticker[ broker_ticker ] = row
                    
    
    def resolve( self, isin=None, ticker=None ):
        # Prefer ISIN because it is more stable
        # across source-system ticker conventions.
        if isin and isin in self.by_isin:
            return self.by_isin[isin]

        if ticker and ticker in self.by_ticker:
            return self.by_ticker[ticker]

        return None
    
    '''
    mapper.resolve(ticker="7203.T") and mapper.resolve(ticker="7203")
    both resolve to the same reference record ISIN "JP3633400001" for Toyota Motor Corporation.
    '''
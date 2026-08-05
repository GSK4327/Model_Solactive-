"""Standalone entry point for running the index model.

The project's existing ``__main__.py`` can remain unchanged. This file provides
an equivalent executable entry point when running ``python main.py``.
"""

import datetime as dt

from index_model.index import IndexModel


def main() -> None:
    """Calculate the index levels and export them to a CSV file."""
    backtest_start = dt.date(year=2020, month=1, day=1)
    backtest_end = dt.date(year=2020, month=12, day=31)

    index = IndexModel()
    index.calc_index_level(
        start_date=backtest_start,
        end_date=backtest_end,
    )
    index.export_values("export.csv")


if __name__ == "__main__":
    main()

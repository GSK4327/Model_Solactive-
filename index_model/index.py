#!/usr/bin/env python
# coding: utf-8

# In[16]:


from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Final, Iterable

import pandas as pd


UNIVERSE: Final[tuple[str, ...]] = tuple(
    f"Stock_{letter}" for letter in "ABCDEFGHIJ"
)

TARGET_WEIGHTS: Final[tuple[float, float, float]] = (
    0.50,
    0.25,
    0.25,
)

INDEX_START_DATE: Final[pd.Timestamp] = pd.Timestamp(
    "2020-01-01"
)

INDEX_START_LEVEL: Final[float] = 100.0


class IndexModelError(ValueError):
    """required when the index calculation gives an error."""


def _find_date_column(
    columns: Iterable[object],
) -> object:
   

    columns = list(columns)

    possible_date_columns = (
        "Date",
        "date",
        "DATE",
        "Datetime",
        "datetime",
    )

    for column in possible_date_columns:
        if column in columns:
            return column

    if not columns:
        raise IndexModelError(
            "The stock price file contains no columns."
        )

    
    return columns[0]


def load_stock_prices(
    file_path: str | Path,
) -> pd.DataFrame:
    

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Stock price file was not found: {file_path.resolve()}\n"
            "Place stock_prices.csv inside the data_sources folder."
        )

    raw_data = pd.read_csv(file_path)

    date_column = _find_date_column(
        raw_data.columns
    )

    try:
        raw_data[date_column] = pd.to_datetime(
            raw_data[date_column],
            errors="raise",
        )
    except (TypeError, ValueError) as error:
        raise IndexModelError(
            f"The column {date_column!r} contains invalid dates."
        ) from error

    missing_columns = [
        stock
        for stock in UNIVERSE
        if stock not in raw_data.columns
    ]

    if missing_columns:
        raise IndexModelError(
            "The following stock columns are missing: "
            + ", ".join(missing_columns)
        )

    prices = (
        raw_data
        .set_index(date_column)
        .loc[:, list(UNIVERSE)]
        .copy()
    )

    prices.index = pd.DatetimeIndex(
        prices.index
    ).normalize()

    prices.index.name = "Date"
    prices = prices.sort_index()

    if prices.index.has_duplicates:
        duplicate_dates = (
            prices.index[
                prices.index.duplicated()
            ]
            .unique()
        )

        formatted_dates = ", ".join(
            date.strftime("%Y-%m-%d")
            for date in duplicate_dates[:5]
        )

        raise IndexModelError(
            "Duplicate dates were found: "
            + formatted_dates
        )

    try:
        prices = (
            prices
            .apply(
                pd.to_numeric,
                errors="raise",
            )
            .astype(float)
        )
    except (TypeError, ValueError) as error:
        raise IndexModelError(
            "All stock prices must be numeric."
        ) from error

    if prices.isna().any().any():
        columns_with_missing_values = (
            prices.columns[
                prices.isna().any()
            ].tolist()
        )

        raise IndexModelError(
            "Missing prices were found in: "
            + ", ".join(
                columns_with_missing_values
            )
        )

    if (prices <= 0).any().any():
        raise IndexModelError(
            "All stock prices must be greater than zero."
        )

    weekend_dates = prices.index[
        prices.index.dayofweek >= 5
    ]

    if len(weekend_dates) > 0:
        formatted_dates = ", ".join(
            date.strftime("%Y-%m-%d")
            for date in weekend_dates[:5]
        )

        raise IndexModelError(
            "Weekend prices are not allowed. "
            f"Example dates: {formatted_dates}"
        )

    if INDEX_START_DATE not in prices.index:
        raise IndexModelError(
            "The stock-price data must include "
            "2020-01-01."
        )

    prior_dates = prices.index[
        prices.index < INDEX_START_DATE
    ]

    if len(prior_dates) == 0:
        raise IndexModelError(
            "At least one price date before "
            "2020-01-01 is required to select "
            "the initial constituents."
        )

    return prices


def _select_constituents(
    prices: pd.DataFrame,
    selection_date: pd.Timestamp,
) -> tuple[str, str, str]:
    

    ranking = pd.DataFrame(
        {
            "stock": list(UNIVERSE),
            "price": prices.loc[
                selection_date,
                list(UNIVERSE),
            ].to_numpy(),
        }
    )

    ranking = ranking.sort_values(
        by=["price", "stock"],
        ascending=[False, True],
        kind="mergesort",
    )

    selected_stocks = tuple(
        ranking.head(3)["stock"].tolist()
    )

    return selected_stocks


def calculate_index_from_prices(
    prices: pd.DataFrame,
    start_date: dt.date | pd.Timestamp,
    end_date: dt.date | pd.Timestamp,
) -> pd.DataFrame:
    """Calculate the daily full-precision index levels."""

    requested_start_date = pd.Timestamp(
        start_date
    ).normalize()

    requested_end_date = pd.Timestamp(
        end_date
    ).normalize()

    if requested_start_date < INDEX_START_DATE:
        raise IndexModelError(
            "The requested start date cannot be before "
            "2020-01-01."
        )

    if requested_end_date < requested_start_date:
        raise IndexModelError(
            "The end date cannot be before the start date."
        )

    if requested_start_date not in prices.index:
        raise IndexModelError(
            f"No price is available for the requested "
            f"start date {requested_start_date:%Y-%m-%d}."
        )

    if requested_end_date not in prices.index:
        raise IndexModelError(
            f"No price is available for the requested "
            f"end date {requested_end_date:%Y-%m-%d}."
        )

   
    calculation_dates = prices.index[
        (prices.index >= INDEX_START_DATE)
        & (prices.index <= requested_end_date)
    ]

    
    rebalance_dates = set(
        calculation_dates
        .to_series()
        .groupby(
            calculation_dates.to_period("M")
        )
        .min()
        .tolist()
    )

    
    units = pd.Series(
        0.0,
        index=list(UNIVERSE),
        dtype=float,
    )

    calculated_levels: list[float] = []
    rebalance_information: list[dict] = []

    for current_date in calculation_dates:

        if current_date == INDEX_START_DATE:
            index_level = INDEX_START_LEVEL
        else:
            current_prices = prices.loc[
                current_date,
                list(UNIVERSE),
            ]

            index_level = float(
                (
                    units
                    * current_prices
                ).sum()
            )

        calculated_levels.append(index_level)

        if current_date in rebalance_dates:

            previous_dates = prices.index[
                prices.index < current_date
            ]

            if len(previous_dates) == 0:
                raise IndexModelError(
                    "A previous business-day price is "
                    f"required for {current_date:%Y-%m-%d}."
                )

            # This is the final business day of the
            # immediately preceding month.
            selection_date = previous_dates[-1]

            selected_stocks = _select_constituents(
                prices=prices,
                selection_date=selection_date,
            )

            
            units[:] = 0.0

            # Establish the new 50%, 25%, 25% 
            
            for stock, target_weight in zip(
                selected_stocks,
                TARGET_WEIGHTS,
            ):
                current_stock_price = prices.loc[
                    current_date,
                    stock,
                ]

                units.loc[stock] = (
                    index_level
                    * target_weight
                    / current_stock_price
                )

            rebalance_information.append(
                {
                    "rebalanceDate": current_date,
                    "selectionDate": selection_date,
                    "firstStock": selected_stocks[0],
                    "firstWeight": TARGET_WEIGHTS[0],
                    "secondStock": selected_stocks[1],
                    "secondWeight": TARGET_WEIGHTS[1],
                    "thirdStock": selected_stocks[2],
                    "thirdWeight": TARGET_WEIGHTS[2],
                }
            )

    full_result = pd.DataFrame(
        {
            "Date": calculation_dates,
            "Index_Level": calculated_levels,
        }
    )

    # Return only the requested output period.
    requested_result = full_result.loc[
        (full_result["Date"] >= requested_start_date)
        & (full_result["Date"] <= requested_end_date)
    ].reset_index(drop=True)

    requested_result.attrs[
        "rebalanceSelections"
    ] = rebalance_information

    return requested_result


class IndexModel:
    """File-based interface used by the project entry point."""

    def __init__(
        self,
        stock_prices_path: str | Path = (
            "data_sources/stock_prices.csv"
        ),
    ) -> None:
        self.stock_prices_path = Path(
            stock_prices_path
        )

        self.index_levels: pd.DataFrame | None = None

    def calc_index_level(
        self,
        start_date: dt.date,
        end_date: dt.date,
    ) -> pd.DataFrame:
        """
        Calculate index levels for the requested date range.
        """

        prices = load_stock_prices(
            self.stock_prices_path
        )

        self.index_levels = calculate_index_from_prices(
            prices=prices,
            start_date=start_date,
            end_date=end_date,
        )

        return self.index_levels.copy()

    def export_values(
        self,
        output_path: str | Path,
    ) -> Path:
        """Export the calculated values to a CSV file."""

        if self.index_levels is None:
            raise IndexModelError(
                "No index values have been calculated. "
                "Run calc_index_level() before export_values()."
            )

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.index_levels.to_csv(
            output_path,
            index=False,
        )

        return output_path


# In[ ]:





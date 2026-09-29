from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


DivergenceType = Literal[
    "regular_bullish",
    "regular_bearish",
    "hidden_bullish",
    "hidden_bearish",
]

PivotType = Literal["high", "low"]


@dataclass
class Pivot:
    index: int
    date: pd.Timestamp
    value: float
    confirmation_index: int
    confirmation_date: pd.Timestamp


@dataclass
class DivergenceSignal:
    signal_date: pd.Timestamp

    indicator: str
    divergence_type: DivergenceType

    price_pivot_1_date: pd.Timestamp
    price_pivot_2_date: pd.Timestamp

    indicator_pivot_1_date: pd.Timestamp
    indicator_pivot_2_date: pd.Timestamp

    price_pivot_1_value: float
    price_pivot_2_value: float

    indicator_pivot_1_value: float
    indicator_pivot_2_value: float

    bars_between: int


class DivergenceEngine:
    """
    Detect regular and hidden divergences between price and indicators.

    Important:
    - Only traded rows are used.
    - Pivot confirmation requires right_bars future candles.
    - signal_date is the first date on which BOTH pivots are confirmed.
    - Price and indicator pivot matching uses the same aligned row index.
    """

    DEFAULT_INDICATORS = (
        "rsi",
        "macd",
        "stoch_k",
        "obv",
    )

    def __init__(
        self,
        left_bars: int = 3,
        right_bars: int = 3,
        min_bars_between_pivots: int = 5,
        max_bars_between_pivots: int = 60,
        max_calendar_days: int | None = None,
        indicator_tolerance_bars: int = 2,
        indicators: tuple[str, ...] | None = None,
    ):
        if left_bars < 1:
            raise ValueError("left_bars must be >= 1")

        if right_bars < 1:
            raise ValueError("right_bars must be >= 1")

        if min_bars_between_pivots < 1:
            raise ValueError("min_bars_between_pivots must be >= 1")

        if max_bars_between_pivots < min_bars_between_pivots:
            raise ValueError(
                "max_bars_between_pivots must be >= min_bars_between_pivots"
            )

        if indicator_tolerance_bars < 0:
            raise ValueError("indicator_tolerance_bars must be >= 0")

        self.left_bars = left_bars
        self.right_bars = right_bars
        self.min_bars_between_pivots = min_bars_between_pivots
        self.max_bars_between_pivots = max_bars_between_pivots
        self.max_calendar_days = max_calendar_days
        self.indicator_tolerance_bars = indicator_tolerance_bars

        self.indicators = (
            indicators
            if indicators is not None
            else self.DEFAULT_INDICATORS
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(
        self,
        df: pd.DataFrame,
        price_column: str = "close",
    ) -> pd.DataFrame:

        data = self._prepare_dataframe(
            df=df,
            price_column=price_column,
        )

        if data.empty:
            return self._empty_result()

        price_low_pivots = self._find_pivots(
            values=data[price_column].to_numpy(dtype=float),
            dates=data["date"].to_numpy(),
            pivot_type="low",
        )

        price_high_pivots = self._find_pivots(
            values=data[price_column].to_numpy(dtype=float),
            dates=data["date"].to_numpy(),
            pivot_type="high",
        )

        signals: list[DivergenceSignal] = []

        for indicator in self.indicators:

            if indicator not in data.columns:
                continue

            # IMPORTANT:
            # Do NOT drop NaN rows here.
            #
            # The indicator and price must remain on exactly the same
            # time-indexed rows so pivot indexes remain comparable.
            indicator_data = data[
                ["date", price_column, indicator]
            ].copy()

            if indicator_data.empty:
                continue

            indicator_values = indicator_data[indicator].to_numpy(
                dtype=float
            )

            indicator_low_pivots = self._find_pivots(
                values=indicator_values,
                dates=indicator_data["date"].to_numpy(),
                pivot_type="low",
            )

            indicator_high_pivots = self._find_pivots(
                values=indicator_values,
                dates=indicator_data["date"].to_numpy(),
                pivot_type="high",
            )

            # ----------------------------------------------------------
            # Bullish divergences
            # ----------------------------------------------------------

            signals.extend(
                self._detect_divergences(
                    price_pivots=price_low_pivots,
                    indicator_pivots=indicator_low_pivots,
                    indicator=indicator,
                    divergence_type="regular_bullish",
                )
            )

            signals.extend(
                self._detect_divergences(
                    price_pivots=price_low_pivots,
                    indicator_pivots=indicator_low_pivots,
                    indicator=indicator,
                    divergence_type="hidden_bullish",
                )
            )

            # ----------------------------------------------------------
            # Bearish divergences
            # ----------------------------------------------------------

            signals.extend(
                self._detect_divergences(
                    price_pivots=price_high_pivots,
                    indicator_pivots=indicator_high_pivots,
                    indicator=indicator,
                    divergence_type="regular_bearish",
                )
            )

            signals.extend(
                self._detect_divergences(
                    price_pivots=price_high_pivots,
                    indicator_pivots=indicator_high_pivots,
                    indicator=indicator,
                    divergence_type="hidden_bearish",
                )
            )

        if not signals:
            return self._empty_result()

        result = pd.DataFrame(
            [
                {
                    "signal_date": signal.signal_date,
                    "indicator": signal.indicator,
                    "divergence_type": signal.divergence_type,

                    "price_pivot_1_date": signal.price_pivot_1_date,
                    "price_pivot_2_date": signal.price_pivot_2_date,

                    "indicator_pivot_1_date": (
                        signal.indicator_pivot_1_date
                    ),
                    "indicator_pivot_2_date": (
                        signal.indicator_pivot_2_date
                    ),

                    "price_pivot_1_value": (
                        signal.price_pivot_1_value
                    ),
                    "price_pivot_2_value": (
                        signal.price_pivot_2_value
                    ),

                    "indicator_pivot_1_value": (
                        signal.indicator_pivot_1_value
                    ),
                    "indicator_pivot_2_value": (
                        signal.indicator_pivot_2_value
                    ),

                    "bars_between": signal.bars_between,
                }
                for signal in signals
            ]
        )

        return (
            result
            .sort_values(
                by=[
                    "signal_date",
                    "indicator",
                    "divergence_type",
                ]
            )
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # Data preparation
    # ------------------------------------------------------------------

    def _prepare_dataframe(
        self,
        df: pd.DataFrame,
        price_column: str,
    ) -> pd.DataFrame:

        required = {"date", price_column}

        missing = required - set(df.columns)

        if missing:
            raise ValueError(
                f"Missing required columns: {sorted(missing)}"
            )

        data = df.copy()

        data["date"] = pd.to_datetime(data["date"])

        # Preserve chronology.
        data = (
            data
            .sort_values("date")
            .reset_index(drop=True)
        )

        # Only traded rows participate in technical analysis.
        #
        # This is important for TSETMC because market-closure rows
        # may exist with volume=0 and invalid OHLC values.
        if "volume" in data.columns:
            data = data[
                data["volume"].fillna(0) > 0
            ].copy()

        data = data[
            data[price_column].notna()
            & np.isfinite(data[price_column].astype(float))
            & (data[price_column].astype(float) > 0)
        ].copy()

        data = (
            data
            .sort_values("date")
            .reset_index(drop=True)
        )

        return data

    # ------------------------------------------------------------------
    # Pivot detection
    # ------------------------------------------------------------------

    def _find_pivots(
        self,
        values: np.ndarray,
        dates: np.ndarray,
        pivot_type: PivotType,
    ) -> list[Pivot]:

        n = len(values)

        if n == 0:
            return []

        pivots: list[Pivot] = []

        start = self.left_bars
        end = n - self.right_bars

        for i in range(start, end):

            value = values[i]

            if not np.isfinite(value):
                continue

            left = values[
                i - self.left_bars : i
            ]

            right = values[
                i + 1 : i + self.right_bars + 1
            ]

            if (
                not np.all(np.isfinite(left))
                or not np.all(np.isfinite(right))
            ):
                continue

            if pivot_type == "low":

                is_pivot = (
                    value < left.min()
                    and value <= right.min()
                )

            else:

                is_pivot = (
                    value > left.max()
                    and value >= right.max()
                )

            if not is_pivot:
                continue

            confirmation_index = i + self.right_bars

            pivots.append(
                Pivot(
                    index=i,
                    date=pd.Timestamp(dates[i]),
                    value=float(value),
                    confirmation_index=confirmation_index,
                    confirmation_date=pd.Timestamp(
                        dates[confirmation_index]
                    ),
                )
            )

        return pivots

    # ------------------------------------------------------------------
    # Divergence detection
    # ------------------------------------------------------------------

    def _detect_divergences(
        self,
        price_pivots: list[Pivot],
        indicator_pivots: list[Pivot],
        indicator: str,
        divergence_type: DivergenceType,
    ) -> list[DivergenceSignal]:

        signals: list[DivergenceSignal] = []

        if len(price_pivots) < 2:
            return signals

        if len(indicator_pivots) < 2:
            return signals

        for p1_idx in range(len(price_pivots) - 1):

            p1 = price_pivots[p1_idx]

            for p2_idx in range(
                p1_idx + 1,
                len(price_pivots),
            ):

                p2 = price_pivots[p2_idx]

                bars_between = p2.index - p1.index

                if (
                    bars_between
                    < self.min_bars_between_pivots
                ):
                    continue

                if (
                    bars_between
                    > self.max_bars_between_pivots
                ):
                    # Since pivots are chronological, all later
                    # p2 values will be even farther away.
                    break

                matched = self._match_indicator_pivots(
                    price_pivot_1=p1,
                    price_pivot_2=p2,
                    indicator_pivots=indicator_pivots,
                )

                if matched is None:
                    continue

                i1, i2 = matched

                if not self._is_valid_divergence(
                    p1=p1,
                    p2=p2,
                    i1=i1,
                    i2=i2,
                    divergence_type=divergence_type,
                ):
                    continue

                # Signal can only exist after BOTH second pivots
                # have been confirmed.
                signal_date = max(
                    p2.confirmation_date,
                    i2.confirmation_date,
                )

                if (
                    self.max_calendar_days is not None
                    and (signal_date - p1.date).days > self.max_calendar_days
                ):
                    continue

                signals.append(
                    DivergenceSignal(
                        signal_date=signal_date,

                        indicator=indicator,
                        divergence_type=divergence_type,

                        price_pivot_1_date=p1.date,
                        price_pivot_2_date=p2.date,

                        indicator_pivot_1_date=i1.date,
                        indicator_pivot_2_date=i2.date,

                        price_pivot_1_value=p1.value,
                        price_pivot_2_value=p2.value,

                        indicator_pivot_1_value=i1.value,
                        indicator_pivot_2_value=i2.value,

                        bars_between=bars_between,
                    )
                )

        return signals

    # ------------------------------------------------------------------
    # Indicator pivot matching
    # ------------------------------------------------------------------

    def _match_indicator_pivots(
        self,
        price_pivot_1: Pivot,
        price_pivot_2: Pivot,
        indicator_pivots: list[Pivot],
    ) -> tuple[Pivot, Pivot] | None:

        # Indicator pivot should occur close to the corresponding
        # price pivot.
        tolerance = self.indicator_tolerance_bars

        candidates_1 = [
            pivot
            for pivot in indicator_pivots
            if abs(pivot.index - price_pivot_1.index)
            <= tolerance
        ]

        candidates_2 = [
            pivot
            for pivot in indicator_pivots
            if abs(pivot.index - price_pivot_2.index)
            <= tolerance
        ]

        if not candidates_1 or not candidates_2:
            return None

        best_pair: tuple[Pivot, Pivot] | None = None
        best_distance: int | None = None

        for i1 in candidates_1:

            for i2 in candidates_2:

                # Indicator pivots must preserve chronology.
                if i2.index <= i1.index:
                    continue

                indicator_bars = i2.index - i1.index

                if (
                    indicator_bars
                    < self.min_bars_between_pivots
                ):
                    continue

                if (
                    indicator_bars
                    > self.max_bars_between_pivots
                ):
                    continue

                distance = (
                    abs(i1.index - price_pivot_1.index)
                    + abs(i2.index - price_pivot_2.index)
                )

                if (
                    best_distance is None
                    or distance < best_distance
                ):
                    best_distance = distance
                    best_pair = (i1, i2)

        return best_pair

    # ------------------------------------------------------------------
    # Divergence rules
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_divergence(
        p1: Pivot,
        p2: Pivot,
        i1: Pivot,
        i2: Pivot,
        divergence_type: DivergenceType,
    ) -> bool:

        if divergence_type == "regular_bullish":
            # Price: lower low
            # Indicator: higher low
            return (
                p2.value < p1.value
                and i2.value > i1.value
            )

        if divergence_type == "regular_bearish":
            # Price: higher high
            # Indicator: lower high
            return (
                p2.value > p1.value
                and i2.value < i1.value
            )

        if divergence_type == "hidden_bullish":
            # Price: higher low
            # Indicator: lower low
            return (
                p2.value > p1.value
                and i2.value < i1.value
            )

        if divergence_type == "hidden_bearish":
            # Price: lower high
            # Indicator: higher high
            return (
                p2.value < p1.value
                and i2.value > i1.value
            )

        return False

    # ------------------------------------------------------------------
    # Empty result
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result() -> pd.DataFrame:

        return pd.DataFrame(
            columns=[
                "signal_date",
                "indicator",
                "divergence_type",

                "price_pivot_1_date",
                "price_pivot_2_date",

                "indicator_pivot_1_date",
                "indicator_pivot_2_date",

                "price_pivot_1_value",
                "price_pivot_2_value",

                "indicator_pivot_1_value",
                "indicator_pivot_2_value",

                "bars_between",
            ]
        )

    # ------------------------------------------------------------------
    # Backward-compatible wrapper
    # ------------------------------------------------------------------

    def calculate_for_symbol(
        self,
        df: pd.DataFrame,
        symbol: str | None = None,
    ) -> pd.DataFrame:

        return self.calculate(df)
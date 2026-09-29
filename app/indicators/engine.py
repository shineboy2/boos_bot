from __future__ import annotations

import pandas as pd

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator


class IndicatorEngine:
    """
    Technical indicator calculation engine.

    Important:
    - Raw market rows are preserved.
    - Rows with volume <= 0 are treated as non-trading rows.
    - Close-based indicators are calculated only on traded rows.
    - OHLC-based indicators are calculated only on valid traded OHLC rows.
    - Indicator results are mapped back to the original date index.
    """

    def __init__(
        self,
        rsi_window: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        stoch_window: int = 14,
        stoch_smooth_window: int = 3,
        stoch_d_window: int = 3,
        ema_windows: tuple[int, ...] = (20, 50, 200),
        bb_window: int = 20,
        bb_std: float = 2.0,
        atr_window: int = 14,
        supertrend_window: int = 10,
        supertrend_multiplier: float = 3.0,
    ):
        self.rsi_window = rsi_window

        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

        self.stoch_window = stoch_window
        self.stoch_smooth_window = stoch_smooth_window
        self.stoch_d_window = stoch_d_window

        self.ema_windows = ema_windows

        self.bb_window = bb_window
        self.bb_std = bb_std

        self.atr_window = atr_window

        self.supertrend_window = supertrend_window
        self.supertrend_multiplier = supertrend_multiplier


    def calculate_for_symbol(
        self,
        df: pd.DataFrame,
        symbol: str | None = None,
    ) -> pd.DataFrame:
        """
        Backward-compatible wrapper used by the existing test/collector code.

        `symbol` is accepted for compatibility but indicator calculation
        itself is performed on the supplied dataframe.
        """
        return self.calculate(df)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all configured indicators.

        Required columns:
            date
            open
            high
            low
            close
            volume

        Returns:
            Original dataframe + indicator columns.
        """

        if df.empty:
            return df.copy()

        result = df.copy()

        required = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        missing = [col for col in required if col not in result.columns]

        if missing:
            raise ValueError(
                f"Missing required columns: {', '.join(missing)}"
            )

        # ---------------------------------------------------------
        # Normalize / sort
        # ---------------------------------------------------------

        result["date"] = pd.to_datetime(result["date"])

        result = (
            result
            .sort_values("date")
            .reset_index(drop=True)
        )

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for column in numeric_columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        # ---------------------------------------------------------
        # Data quality masks
        # ---------------------------------------------------------

        result["has_trade"] = result["volume"] > 0

        result["close_valid"] = (
            result["close"] > 0
        )

        result["ohlc_valid"] = (
            (result["open"] > 0)
            & (result["high"] > 0)
            & (result["low"] > 0)
            & (result["close"] > 0)
            & (result["high"] >= result["low"])
            & (result["high"] >= result["close"])
            & (result["low"] <= result["close"])
        )

        # A row is usable for technical calculations only when
        # an actual trade occurred and the corresponding data is valid.
        result["close_trade_valid"] = (
            result["close_valid"]
            & result["has_trade"]
        )

        result["ohlc_trade_valid"] = (
            result["ohlc_valid"]
            & result["has_trade"]
        )

        # ---------------------------------------------------------
        # Create masks
        # ---------------------------------------------------------

        close_mask = result["close_trade_valid"]
        ohlc_mask = result["ohlc_trade_valid"]

        # IMPORTANT:
        #
        # Do NOT calculate close-based indicators on the complete
        # dataframe because TSETMC can return repeated positive
        # close values during market closures while volume == 0.
        #
        # Instead, compress the calculation input to actual
        # trading rows only.
        #
        close_data = result.loc[
            close_mask,
            ["date", "close", "volume"],
        ].copy()

        ohlc_data = result.loc[
            ohlc_mask,
            ["date", "open", "high", "low", "close", "volume"],
        ].copy()

        # ---------------------------------------------------------
        # Initialize indicator columns
        # ---------------------------------------------------------

        indicator_columns = [
            "rsi",
            "macd",
            "macd_signal",
            "macd_histogram",
            "stoch_k",
            "stoch_d",
            "ema_20",
            "ema_50",
            "ema_200",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "bb_width",
            "obv",
            "atr",
            "supertrend",
            "supertrend_direction",
        ]

        for column in indicator_columns:
            result[column] = pd.NA

        # ---------------------------------------------------------
        # Close-based indicators
        # ---------------------------------------------------------

        if not close_data.empty:

            close_series = close_data["close"]

            # RSI
            if len(close_data) >= self.rsi_window:
                rsi = RSIIndicator(
                    close=close_series,
                    window=self.rsi_window,
                    fillna=False,
                ).rsi()

                result.loc[
                    close_mask,
                    "rsi"
                ] = rsi.to_numpy()

            # MACD
            if len(close_data) >= self.macd_slow:

                macd_indicator = MACD(
                    close=close_series,
                    window_fast=self.macd_fast,
                    window_slow=self.macd_slow,
                    window_sign=self.macd_signal,
                    fillna=False,
                )

                result.loc[
                    close_mask,
                    "macd"
                ] = macd_indicator.macd().to_numpy()

                result.loc[
                    close_mask,
                    "macd_signal"
                ] = macd_indicator.macd_signal().to_numpy()

                result.loc[
                    close_mask,
                    "macd_histogram"
                ] = macd_indicator.macd_diff().to_numpy()

            # EMA
            for window in self.ema_windows:

                if len(close_data) >= window:

                    ema = EMAIndicator(
                        close=close_series,
                        window=window,
                        fillna=False,
                    ).ema_indicator()

                    column_name = f"ema_{window}"

                    # Only create configured standard columns.
                    # This keeps compatibility with the current
                    # scanner schema.
                    if column_name in result.columns:

                        result.loc[
                            close_mask,
                            column_name
                        ] = ema.to_numpy()

            # Bollinger Bands
            if len(close_data) >= self.bb_window:

                bb = BollingerBands(
                    close=close_series,
                    window=self.bb_window,
                    window_dev=self.bb_std,
                    fillna=False,
                )

                result.loc[
                    close_mask,
                    "bb_upper"
                ] = bb.bollinger_hband().to_numpy()

                result.loc[
                    close_mask,
                    "bb_middle"
                ] = bb.bollinger_mavg().to_numpy()

                result.loc[
                    close_mask,
                    "bb_lower"
                ] = bb.bollinger_lband().to_numpy()

                result.loc[
                    close_mask,
                    "bb_width"
                ] = bb.bollinger_wband().to_numpy()

            # OBV
            #
            # OBV is also calculated only on actual trading rows.
            if len(close_data) >= 2:

                obv = OnBalanceVolumeIndicator(
                    close=close_data["close"],
                    volume=close_data["volume"],
                    fillna=False,
                ).on_balance_volume()

                result.loc[
                    close_mask,
                    "obv"
                ] = obv.to_numpy()

        # ---------------------------------------------------------
        # OHLC-based indicators
        # ---------------------------------------------------------

        if not ohlc_data.empty:

            high = ohlc_data["high"]
            low = ohlc_data["low"]
            close = ohlc_data["close"]

            # Stochastic
            if len(ohlc_data) >= self.stoch_window:

                stoch = StochasticOscillator(
                    high=high,
                    low=low,
                    close=close,
                    window=self.stoch_window,
                    smooth_window=self.stoch_smooth_window,
                    fillna=False,
                )

                result.loc[
                    ohlc_mask,
                    "stoch_k"
                ] = stoch.stoch().to_numpy()

                result.loc[
                    ohlc_mask,
                    "stoch_d"
                ] = stoch.stoch_signal().to_numpy()

            # ATR
            if len(ohlc_data) >= self.atr_window:

                atr_indicator = AverageTrueRange(
                    high=high,
                    low=low,
                    close=close,
                    window=self.atr_window,
                    fillna=False,
                )

                atr = atr_indicator.average_true_range()

                result.loc[
                    ohlc_mask,
                    "atr"
                ] = atr.to_numpy()

                # Supertrend
                supertrend, direction = self._calculate_supertrend(
                    ohlc_data=ohlc_data,
                    atr=atr,
                )

                result.loc[
                    ohlc_mask,
                    "supertrend"
                ] = supertrend.to_numpy()

                result.loc[
                    ohlc_mask,
                    "supertrend_direction"
                ] = direction.to_numpy()

        # ---------------------------------------------------------
        # Numeric conversion
        # ---------------------------------------------------------

        for column in indicator_columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        return result

    def _calculate_supertrend(
        self,
        ohlc_data: pd.DataFrame,
        atr: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:
        """
        Calculate Supertrend using standard band/state logic.

        Returns:
            supertrend
            direction

        Direction:
            +1 = bullish
            -1 = bearish
        """

        high = ohlc_data["high"]
        low = ohlc_data["low"]
        close = ohlc_data["close"]

        hl2 = (high + low) / 2.0

        basic_upper = (
            hl2
            + self.supertrend_multiplier * atr
        )

        basic_lower = (
            hl2
            - self.supertrend_multiplier * atr
        )

        final_upper = pd.Series(
            index=ohlc_data.index,
            dtype="float64",
        )

        final_lower = pd.Series(
            index=ohlc_data.index,
            dtype="float64",
        )

        supertrend = pd.Series(
            index=ohlc_data.index,
            dtype="float64",
        )

        direction = pd.Series(
            index=ohlc_data.index,
            dtype="float64",
        )

        valid_indices = list(ohlc_data.index)

        if not valid_indices:
            return supertrend, direction

        for position, idx in enumerate(valid_indices):

            current_atr = atr.loc[idx]

            if pd.isna(current_atr):
                continue

            current_basic_upper = basic_upper.loc[idx]
            current_basic_lower = basic_lower.loc[idx]
            current_close = close.loc[idx]

            if position == 0:

                final_upper.loc[idx] = current_basic_upper
                final_lower.loc[idx] = current_basic_lower

                supertrend.loc[idx] = current_basic_upper
                direction.loc[idx] = -1

                continue

            prev_idx = valid_indices[position - 1]

            previous_close = close.loc[prev_idx]

            previous_final_upper = final_upper.loc[prev_idx]
            previous_final_lower = final_lower.loc[prev_idx]

            previous_supertrend = supertrend.loc[prev_idx]
            previous_direction = direction.loc[prev_idx]

            # -----------------------------------------------------
            # Final upper band
            # -----------------------------------------------------

            if (
                current_basic_upper < previous_final_upper
                or previous_close > previous_final_upper
            ):
                final_upper.loc[idx] = current_basic_upper
            else:
                final_upper.loc[idx] = previous_final_upper

            # -----------------------------------------------------
            # Final lower band
            # -----------------------------------------------------

            if (
                current_basic_lower > previous_final_lower
                or previous_close < previous_final_lower
            ):
                final_lower.loc[idx] = current_basic_lower
            else:
                final_lower.loc[idx] = previous_final_lower

            current_final_upper = final_upper.loc[idx]
            current_final_lower = final_lower.loc[idx]

            # -----------------------------------------------------
            # Supertrend state
            # -----------------------------------------------------

            if previous_direction == -1:

                if current_close <= current_final_upper:
                    direction.loc[idx] = -1
                    supertrend.loc[idx] = current_final_upper
                else:
                    direction.loc[idx] = 1
                    supertrend.loc[idx] = current_final_lower

            else:

                if current_close >= current_final_lower:
                    direction.loc[idx] = 1
                    supertrend.loc[idx] = current_final_lower
                else:
                    direction.loc[idx] = -1
                    supertrend.loc[idx] = current_final_upper

        return supertrend, direction
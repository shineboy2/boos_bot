import pandas as pd
from typing import Dict, List, Any
from datetime import datetime
import numpy as np

class DataQualityService:
    @staticmethod
    def validate_daily_history(df: pd.DataFrame, ins_code: str) -> Dict[str, Any]:
        """
        Validates historical data to detect anomalies and quality issues.
        Returns a dict of issues. If issues are severe, the data might be flagged.
        """
        issues = []
        
        if df.empty:
            return {"status": "failed", "issues": [{"type": "empty_data", "severity": "high"}]}
            
        # 1. Invalid or duplicated dates
        if df['date'].duplicated().any():
            dups = df[df['date'].duplicated()]['date'].tolist()
            issues.append({"type": "duplicate_dates", "severity": "high", "details": dups})
            
        # 2. Zero or negative prices (where they shouldn't be)
        # Note: 'yesterday' could technically be zero for the very first day, so we check OHLC.
        for col in ['open', 'high', 'low', 'close']:
            if (df[col] <= 0).any():
                count = (df[col] <= 0).sum()
                issues.append({"type": f"invalid_{col}", "severity": "high", "details": f"{count} records with <= 0"})
                
        # 3. OHLC Logic
        invalid_ohlc = df[(df['high'] < df['low']) | (df['high'] < df['close']) | (df['low'] > df['close'])]
        if not invalid_ohlc.empty:
            issues.append({"type": "invalid_ohlc_logic", "severity": "high", "details": f"{len(invalid_ohlc)} records"})
            
        # 4. Volume logic
        negative_vol = df[df['volume'] < 0]
        if not negative_vol.empty:
            issues.append({"type": "negative_volume", "severity": "high", "details": f"{len(negative_vol)} records"})
            
        # 5. Missing values
        missing_counts = df[['open', 'high', 'low', 'close', 'volume']].isna().sum()
        if missing_counts.sum() > 0:
            issues.append({"type": "missing_values", "severity": "medium", "details": missing_counts.to_dict()})
            
        status = "passed" if not any(i['severity'] == 'high' for i in issues) else "flagged"
        
        return {
            "status": status,
            "issues": issues,
            "ins_code": ins_code,
            "records_checked": len(df)
        }

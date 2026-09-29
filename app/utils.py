def parse_date(d_even):
    """
    TSETMC dEven:
        20260915 -> 2026-09-15
    """
    value = str(int(d_even))
    if len(value) != 8:
        raise ValueError(f"Invalid dEven: {d_even}")
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"

def to_int(value):
    if value is None: return None
    return int(round(float(value)))

def to_float(value):
    if value is None: return None
    return float(value)

def normalize_symbol(symbol: str) -> str:
    """Normalize Arabic/Persian characters in symbol."""
    if not symbol:
        return symbol
    return symbol.replace('ك', 'ک').replace('ي', 'ی').strip()

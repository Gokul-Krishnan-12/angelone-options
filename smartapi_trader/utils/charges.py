from typing import Dict, Any

def calculate_option_charges(entry_price: float, exit_price: float, quantity: int, exchange: str = "NSE") -> Dict[str, float]:
    """
    Computes precise Angel One broker brokerage and statutory taxes for Indian Index Options (F&O):
    1. Brokerage: ₹20 per executed order (Buy order: ₹20, Sell order: ₹20) = ₹40.00
    2. STT (Securities Transaction Tax): 0.1% on Sell turnover (SEBI revised rate)
    3. Exchange Txn Charge: 0.0505% on total turnover (NSE) or 0.05% (BSE)
    4. SEBI Turnover Fee: ₹10 per crore (0.0001% on total turnover)
    5. Stamp Duty: 0.003% on Buy turnover
    6. GST: 18% on (Brokerage + Exchange Txn + SEBI)
    """
    qty = abs(quantity)
    buy_val = round(entry_price * qty, 2)
    sell_val = round(exit_price * qty, 2)
    total_turnover = round(buy_val + sell_val, 2)

    # 1. Flat Angel One Brokerage: ₹20/order
    brokerage = 40.0 if exit_price > 0 else 20.0

    # 2. STT: 0.1% on sell side
    stt = round(sell_val * 0.001, 2) if exit_price > 0 else 0.0

    # 3. Exchange transaction charges
    exch_rate = 0.000505 if "NSE" in exchange.upper() or "NFO" in exchange.upper() else 0.00050
    exch_charges = round(total_turnover * exch_rate, 2)

    # 4. SEBI charges: 0.0001%
    sebi_charges = round(total_turnover * 0.000001, 2)

    # 5. Stamp duty: 0.003% on buy side
    stamp_duty = round(buy_val * 0.00003, 2)

    # 6. GST: 18% on (Brokerage + Exchange Txn + SEBI)
    gst = round((brokerage + exch_charges + sebi_charges) * 0.18, 2)

    total_charges = round(brokerage + stt + exch_charges + sebi_charges + stamp_duty + gst, 2)
    gross_pnl = round((exit_price - entry_price) * qty, 2) if exit_price > 0 else 0.0
    net_pnl = round(gross_pnl - total_charges, 2)

    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_charges": exch_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "total_charges": total_charges,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl
    }

"""Render the Snapshot and DailyData tabs from the facts store.

The layouts here are the contract. They were reverse-engineered from the
24.07.2026 workbook in Drive, which the user confirmed is the source of truth
(NC ROAS is Triple Attribution, not the 1d replay).

Nothing in this module talks to a connector. It is pure facts -> rows, which
means it can be validated against the golden workbook without spending a single
API call.
"""
import csv
from datetime import date, timedelta

SNAPSHOT_COLS = 11
DAILYDATA_COLS = 30

SNAPSHOT_HEADER = [
    "Date", "Shopify Sales", "Total Ad Spend", "Blended ROAS", "Meta Spend",
    "Meta NC ROAS (TA)*", "Google Spend", "Google NC ROAS (TA)*",
    "AppLovin Spend", "AppLovin NC ROAS (TA)*", "Klaviyo Attr. Revenue",
]

DAILYDATA_HEADER = [
    "Date", "Sales", "Orders", "AOV", "Returns", "Total Ad Spend",
    "Meta Total Spend", "Meta Platform ROAS", "Meta US Spend", "Meta US NC ROAS",
    "Meta WW Spend", "Meta WW NC ROAS", "Meta CPC", "Meta CTR", "Meta CR",
    "Google Total Spend", "Google Platform ROAS", "Google US Spend",
    "Google US NC ROAS", "Google WW Spend", "Google WW NC ROAS", "Google CPC",
    "Google CTR", "Google CR", "AppLovin Spend", "AppLovin NC ROAS",
    "AppLovin Platform ROAS d7", "AppLovin CPC", "AppLovin CTR", "AppLovin CR",
]

TA_FOOTNOTE = ("* Triple Attribution placeholder until First Click/1d is "
               "unlocked on the Triple Whale plan.")


# ---------------------------------------------------------------- formatting

def _num(x, dp):
    """Round to dp and drop the trailing zero the way the golden file does."""
    if x is None:
        return ""
    v = round(float(x) + 0.0, dp)
    if v == 0:
        return "0.0"
    s = f"{v:.{dp}f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def money(x):
    return _num(x, 2)


def count(x):
    return "" if x is None else f"{float(x):.1f}"


def ratio2(num, den):
    """ROAS / CPC / AOV. Blank when the denominator is zero - never 0.0, which
    would read as 'measured and it was nothing'."""
    if num is None or den in (None, 0) or float(den) == 0:
        return ""
    return _num(float(num) / float(den), 2)


def ratio4(num, den):
    """CTR / CR, stored as decimal fractions not percentages."""
    if den in (None, 0) or float(den) == 0:
        return ""
    return _num(float(num) / float(den), 4)


def ddmmyy(d):
    return d.strftime("%d.%m.%y")


def pad(row, width):
    return list(row) + [""] * (width - len(row))


# ------------------------------------------------------------------ derived

def total_spend(r):
    return (r["meta_spend"] or 0) + (r["google_spend"] or 0) + (r["applovin_spend"] or 0)


def _sum(rows, col):
    return sum((r[col] or 0) for r in rows)


# ------------------------------------------------------------------ snapshot

def snapshot_row(r):
    ts = total_spend(r)
    return [
        ddmmyy(r["date"]),
        money(r["shopify_sales"]),
        money(ts),
        ratio2(r["shopify_sales"], ts),
        money(r["meta_spend"]),
        ratio2(r["meta_nc_rev"], r["meta_spend"]),
        money(r["google_spend"]),
        ratio2(r["google_nc_rev"], r["google_spend"]),
        money(r["applovin_spend"]),
        ratio2(r["applovin_nc_rev"], r["applovin_spend"]),
        money(r["klaviyo_attr_rev"]),
    ]


def snapshot_total(rows):
    ts = sum(total_spend(r) for r in rows)
    return [
        "TOTAL (last 30d)",
        money(_sum(rows, "shopify_sales")),
        money(ts),
        ratio2(_sum(rows, "shopify_sales"), ts),
        money(_sum(rows, "meta_spend")),
        ratio2(_sum(rows, "meta_nc_rev"), _sum(rows, "meta_spend")),
        money(_sum(rows, "google_spend")),
        ratio2(_sum(rows, "google_nc_rev"), _sum(rows, "google_spend")),
        money(_sum(rows, "applovin_spend")),
        ratio2(_sum(rows, "applovin_nc_rev"), _sum(rows, "applovin_spend")),
        money(_sum(rows, "klaviyo_attr_rev")),
    ]


def monthly_block(all_rows, year):
    """Every month of the year to date, from the same daily facts."""
    out = [["Period", "Revenue", "Ad Spend", "Blended ROAS"]]
    months = sorted({(r["date"].year, r["date"].month) for r in all_rows
                     if r["date"].year == year})
    for y, m in months:
        rows = [r for r in all_rows if r["date"].year == y and r["date"].month == m]
        rev, spend = _sum(rows, "shopify_sales"), sum(total_spend(r) for r in rows)
        # The old report emitted '2026-01-01 00:00:00' here - a raw timestamp
        # leaking into a label column. Rendered as a month name instead.
        label = date(y, m, 1).strftime("%B %Y")
        out.append([label, money(rev), money(spend), ratio2(rev, spend)])
    return out


def weekly_block(all_rows, as_of, n=4):
    """Last n COMPLETE Mon-Sun weeks before as_of."""
    out = [["Week", "Revenue", "Ad Spend", "Blended ROAS"]]
    last_sunday = as_of - timedelta(days=as_of.weekday() + 1)
    weeks = []
    for i in range(n - 1, -1, -1):
        end = last_sunday - timedelta(days=7 * i)
        weeks.append((end - timedelta(days=6), end))
    for start, end in weeks:
        rows = [r for r in all_rows if start <= r["date"] <= end]
        rev, spend = _sum(rows, "shopify_sales"), sum(total_spend(r) for r in rows)
        label = f"{start.strftime('%d.%m.')}–{end.strftime('%d.%m.%Y')}"
        out.append([label, money(rev), money(spend), ratio2(rev, spend)])
    return out


def build_snapshot(all_rows, as_of, generated_at, insights=None, window=30):
    rows = sorted(all_rows, key=lambda r: r["date"])
    win = [r for r in rows if r["date"] <= as_of][-window:]
    out = [[f"NoroSync Snapshot — generated {generated_at}"]]
    out.append(SNAPSHOT_HEADER)
    out += [snapshot_row(r) for r in win]
    out.append(snapshot_total(win))
    out.append([])
    out += monthly_block(rows, as_of.year)
    out.append([])
    out += weekly_block(rows, as_of)
    out.append([])
    for i, text in enumerate(insights or ["", "", ""], start=1):
        out.append([f"{i} — {text}"])
    out.append([TA_FOOTNOTE])
    out.append([])
    return [pad(r, SNAPSHOT_COLS) for r in out]


# ----------------------------------------------------------------- dailydata

def _channel_block(r, p):
    """Spend / platform ROAS / US / WW / CPC / CTR / CR for one ad channel."""
    return [
        money(r[f"{p}_spend"]),
        ratio2(r[f"{p}_platform_rev"], r[f"{p}_spend"]),
        money(r[f"{p}_us_spend"]),
        ratio2(r[f"{p}_us_nc_rev"], r[f"{p}_us_spend"]),
        money(r[f"{p}_ww_spend"]),
        ratio2(r[f"{p}_ww_nc_rev"], r[f"{p}_ww_spend"]),
        ratio2(r[f"{p}_spend"], r[f"{p}_clicks"]),
        ratio4(r[f"{p}_clicks"], r[f"{p}_impressions"]),
        ratio4(r[f"{p}_purchases"], r[f"{p}_clicks"]),
    ]


def dailydata_row(r):
    return ([
        ddmmyy(r["date"]),
        money(r["shopify_sales"]),
        count(r["shopify_orders"]),
        ratio2(r["shopify_sales"], r["shopify_orders"]),
        money(r["shopify_returns"]),
        money(total_spend(r)),
    ] + _channel_block(r, "meta") + _channel_block(r, "google") + [
        money(r["applovin_spend"]),
        ratio2(r["applovin_nc_rev"], r["applovin_spend"]),
        ratio2(r["applovin_platform_rev_d7"], r["applovin_spend"]),
        ratio2(r["applovin_spend"], r["applovin_clicks"]),
        ratio4(r["applovin_clicks"], r["applovin_impressions"]),
        ratio4(r["applovin_purchases"], r["applovin_clicks"]),
    ])


def _channel_total(rows, p):
    return [
        money(_sum(rows, f"{p}_spend")),
        ratio2(_sum(rows, f"{p}_platform_rev"), _sum(rows, f"{p}_spend")),
        money(_sum(rows, f"{p}_us_spend")),
        ratio2(_sum(rows, f"{p}_us_nc_rev"), _sum(rows, f"{p}_us_spend")),
        money(_sum(rows, f"{p}_ww_spend")),
        ratio2(_sum(rows, f"{p}_ww_nc_rev"), _sum(rows, f"{p}_ww_spend")),
        ratio2(_sum(rows, f"{p}_spend"), _sum(rows, f"{p}_clicks")),
        ratio4(_sum(rows, f"{p}_clicks"), _sum(rows, f"{p}_impressions")),
        ratio4(_sum(rows, f"{p}_purchases"), _sum(rows, f"{p}_clicks")),
    ]


def dailydata_total(rows):
    return ([
        "TOTAL",
        money(_sum(rows, "shopify_sales")),
        count(_sum(rows, "shopify_orders")),
        ratio2(_sum(rows, "shopify_sales"), _sum(rows, "shopify_orders")),
        money(_sum(rows, "shopify_returns")),
        money(sum(total_spend(r) for r in rows)),
    ] + _channel_total(rows, "meta") + _channel_total(rows, "google") + [
        money(_sum(rows, "applovin_spend")),
        ratio2(_sum(rows, "applovin_nc_rev"), _sum(rows, "applovin_spend")),
        ratio2(_sum(rows, "applovin_platform_rev_d7"), _sum(rows, "applovin_spend")),
        ratio2(_sum(rows, "applovin_spend"), _sum(rows, "applovin_clicks")),
        ratio4(_sum(rows, "applovin_clicks"), _sum(rows, "applovin_impressions")),
        ratio4(_sum(rows, "applovin_purchases"), _sum(rows, "applovin_clicks")),
    ])


def build_dailydata(all_rows, as_of, generated_at, window=30):
    rows = sorted(all_rows, key=lambda r: r["date"])
    win = [r for r in rows if r["date"] <= as_of][-window:]
    out = [[f"NoroSync DailyData — generated {generated_at}"], DAILYDATA_HEADER]
    out += [dailydata_row(r) for r in win]
    out.append(dailydata_total(win))
    return [pad(r, DAILYDATA_COLS) for r in out]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

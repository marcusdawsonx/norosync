"""Facts schema for the Noro Arts daily snapshot.

DESIGN RULE: the facts store holds NUMERATORS AND DENOMINATORS, never ratios.
Every ratio (ROAS, CPC, CTR, CR, AOV) is derived at render time from sums, so
TOTAL rows and any merge are correctly weighted. Storing a ratio and averaging
it later is the single most common way these reports go wrong.

One row per calendar day, shop timezone (Asia/Makassar), currency USD.
~31 numbers per day => a full year is ~200KB of plain CSV, which is cheap to
round-trip through the Drive connector as text.
"""

DATE_COL = "date"

# (column, kind) - kind drives rendering/rounding only
FACT_COLUMNS = [
    # Shopify
    ("shopify_sales", "money"),
    ("shopify_orders", "count"),
    ("shopify_returns", "money"),
    # Meta
    ("meta_spend", "money"),
    ("meta_us_spend", "money"),
    ("meta_ww_spend", "money"),
    ("meta_nc_rev", "money"),
    ("meta_us_nc_rev", "money"),
    ("meta_ww_nc_rev", "money"),
    ("meta_platform_rev", "money"),
    ("meta_impressions", "count"),
    ("meta_clicks", "count"),
    ("meta_purchases", "count"),
    # Google Ads
    ("google_spend", "money"),
    ("google_us_spend", "money"),
    ("google_ww_spend", "money"),
    ("google_nc_rev", "money"),
    ("google_us_nc_rev", "money"),
    ("google_ww_nc_rev", "money"),
    ("google_platform_rev", "money"),
    ("google_impressions", "count"),
    ("google_clicks", "count"),
    ("google_purchases", "count"),
    # AppLovin
    ("applovin_spend", "money"),
    ("applovin_nc_rev", "money"),
    ("applovin_platform_rev_d7", "money"),
    ("applovin_impressions", "count"),
    ("applovin_clicks", "count"),
    ("applovin_purchases", "count"),
    # Klaviyo
    ("klaviyo_attr_rev", "money"),
]

FACT_NAMES = [c for c, _ in FACT_COLUMNS]
ALL_COLUMNS = [DATE_COL] + FACT_NAMES

# Days re-pulled on every run because the upstream platforms restate them.
# Meta spend and Triple Whale attribution settle within a few days; Shopify
# refunds keep moving for weeks, which the weekly reconcile catches.
RESTATEMENT_DAYS = 7
RECONCILE_DAYS = 90

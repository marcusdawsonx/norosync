RUNBOOK
NoroSync runbook
Store: Noro Arts (aa5f65-ed.myshopify.com). Currency USD. Timezone Asia/Makassar.
Output folder: 1iS8hL5bl_wHb32fj4ZCM4eYi3iOPccI9.
Scope (simplified 05.08.2026): the pipeline produces the DAILY run only —
Snapshot + DailyData. The weekly deep-dive (LandingPages, CreativeCoverage,
Creatives) and its scheduled task are retired. weekly.py stays in the repo
for history but is not fetched, not run, and its validation gates do not apply.
The weekly call list and rules live in git history if it is ever revived.
Deployment: fetch from GitHub with curl, never from Drive.
mkdir -p /root/noro-sync/{pipeline,raw,out} && cd /root/noro-sync/pipeline
BASE=https://raw.githubusercontent.com/marcusdawsonx/norosync/main
for f in RUNBOOK.md run.py schema.py render.py build_facts.py \
         build_workbook.py; do curl -sfO "$BASE/$f"; done
​
Six files — weekly.py deliberately excluded; the daily path was verified to run
without it (05.08.2026). The repo is public: no token, nothing can expire.
Drive remains the OUTPUT path (CSVs for the Apps Script sweep), never the input.
The pipeline is stateless. Nothing carries over between runs; every run pulls
what it needs and rebuilds from scratch. There is no state file to corrupt.
Rules that are not obvious and have already cost a day each
accounts: ["aa5f65-ed.myshopify.com"] is MANDATORY on every triplewhale
call. Windsor is authorised for two shops. Without the parameter it sums
Noro Arts and Moonstone Magic into single rows, with no error and no warning.
Meta spend comes back 3.6x too high.
Spend comes from Triple Whale attribution_spend, for every channel.
Windsor's facebook connector only covers one of the two Meta ad accounts
that ran until 18.07.2026, so its history is incomplete before that date.
The two agree to the cent from 18.07 onward. Windsor is still the only source
for impressions, clicks, purchases and platform revenue.
AppLovin: pull delivery metrics and 7-day checkout metrics in SEPARATE
calls. Combined, spend/impressions/clicks come back silently wrong
(249.71 against a true 252.00).
Klaviyo's reported figure is attribution_revenue (total), not
attribution_new_customer_revenue.
Shopify returns its date column as day and all values as strings.
Daily run — 7 calls
(Seven, not eight. An earlier version of this file and of the trigger prompt
both said eight, which sent a run hunting for a call that does not exist.)
Window: yesterday back 30 days, plus a YTD pull for the monthly and weekly blocks.
#
Connector
Fields
Saved to
1
Shopify run-analytics-query
FROM sales SHOW total_sales, orders, returns TIMESERIES day SINCE 2026-01-01 UNTIL <yesterday>
raw/backfill_shopify.json
2
triplewhale
date, attribution_channel, attribution_spend, attribution_new_customer_revenue, attribution_revenue — YTD
raw/ytd_triplewhale.json
3
triplewhale
date, attribution_channel, attribution_campaign, attribution_spend, attribution_new_customer_revenue — last 30d
raw/tw_campaign_30d.json
4
facebook
date, campaign, spend, impressions, clicks, actions_omni_purchase, action_values_omni_purchase — last 30d
raw/meta_campaign_30d.json
5
google_ads
date, cost, impressions, clicks, conversions, conversion_value — last 30d
raw/google_30d.json
6
applovin
date, spend, impressions, clicks — last 30d
raw/applovin_delivery_30d.json
7
applovin
date, checkouts_7d, checkout_usd_7d — last 30d
raw/applovin_checkouts_30d.json
Then: python3 run.py daily — the single entry point. It builds Daily Snapshot
and Daily Data, writes the two CSVs, runs the recalc check and prints the
reconciliation output.
Comparison window
"The prior 30 days" means the 30 days immediately before the current window,
contiguous with it — for a window ending yesterday, that is days 31 to 60 back.
Do not use the same calendar month or any other definition.
Monthly (not built, not scheduled)
The Shopify Admin GraphQL order crawl with customerJourneySummary that would
populate "Revenue all" / "RPV all" has never been built. Those columns stay
empty with a NOTE row stamping the as-of date.
Decisions on record
DPA/catalog ads are always their own category, even when their link resolves
to a product page. Decided 29.07.2026; departs from the original spec.
Meta DPA campaigns are allocated to US in the US/WW split. Decided 29.07.2026;
WW figures are therefore not comparable to reports before that date.
Weekly deep-dive retired 05.08.2026 (scheduled task deleted). Its decisions
(Konzepte counting, variant merging, session-query LIMIT 5000,
attributed_order_channel filtering, effective_status readings) are preserved
in git history with weekly.py.
Validation before delivering (daily)
recalc.py must report zero errors.
Total Ad Spend must equal the sum of its own components.
The monthly block must reproduce prior published figures for closed months.

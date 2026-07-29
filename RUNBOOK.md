# NoroSync runbook

Store: Noro Arts (`aa5f65-ed.myshopify.com`). Currency USD. Timezone Asia/Makassar.
Pipeline source lives in Drive folder `NoroSync Pipeline`
(`1W4QipN34LaWtGBRNRS-ZCq35yLNp0XHj`). Output folder is
`1iS8hL5bl_wHb32fj4ZCM4eYi3iOPccI9`.

**Deployment: fetch from GitHub with curl, never from Drive.**

    BASE=https://raw.githubusercontent.com/marcusdawsonx/norosync/main
    for f in RUNBOOK.md run.py schema.py render.py build_facts.py \
             build_workbook.py weekly.py; do curl -sfO "$BASE/$f"; done

The repo is public, so this needs no token and nothing can expire. Measured
29.07.2026: 2.07 seconds and zero tokens, against ~25 minutes and 19 tool calls
for the same files via the Drive connector. The reason is structural — a Drive
download returns base64 into the model's context, which then has to be retyped
to reach disk; curl writes bytes straight to disk and the model never sees them.
Drive remains the OUTPUT path (CSVs for the Apps Script sweep). It is not the
input path.

The pipeline is stateless. Nothing carries over between runs; every run pulls
what it needs and rebuilds from scratch. There is no state file to corrupt.

## Rules that are not obvious and have already cost a day each

1. **`accounts: ["aa5f65-ed.myshopify.com"]` is MANDATORY on every `triplewhale`
   call.** Windsor is authorised for two shops. Without the parameter it sums
   Noro Arts and Moonstone Magic into single rows, with no error and no warning.
   Meta spend comes back 3.6x too high.
2. **Spend comes from Triple Whale `attribution_spend`, for every channel.**
   Windsor's `facebook` connector only covers one of the two Meta ad accounts
   that ran until 18.07.2026, so its history is incomplete before that date.
   The two agree to the cent from 18.07 onward. Windsor is still the only source
   for impressions, clicks, purchases and platform revenue.
3. **AppLovin: pull delivery metrics and 7-day checkout metrics in SEPARATE
   calls.** Combined, spend/impressions/clicks come back silently wrong
   (249.71 against a true 252.00).
4. **Triple Whale landing-page revenue uses `attributed_order_channel`,** not
   `attribution_channel`. Those fields live in different Windsor tables, and
   filtering with the wrong one returns zero revenue on every channel silently.
5. **Never leave a ShopifyQL session query at `LIMIT 100`.** The real result is
   718 / 2469 rows. Use `LIMIT 5000`.
6. **Klaviyo's reported figure is `attribution_revenue`** (total), not
   `attribution_new_customer_revenue`.
7. Shopify returns its date column as `day` and all values as strings.
8. `effective_status` has six values. "Active" means strictly `ACTIVE`.

## Daily run — 7 calls

(Seven, not eight. An earlier version of this file and of the trigger prompt
both said eight, which sent a run hunting for a call that does not exist.)

Window: yesterday back 30 days, plus a YTD pull for the monthly and weekly blocks.

| # | Connector | Fields | Saved to |
|---|---|---|---|
| 1 | Shopify `run-analytics-query` | `FROM sales SHOW total_sales, orders, returns TIMESERIES day SINCE 2026-01-01 UNTIL <yesterday>` | `raw/backfill_shopify.json` |
| 2 | triplewhale | date, attribution_channel, attribution_spend, attribution_new_customer_revenue, attribution_revenue — YTD | `raw/ytd_triplewhale.json` |
| 3 | triplewhale | date, attribution_channel, attribution_campaign, attribution_spend, attribution_new_customer_revenue — last 30d | `raw/tw_campaign_30d.json` |
| 4 | facebook | date, campaign, spend, impressions, clicks, actions_omni_purchase, action_values_omni_purchase — last 30d | `raw/meta_campaign_30d.json` |
| 5 | google_ads | date, cost, impressions, clicks, conversions, conversion_value — last 30d | `raw/google_30d.json` |
| 6 | applovin | date, spend, impressions, clicks — last 30d | `raw/applovin_delivery_30d.json` |
| 7 | applovin | date, checkouts_7d, checkout_usd_7d — last 30d | `raw/applovin_checkouts_30d.json` |

Then: `python3 pipeline/build_workbook.py` builds Daily Snapshot and Daily Data.

## Comparison window

"The prior 30 days" means the 30 days immediately before the current window,
contiguous with it — for a window ending yesterday, that is days 31 to 60 back.
Do not use the same calendar month or any other definition.

## Weekly run — the daily 7 plus 6 more

| # | Connector | Fields | Saved to |
|---|---|---|---|
| 8 | Shopify | sessions + sessions_that_completed_checkout, `WHERE utm_source IN ('facebook','ig','facebook-FeaturedOfferings') GROUP BY landing_page_path`, LIMIT 5000 | `raw/wk_sessions_meta.json` |
| 9 | Shopify | same, `GROUP BY utm_campaign, landing_page_path` | `raw/wk_sessions_meta_campaign.json` |
| 10 | Shopify | same, no utm filter, `GROUP BY landing_page_path` | `raw/wk_sessions_all.json` |
| 11 | triplewhale | attributed_order_landing_page, attributed_order_revenue, filter `attributed_order_channel eq facebook-ads` | `raw/wk_tw_landing_pages.json` |
| 12 | facebook | ad_id, ad_name, campaign, effective_status, ad_created_time, spend, impressions, clicks, frequency, actions_video_view, video_play_actions_video_view, video_thruplay_watched_actions_video_view, actions_omni_purchase, action_values_omni_purchase, link, website_destination_url, instagram_permalink_url | `raw/wk_meta_ads.json` |
| 13 | facebook | campaign_id, campaign, spend / and ad_id, campaign_id | `raw/wk_meta_campaign_ids.json`, `raw/wk_ad_campaign_map.json` |

## Monthly

Additionally run the Shopify Admin GraphQL order crawl with
`customerJourneySummary` to populate "Revenue all" and "RPV all". This is the
single most expensive operation in the report and drives no signal, so it runs
monthly and its as-of date is stamped in a NOTE row.

## Decisions on record

- DPA/catalog ads are always their own category, even when their link resolves
  to a product page. Decided 29.07.2026; departs from the original spec.
- Meta DPA campaigns are allocated to US in the US/WW split. Decided 29.07.2026;
  WW figures are therefore not comparable to reports before that date.
- "Konzepte" counts distinct concept codes among ACTIVE ads only.
- Bare `AC{n}` codes with no hook number count as their own concept.
- Variant product pages merge into their base only when the base itself has
  traffic. Merged rows are marked with a circled plus.

## Validation before delivering

- Meta spend allocated across landing pages must equal total campaign spend.
- Creatives listed spend plus the small-ad NOTE must equal ad-level total spend.
- Sessions in the landing-page table must equal the session query total.
- `recalc.py` must report zero errors.

"""Turn saved connector payloads into the daily facts store.

SOURCE OF TRUTH FOR SPEND: Triple Whale `attribution_spend`, everywhere.
Decided 29.07.2026 after measuring both sources day by day. Windsor's Meta
connector was hooked up around 2026-07-18; from that date the two agree to the
cent, but before it Windsor is progressively incomplete (June -10%, May -50%,
April -93%, nothing before 13.04). Triple Whale is not a rival estimate of
spend - it is the same number with complete history. Windsor is still the only
source for delivery metrics (impressions, clicks, purchases, platform revenue).

Other landmines, each discovered the hard way and encoded here so nobody has to
find them twice:

  * triplewhale REQUIRES accounts=["aa5f65-ed.myshopify.com"]. Without it Windsor
    silently sums Noro Arts and moonstonemagic - Meta spend comes back 3.6x high
    with no error and no warning.
  * applovin delivery metrics and 7d checkout metrics must be pulled SEPARATELY.
    Combined, spend/impressions/clicks are silently wrong (249.71 vs 252.00).
  * Shopify returns dates under the key 'day' and all values as STRINGS.
  * Triple Whale carries 18 channel values including 'Direct', 'Excluded',
    'Non-attributed', a truncated 'th', and the unrendered template literal
    '{{site_source_name}}'. Only ever sum an explicit allow-list.
  * Klaviyo's reported figure is attribution_revenue (total), NOT
    attribution_new_customer_revenue. Confirmed to the cent against 4646.95.
  * Google Ads genuinely had zero spend 22.05-10.06; that gap is real data.
"""
import csv
import json
from collections import defaultdict
from datetime import datetime

RAW = "/root/noro-sync/raw"
OUT = "/root/noro-sync/warehouse/facts.csv"

# Explicit allow-list. Anything not named here is a bucket, not a channel.
CHANNELS = {"facebook-ads": "meta", "google-ads": "google", "applovin": "applovin"}
KLAVIYO = "klaviyo"

# Geo rule for Meta, agreed 29.07.2026. Campaign naming uses three conventions:
# 'USA | ...' prefix, 'WW | ...' prefix, and a '3 | ...' family where the geo
# marker is trailing or absent. DPA campaigns target both and are allocated to
# US by decision - this differs from reports before 29.07.2026, so WW figures
# are not comparable to older ones.
def geo(campaign):
    c = campaign or ""
    return "us" if ("USA" in c or "| DPA" in c) else "ww"


def load(name):
    with open(f"{RAW}/{name}.json", encoding="utf-8") as f:
        return json.load(f)


def d(x):
    return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()


def n(x):
    return 0.0 if x in (None, "") else float(x)


def sum_by_date(rows, fields, date_key="date"):
    out = defaultdict(lambda: defaultdict(float))
    for r in rows:
        day = d(r[date_key])
        for f in fields:
            out[day][f] += n(r.get(f))
    return out


def build():
    # ---- YTD spine: Shopify revenue + Triple Whale attribution, every day ----
    shop = {d(r["day"]): r for r in load("backfill_shopify")}

    tw = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in load("ytd_triplewhale"):
        ch = r.get("attribution_channel")
        if ch not in CHANNELS and ch != KLAVIYO:
            continue
        day = d(r["date"])
        for f in ("attribution_spend", "attribution_new_customer_revenue",
                  "attribution_revenue"):
            tw[day][ch][f] += n(r.get(f))

    def tws(day, ch, f):
        return tw[day][ch][f]

    # ---- last 30 days: delivery metrics and the US/WW split ----
    meta_del = sum_by_date(
        load("meta_campaign_30d"),
        ["impressions", "clicks", "actions_omni_purchase",
         "action_values_omni_purchase"])
    google = sum_by_date(
        load("google_30d"),
        ["impressions", "clicks", "conversions", "conversion_value"])
    al_del = sum_by_date(load("applovin_delivery_30d"), ["impressions", "clicks"])
    al_chk = sum_by_date(load("applovin_checkouts_30d"),
                         ["checkouts_7d", "checkout_usd_7d"])

    # US/WW split of BOTH spend and new-customer revenue, from the same
    # campaign rows and the same rule - so the two can never disagree.
    split = defaultdict(lambda: defaultdict(float))
    for r in load("tw_campaign_30d"):
        if r.get("attribution_channel") != "facebook-ads":
            continue
        g = geo(r.get("attribution_campaign"))
        day = d(r["date"])
        split[day][f"{g}_spend"] += n(r.get("attribution_spend"))
        split[day][f"{g}_nc"] += n(r.get("attribution_new_customer_revenue"))

    facts = []
    for day in sorted(shop):
        s = shop[day]
        meta_spend = tws(day, "facebook-ads", "attribution_spend")
        google_spend = tws(day, "google-ads", "attribution_spend")
        al_spend = tws(day, "applovin", "attribution_spend")
        has_detail = day in meta_del or day in google

        row = {
            "date": day,
            "shopify_sales": n(s["total_sales"]),
            "shopify_orders": n(s["orders"]),
            "shopify_returns": n(s["returns"]),

            "meta_spend": meta_spend,
            "meta_us_spend": split[day]["us_spend"] if has_detail else None,
            "meta_ww_spend": split[day]["ww_spend"] if has_detail else None,
            "meta_nc_rev": tws(day, "facebook-ads", "attribution_new_customer_revenue"),
            "meta_us_nc_rev": split[day]["us_nc"] if has_detail else None,
            "meta_ww_nc_rev": split[day]["ww_nc"] if has_detail else None,
            "meta_platform_rev": meta_del[day]["action_values_omni_purchase"] if has_detail else None,
            "meta_impressions": meta_del[day]["impressions"] if has_detail else None,
            "meta_clicks": meta_del[day]["clicks"] if has_detail else None,
            "meta_purchases": meta_del[day]["actions_omni_purchase"] if has_detail else None,

            # Google is 100% US for this store; WW is a structural zero.
            "google_spend": google_spend,
            "google_us_spend": google_spend if has_detail else None,
            "google_ww_spend": 0.0 if has_detail else None,
            "google_nc_rev": tws(day, "google-ads", "attribution_new_customer_revenue"),
            "google_us_nc_rev": tws(day, "google-ads", "attribution_new_customer_revenue") if has_detail else None,
            "google_ww_nc_rev": None,
            "google_platform_rev": google[day]["conversion_value"] if has_detail else None,
            "google_impressions": google[day]["impressions"] if has_detail else None,
            "google_clicks": google[day]["clicks"] if has_detail else None,
            "google_purchases": google[day]["conversions"] if has_detail else None,

            "applovin_spend": al_spend,
            "applovin_nc_rev": tws(day, "applovin", "attribution_new_customer_revenue"),
            "applovin_platform_rev_d7": al_chk[day]["checkout_usd_7d"] if has_detail else None,
            "applovin_impressions": al_del[day]["impressions"] if has_detail else None,
            "applovin_clicks": al_del[day]["clicks"] if has_detail else None,
            "applovin_purchases": al_chk[day]["checkouts_7d"] if has_detail else None,

            "klaviyo_attr_rev": tws(day, KLAVIYO, "attribution_revenue"),
        }
        facts.append(row)
    return facts


def write_facts(facts, path=OUT):
    import schema
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=schema.ALL_COLUMNS)
        w.writeheader()
        for r in facts:
            w.writerow({k: ("" if r.get(k) is None else r.get(k))
                        for k in schema.ALL_COLUMNS})


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/root/noro-sync/pipeline")
    f = build()
    write_facts(f)
    detail = [r for r in f if r["meta_clicks"] is not None]
    print(f"facts store: {len(f)} days, {f[0]['date']} -> {f[-1]['date']}")
    print(f"  full detail (DailyData-capable): {len(detail)} days, "
          f"{detail[0]['date']} -> {detail[-1]['date']}")
    print(f"  revenue-and-spend only (Snapshot blocks): {len(f) - len(detail)} days")

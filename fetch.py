#!/usr/bin/env python3
"""
Pulls the numbers behind the dashboard from Shopify and writes data.json.

    SHOPIFY_SHOP=aa5f65-ed.myshopify.com \
    SHOPIFY_ADMIN_TOKEN=shpat_xxx \
    python3 fetch.py

Standard library only. Writes data.json only on complete success, so a failed run
leaves the previous snapshot intact rather than publishing a half-empty dashboard.

Every query is documented in QUERIES.md. Method decisions are in CONTEXT.md.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- configuration
SHOP = os.environ.get("SHOPIFY_SHOP", "").strip()
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-07").strip()

# Launch window. Default reproduces the original brief: a fixed start date, end =
# today. Set LAUNCH_WINDOW_DAYS=90 to switch to a rolling 90-day window instead —
# recommended once you have seen one clean run, because it keeps the list current,
# bounded, and guarantees "revenue since launch" equals the 90-day figure for every
# member. Switching will add the eight 6 May Totem Pole sizes to the launch list.
LAUNCH_START_FIXED = os.environ.get("LAUNCH_START", "2026-05-11")
LAUNCH_WINDOW_DAYS = os.environ.get("LAUNCH_WINDOW_DAYS", "").strip()

SHOP_NAME = os.environ.get("SHOP_NAME", "Noro Arts")
SHOP_DOMAIN = os.environ.get("SHOP_DOMAIN", "noro-arts.com")
TZ_OFFSET_HOURS = int(os.environ.get("TZ_OFFSET_HOURS", "-4"))   # store timezone, EDT
EXCLUDE_TITLES = {"E-Gift Card"}                                  # kept in `published`, excluded from maths

if not SHOP or not TOKEN:
    sys.exit("ERROR: set SHOPIFY_SHOP and SHOPIFY_ADMIN_TOKEN.\n"
             "In GitHub Actions these come from repository secrets.")

ENDPOINT = "https://%s/admin/api/%s/graphql.json" % (SHOP, API_VERSION)
TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))
TODAY = datetime.now(TZ).date()


# ---------------------------------------------------------------- transport
def gql(query, variables=None, attempt=1):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": TOKEN,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", "replace")[:600]
        if ex.code == 404:
            sys.exit("ERROR: 404 from %s\n"
                     "The API version '%s' is probably not valid for this store.\n"
                     "Set SHOPIFY_API_VERSION to a supported version and re-run."
                     % (ENDPOINT, API_VERSION))
        if ex.code in (401, 403):
            sys.exit("ERROR: %d from Shopify — the token is rejected or lacks scopes.\n"
                     "The custom app needs read_products, read_orders and the reports/\n"
                     "analytics scope. Detail: %s" % (ex.code, detail))
        if ex.code == 429 and attempt <= 4:
            time.sleep(2 * attempt)
            return gql(query, variables, attempt + 1)
        sys.exit("ERROR: HTTP %d from Shopify. Detail: %s" % (ex.code, detail))
    except Exception as ex:                                   # noqa: BLE001
        if attempt <= 3:
            time.sleep(2 * attempt)
            return gql(query, variables, attempt + 1)
        sys.exit("ERROR: could not reach %s — %s" % (ENDPOINT, ex))

    if payload.get("errors"):
        sys.exit("ERROR: GraphQL errors:\n" + json.dumps(payload["errors"], indent=2)[:1500])
    if "data" not in payload:
        sys.exit("ERROR: no data in response:\n" + json.dumps(payload)[:1000])
    return payload["data"]


# ---------------------------------------------------------------- ShopifyQL
QL = """
query Ql($q: String!) {
  shopifyqlQuery(query: $q) {
    parseErrors
    tableData {
      columns { name }
      rows
    }
  }
}
"""

def shopifyql(q):
    """Run a ShopifyQL query and return a list of dicts keyed by column name.

    Verified against the live API 2026-07-29: `parseErrors` is a plain [String!]!,
    and `tableData.rows` is a JSON scalar that comes back as a list of OBJECTS
    already keyed by column name (not a list of arrays). Both forms are handled
    below in case that changes.
    """
    res = gql(QL, {"q": " ".join(q.split())}).get("shopifyqlQuery")
    if not res:
        sys.exit("ERROR: shopifyqlQuery returned nothing. The token most likely lacks\n"
                 "the reports/analytics scope. Query was:\n  %s" % q)
    if res.get("parseErrors"):
        sys.exit("ERROR: ShopifyQL rejected the query:\n  %s\nQuery:\n  %s"
                 % ("; ".join(str(e) for e in res["parseErrors"]), q))
    table = res.get("tableData")
    if not table:
        sys.exit("ERROR: no tableData returned for query:\n  %s" % q)

    cols = [c["name"] for c in table["columns"]]
    rows = table["rows"] or []
    if isinstance(rows, str):                       # JSON scalar arriving as text
        rows = json.loads(rows)
    out = []
    for row in rows:
        out.append(dict(row) if isinstance(row, dict) else dict(zip(cols, row)))
    if rows and not any(out[0].get(c) is not None for c in cols):
        sys.exit("ERROR: could not map ShopifyQL rows to columns %s. First row: %r"
                 % (cols, rows[0]))
    return out


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- 1. products
PRODUCTS = """
query Published($first: Int!, $after: String) {
  products(first: $first, after: $after, query: "published_status:published", sortKey: PUBLISHED_AT) {
    nodes { title publishedAt featuredImage { url } }
    pageInfo { hasNextPage endCursor }
  }
}
"""

print("fetching products ...", flush=True)
published, images, cursor = {}, {}, None
for page in range(1, 21):
    d = gql(PRODUCTS, {"first": 50, "after": cursor})["products"]
    for n in d["nodes"]:
        t = n["title"]
        if not n.get("publishedAt"):
            continue
        published[t] = n["publishedAt"]
        if n.get("featuredImage") and n["featuredImage"].get("url"):
            images[t] = n["featuredImage"]["url"].split("?")[0]
    if not d["pageInfo"]["hasNextPage"]:
        break
    cursor = d["pageInfo"]["endCursor"]
else:
    sys.exit("ERROR: product pagination did not terminate after 20 pages.")

if len(published) < 10:
    sys.exit("ERROR: only %d published products found — that is implausible, "
             "refusing to overwrite data.json." % len(published))
print("  %d published products, %d with images" % (len(published), len(images)))


# ---------------------------------------------------------------- 2-4. sales
def by_title(rows, fields):
    """Collapse ShopifyQL rows to {title: {field: value}}, dropping the
    unattributed-refunds row that comes back with an empty product_title."""
    out = {}
    for r in rows:
        t = (r.get("product_title") or "").strip()
        if not t:
            continue
        out[t] = {k: (int(num(r.get(src))) if kind is int else round(num(r.get(src)), 2))
                  for k, src, kind in fields}
    return out

print("fetching lifetime sales ...", flush=True)
life_rows = shopifyql("""FROM sales SHOW net_sales, net_items_sold
  GROUP BY product_title ORDER BY net_sales DESC
  SINCE 2024-01-01 UNTIL today LIMIT 250""")
lifetime = {t: v["net_sales"] for t, v in
            by_title(life_rows, [("net_sales", "net_sales", float)]).items()}
print("  %d products with lifetime sales" % len(lifetime))

print("fetching trailing 90 days ...", flush=True)
d90 = by_title(shopifyql("""FROM sales SHOW net_sales, net_items_sold, returns, discounts
  GROUP BY product_title ORDER BY net_sales DESC
  SINCE -90d UNTIL today LIMIT 250"""),
  [("net_sales", "net_sales", float), ("units", "net_items_sold", int),
   ("returns", "returns", float), ("discounts", "discounts", float)])
print("  %d products with 90-day sales" % len(d90))

print("fetching trailing 30 days ...", flush=True)
d30 = by_title(shopifyql("""FROM sales SHOW net_sales, net_items_sold
  GROUP BY product_title ORDER BY net_sales DESC
  SINCE -30d UNTIL today LIMIT 250"""),
  [("net_sales", "net_sales", float), ("units", "net_items_sold", int)])
print("  %d products with 30-day sales" % len(d30))

if not d90:
    sys.exit("ERROR: no 90-day sales rows returned — refusing to overwrite data.json.")


# ---------------------------------------------------------------- 5. launches
if LAUNCH_WINDOW_DAYS:
    start = TODAY - timedelta(days=int(LAUNCH_WINDOW_DAYS))
    window_note = "rolling %s days" % LAUNCH_WINDOW_DAYS
else:
    start = datetime.fromisoformat(LAUNCH_START_FIXED).date()
    window_note = "fixed start %s" % LAUNCH_START_FIXED

def pub_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).date()

launches = []
for t, iso in published.items():
    if t in EXCLUDE_TITLES:
        continue
    d = pub_date(iso)
    if start <= d <= TODAY:
        s = d90.get(t, {})
        launches.append({
            "title": t,
            "published_at": iso,
            "image": (images.get(t, "") or ""),
            "net_revenue_since_launch": s.get("net_sales", 0.0),
            "units_since_launch": s.get("units", 0),
        })
launches.sort(key=lambda x: x["published_at"])
print("  %d launches (%s)" % (len(launches), window_note))

# "since launch" only equals the 90-day figure while every launch is under 90 days old
stale = [l["title"] for l in launches if (TODAY - pub_date(l["published_at"])).days > 90]
if stale:
    print("  NOTE: %d launch(es) are now over 90 days old, so their 'since launch'\n"
          "        revenue is understated (it is the 90-day figure). Consider setting\n"
          "        LAUNCH_WINDOW_DAYS=90. Affected: %s" % (len(stale), ", ".join(stale)),
          flush=True)


# ---------------------------------------------------------------- write
missing_sales = [t for t in published if t not in EXCLUDE_TITLES and t not in lifetime]
if missing_sales:
    print("  NOTE: %d published product(s) have no lifetime sales row and will be\n"
          "        treated as zero: %s" % (len(missing_sales), ", ".join(missing_sales[:6])))
    for t in missing_sales:
        lifetime[t] = 0.0

out = {
    "meta": {
        "shop": SHOP_NAME,
        "domain": SHOP_DOMAIN,
        "currency": "USD",
        "timezone_offset_hours": TZ_OFFSET_HOURS,
        "report_date": TODAY.isoformat(),
        "launch_window": [start.isoformat(), TODAY.isoformat()],
        "source": "Shopify Admin API (products, publish dates, images) + ShopifyQL "
                  "(net_sales, net_items_sold, returns, discounts)",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_version": API_VERSION,
    },
    "published": published,
    "lifetime_net_sales": lifetime,
    "launches": launches,
    "d90": d90,
    "d30": d30,
    "images": {t: u for t, u in images.items() if t not in EXCLUDE_TITLES},
}

target = HERE / "data.json"
target.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote %s — %d products, %d launches, report date %s"
      % (target.name, len(published), len(launches), TODAY))

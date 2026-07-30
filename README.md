# Noro Arts — Product Performance dashboard

A single-page dashboard covering product launches, bestsellers, design families,
performance against a catalogue benchmark, insights, and discontinue candidates.

`index.html` is completely self-contained: all CSS and JavaScript is inline, there
is no build step and no dependencies. The only thing it loads from the network is
product photography, straight from Shopify's CDN.

Data as at **29 July 2026**.

---

## Deploy to Vercel

1. Create a new **empty** repository on GitHub (private is fine — Vercel can read
   private repos on the free plan).
2. Push these files to it:

   ```bash
   git init
   git add .
   git commit -m "Noro Arts product performance dashboard"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

   Or, if you'd rather not touch the command line: on the new repo's page use
   **Add file → Upload files**, drag everything in, and commit.

3. In Vercel: **Add New… → Project → Import** the repository.
4. Vercel will ask about a framework. Choose **Other**. Leave the build command
   and output directory empty — there is nothing to build.
5. Deploy. You get a `https://<project>.vercel.app` URL, live in about 30 seconds.

Every later `git push` redeploys automatically.

### A word on who can see it

That URL is **public to anyone who has it**. It contains product-level revenue.
Vercel's password protection is a paid feature. If it needs to be gated, the
cheapest route is Cloudflare Pages instead of Vercel — Cloudflare Access is free
for up to 50 users and will require an emailed one-time code before the page
loads. The repo works identically on either platform.

---

## Refreshing the numbers

`generate.py` reads `data.json` and writes `index.html`. It never calls Shopify —
the fetching is deliberately kept separate so the dashboard can be rebuilt from a
known snapshot at any time.

```bash
python3 generate.py     # needs only the standard library
git commit -am "Refresh data" && git push
```

So a refresh is: replace `data.json`, run the script, push. Vercel does the rest.

### data.json

| Key | Shape | Source |
|---|---|---|
| `meta` | shop name, domain, currency, timezone offset, report date, launch window | fixed |
| `published` | `{product title: publish date (ISO, UTC)}` — every currently-published product | Shopify Admin API `products` |
| `lifetime_net_sales` | `{product title: net revenue, all time}` | ShopifyQL `FROM sales SHOW net_sales GROUP BY product_title` |
| `launches` | list of the products in the launch window, with image URL, revenue and units since launch | Admin API + ShopifyQL |
| `d90` | `{title: {net_sales, units, returns, discounts}}` — trailing 90 days | ShopifyQL, `SINCE -90d` |
| `d30` | `{title: {net_sales, units}}` — trailing 30 days | ShopifyQL, `SINCE -30d` |
| `images` | `{title: featured image URL}` | Admin API `featuredImage` |

Product titles are the join key throughout, so they must match exactly across
every section. `E-Gift Card` is present in `published` and deliberately excluded
from all calculations.

The benchmark, family grouping, ratings, Pareto thresholds and cut lists are all
derived at generation time — there is nothing to configure.

---

## Automatic weekly refresh

Built and wired up. `.github/workflows/refresh.yml` runs every **Monday 06:00 UTC**,
and there is a **Run workflow** button in the Actions tab for testing.

```
fetch.py   →  data.json   →  generate.py  →  index.html  →  commit  →  Vercel deploys
```

The workflow only commits when something actually changed, so quiet weeks produce
no noise.

### One-time setup

**1. Shopify custom app** — Shopify admin → Settings → Apps and sales channels →
Develop apps → **Create an app**. Under *Configure Admin API scopes* tick:

- `read_products`
- `read_orders`
- the reports/analytics scope (usually `read_reports`) — ShopifyQL needs it

Install the app, then reveal and copy the **Admin API access token** (`shpat_…`).
It is shown once.

**2. GitHub secrets** — repo → Settings → Secrets and variables → Actions →
**New repository secret**, twice:

| Name | Value |
|---|---|
| `SHOPIFY_SHOP` | `aa5f65-ed.myshopify.com` |
| `SHOPIFY_ADMIN_TOKEN` | the `shpat_…` token |

**3. Test it** — Actions tab → *Refresh dashboard* → **Run workflow**. Watch the log.

### If the first run fails

The two likely causes, both one-line fixes:

- **404 / "API version not valid"** — uncomment `SHOPIFY_API_VERSION` in the
  workflow and set a supported version.
- **401/403, or "shopifyqlQuery returned nothing"** — the analytics scope is
  missing. Add it in the Shopify app, save, and re-run.

`fetch.py` fails loudly and **never writes a partial `data.json`**, so a bad run
leaves the live dashboard exactly as it was.

### Verified before shipping

The ShopifyQL response shape was checked against the live API on 29 July 2026:
`parseErrors` is a plain list of strings, and `tableData.rows` returns objects
already keyed by column name — *not* arrays, which is the obvious thing to assume
and would have silently produced an empty dashboard. The parser handles both, and
the coercion path is unit-tested (string money values → floats, integer units →
ints, and the unattributed-refunds row with a blank product title is dropped).

What could **not** be tested from here is the HTTP call itself — this environment
cannot reach the Shopify API. That is what the manual test run in step 3 is for.

### Switching to a rolling launch window

Right now "launches" means *published on or after 2026-05-11*, which reproduces the
original brief. That list grows forever and, once a product passes 90 days,
its "revenue since launch" quietly becomes just its 90-day revenue.

Uncomment `LAUNCH_WINDOW_DAYS: '90'` in the workflow to make it a rolling 90-day
window instead. Recommended after your first clean run. It keeps the list bounded
and correct — and it pulls in the eight 6 May Totem Pole sizes, which currently miss
the cut by five days despite being the strongest launch group in the period.
`fetch.py` prints a warning when any launch has aged past 90 days.

## Files

```
index.html                      the dashboard — this is what gets served
generate.py                     builds index.html from data.json
fetch.py                        pulls fresh numbers from Shopify → data.json
data.json                       the data snapshot
.github/workflows/refresh.yml   weekly cron + manual trigger
README.md                       this file — deploy and refresh
CONTEXT.md                      why every metric is defined the way it is; bugs
                                already found and fixed; dead ends; open threads
QUERIES.md                      the exact Shopify queries, verbatim
```

**Picking this up later — read `CONTEXT.md` first.** It carries the reasoning,
several corrections that are easy to re-introduce, and a list of approaches already
proven not to work.

## Caveats carried by the numbers

- **No product-level traffic.** Shopify Analytics cannot group sessions by
  product, so a product with weak revenue may simply never have been shown to
  anyone. Every "cut" recommendation assumes fair exposure. Check sessions and
  conversion before acting on one.
- **No margin.** Everything is revenue, not profit.
- **No inventory.** Stock, cover and reorder logic were deliberately removed —
  the counts were not reliable enough to base decisions on.
- Revenue is net of discounts and refunds, in USD.

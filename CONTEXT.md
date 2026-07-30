# Context & decision log

Read this first if you are picking this work up — a new Claude session, a colleague,
or you in three months. It records not just what the dashboard does but **why it
does it that way**, including several things that were got wrong first and then
corrected. The reasoning is the part that is expensive to rebuild.

Last updated: 29 July 2026.

---

## 1. What exists

| Thing | Where |
|---|---|
| Live dashboard | https://noro-dashboard.vercel.app/ |
| Repo (deploy source) | `marcusdawsonx/norosync` — pushes auto-deploy via Vercel |
| Generator | `generate.py` — reads `data.json`, writes `index.html` |
| Data snapshot | `data.json` |
| Earlier spreadsheet version | `.xlsx` delivered in chat, four tabs, superseded by this dashboard |
| Google Sheets (partial) | two files in the Drive folder, superseded — see §7 |

The dashboard has six tabs: Launches (+ 13-week cadence), Bestsellers, Families,
All products, Insights, Discontinue.

## 2. Store facts

- Shopify Plus, `noro-arts.com`, store admin handle `totem-poles`, myshopify domain
  `aa5f65-ed.myshopify.com`. USD. Store timezone EDT (UTC−4).
- 57 published products excluding `E-Gift Card`, which is excluded from every
  calculation. Around 130 more products exist as drafts and are ignored.
- Hand-carved teak wall art, wood sculptures and totem poles, produced in Indonesia.
- Trailing 90-day net revenue at the snapshot date: **$1,310,860**.

## 3. Metric definitions — the decisions that matter

**Benchmark = $223.94.** Median revenue/day across all 57 published products, each
measured over *its own* days live since publish. Not a mean — a mean would be
dragged up by Octopus. Not the launch cohort only — the point is to compare a new
product against the catalogue it joined. E-Gift Card excluded.

**Revenue/day and units/day.** Trailing-90-day totals divided by days live, **capped
at 90**. The cap matters: without it a product live 20 days is divided by 90 and
looks 4.5× worse than it is. This bug existed in an early version and produced
Parrot and Swirl showing *42 months of stock cover* when they had been live two days.

**vs bench** = revenue/day ÷ benchmark. 1.00× is a typical product.

**Trend** = 30-day revenue/day ÷ 90-day revenue/day, displayed as a signed
percentage. Originally called "Momentum" and shown as a ratio (`1.24×`); renamed
because the label failed a real reader. **It is suppressed below 10 units** in the
window — see §5.

**Rating bands.** Winner ≥ 2.0× · Above benchmark 1.0–2.0× · Below benchmark
0.5–1.0× · Underperformer < 0.5× · unrated under 14 days live.

**Discontinue = bottom 5% of the revenue ladder, live 60+ days.** Products are
sorted ascending by 90-day revenue and accumulated until the running total reaches
5% of catalogue revenue. That tail is 19 products; 3 are under 60 days and excluded,
leaving 15. This replaced an earlier, narrower rule (no sales in 90 days, or
< 0.25× benchmark) which caught only 11 — the bottom-5% rule is a strict superset.

**Families.** Titles are parsed into `<form> · <design>`, stripping ` (Dark Teak)`
and any ` | <size>` suffix. 57 SKUs collapse to 41 designs; 12 ship in more than one
form. The form prefix is deliberately kept, so `Teak Wall Art · Snake` and
`Teak Wood Sculpture · Snake` stay separate — same name, different products.
Family `vs bench` is **per SKU**, so a 4-SKU family is not automatically flattered.

## 4. What is deliberately excluded, and why

- **Inventory.** Stock levels, months of cover, reorder points and stock value were
  all built and then removed, on the owner's instruction that Shopify's counts are
  not reliable enough to base decisions on. If that ever changes, note that Shopify
  exposes three different numbers — `available`, `on_hand` and `committed`, where
  available = on_hand − committed. An early version used `available` and therefore
  reported Hammerhead Sharks as "out of stock, nothing to sell" when it had 144
  units physically on hand against 165 committed. That is a fulfilment backlog, not
  an empty shelf. Do not repeat that mistake.
- **Margin.** Unit cost *is* populated on every product in Shopify (margins compute
  to 81–92%), but the owner's instruction is to disregard it as unreliable. So every
  figure here is revenue, not profit. A high-revenue product could still be a poor
  one and nothing here would show it.
- **Traffic.** Not available, not a choice — see §5.

## 5. Known gaps and traps

**No product-level traffic. This is the single biggest limitation.** Shopify
Analytics cannot group sessions by product, and the store's Triple Whale connection
is not on a plan that permits MCP queries (confirmed by an explicit error). So a
product with weak revenue may simply never have been shown to anyone. Every cut
recommendation assumes fair exposure. The dashboard says this on the Discontinue
tab. If Triple Whale is ever upgraded, closing this gap is the highest-value
addition available.

**Low-volume trend figures are noise.** Trend is a ratio of two small numbers. Velora
sold **one unit in 90 days** and showed a trend of `+200%` purely because that sale
landed in the last 30 days — which was enough to keep it off the cut list under an
earlier rule. Trend is now ignored as a rescue signal below 10 units, and the Why
column says so explicitly. Four products moved onto the cut list when this was fixed.

**Pulled and unshipped products are invisible.** A launch-date query can only see
products that are still published. `Skeleton` launched, sold one unit, and was set
back to draft — its `publishedAt` is now null, so no date-range query will ever find
it. `Mystic Medusa` was created alongside the 7 June batch and never published. If
launch counts ever need to be exact, cross-check `createdAt` on draft and archived
products.

**The launch window starts 11 May, which cuts off the Totem Poles.** The eight
Cosmo/Phoenix sizes were published **6 May — five days earlier** — and did $205,549
in 90 days, which would make them collectively the strongest thing in the period.
They are excluded from the 12-product launch list because 11 May was the specified
window, but the cadence table runs 13 weeks so they are at least visible. Consider
pulling the window back to 1 May.

**Ten products have two variants** (Octopus, Crocodile, Eternal Flow, Root Spiral,
Marlin, Whale, both Manta Rays, Crocodile Dark, Octopus Dark). Any per-unit price
maths that multiplies a product-level quantity by the *first* variant's price will
be wrong for those. Not currently an issue since price is no longer used.

## 6. Corrections made — do not re-introduce

1. **Cover/pace divided by a fixed 90 days** → 2-day-old products showed 42 months
   of cover. Fixed by capping the denominator at days live.
2. **Trend rescued near-dead products** on 1–8 units of volume. Fixed with the
   10-unit floor.
3. **"Discontinue 17" counted two different verdicts** (7 cuts + 10 softer). Split
   into separate lists with the badge counting cuts only.
4. **"Dark Teak often outsells the standard finish"** — this was asserted off three
   examples and is wrong. Measured on revenue/day across all ten dual-finish
   designs, Dark Teak wins **3 of 10** (Aurex +197%, Crocodile +24%, Golden Tides
   +17%; Octopus Dark is 65% *below* standard, Birds Dark 73% below). It is a
   per-design decision, not a range strategy.
5. **Out-of-stock winners were rated neutral** in the inventory version. Irrelevant
   now that inventory is out of scope, but the reasoning is worth keeping: zero stock
   on a 7× benchmark product is the most expensive state in a catalogue, not a
   neutral one.

## 7. Dead ends — don't retry these

- **`=IMAGE()` in Google Sheets does not work via the API.** Google neuters it on
  import — the cell arrives as literal text with a leading apostrophe. Verified by
  inspecting the cell in the browser. Ordinary formulas (`IF`, arithmetic) import
  and evaluate fine; `IMAGE` specifically does not, because it makes outbound
  requests. A synthetic paste event is also ignored — Sheets only trusts real
  keystrokes. There is no programmatic route to images in Google Sheets. This is why
  the dashboard is HTML.
- **The Cowork sandbox cannot reach `cdn.shopify.com`, `noro-arts.com`,
  `api.netlify.com`, `api.vercel.com`, or `*.vercel.app`.** It *can* reach
  `github.com` and `api.github.com` (verified with `git ls-remote`) and the package
  registries. So image bytes cannot be downloaded server-side, and the live site
  cannot be checked from the sandbox — verification has to go through the user's
  browser.
- **Chrome blocks scripted downloads.** Shopify's storefront CSP blocks blob
  downloads outright, and even on a CSP-free page a programmatic click does not
  produce a file. Getting bytes out of the browser is not viable.
- Two Google Sheets in the Drive folder are leftovers from the `=IMAGE()` attempt.
  One is titled with a literal `&amp;` from an HTML-escaping error. Both are
  superseded and can be deleted; the Drive connector has no rename or delete tool.

## 8. Headline findings at the snapshot date

- **Top 10 products = 52% of revenue. Top 5 *designs* = 50%.** One product (Octopus)
  is 12%; the Octopus design across both finishes is 16.2%. Concentration is high.
- **The bottom 26 products are 10% of revenue.** The tail is much longer than the
  15-product cut list.
- **Abstract designs are 21 of 57 products — the largest group — but 17% of revenue**,
  median 0.36× benchmark. Marine subjects: 15 products, 46% of revenue, median
  1.89×. **12 of the 15 cut candidates are abstract.** The range is developed most
  heavily in the category that sells least.
- **Hammerhead Sharks reached #3 in the catalogue in 52 days** — $81,993, 221 units,
  7.04× benchmark, zero discounting. Fastest ramp in the data.
- **The catalogue is running +16% ahead of its own 90-day pace.**
- **Discounts 2.9% of gross, refunds 1.3%.** No margin leak. Only Aurex is
  discount-dependent (20.8%) and it is on the cut list.
- **Launch cadence is lumpy**: 20 products across 8 of 13 weeks, with a three-week
  gap through July. Batched creation and one prepared-but-never-shipped product
  suggest a production queue rather than a release strategy.
- **Size ladders earn at both ends**: Cosmo 3'3" moves the most units (88) at a $292
  average; Cosmo 10'0" moves 9 at $1,999 and still books $17,991. Judging a size on
  revenue/day alone always condemns the entry size — which is why Phoenix 3'3" is a
  "range decision" rather than a cut.

## 9. Open threads

1. **Automate the refresh.** `shopifyqlQuery` is confirmed available in the Admin
   GraphQL API, so a `fetch.py` can run the same three ShopifyQL queries plus one
   product query and write `data.json`. Plan: GitHub Actions weekly cron → fetch →
   generate → commit → Vercel redeploys. Needs a Shopify custom-app token added by
   the owner as a repo secret (scopes: `read_products`, `read_orders`,
   `read_reports`). Not yet built.
2. **Seasonality.** 18 months of history exist. Reordering and range decisions in
   July without knowing the Q4 curve is risky. Not yet analysed.
3. **Traffic**, if Triple Whale is upgraded — see §5.
4. **Access control.** The Vercel URL is public and contains product-level revenue.
   Cloudflare Pages + Cloudflare Access is free for 50 users; Vercel's password
   protection is paid.
5. Consider widening the launch window to 1 May to include the Totem Poles.

## 10. Working notes

- The owner's stated scope, in their words: *"we only want to know what's working and
  what we should remove."* Inventory management is explicitly out.
- They prefer to be told when a plan is flawed, and asked for trade-offs and a
  recommendation rather than a menu.
- Claude cannot accept API tokens or keys. Any credential must be added by the owner
  directly into GitHub/Shopify, never pasted into chat.

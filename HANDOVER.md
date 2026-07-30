# NoroSync — project state and handover

Last updated 30.07.2026. Read this first in any new session.

## What this is

Automated marketing reporting for the **Noro Arts** Shopify store
(`aa5f65-ed.myshopify.com`, USD, Asia/Makassar). Replaces a single 14,249-character
scheduled prompt that took 20–30 minutes a day and re-derived every rule from
prose on each run. Now: ~5 minutes a day, logic frozen in code.

**The deliverable Walter reads is the Google Sheet, not the xlsx file:**
https://docs.google.com/spreadsheets/d/1J_68CLi43M3EzUzaNewf_OPQal2CFktTGRdK1XfshxQ

## Where things live

| Thing | Location |
|---|---|
| Pipeline source (authoritative) | https://github.com/marcusdawsonx/norosync |
| Operational doc | `RUNBOOK.md` in that repo |
| Drive output folder | `1iS8hL5bl_wHb32fj4ZCM4eYi3iOPccI9` ("Noro Arts Marketing Reports") |
| The Sheet | `1J_68CLi43M3EzUzaNewf_OPQal2CFktTGRdK1XfshxQ` |
| Daily trigger | `trig_01JEycfvBDV4TneWhBE464uS` — cron `0 23 * * *` = 07:00 WITA |
| Weekly trigger | `trig_01BMDhS5bYQoR2duawdEwBUx` — cron `0 23 * * 0` = Mon 07:00 WITA |

Drive also holds a `NoroSync Pipeline` folder with stale copies of the code. It is
**obsolete** — GitHub is the source of truth. Safe to delete.

## How a run works

1. `curl` the seven files from GitHub raw — 2 seconds, no auth, zero tokens.
   Do NOT fetch code through the Drive connector: it returns base64 into context
   which then has to be retyped to disk. That cost 25 minutes and ~40–50k tokens
   per run. Drive is the OUTPUT path only.
2. Make the connector calls listed in `RUNBOOK.md` — 7 daily, 13 weekly. Delegate
   to subagents that write results straight to `raw/` so payloads never enter
   context.
3. `python3 run.py daily` (or `weekly`). Builds the workbook, writes the CSVs,
   runs the xlsx recalc check, prints reconciliation checks.
4. Replace the three PLACEHOLDER insight rows with real observations, then upload
   the CSVs to the Drive folder as Google Sheets. Walter's Apps Script sweeps them
   into fixed tabs every 15 minutes, applies all styling, then trashes the sources.

The pipeline is **stateless**. Every run rebuilds from source; there is no state
file to corrupt, and restatement is handled for free.

## Architecture decisions, and why

- **Spend comes from Triple Whale `attribution_spend` for every channel.** Windsor's
  Meta connector only covers one of the two ad accounts that ran until 18.07.2026.
  From that date the two agree to the cent; before it Windsor is progressively
  incomplete (June −10%, May −50%, April −93%, nothing before 13.04).
- **No database.** Aggregate pulls are cheap enough to rebuild each run. A DuckDB
  file could not round-trip through Drive (512KB minimum, binary corrupts when
  passed through model context) and the container has no egress to any hosted DB.
- **DPA campaigns are allocated to US** in the Meta US/WW split (decided 29.07.2026).
  WW figures are therefore not comparable to reports before that date.
- **DPA/catalog ads are always their own category** even when their link resolves,
  a deliberate departure from the original spec.
- **Konzepte counts distinct concept codes among ACTIVE ads only.** Bare `AC{n}`
  codes with no hook number count as their own concept.
- **Revenue all / RPV all** need a Shopify order crawl. Decided to run monthly.
  NOT BUILT YET — those columns stay empty with a NOTE row.

## Landmines — each of these cost a day

1. Every `triplewhale` call REQUIRES `accounts: ["aa5f65-ed.myshopify.com"]`.
   Without it Windsor silently sums Noro Arts and moonstonemagic — Meta spend
   comes back 3.6x high, no error, no warning.
2. AppLovin delivery metrics and 7-day checkout metrics must be SEPARATE calls.
   Combined, spend/impressions/clicks are silently wrong (249.71 vs 252.00).
3. Triple Whale landing-page revenue filters on `attributed_order_channel`, never
   `attribution_channel` — different tables, and the wrong one returns zero
   revenue on every channel, silently.
4. Never leave a ShopifyQL session query at `LIMIT 100`. Real results are 718 and
   2469 rows; the old report was missing ~6% of Meta sessions and ~9% of all.
5. `create_file` always CREATES, never replaces. Verify with `search_files` before
   retrying an upload. A retry storm on 29.07 made eleven duplicate files, and
   the Apps Script picks whichever was created LAST, not the newest data.
6. Klaviyo's figure is `attribution_revenue` (total), not new-customer revenue.
7. `effective_status` has six values. "Active" means strictly `ACTIVE`.
8. Shopify returns its date column as `day`, with all values as strings.

## Bugs found in the old report

1. Meta spend understated before 18.07 (second ad account) — blended ROAS was
   2.48, not 2.62.
2. Weekly/monthly blocks used a different spend source than the daily rows above
   them, off by up to 3.4%.
3. No restatement window: Google Platform ROAS published 5.22 for 23.07 when the
   true figure was 8.92, and never corrected.
4. `LIMIT 100` hid half the landing-page table (94 rows shown, 181 real).
5. Total Ad Spend did not equal the sum of its own components.
6. Older-format concept codes were unparseable, undercounting creative diversity.
7. The Triple Whale multi-shop trap (landmine 1) was live and unnoticed.

## Open items

- [ ] **Monthly order crawl** for Revenue all / RPV all. Not built, not scheduled.
- [ ] **Konzepte interpretation** — code counts ACTIVE ads only, giving 9 for
      /collections/shop-all against the old report's 15. Walter has not confirmed
      which reading he wants.
- [ ] **Windsor.ai native sync to Google Sheets** — a structural saving Walter can
      configure in Windsor's own UI, taking ad data out of the token economy.
- [ ] **A GitHub token issued 29.07 was NOT successfully revoked** — a write test
      succeeded after Walter believed he had deleted it. Fine-grained tokens live
      at github.com/settings/personal-access-tokens, not /settings/tokens.
- [ ] Delete the obsolete `NoroSync Pipeline` folder in Drive.

## Validation you can re-run

- Landing-page allocated spend must equal total campaign spend (was exact).
- Creatives listed spend + the small-ad NOTE must equal ad-level total spend.
- Sessions in the landing-page table must equal the session query total.
- `recalc.py` must report zero formula errors.
- The monthly block reproduced the old report to the cent for Jan–Jun 2026.

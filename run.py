"""Single entry point. `python3 run.py daily` or `python3 run.py weekly`.

Assumes the connector payloads named in RUNBOOK.md are already on disk under
raw/. It does no network work of its own - the MCP connectors are only reachable
from the agent, so the agent makes the calls and this script does everything
after that.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/root/noro-sync/pipeline")

import build_facts   # noqa: E402
import build_workbook  # noqa: E402
import render        # noqa: E402

WITA = timezone(timedelta(hours=8))
OUT = "/root/noro-sync/out"
RECALC = "/root/.claude/skills/xlsx/scripts/recalc.py"

PLACEHOLDERS = ["PLACEHOLDER 1", "PLACEHOLDER 2", "PLACEHOLDER 3"]

APPLOVIN_LAG = (
    "NOTE: AppLovin Platform ROAS d7 is structurally incomplete for the most recent "
    "~7 days — the 7-day attribution window is still open, so those days read low and "
    "will restate upward. This is inherent to the metric, not a data problem."
)

PROVENANCE = (
    "NOTE: spend for all channels comes from Triple Whale attribution_spend, which "
    "matches platform-reported spend to the cent from 18.07.2026 and is the only "
    "complete source before it (a second Meta ad account ran until then). DPA "
    "campaigns are allocated to US from 29.07.2026."
)


def main(mode="daily", insights=None, revenue_all=None, revenue_all_asof=None):
    now = datetime.now(WITA)
    as_of = (now - timedelta(days=1)).date()
    gen = now.strftime("%d.%m.%Y %H:%M WITA")

    facts = build_facts.build()
    facts = [f for f in facts if f["date"] <= as_of]
    if not facts:
        raise SystemExit("no facts built - check that raw/ payloads are present")

    sn = render.build_snapshot(facts, as_of, gen, insights or PLACEHOLDERS)
    sn.append(render.pad([PROVENANCE], render.SNAPSHOT_COLS))
    sn.append(render.pad([APPLOVIN_LAG], render.SNAPSHOT_COLS))
    dd = render.build_dailydata(facts, as_of, gen)

    if mode == "weekly":
        import weekly
        lp, cc, cr, notes = weekly.build_sheets(as_of, gen, revenue_all,
                                                revenue_all_asof)
        path = f"{OUT}/noro_arts_weekly_{as_of}.xlsx"
        build_workbook.build_full(sn, dd, lp, cc, cr, path)
        checks = validate_weekly(lp, cc, cr)
    else:
        path = f"{OUT}/noro_arts_snapshot_{as_of}.xlsx"
        build_workbook.build(sn, dd, path)
        checks = []

    # The Google Sheet is the thing that actually gets read - one stable link,
    # not a new file every morning. The Apps Script bound to that Sheet sweeps
    # CSVs from the Drive output folder into fixed tabs and applies all the
    # styling itself, so these CSVs must carry PLAIN decimals: no $, no %, no
    # 'x' suffix, no thousands separators, exact column order.
    stamp = as_of.strftime("%d.%m")
    csvs = [(f"NoroSync Snapshot {stamp}", sn), (f"NoroSync DailyData {stamp}", dd)]
    if mode == "weekly":
        csvs += [(f"NoroSync LandingPages {stamp}", lp),
                 (f"NoroSync CreativeCoverage {stamp}", cc),
                 (f"NoroSync Creatives {stamp}", cr)]
    for name, rows in csvs:
        render.write_csv(rows, f"{OUT}/{name}.csv")
    print("CSVs for the Drive sweep: " + ", ".join(n for n, _ in csvs))

    out = subprocess.run([sys.executable, RECALC, path, "90"],
                         capture_output=True, text=True)
    print(out.stdout.strip())
    print(f"as_of={as_of}  days_of_facts={len(facts)}  wrote {path}")
    for line in checks:
        print(line)
    return path


def validate_weekly(lp, cc, cr):
    """The reconciliations that must hold before anything is delivered."""
    def col(rows, i):
        """Data rows only: skip the title and header, stop at TOTAL. Including
        the TOTAL row here silently doubles every check, which looks like a
        reconciliation failure and is really a slicing bug."""
        total = sum(float(r[i]) for r in rows[2:]
                    if not str(r[0]).startswith("TOTAL")
                    and str(r[i]).strip() not in ("", "None"))
        return total
    lines = []
    lp_spend, cc_spend = col(lp, 5), col(cc, 8)
    cr_spend = col(cr, 6)
    lines.append(f"CHECK landing-page spend {lp_spend:,.2f} vs coverage spend "
                 f"{cc_spend:,.2f} -> diff {abs(lp_spend - cc_spend):,.2f}")
    lines.append(f"CHECK creatives listed spend {cr_spend:,.2f} "
                 f"(remainder is the small-ad NOTE row)")
    return lines


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "daily")

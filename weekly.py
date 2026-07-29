"""Weekly tabs: LandingPages, CreativeCoverage, Creatives.

This is the half of the report that was previously re-derived from prose on every
run. Every rule below came from that prose; where the prose allowed a judgement
call, the resolution is stated in a comment so it is auditable rather than
re-invented.

Landmines encoded here:
  * Triple Whale's landing-page and revenue fields live in the 'Attributed
    Orders' table, so they must be filtered with attributed_order_channel.
    Filtering with attribution_channel returns zero revenue on every channel,
    silently and without error.
  * Shopify's utm_campaign is Meta's numeric campaign_id, not a campaign name.
  * effective_status has six values. 'Active' means strictly ACTIVE; the
    ADSET_PAUSED and CAMPAIGN_PAUSED ads are not running.
  * ShopifyQL session queries must not be left at LIMIT 100: the real result is
    718 / 2469 rows and the top 100 hold only 94% / 91% of sessions.
"""
import json
import re
from collections import defaultdict
from datetime import date, datetime

RAW = "/root/noro-sync/raw"

LP_HEADER = ["Landing page", "Typ", "% of Meta traffic", "Sessions", "Sessions all",
             "Meta Spend", "Cost/Session", "On-page CVR", "CVR all", "TW Revenue",
             "Revenue all", "RPV", "RPV all", "Page ROAS", "Signal"]

CC_HEADER = ["Landing page", "Typ", "LP-Signal", "Sessions", "Page ROAS", "RPV all",
             "Active Ads", "Konzepte", "Spend", "Purchases", "Platform ROAS",
             "Top-Ad Share", "Avg Age (days)", "Creative-Gap"]

CR_HEADER = ["Ad Name", "Landing page", "Status", "Format", "AC-H", "Age (days)",
             "Spend", "CTR", "Frequency", "Hook Rate", "Hold Rate", "Purchases",
             "Revenue", "ROAS", "Ad-Signal"]

MERGED = " ⊕"
LOCALE = re.compile(r"^/[a-z]{2}-[a-z]{2}(?=/|$)")
COLLECTION_PRODUCT = re.compile(r"^/collections/[^/]+(/products/.+)$")


# ------------------------------------------------------------------ loading

def _load(name):
    with open(f"{RAW}/{name}.json", encoding="utf-8") as f:
        return json.load(f)


def shopify_rows(name):
    """ShopifyQL responses are an envelope: columns + rows-as-lists."""
    d = _load(name)
    cols = [c["name"] for c in d["columns"]]
    return [dict(zip(cols, r)) for r in d["rows"]]


def windsor_rows(name):
    d = _load(name)
    return d["rows"] if isinstance(d, dict) else d


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------- path normalization

def base_path(p):
    """Domain and locale stripping, plus collection-scoped product collapse.
    Does NOT do variant merging - that needs the full set of live paths."""
    if not p:
        return None
    p = re.sub(r"^https?://[^/]+", "", p)
    p = p.split("?")[0].split("#")[0]
    if not p.startswith("/"):
        p = "/" + p
    p = LOCALE.sub("", p) or "/"
    m = COLLECTION_PRODUCT.match(p)
    if m:
        p = m.group(1)
    return p.rstrip("/") or "/"


def build_variant_map(paths):
    """Merge variant product pages into their base product.

    RESOLVED AMBIGUITY: the spec says to strip 'trailing variant suffixes
    (-dark-teak and analogous colour/finish suffixes)' without listing them.
    Hardcoding a colour list would rot the first time a new finish launches, so
    the rule here is data-driven: strip up to two trailing hyphen segments, and
    merge ONLY if the shortened handle is itself a page with traffic. A variant
    whose base has no traffic stays standalone, exactly as the spec requires.
    """
    live = set(paths)
    mapping = {}
    for p in paths:
        if not p.startswith("/products/"):
            continue
        parts = p.split("-")
        for cut in (1, 2):
            if len(parts) <= cut + 1:
                continue
            cand = "-".join(parts[:-cut])
            if cand in live and cand != p:
                mapping[p] = cand
                break
    return mapping


def normalizer(all_paths):
    norm1 = {p: base_path(p) for p in all_paths}
    variants = build_variant_map(set(norm1.values()))

    def norm(p):
        b = norm1.get(p, base_path(p))
        return variants.get(b, b)
    return norm, variants


def typ(p):
    if p.startswith("/products/"):
        return "Produkt"
    if p.startswith("/collections/"):
        return "Collection"
    return "Seite"


# ------------------------------------------------------------ ad name rules

COPY_SUFFIX = re.compile(r"(\s*-\s*Copy|\s*\(\d+\))+$", re.I)
ACH = re.compile(r"\b(AC\d+)\s*-\s*(H\d+)\b", re.I)
DEST = re.compile(r"\b(SA|TP|CP|PDP|WA)\b")


def clean_ad_name(name):
    return COPY_SUFFIX.sub("", name or "").strip()


def ad_format(name):
    n = (name or "").lower()
    if n.startswith("dpa"):
        return "DPA"
    if "video" in n:
        return "Video"
    if "static" in n:
        return "Static"
    return ""


AC_ONLY = re.compile(r"\bAC\s*(\d+)\b", re.I)


def ad_ach(name):
    """The concept code. The spec assumed every name carries 'AC{n} - H{n}', but
    an older naming generation carries a bare 'AC{n}' with no hook number
    (e.g. '... | LPMaritime | AC5'). Treating those as unparseable dropped 20%
    of ads out of the Konzepte count, which is why the old report undercounted
    creative diversity. Bare AC codes now count as their own concept."""
    m = ACH.search(name or "")
    if m:
        return f"{m.group(1).upper()}-{m.group(2).upper()}"
    m = AC_ONLY.search(name or "")
    return f"AC{m.group(1)}" if m else ""


def motif_of(name):
    """The motif sits between the format token and the destination token."""
    parts = [p.strip() for p in clean_ad_name(name).split(" - ")]
    dest_i = next((i for i, p in enumerate(parts) if DEST.fullmatch(p)), None)
    if dest_i is None or dest_i == 0:
        return ""
    return parts[dest_i - 1]


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def map_ad_to_page(ad, live_pages, campaign_dominant, norm):
    """STRICT PRIORITY ORDER, exactly as specced."""
    name = clean_ad_name(ad.get("ad_name"))
    link = ad.get("link") or ad.get("website_destination_url") or ""

    # (0) DPA / catalog ads are ALWAYS their own category.
    # DECIDED 29.07.2026: the spec made this conditional on the link being null,
    # but these ads now carry resolvable links, which would attribute a whole
    # catalogue campaign to whichever single product the link happened to point
    # at. A catalog ad does not belong to one landing page, so the category wins
    # over the link. This is a deliberate departure from the written spec.
    if name.upper().startswith("DPA"):
        return "DPA / Catalog", "category"

    # (1) a real shop link wins
    if link and "instagram.com" not in link and "/" in link:
        p = norm(base_path(link))
        if p and p != "/" and (p in live_pages or p.startswith(("/products/", "/collections/"))):
            return p, "link"

    # (2) derive from the ad name
    parts = [p.strip() for p in name.split(" - ")]
    dest = next((p for p in parts if DEST.fullmatch(p)), None)
    motif = motif_of(name)
    if dest == "SA":
        return "/collections/shop-all", "name"
    if dest == "TP" or "totem pole" in motif.lower():
        return "/collections/totem-poles-collection", "name"
    if dest in ("CP", "PDP") and motif:
        slug = slugify(motif)
        prefix = "/collections/" if dest == "CP" else "/products/"
        hits = [p for p in live_pages if p.startswith(prefix) and slug and slug in p]
        if len(hits) == 1:                      # 'accept only unambiguous matches'
            return hits[0], "name"
        exact = [p for p in live_pages if p == f"{prefix}{slug}"
                 or p == f"{prefix}{slug}-collection"]
        if len(exact) == 1:
            return exact[0], "name"

    # (4) fall back to the campaign's dominant landing page
    dom = campaign_dominant.get(ad.get("campaign_id"))
    if dom:
        return dom, "campaign"

    # (5) give up, and say so rather than guessing
    return "IG-Post (unzugeordnet)", "unassigned"


# --------------------------------------------------------------- signals

def lp_signal(sessions, page_roas, meta_spend, cvr_all, on_page_cvr):
    if sessions < 300 or page_roas is None:
        return ""
    out = []
    if page_roas >= 3:
        out.append("▲ Skalieren")
    if meta_spend >= 2000 and page_roas < 1.5:
        out.append("● Fixen")
    if cvr_all >= 0.003 and (on_page_cvr == 0 or cvr_all >= 2 * on_page_cvr):
        out.append("✎ Creative")
    return " + ".join(out) if out else "–"


def coverage_signal(lpsig, active_ads, konzepte, spend, top_share, avg_age, is_category):
    if is_category:
        return ""
    out = []
    if "Skalieren" in lpsig and (active_ads <= 2 or konzepte <= 1):
        out.append("▲ Mehr Creatives")
    elif (konzepte <= 1 or top_share >= 0.6) and spend >= 1000:
        out.append("✎ Diversifizieren")
    if "Fixen" in lpsig:
        out.append("▼ LP zuerst fixen")
    if "Creative" in lpsig:
        out.append("✎ Neue Angles")
    s = " + ".join(out) if out else "–"
    if avg_age >= 90:
        s = (s if s != "–" else "") + (" + " if s != "–" else "") + "\U0001f504 Refresh"
    return s


def ad_signal(roas, purchases, spend, age, frequency):
    out = []
    if roas is not None and roas >= 3 and purchases >= 3:
        out.append("▲ Winner")
    if spend >= 500 and purchases == 0:
        out.append("▼ Kill")
    if age >= 90 or frequency >= 4:
        out.append("\U0001f504 Refresh")
    return " + ".join(out) if out else "–"


# ------------------------------------------------------------ table builder

def build_tables(as_of=date(2026, 7, 28), revenue_all=None, revenue_all_asof=None):
    """revenue_all: {normalized_page: revenue} from the monthly order crawl.
    Left empty between monthly runs; the as-of date is stamped in a NOTE row."""
    revenue_all = revenue_all or {}

    ses_meta = shopify_rows("wk_sessions_meta")
    ses_all = shopify_rows("wk_sessions_all")
    ses_camp = shopify_rows("wk_sessions_meta_campaign")
    tw_lp = windsor_rows("wk_tw_landing_pages")
    ads_raw = windsor_rows("wk_meta_ads")
    camps = windsor_rows("wk_meta_campaign_ids")
    ad_camp = {r["ad_id"]: r["campaign_id"] for r in windsor_rows("wk_ad_campaign_map")}

    raw_paths = ({r["landing_page_path"] for r in ses_meta}
                 | {r["landing_page_path"] for r in ses_all}
                 | {r["landing_page_path"] for r in ses_camp}
                 | {r["attributed_order_landing_page"] for r in tw_lp
                    if r.get("attributed_order_landing_page")})
    norm, variants = normalizer(raw_paths)

    # ---- session aggregates -------------------------------------------
    m_ses, m_chk, a_ses, a_chk = (defaultdict(float) for _ in range(4))
    for r in ses_meta:
        p = norm(r["landing_page_path"])
        m_ses[p] += f(r["sessions"]); m_chk[p] += f(r["sessions_that_completed_checkout"])
    for r in ses_all:
        p = norm(r["landing_page_path"])
        a_ses[p] += f(r["sessions"]); a_chk[p] += f(r["sessions_that_completed_checkout"])

    tw_rev = defaultdict(float)
    tw_null = 0.0
    for r in tw_lp:
        p = r.get("attributed_order_landing_page")
        if not p:
            tw_null += f(r["attributed_order_revenue"]); continue
        tw_rev[norm(p)] += f(r["attributed_order_revenue"])

    # ---- Meta spend allocated to pages by session share ----------------
    camp_spend = defaultdict(float)
    camp_name = {}
    for r in camps:
        camp_spend[r["campaign_id"]] += f(r["spend"]); camp_name[r["campaign_id"]] = r["campaign"]
    camp_page_ses = defaultdict(lambda: defaultdict(float))
    for r in ses_camp:
        camp_page_ses[r["utm_campaign"]][norm(r["landing_page_path"])] += f(r["sessions"])
    lp_spend = defaultdict(float)
    unallocated_spend = 0.0
    for cid, spend in camp_spend.items():
        pages = camp_page_ses.get(cid)
        if not pages:
            unallocated_spend += spend; continue
        tot = sum(pages.values()) or 1
        for p, s in pages.items():
            lp_spend[p] += spend * s / tot
    campaign_dominant = {}
    for cid, pages in camp_page_ses.items():
        tot = sum(pages.values()) or 1
        top, val = max(pages.items(), key=lambda kv: kv[1])
        if val / tot >= 0.70:
            campaign_dominant[cid] = top

    # ---- LandingPages --------------------------------------------------
    live_pages = {p for p in m_ses if p}
    total_m_ses = sum(m_ses.values()) or 1
    lp_rows, lp_index = [], {}
    for p in sorted(live_pages, key=lambda x: -m_ses[x]):
        s, sa = m_ses[p], a_ses.get(p, 0.0)
        spend, rev = lp_spend.get(p, 0.0), tw_rev.get(p, 0.0)
        onp = m_chk[p] / s if s else 0.0
        cva = a_chk.get(p, 0.0) / sa if sa else 0.0
        roas = rev / spend if spend else None
        rall = revenue_all.get(p)
        sig = lp_signal(s, roas, spend, cva, onp)
        label = p + (MERGED if p in variants.values() and any(
            v == p for v in variants.values()) else "")
        lp_index[p] = {"sig": sig, "sessions": s, "roas": roas,
                       "rpv_all": (rall / sa if rall and sa else None), "typ": typ(p)}
        lp_rows.append([label, typ(p), s / total_m_ses, s, sa or "", spend,
                        spend / s if s else "", onp, cva, rev,
                        rall if rall is not None else "",
                        rev / s if s else "", (rall / sa) if rall and sa else "",
                        roas if roas is not None else "", sig])

    # ---- ad-level aggregation -----------------------------------------
    ads = defaultdict(lambda: defaultdict(float))
    meta = {}
    for r in ads_raw:
        i = r["ad_id"]
        for k in ("spend", "impressions", "clicks", "actions_video_view",
                  "video_play_actions_video_view",
                  "video_thruplay_watched_actions_video_view",
                  "actions_omni_purchase", "action_values_omni_purchase"):
            ads[i][k] += f(r.get(k))
        ads[i]["_freq_num"] += f(r.get("frequency")) * f(r.get("impressions"))
        if i not in meta:
            meta[i] = {"ad_name": r.get("ad_name"), "campaign": r.get("campaign"),
                       "effective_status": r.get("effective_status"),
                       "ad_created_time": r.get("ad_created_time"),
                       "link": r.get("link"),
                       "website_destination_url": r.get("website_destination_url"),
                       "campaign_id": ad_camp.get(i)}

    def age_days(ts):
        if not ts:
            return 0
        try:
            return (as_of - datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()).days
        except ValueError:
            return 0

    mapping_stats = defaultdict(float)
    cr_rows, per_page = [], defaultdict(list)
    for i, m in meta.items():
        a = ads[i]
        page, how = map_ad_to_page(m, live_pages, campaign_dominant, norm)
        mapping_stats[how] += a["spend"]
        imps, clicks = a["impressions"], a["clicks"]
        freq = a["_freq_num"] / imps if imps else 0.0
        age = age_days(m["ad_created_time"])
        fmt = ad_format(m["ad_name"])
        roas = a["action_values_omni_purchase"] / a["spend"] if a["spend"] else None
        rec = {"page": page, "spend": a["spend"], "purchases": a["actions_omni_purchase"],
               "rev": a["action_values_omni_purchase"], "age": age,
               "status": m["effective_status"], "ach": ad_ach(m["ad_name"])}
        per_page[page].append(rec)
        if a["spend"] >= 50:
            cr_rows.append([clean_ad_name(m["ad_name"]), page, m["effective_status"], fmt,
                            rec["ach"], age, a["spend"],
                            clicks / imps if imps else "", freq,
                            (a["actions_video_view"] / imps) if imps and fmt == "Video" else "",
                            (a["video_thruplay_watched_actions_video_view"]
                             / a["video_play_actions_video_view"])
                            if a["video_play_actions_video_view"] and fmt == "Video" else "",
                            a["actions_omni_purchase"], a["action_values_omni_purchase"],
                            roas if roas is not None else "",
                            ad_signal(roas, a["actions_omni_purchase"], a["spend"], age, freq)])
    small = [i for i in meta if ads[i]["spend"] < 50]
    cr_rows.sort(key=lambda r: (r[1], -r[6]))

    # ---- CreativeCoverage ---------------------------------------------
    cc_rows = []
    for page, recs in sorted(per_page.items(), key=lambda kv: -sum(r["spend"] for r in kv[1])):
        spend = sum(r["spend"] for r in recs)
        active = [r for r in recs if r["status"] == "ACTIVE" and r["spend"] > 0]
        konz = len({r["ach"] for r in active if r["ach"]})
        top = max((r["spend"] for r in recs), default=0.0)
        avg_age = int(round(sum(r["age"] * r["spend"] for r in recs) / spend)) if spend else 0
        is_cat = page in ("DPA / Catalog", "IG-Post (unzugeordnet)")
        info = lp_index.get(page, {})
        purch = sum(r["purchases"] for r in recs)
        prev = sum(r["rev"] for r in recs)
        cc_rows.append([page, "Kategorie" if is_cat else info.get("typ", typ(page)),
                        info.get("sig", ""), info.get("sessions", ""),
                        info.get("roas") if info.get("roas") is not None else "",
                        info.get("rpv_all") if info.get("rpv_all") is not None else "",
                        len(active), konz, spend, purch,
                        prev / spend if spend else "", top / spend if spend else "",
                        avg_age,
                        coverage_signal(info.get("sig", ""), len(active), konz, spend,
                                        top / spend if spend else 0, avg_age, is_cat)])

    zero_session_rev = sum(v for k, v in tw_rev.items() if k not in live_pages)
    notes = {
        "tw_null_revenue": tw_null,
        "tw_revenue_on_zero_session_pages": zero_session_rev,
        "unallocated_campaign_spend": unallocated_spend,
        "mapping_by_spend": dict(mapping_stats),
        "small_ads_count": len(small),
        "small_ads_spend": sum(ads[i]["spend"] for i in small),
        "revenue_all_asof": revenue_all_asof,
        "variants_merged": len(variants),
    }
    return lp_rows, cc_rows, cr_rows, notes


# ------------------------------------------------------------- sheet output

def _fmt(v, kind):
    if v == "" or v is None:
        return ""
    if kind == "money":
        return round(float(v), 2)
    if kind == "ratio":
        return round(float(v), 2)
    if kind == "pct":
        return round(float(v), 4)
    if kind == "int":
        return int(round(float(v)))
    return v


LP_KINDS = ["t", "t", "pct", "int", "int", "money", "ratio", "pct", "pct",
            "money", "money", "ratio", "ratio", "ratio", "t"]
CC_KINDS = ["t", "t", "t", "int", "ratio", "ratio", "int", "int", "money",
            "int", "ratio", "pct", "int", "t"]
CR_KINDS = ["t", "t", "t", "t", "t", "int", "money", "pct", "ratio", "pct",
            "pct", "int", "money", "ratio", "t"]


def _sheet(title, header, rows, kinds, total_label, sum_cols, ratio_totals, notes_lines):
    out = [[f"NoroSync {title}"], header]
    for r in rows:
        out.append([_fmt(v, k) for v, k in zip(r, kinds)])
    tot = [""] * len(header)
    tot[0] = total_label
    for c in sum_cols:
        tot[c] = _fmt(sum(float(r[c]) for r in rows if r[c] not in ("", None)), kinds[c])
    for c, (num, den) in ratio_totals.items():
        n = sum(float(r[num]) for r in rows if r[num] not in ("", None))
        d = sum(float(r[den]) for r in rows if r[den] not in ("", None))
        tot[c] = round(n / d, 4 if kinds[c] == "pct" else 2) if d else ""
    out.append(tot)
    out.append([])
    for line in notes_lines:
        out.append([line])
    width = len(header)
    return [list(r) + [""] * (width - len(r)) for r in out]


def build_sheets(as_of=date(2026, 7, 28), generated="", revenue_all=None,
                 revenue_all_asof=None):
    lp, cc, cr, n = build_tables(as_of, revenue_all, revenue_all_asof)

    m = n["mapping_by_spend"]
    lp_notes = [
        f"NOTE: {n['tw_null_revenue']:,.2f} of Triple Whale revenue has no landing page "
        f"recorded and is excluded from the rows above.",
        f"NOTE: {n['tw_revenue_on_zero_session_pages']:,.2f} of Triple Whale revenue "
        f"landed on pages with no Meta sessions, which are not eligible for this table.",
        f"NOTE: {n['variants_merged']} product variant pages were merged into their base "
        f"product (rows marked {MERGED.strip()}); merges are weighted, ratios recomputed from sums.",
        "NOTE: 'Revenue all' and 'RPV all' come from the monthly order crawl. "
        + (f"Last refreshed {revenue_all_asof}." if revenue_all_asof
           else "Not yet populated in this run."),
    ]
    cc_notes = [
        "NOTE: ad-to-landing-page mapping by spend — "
        + " · ".join(f"{k} {v:,.0f}" for k, v in sorted(m.items(), key=lambda kv: -kv[1])),
        "NOTE: DPA/catalog ads are always their own category, even when their link "
        "resolves to a product page (decided 29.07.2026).",
        "NOTE: 'Active Ads' means effective_status ACTIVE only. ADSET_PAUSED and "
        "CAMPAIGN_PAUSED ads are not running and are excluded.",
        "NOTE: 'Konzepte' counts distinct concept codes among ACTIVE ads, per spec.",
    ]
    cr_notes = [
        f"NOTE: {n['small_ads_count']} ads with spend below 50 are omitted; "
        f"they total {n['small_ads_spend']:,.2f} in spend.",
    ]

    lp_sheet = _sheet("LandingPages — generated " + generated, LP_HEADER, lp, LP_KINDS,
                      "TOTAL", [3, 4, 5, 9], {2: (3, 3), 7: (3, 3), 13: (9, 5)}, lp_notes)
    # TOTAL ratios that must be weighted, computed from the underlying sums
    tot = lp_sheet[2 + len(lp)]
    s_ses = sum(float(r[3]) for r in lp)
    s_all = sum(float(r[4]) for r in lp if r[4] != "")
    s_spend = sum(float(r[5]) for r in lp)
    s_rev = sum(float(r[9]) for r in lp)
    tot[2] = 1.0
    tot[6] = round(s_spend / s_ses, 2) if s_ses else ""
    tot[7] = ""
    tot[8] = ""
    tot[11] = round(s_rev / s_ses, 2) if s_ses else ""
    tot[12] = ""
    tot[13] = round(s_rev / s_spend, 2) if s_spend else ""

    cc_sheet = _sheet("CreativeCoverage — generated " + generated, CC_HEADER, cc,
                      CC_KINDS, "TOTAL", [6, 7, 8, 9], {}, cc_notes)
    ct = cc_sheet[2 + len(cc)]
    cs = sum(float(r[8]) for r in cc)
    ct[7] = ""   # concepts do not sum across pages; the same code can serve several
    ct[10] = round(sum(float(r[10]) * float(r[8]) for r in cc if r[10] != "") / cs, 2) if cs else ""

    cr_sheet = _sheet("Creatives — generated " + generated, CR_HEADER, cr, CR_KINDS,
                      "TOTAL", [6, 11, 12], {}, cr_notes)
    rt = cr_sheet[2 + len(cr)]
    tspend = sum(float(r[6]) for r in cr)
    trev = sum(float(r[12]) for r in cr)
    rt[13] = round(trev / tspend, 2) if tspend else ""

    return lp_sheet, cc_sheet, cr_sheet, n

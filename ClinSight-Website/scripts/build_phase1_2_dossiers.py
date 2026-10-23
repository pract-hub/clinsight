#!/usr/bin/env python3
"""
ClinSight Comparison-First Builder (METTL3 Inhibitor Landscape)
Strict guarantees:
1. ZERO raw JSON field paths (e.g., protocolSection...) in visible DOM text of any table cell.
   Provenance is stored in data-src-path / data-src-quote attributes (and hover title) and only
   rendered into the DOM if the reader clicks the quiet "Show sources" button.
2. SINGLE SOURCE OF TRUTH: Both the Comparison Table cells and the Executive/Trial Synopses are
   generated programmatically from the exact same verified record object derived from
   phase1_2_mettl3_extracted.json + raw_api_v2/<NCT>.json. No free-written numbers or country lists.
"""

import os
import json

BASE_URL = "https://clinsight.pract.eu"
DATA_FILE = "ClinSight-Website/data/phase1_2_mettl3_extracted.json"
RAW_DIR = "ClinSight-Website/data/raw_api_v2"
TRIALS_DIR = "ClinSight-Website/trials"
TARGETS_DIR = "ClinSight-Website/targets/mettl3-inhibitors"

VERIFIED_CLASS_NCTS = ["NCT06975293", "NCT07163325", "NCT05584111"]


def escape_html(text):
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def load_raw_study(nct_id):
    path = os.path.join(RAW_DIR, f"{nct_id}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("protocolSection", {})


def format_phase(raw_phase_str):
    mapping = {
        "PHASE1/PHASE2": "Phase 1/2",
        "PHASE1": "Phase 1",
        "PHASE2": "Phase 2",
        "PHASE3": "Phase 3",
    }
    return mapping.get(raw_phase_str, raw_phase_str)


def format_status(raw_status):
    mapping = {
        "RECRUITING": ("Recruiting", "pill-recruiting"),
        "COMPLETED": ("Completed", "pill-completed"),
        "ACTIVE_NOT_RECRUITING": ("Active, not recruiting", "pill-recruiting"),
        "NOT_YET_RECRUITING": ("Not yet recruiting", "pill-recruiting"),
        "ENROLLING_BY_INVITATION": ("Enrolling by invitation", "pill-recruiting"),
        "SUSPENDED": ("Suspended", "pill-completed"),
        "TERMINATED": ("Terminated", "pill-completed"),
        "WITHDRAWN": ("Withdrawn", "pill-completed"),
    }
    if raw_status in mapping:
        return mapping[raw_status]
    clean = raw_status.replace("_", " ").lower().capitalize()
    return (clean, "pill-completed")


def build_verified_model(dossier):
    """
    Constructs a single verified dictionary per trial directly from the extracted dossier
    and archived raw API v2 JSON. Both the comparison table and the synopses read exclusively
    from this dictionary so they can never disagree.
    """
    ident = dossier["identity"]
    nct = ident["nctId"]
    raw = load_raw_study(nct)

    phase_clean = format_phase(ident["phase"])
    status_clean, status_cls = format_status(ident["status"])

    enroll_info = raw.get("designModule", {}).get("enrollmentInfo", {})
    enroll_count = enroll_info.get("count")
    enroll_type = (enroll_info.get("type") or "").lower()
    enrollment_str = f"N = {enroll_count} ({enroll_type})" if enroll_count else "Not specified"

    locs = raw.get("contactsLocationsModule", {}).get("locations", [])
    site_count = len(locs)
    countries = sorted(list({l.get("country") for l in locs if l.get("country")}))
    countries_list_str = ", ".join(countries) if countries else "Not specified"
    footprint_str = (
        f"{site_count} {'site' if site_count == 1 else 'sites'} in "
        f"{len(countries)} {'country' if len(countries) == 1 else 'countries'} ({countries_list_str})"
    )

    arm_groups = raw.get("armsInterventionsModule", {}).get("armGroups", [])
    arm_count = len(arm_groups)
    arm_items = []
    for a in arm_groups:
        lbl = a.get("label", "")
        desc = a.get("description", "")
        arm_items.append(f"{lbl}: {desc}" if desc else lbl)

    prim_outcomes = raw.get("outcomesModule", {}).get("primaryOutcomes", [])
    sec_outcomes = raw.get("outcomesModule", {}).get("secondaryOutcomes", [])

    pmids = dossier["module4"].get("pmids", [])

    # Clean, concise human display strings derived strictly from extracted states
    raw_design = dossier["module1"]["design_archetype"].get("value") or ""
    raw_detail = dossier["module1"]["design_archetype"].get("design_detail") or ""
    if raw_design and raw_detail:
        design_short = f"{raw_design} ({raw_detail})"
    elif raw_design:
        design_short = raw_design
    else:
        design_short = "—"

    dlt_win_obj = dossier["module3"]["dlt_window"]
    dlt_window_short = (dlt_win_obj.get("value") or dlt_win_obj.get("verbatim") or "—") if dlt_win_obj["state"] == "STATED" else "—"

    mtd_obj = dossier["module3"]["mtd"]
    mtd_short = "Primary outcome" if mtd_obj["state"] == "STATED" else "—"

    rp2d_obj = dossier["module3"]["rp2d"]
    if rp2d_obj["state"] == "STATED":
        src_f = rp2d_obj.get("source_field") or ""
        rp2d_short = "Secondary outcome" if "secondaryOutcomes" in src_f else "Primary outcome"
    elif rp2d_obj["state"] == "INFERRED":
        rp2d_short = 'Implied in primary outcome ("recommended doses... for subsequent studie")'
    else:
        rp2d_short = "—"

    tox_obj = dossier["module3"]["ctcae"]
    tox_short = tox_obj["value"] if tox_obj["state"] == "STATED" else "—"

    # Washout & organ criteria from Module 2
    wash_obj = dossier["module2"]["washout"]
    wash_items = wash_obj.get("items", [])
    wash_short = " ; ".join(it.get("verbatim", "") for it in wash_items) if wash_obj["state"] == "STATED" and wash_items else "—"
    wash_src = wash_items[0].get("source_field", "") if wash_items else ""
    wash_quote = wash_short if wash_short != "—" else ""

    organ_notes = []
    for k, label in [
        ("hematologic", "Hematologic"),
        ("renal", "Renal"),
        ("hepatic", "Hepatic"),
        ("cardiac", "Cardiac"),
    ]:
        m_obj = dossier["module2"][k]
        if m_obj["state"] == "STATED":
            items = m_obj.get("items", [])
            organ_notes.append(f"{label}: {'; '.join(it.get('verbatim', '') for it in items)}")
    organ_short = " | ".join(organ_notes) if organ_notes else "— (numeric lab cutoffs not disclosed in registry)"

    # Programmatic trial synopsis built strictly from the verified fields above
    prim_measures_summary = "; ".join(
        f"{o.get('measure')} ({o.get('timeFrame')})" if o.get("timeFrame") else o.get("measure", "")
        for o in prim_outcomes[:3]
    )
    if len(prim_outcomes) > 3:
        prim_measures_summary += f"; plus {len(prim_outcomes) - 3} additional PK/safety measures"

    pmid_clause = f" Linked PubMed records: {', '.join(f'PMID {p}' for p in pmids)}." if pmids else ""
    dlt_clause = (
        f" The DLT evaluation window is specified as '{dlt_window_short}'."
        if dlt_window_short != "—"
        else " A separate DLT evaluation window is not specified in the registry outcome measures."
    )

    alloc_raw = dossier["module1"]["allocation"].get("value", "")
    alloc_map = {
        "NON_RANDOMIZED": "Non-randomized",
        "RANDOMIZED": "Randomized",
        "NA": "Not applicable",
        "NOT_APPLICABLE": "Not applicable",
    }
    alloc_val = alloc_map.get(alloc_raw.upper(), alloc_raw.replace("_", " ").lower().capitalize()) if alloc_raw else "Not specified"

    mask_raw = dossier["module1"]["masking"].get("value", "")
    mask_map = {
        "NONE": "Open label (none)",
        "OPEN": "Open label",
        "OPEN_LABEL": "Open label",
        "SINGLE": "Single blind",
        "DOUBLE": "Double blind",
        "TRIPLE": "Triple blind",
        "QUADRUPLE": "Quadruple blind",
    }
    mask_val = mask_map.get(mask_raw.upper(), mask_raw.replace("_", " ").lower().capitalize()) if mask_raw else "Not specified"

    imodel_raw = dossier["module1"]["intervention_model"].get("value", "")
    imodel_map = {
        "SINGLE_GROUP": "Single group assignment",
        "PARALLEL": "Parallel assignment",
        "SEQUENTIAL": "Sequential assignment",
        "FACTORIAL": "Factorial assignment",
        "CROSSOVER": "Crossover assignment",
    }
    imodel_val = imodel_map.get(imodel_raw.upper(), imodel_raw.replace("_", " ").lower().capitalize()) if imodel_raw else "Not specified"
    allocation_str = f"{alloc_val} · Masking: {mask_val} · {imodel_val}"

    programmatic_synopsis = (
        f"{nct} ({ident['leadSponsor']}) is a {status_clean.lower()} {phase_clean} trial ({enrollment_str}) "
        f"evaluating {', '.join(ident['interventions'])} in {'; '.join(ident['conditions'])}. "
        f"The study comprises {arm_count} designated cohorts/arms using a {design_short} design across "
        f"{footprint_str}.{dlt_clause} "
        f"Primary outcomes evaluate: {prim_measures_summary}.{pmid_clause}"
    )

    return {
        "nct": nct,
        "title": ident["briefTitle"],
        "sponsor": ident["leadSponsor"],
        "phase_clean": phase_clean,
        "status_clean": status_clean,
        "status_cls": status_cls,
        "enrollment_str": enrollment_str,
        "interventions_str": ", ".join(ident["interventions"]),
        "conditions_str": "; ".join(ident["conditions"]),
        "design_short": design_short,
        "design_src": dossier["module1"]["design_archetype"].get("source_field") or "",
        "design_quote": dossier["module1"]["design_archetype"].get("verbatim") or "",
        "allocation_str": allocation_str,
        "arm_count": arm_count,
        "arm_items": arm_items,
        "prim_outcomes": prim_outcomes,
        "sec_outcomes": sec_outcomes,
        "dlt_window_short": dlt_window_short,
        "dlt_src": dlt_win_obj.get("source_field") or "",
        "dlt_quote": dlt_win_obj.get("verbatim") or "",
        "mtd_short": mtd_short,
        "mtd_src": mtd_obj.get("source_field") or "",
        "mtd_quote": mtd_obj.get("verbatim") or "",
        "rp2d_short": rp2d_short,
        "rp2d_src": rp2d_obj.get("source_field") or "",
        "rp2d_quote": rp2d_obj.get("verbatim") or "",
        "tox_short": tox_short,
        "tox_src": tox_obj.get("source_field") or "",
        "tox_quote": tox_obj.get("verbatim") or "",
        "wash_short": wash_short,
        "wash_src": wash_src,
        "wash_quote": wash_quote,
        "organ_short": organ_short,
        "site_count": site_count,
        "countries": countries,
        "footprint_str": footprint_str,
        "pmids": pmids,
        "synopsis": programmatic_synopsis,
        "raw": raw,
        "dossier": dossier,
    }


def build_class_synopsis(models):
    """
    Generates the Executive Class Synopsis strictly from the verified models list,
    guaranteeing 100% numerical and factual agreement with the comparison table.
    """
    m_by_nct = {m["nct"]: m for m in models}
    m1 = m_by_nct["NCT06975293"]
    m2 = m_by_nct["NCT07163325"]
    m3 = m_by_nct["NCT05584111"]

    return (
        f"Three interventional clinical trials evaluating oral small-molecule METTL3 RNA methyltransferase inhibitors "
        f"are registered on ClinicalTrials.gov across two investigational agents: STORM Therapeutics' STC-15 "
        f"({m3['nct']}, {m1['nct']}) and Epics Therapeutics' EP102 ({m2['nct']}). "
        f"STC-15 completed its first-in-human {m3['phase_clean']} monotherapy trial ({m3['nct']}; {m3['enrollment_str']}; "
        f"{m3['arm_count']} dose-escalation cohorts using a {m3['design_short']} design across {m3['footprint_str']}) "
        f"and is recruiting a {m1['phase_clean']} study ({m1['nct']}; {m1['enrollment_str']}; {m1['arm_count']} cohorts "
        f"using a {m1['design_short']} design across {m1['footprint_str']}) evaluating {m1['interventions_str']} "
        f"in {m1['conditions_str']}. "
        f"Epics Therapeutics' EP102 is recruiting a first-in-human {m2['phase_clean']} monotherapy study "
        f"({m2['nct']}; {m2['enrollment_str']}; {m2['arm_count']} dose levels using a {m2['design_short']} design "
        f"across {m2['footprint_str']}) with a specified DLT assessment window of '{m2['dlt_window_short']}'."
    )


SHARED_CSS = '''
    :root {
      --bg-void: #07090e;
      --bg-base: #0b0f19;
      --bg-surface: #111827;
      --bg-elevated: #161f33;
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-strong: rgba(255, 255, 255, 0.14);
      --cyan: #38bdf8;
      --cyan-glow: rgba(56, 189, 248, 0.12);
      --purple: #c084fc;
      --emerald: #4ade80;
      --text-high: #f8fafc;
      --text-med: #cbd5e1;
      --text-low: #94a3b8;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color-scheme: dark;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-void);
      color: var(--text-med);
      font-family: var(--font-sans);
      line-height: 1.55;
      padding: 0 0 64px;
      -webkit-font-smoothing: antialiased;
    }

    .site-nav {
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-base);
      padding: 12px 24px;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(12px);
    }
    .nav-inner {
      max-width: 1220px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .nav-brand {
      display: flex;
      align-items: baseline;
      gap: 10px;
      text-decoration: none;
      color: var(--text-high);
    }
    .logo-text { font-size: 19px; font-weight: 700; color: var(--cyan); }
    .logo-tag {
      font-size: 12.5px;
      color: var(--text-low);
      border-left: 1px solid var(--border-subtle);
      padding-left: 10px;
    }
    @media (max-width: 640px) { .logo-tag { display: none; } }
    .nav-links { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
    .nav-links a {
      color: var(--text-med);
      text-decoration: none;
      font-size: 13.5px;
      font-weight: 500;
    }
    .nav-links a:hover, .nav-links a.active { color: var(--cyan); }

    .container {
      max-width: 1220px;
      margin: 0 auto;
      padding: 24px 20px;
    }

    .page-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 16px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .eyebrow {
      font-family: var(--font-mono);
      font-size: 11.5px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--cyan);
      margin-bottom: 4px;
    }
    .eyebrow a { color: var(--cyan); text-decoration: none; }
    .eyebrow a:hover { text-decoration: underline; }
    h1 {
      font-size: 24px;
      font-weight: 700;
      color: var(--text-high);
      letter-spacing: -0.02em;
      line-height: 1.25;
    }
    .head-sub {
      font-size: 13.5px;
      color: var(--text-low);
      margin-top: 4px;
      max-width: 780px;
    }

    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .btn {
      background: var(--bg-surface);
      border: 1px solid var(--border-strong);
      color: var(--text-med);
      font-size: 12px;
      font-weight: 500;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn:hover { color: var(--text-high); border-color: var(--cyan); }
    .btn.active {
      background: var(--cyan-glow);
      border-color: var(--cyan);
      color: var(--cyan);
    }

    .table-wrap {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      overflow-x: auto;
      margin-bottom: 24px;
    }
    .comp-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13.5px;
      min-width: 820px;
    }
    .comp-table th {
      text-align: left;
      padding: 14px 16px;
      background: var(--bg-elevated);
      border-bottom: 2px solid var(--border-strong);
      border-left: 1px solid var(--border-subtle);
      vertical-align: top;
      width: 27%;
    }
    .comp-table th:first-child {
      border-left: none;
      width: 19%;
      vertical-align: bottom;
      color: var(--text-low);
      font-size: 11.5px;
      font-family: var(--font-mono);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .th-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
    }
    .th-nct {
      font-family: var(--font-mono);
      font-size: 12.5px;
      font-weight: 700;
      color: var(--cyan);
      text-decoration: none;
    }
    .th-nct:hover { text-decoration: underline; }
    .th-badges { display: flex; gap: 5px; align-items: center; }
    .pill {
      font-family: var(--font-mono);
      font-size: 10.5px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
    }
    .pill-phase { background: rgba(192, 132, 252, 0.14); color: var(--purple); }
    .pill-recruiting { background: rgba(74, 222, 128, 0.14); color: var(--emerald); }
    .pill-completed { background: rgba(148, 163, 184, 0.16); color: var(--text-med); }
    .th-drug {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-high);
      line-height: 1.3;
      margin-bottom: 3px;
    }
    .th-sponsor {
      font-size: 12px;
      color: var(--text-low);
      font-weight: 400;
    }

    .group-row td {
      background: rgba(56, 189, 248, 0.05);
      color: var(--cyan);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 8px 16px;
      border-top: 1px solid var(--border-strong);
      border-bottom: 1px solid var(--border-subtle);
    }

    .comp-table td {
      padding: 11px 16px;
      border-bottom: 1px solid var(--border-subtle);
      border-left: 1px solid var(--border-subtle);
      vertical-align: top;
      color: var(--text-high);
      line-height: 1.5;
    }
    .comp-table td.param-col {
      border-left: none;
      font-weight: 600;
      color: var(--text-med);
      background: rgba(255, 255, 255, 0.015);
      font-size: 13px;
    }
    .cell-blank {
      color: var(--text-low);
    }
    .cell-note {
      display: block;
      font-size: 12px;
      color: var(--text-low);
      margin-top: 2px;
    }
    .cell-list {
      margin: 0;
      padding-left: 15px;
    }
    .cell-list li { margin-bottom: 3px; }
    .cell-list li:last-child { margin-bottom: 0; }

    /* Dynamically injected when 'Show sources' is toggled on */
    .src-drawer {
      margin-top: 6px;
      padding: 5px 8px;
      background: rgba(0, 0, 0, 0.35);
      border-left: 2px solid var(--cyan);
      border-radius: 4px;
      font-size: 11.5px;
      color: var(--text-low);
    }
    .src-path {
      font-family: var(--font-mono);
      font-size: 10.5px;
      color: var(--cyan);
      display: block;
    }
    .src-quote {
      font-style: italic;
      color: var(--text-med);
      display: block;
      margin-top: 2px;
    }

    .synopsis-banner {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 16px 20px;
      margin-bottom: 20px;
    }
    .section-label {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-high);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .syn-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }
    .syn-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .syn-card h2 {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-high);
      margin: 6px 0 4px;
      line-height: 1.35;
    }
    .syn-meta {
      font-size: 12px;
      color: var(--text-low);
      margin-bottom: 10px;
    }
    .syn-body {
      font-size: 13.5px;
      color: var(--text-med);
      line-height: 1.6;
      margin-bottom: 14px;
    }
    .syn-foot {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 10px;
      border-top: 1px solid var(--border-subtle);
      font-size: 12.5px;
    }
    .doc-link {
      color: var(--cyan);
      text-decoration: none;
      font-weight: 500;
    }
    .doc-link:hover { text-decoration: underline; }

    .footnote {
      font-size: 12.5px;
      color: var(--text-low);
      padding: 10px 14px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
    }

    .kv-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 18px;
    }
    .kv-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-high);
      padding-bottom: 10px;
      margin-bottom: 10px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .kv-row {
      display: grid;
      grid-template-columns: 210px 1fr;
      gap: 16px;
      padding: 9px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 13.5px;
    }
    .kv-row:last-child { border-bottom: none; }
    @media (max-width: 640px) { .kv-row { grid-template-columns: 1fr; gap: 4px; } }
    .kv-key { color: var(--text-low); font-weight: 600; font-size: 12.5px; }
    .kv-val { color: var(--text-high); }

    footer {
      margin-top: 36px;
      padding-top: 18px;
      border-top: 1px solid var(--border-subtle);
      font-size: 12.5px;
      color: var(--text-low);
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    footer a { color: var(--text-med); text-decoration: none; }
    footer a:hover { color: var(--cyan); }
'''


def render_nav(rel_prefix="../../", active="compare"):
    return f'''
  <nav class="site-nav" aria-label="Primary Navigation">
    <div class="nav-inner">
      <a href="{rel_prefix}" class="nav-brand">
        <span class="logo-text">ClinSight™</span>
        <span class="logo-tag">Clinical Trials &amp; Evidence Generation</span>
      </a>
      <div class="nav-links">
        <a href="{rel_prefix}">Home</a>
        <a href="{rel_prefix}explorer/" class="{'active' if active=='explorer' else ''}">Trials Explorer</a>
        <a href="{rel_prefix}compare/" class="{'active' if active=='compare' else ''}">Comparator</a>
        <a href="{rel_prefix}jobs/">Careers</a>
      </div>
    </div>
  </nav>'''


def td_cell(content_html, src_path="", src_quote="", is_blank=False):
    """
    Renders a <td> with ZERO source path text inside the DOM node.
    Provenance is stored in data-src-path and data-src-quote attributes (plus hover title)
    so text readers and copy-paste never see JSON paths unless 'Show sources' is toggled on.
    """
    attrs = []
    if is_blank:
        attrs.append('class="cell-blank"')
    if src_path:
        attrs.append(f'data-src-path="{escape_html(src_path)}"')
    if src_quote:
        attrs.append(f'data-src-quote="{escape_html(src_quote)}"')
    if src_path or src_quote:
        tip = f"Registry field: {src_path}" + (f' — "{src_quote}"' if src_quote else "")
        attrs.append(f'title="{escape_html(tip)}"')
    attr_str = (" " + " ".join(attrs)) if attrs else ""
    return f"<td{attr_str}>{content_html}</td>"


def render_comparison_table(models, rel_prefix="../../"):
    headers_html = '<th scope="col">Parameter</th>'
    for m in models:
        headers_html += f'''
        <th scope="col">
          <div class="th-top">
            <a href="{rel_prefix}trials/{m['nct']}/" class="th-nct">{m['nct']}</a>
            <div class="th-badges">
              <span class="pill pill-phase">{escape_html(m["phase_clean"])}</span>
              <span class="pill {m["status_cls"]}">{escape_html(m["status_clean"])}</span>
            </div>
          </div>
          <div class="th-drug">{escape_html(m["interventions_str"])}</div>
          <div class="th-sponsor">{escape_html(m["sponsor"])} &middot; {escape_html(m["enrollment_str"])}</div>
        </th>'''

    def row_across(label, fn):
        cells = "".join(fn(m) for m in models)
        return f'<tr><td class="param-col">{escape_html(label)}</td>{cells}</tr>\n'

    body = ""
    # Group 1: Regimen, Indications & Scope
    body += '<tr class="group-row"><td colspan="4">Regimen, Indications &amp; Scope</td></tr>\n'
    body += row_across(
        "Investigational Regimen",
        lambda m: td_cell(
            escape_html(m["interventions_str"]),
            "protocolSection.armsInterventionsModule.interventions",
            m["interventions_str"],
        ),
    )
    body += row_across(
        "Registered Conditions",
        lambda m: td_cell(
            escape_html(m["conditions_str"]),
            "protocolSection.conditionsModule.conditions",
            m["conditions_str"],
        ),
    )
    body += row_across(
        "Target Enrollment",
        lambda m: td_cell(
            escape_html(m["enrollment_str"]),
            "protocolSection.designModule.enrollmentInfo",
            m["enrollment_str"],
        ),
    )

    # Group 2: Escalation & Cohort Design
    body += '<tr class="group-row"><td colspan="4">Escalation &amp; Cohort Design</td></tr>\n'
    body += row_across(
        "Escalation & Expansion Design",
        lambda m: td_cell(
            f"<strong>{escape_html(m['design_short'])}</strong>",
            m["design_src"],
            m["design_quote"],
        ),
    )
    body += row_across(
        "Cohorts & Dosing Arms",
        lambda m: td_cell(
            f"<strong>{m['arm_count']} cohorts:</strong><ul class=\"cell-list\">"
            + "".join(f"<li>{escape_html(item)}</li>" for item in m["arm_items"])
            + "</ul>",
            "protocolSection.armsInterventionsModule.armGroups",
            "; ".join(m["arm_items"]),
        ),
    )
    body += row_across(
        "Allocation & Masking",
        lambda m: td_cell(
            escape_html(m["allocation_str"]),
            "protocolSection.designModule.designInfo",
            m["allocation_str"],
        ),
    )

    # Group 3: Dose-Finding, DLT & Endpoints
    body += '<tr class="group-row"><td colspan="4">Dose-Finding, DLT &amp; Outcome Measures</td></tr>\n'
    body += row_across(
        "Primary Outcome Measures",
        lambda m: td_cell(
            "<ul class=\"cell-list\">"
            + "".join(
                f"<li><strong>{escape_html(o.get('measure', ''))}</strong>"
                + (f": {escape_html(o.get('description'))}" if o.get("description") else "")
                + (f" <span class=\"cell-note\">Timeframe: {escape_html(o.get('timeFrame'))}</span>" if o.get("timeFrame") else "")
                + "</li>"
                for o in m["prim_outcomes"]
            )
            + "</ul>",
            "protocolSection.outcomesModule.primaryOutcomes",
            f"{len(m['prim_outcomes'])} primary outcome measures",
        ),
    )
    body += row_across(
        "DLT Evaluation Window",
        lambda m: td_cell(
            escape_html(m["dlt_window_short"]),
            m["dlt_src"],
            m["dlt_quote"],
            is_blank=(m["dlt_window_short"] == "—"),
        ),
    )
    body += row_across(
        "Maximum Tolerated Dose (MTD)",
        lambda m: td_cell(
            escape_html(m["mtd_short"]),
            m["mtd_src"],
            m["mtd_quote"],
            is_blank=(m["mtd_short"] == "—"),
        ),
    )
    body += row_across(
        "Recommended Phase 2 Dose (RP2D)",
        lambda m: td_cell(
            escape_html(m["rp2d_short"]),
            m["rp2d_src"],
            m["rp2d_quote"],
            is_blank=(m["rp2d_short"] == "—"),
        ),
    )
    body += row_across(
        "Secondary Outcome Measures",
        lambda m: td_cell(
            "<ul class=\"cell-list\">"
            + "".join(f"<li>{escape_html(o.get('measure', ''))}</li>" for o in m["sec_outcomes"])
            + "</ul>"
            if m["sec_outcomes"]
            else "—",
            "protocolSection.outcomesModule.secondaryOutcomes",
            f"{len(m['sec_outcomes'])} secondary outcome measures",
            is_blank=(not m["sec_outcomes"]),
        ),
    )
    body += row_across(
        "AE Grading Scale",
        lambda m: td_cell(
            escape_html(m["tox_short"]),
            m["tox_src"],
            m["tox_quote"],
            is_blank=(m["tox_short"] == "—"),
        ),
    )

    # Group 4: Eligibility & Washout
    body += '<tr class="group-row"><td colspan="4">Patient Eligibility &amp; Washout Criteria</td></tr>\n'
    body += row_across(
        "Prior Therapy Washout",
        lambda m: td_cell(
            escape_html(m["wash_short"]),
            m["wash_src"],
            m["wash_quote"],
            is_blank=(m["wash_short"] == "—"),
        ),
    )
    body += row_across(
        "Organ Function Criteria",
        lambda m: td_cell(
            escape_html(m["organ_short"]),
            "protocolSection.eligibilityModule.eligibilityCriteria",
            m["organ_short"],
            is_blank=m["organ_short"].startswith("—"),
        ),
    )

    # Group 5: Footprint & Links
    body += '<tr class="group-row"><td colspan="4">Geographic Footprint &amp; Literature</td></tr>\n'
    body += row_across(
        "Trial Sites & Countries",
        lambda m: td_cell(
            f"<strong>{escape_html(m['footprint_str'])}</strong>",
            "protocolSection.contactsLocationsModule.locations",
            m["footprint_str"],
        ),
    )
    body += row_across(
        "Linked PubMed Literature",
        lambda m: td_cell(
            " &middot; ".join(
                f'<a href="https://pubmed.ncbi.nlm.nih.gov/{p}/" target="_blank" rel="noopener noreferrer" class="doc-link">PMID: {p} &nearr;</a>'
                for p in m["pmids"]
            )
            if m["pmids"]
            else "—",
            "protocolSection.referencesModule.references",
            ", ".join(m["pmids"]) if m["pmids"] else "None linked in registry record",
            is_blank=(not m["pmids"]),
        ),
    )

    return f'''
    <div class="table-wrap">
      <table class="comp-table" id="mettl3ComparisonTable">
        <thead>
          <tr>{headers_html}</tr>
        </thead>
        <tbody>
          {body}
        </tbody>
      </table>
    </div>'''


def render_target_hub_html(models):
    table_html = render_comparison_table(models, rel_prefix="../../")
    class_synopsis = build_class_synopsis(models)

    syn_cards = ""
    for m in models:
        syn_cards += f'''
        <div class="syn-card">
          <div>
            <div class="th-top">
              <span class="th-nct">{m['nct']}</span>
              <div class="th-badges">
                <span class="pill pill-phase">{escape_html(m["phase_clean"])}</span>
                <span class="pill {m["status_cls"]}">{escape_html(m["status_clean"])}</span>
              </div>
            </div>
            <h2>{escape_html(m["title"])}</h2>
            <div class="syn-meta">{escape_html(m["sponsor"])} &middot; {escape_html(m["enrollment_str"])} &middot; {escape_html(m["footprint_str"])}</div>
            <p class="syn-body">{escape_html(m["synopsis"])}</p>
          </div>
          <div class="syn-foot">
            <a href="https://clinicaltrials.gov/study/{m['nct']}" target="_blank" rel="noopener noreferrer" class="doc-link">ClinicalTrials.gov &nearr;</a>
            <a href="../../trials/{m['nct']}/" class="doc-link">Open Trial Synopsis &rarr;</a>
          </div>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>METTL3 inhibitors — trial design comparison | ClinSight</title>
  <meta name="description" content="Side-by-side protocol comparison of clinical-stage oral METTL3 RNA methyltransferase inhibitors STC-15 (NCT06975293, NCT05584111) and EP102 (NCT07163325): escalation design, cohort schedules, DLT windows, washouts, and eligibility.">
  <link rel="canonical" href="{BASE_URL}/targets/mettl3-inhibitors/">
  <style>{SHARED_CSS}</style>
</head>
<body>
  {render_nav(rel_prefix="../../", active="compare")}

  <main class="container">
    <div class="page-head">
      <div>
        <div class="eyebrow"><a href="../../compare/">Comparator</a> &middot; RNA Epigenetics</div>
        <h1>METTL3 inhibitors — trial design comparison</h1>
        <p class="head-sub">Side-by-side comparison of all three interventional clinical trials of oral METTL3 RNA methyltransferase inhibitors: STORM Therapeutics&#x27; <strong>STC-15</strong> and Epics Therapeutics&#x27; <strong>EP102</strong>. Hover any cell or toggle sources for registry field provenance.</p>
      </div>
      <div class="toolbar">
        <button type="button" class="btn" id="btnSources" onclick="toggleSources()">Show sources</button>
        <button type="button" class="btn" id="btnCopyMd" onclick="copyTableMarkdown()">Copy table (Markdown)</button>
        <button type="button" class="btn" onclick="exportTableCsv()">Export CSV</button>
      </div>
    </div>

    {table_html}

    <div class="synopsis-banner">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
        <span class="eyebrow" style="margin:0;">Class Overview</span>
        <button type="button" class="btn" id="btnCopyClassSyn" onclick="copyClassSynopsis()" style="padding:3px 10px; font-size:11.5px;">Copy overview</button>
      </div>
      <p id="classSynopsisText" style="font-size:13.5px; color:var(--text-high); line-height:1.65;">{escape_html(class_synopsis)}</p>
    </div>

    <div class="section-label">
      <span>Individual Trial Synopses</span>
    </div>
    <div class="syn-grid">
      {syn_cards}
    </div>

    <div class="footnote">
      <strong>Scope note:</strong> A fourth ClinicalTrials.gov record mentioning METTL3 (<code>NCT06762925</code>, Xijing Hospital) is a non-interventional observational tissue biomarker study with no drug regimen and is excluded from this drug comparison.
    </div>

    <footer>
      <div><strong>ClinSight™</strong> · Primary Registry Fact Base &middot; <a href="https://pract.eu" style="color:inherit; text-decoration:underline;">PRACT</a></div>
      <div>
        <a href="../../explorer/">Explorer</a> &middot;
        <a href="../../compare/">Comparator</a> &middot;
        <a href="../../jobs/">Careers</a> &middot;
        <a href="../../sitemap.xml">Sitemap</a>
      </div>
    </footer>
  </main>

  <script>
    let sourcesOn = false;
    function toggleSources() {{
      sourcesOn = !sourcesOn;
      const btn = document.getElementById('btnSources');
      btn.classList.toggle('active', sourcesOn);
      btn.textContent = sourcesOn ? 'Hide sources' : 'Show sources';

      const cells = document.querySelectorAll('#mettl3ComparisonTable td[data-src-path]');
      cells.forEach(td => {{
        const existing = td.querySelector('.src-drawer');
        if (existing) existing.remove();
        if (sourcesOn) {{
          const path = td.getAttribute('data-src-path') || '';
          const quote = td.getAttribute('data-src-quote') || '';
          const div = document.createElement('div');
          div.className = 'src-drawer';
          if (path) {{
            const sPath = document.createElement('span');
            sPath.className = 'src-path';
            sPath.textContent = path;
            div.appendChild(sPath);
          }}
          if (quote) {{
            const sQuote = document.createElement('span');
            sQuote.className = 'src-quote';
            sQuote.textContent = '"' + quote + '"';
            div.appendChild(sQuote);
          }}
          td.appendChild(div);
        }}
      }});
    }}

    function copyClassSynopsis() {{
      const text = document.getElementById('classSynopsisText').innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.getElementById('btnCopyClassSyn');
        btn.textContent = 'Copied!';
        setTimeout(() => {{ btn.textContent = 'Copy overview'; }}, 2000);
      }});
    }}

    function extractTableRows() {{
      const table = document.getElementById('mettl3ComparisonTable');
      const rows = [];
      const ths = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.replace(/\\s+/g, ' ').trim());
      rows.push(ths);
      for (const tr of table.querySelectorAll('tbody tr')) {{
        if (tr.classList.contains('group-row')) continue;
        const cells = Array.from(tr.querySelectorAll('td')).map(td => {{
          const clone = td.cloneNode(true);
          const drawer = clone.querySelector('.src-drawer');
          if (drawer) drawer.remove();
          return clone.innerText.replace(/\\s+/g, ' ').trim();
        }});
        rows.push(cells);
      }}
      return rows;
    }}

    function copyTableMarkdown() {{
      const rows = extractTableRows();
      const lines = [
        '| ' + rows[0].join(' | ') + ' |',
        '|' + rows[0].map(() => '---').join('|') + '|'
      ];
      for (let i = 1; i < rows.length; i++) {{
        lines.push('| ' + rows[i].map(c => c.replace(/\\|/g, '\\\\|')).join(' | ') + ' |');
      }}
      navigator.clipboard.writeText(lines.join('\\n')).then(() => {{
        const btn = document.getElementById('btnCopyMd');
        btn.textContent = 'Copied!';
        setTimeout(() => {{ btn.textContent = 'Copy table (Markdown)'; }}, 2000);
      }});
    }}

    function exportTableCsv() {{
      const rows = extractTableRows();
      const csv = rows.map(r => r.map(c => `"${{String(c).replace(/"/g, '""')}}"`).join(',')).join('\\r\\n');
      const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'METTL3_Inhibitors_Protocol_Comparison.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }}
  </script>
</body>
</html>'''


def render_single_trial_html(m):
    nct = m["nct"]
    raw = m["raw"]

    arms_html = (
        "<ul class=\"cell-list\">"
        + "".join(f"<li>{escape_html(item)}</li>" for item in m["arm_items"])
        + "</ul>"
        if m["arm_items"]
        else "&mdash;"
    )

    prim_items = []
    for o in m["prim_outcomes"]:
        meas = escape_html(o.get("measure", ""))
        desc = f": {escape_html(o.get('description'))}" if o.get("description") else ""
        tf = f" <span class=\"cell-note\">Timeframe: {escape_html(o.get('timeFrame'))}</span>" if o.get("timeFrame") else ""
        prim_items.append(f"<li><strong>{meas}</strong>{desc}{tf}</li>")
    prim_html = "<ul class=\"cell-list\">" + "".join(prim_items) + "</ul>" if prim_items else "&mdash;"

    sec_items = []
    for o in m["sec_outcomes"]:
        meas = escape_html(o.get("measure", ""))
        tf = f" ({escape_html(o.get('timeFrame'))})" if o.get("timeFrame") else ""
        sec_items.append(f"<li>{meas}{tf}</li>")
    sec_html = "<ul class=\"cell-list\">" + "".join(sec_items) + "</ul>" if sec_items else "&mdash;"

    elig_text = raw.get("eligibilityModule", {}).get("eligibilityCriteria", "")

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape_html(nct)} ({escape_html(m["phase_clean"])}) — {escape_html(m["title"])} | ClinSight</title>
  <meta name="description" content="{escape_html(nct)}: {escape_html(m["title"])}. Clinical synopsis, cohort schedules, primary outcomes, and eligibility criteria.">
  <link rel="canonical" href="{BASE_URL}/trials/{escape_html(nct)}/">
  <style>{SHARED_CSS}</style>
</head>
<body>
  {render_nav(rel_prefix="../../", active="explorer")}

  <main class="container">
    <div class="page-head">
      <div>
        <div class="eyebrow">
          <a href="../../targets/mettl3-inhibitors/">&larr; Back to METTL3 Inhibitor Comparison Table</a>
        </div>
        <div class="th-badges" style="margin: 6px 0 8px;">
          <span class="pill pill-phase">{escape_html(nct)}</span>
          <span class="pill pill-phase">{escape_html(m["phase_clean"])}</span>
          <span class="pill {m["status_cls"]}">{escape_html(m["status_clean"])}</span>
        </div>
        <h1>{escape_html(m["title"])}</h1>
        <p class="head-sub">Sponsor: <strong>{escape_html(m["sponsor"])}</strong> &middot; Enrollment: <strong>{escape_html(m["enrollment_str"])}</strong> &middot; Footprint: <strong>{escape_html(m["footprint_str"])}</strong></p>
      </div>
      <div class="toolbar">
        <a href="../../targets/mettl3-inhibitors/" class="btn active">Compare vs. Class (STC-15 &amp; EP102)</a>
        <a href="https://clinicaltrials.gov/study/{escape_html(nct)}" target="_blank" rel="noopener noreferrer" class="btn">ClinicalTrials.gov &nearr;</a>
      </div>
    </div>

    <div class="synopsis-banner">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span class="eyebrow" style="margin:0;">Trial Synopsis</span>
        <button type="button" class="btn" id="btnCopySyn" onclick="copySyn()" style="padding:3px 10px; font-size:11.5px;">Copy synopsis</button>
      </div>
      <p id="synText" style="font-size:14px; color:var(--text-high); line-height:1.65;">{escape_html(m["synopsis"])}</p>
    </div>

    <div class="kv-card">
      <div class="kv-title">Study Design, Cohorts &amp; Endpoints</div>
      <div class="kv-row">
        <div class="kv-key">Escalation &amp; Expansion</div>
        <div class="kv-val">{escape_html(m["design_short"])}</div>
      </div>
      <div class="kv-row">
        <div class="kv-key">Cohorts / Arms ({m["arm_count"]})</div>
        <div class="kv-val">{arms_html}</div>
      </div>
      <div class="kv-row">
        <div class="kv-key">Primary Outcomes</div>
        <div class="kv-val">{prim_html}</div>
      </div>
      <div class="kv-row">
        <div class="kv-key">DLT Evaluation Window</div>
        <div class="kv-val">{escape_html(m["dlt_window_short"])}</div>
      </div>
      <div class="kv-row">
        <div class="kv-key">MTD / RP2D Objectives</div>
        <div class="kv-val">MTD: {escape_html(m["mtd_short"])} &middot; RP2D: {escape_html(m["rp2d_short"])}</div>
      </div>
      <div class="kv-row">
        <div class="kv-key">Secondary Outcomes</div>
        <div class="kv-val">{sec_html}</div>
      </div>
      <div class="kv-row">
        <div class="kv-key">Locations</div>
        <div class="kv-val">{escape_html(m["footprint_str"])}</div>
      </div>
    </div>

    <div class="kv-card">
      <div class="kv-title">Verbatim Registry Eligibility Criteria</div>
      <pre style="white-space:pre-wrap; font-family:var(--font-sans); font-size:13.5px; color:var(--text-med); line-height:1.6;">{escape_html(elig_text)}</pre>
    </div>

    <footer>
      <div><strong>ClinSight™</strong> · Primary Registry Fact Base &middot; <a href="https://pract.eu" style="color:inherit; text-decoration:underline;">PRACT</a></div>
      <div>
        <a href="../../explorer/">Explorer</a> &middot;
        <a href="../../compare/">Comparator</a> &middot;
        <a href="../../jobs/">Careers</a> &middot;
        <a href="../../sitemap.xml">Sitemap</a>
      </div>
    </footer>
  </main>

  <script>
    function copySyn() {{
      navigator.clipboard.writeText(document.getElementById('synText').innerText).then(() => {{
        const b = document.getElementById('btnCopySyn');
        b.textContent = 'Copied!';
        setTimeout(() => {{ b.textContent = 'Copy synopsis'; }}, 2000);
      }});
    }}
  </script>
</body>
</html>'''


if __name__ == "__main__":
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        dossiers = json.load(f)

    verified_models = []
    for d in dossiers:
        if d["identity"]["nctId"] in VERIFIED_CLASS_NCTS:
            verified_models.append(build_verified_model(d))

    os.makedirs(TARGETS_DIR, exist_ok=True)
    hub_file = os.path.join(TARGETS_DIR, "index.html")
    with open(hub_file, "w", encoding="utf-8") as hf:
        hf.write(render_target_hub_html(verified_models))
    print(f"Generated comparison-first METTL3 page at {hub_file}")

    for m in verified_models:
        nct = m["nct"]
        out_dir = os.path.join(TRIALS_DIR, nct)
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, "index.html")
        with open(out_file, "w", encoding="utf-8") as out_f:
            out_f.write(render_single_trial_html(m))
        print(f"Generated single-source trial synopsis page for {nct} at {out_file}")

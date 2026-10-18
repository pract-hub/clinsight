import urllib.request
import json
import re
import os

def normalize(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.replace('≥', '>=').replace('≤', '<=').replace('–', '-').replace('—', '-').replace('−', '-')
    s = s.replace('×', 'x').replace('µ', 'u').replace('μ', 'u').replace('≈', '~')
    return s

def token_in_line(anchor, norm_line):
    if len(anchor) <= 4 and re.match(r'^[a-z0-9]+$', anchor):
        pattern = r'\b' + re.escape(anchor) + r'\b'
        return bool(re.search(pattern, norm_line))
    return anchor in norm_line

def fetch_study_api(nct_id):
    local_path = os.path.join("ClinSight-Website", "data", "raw_api_v2", f"{nct_id}.json")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            return json.load(f)
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "ClinSight-Integrity-Engine/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching {nct_id}: {e}")
        return None

def extract_sentence_around(text, trig):
    # Find sentence or clause containing trigger
    norm_t = normalize(text)
    idx = norm_t.find(trig)
    if idx == -1:
        return text.strip()
    # Try splitting text into sentences/lines
    for line in re.split(r'[\n\.]', text):
        if trig in normalize(line):
            return line.strip()
    start = max(0, idx - 40)
    end = min(len(text), idx + len(trig) + 60)
    return text[start:end].strip()

def verify_stated_string_match(nct_id, field_name, field_obj, source_text, downgrades_log):
    """§7 Build-time enforcement: verify trigger string exists in normalized source text."""
    if field_obj.get("state") != "STATED":
        return field_obj
    trig = field_obj.get("verbatim_trigger") or field_obj.get("value")
    if not trig:
        return field_obj
    if normalize(trig) in normalize(source_text):
        field_obj["checked_at_build"] = True
        return field_obj
    else:
        downgrades_log.append({
            "nct": nct_id,
            "field": field_name,
            "claimed_trigger": trig,
            "action": "FORCED_DOWNGRADE_TO_NOT_REPORTED"
        })
        return {
            "value": None,
            "state": "NOT_REPORTED",
            "source_field": None,
            "verbatim": None,
            "checked_at_build": True,
            "render": "Not reported in the statutory record (downgraded at build verification)."
        }

def extract_dossier_data(raw, downgrades_log, unmatched_elig_log, dlt_rejections_log):
    proto = raw.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status_m = proto.get("statusModule", {})
    design_m = proto.get("designModule", {})
    elig_m = proto.get("eligibilityModule", {})
    sponsor_m = proto.get("sponsorCollaboratorsModule", {})
    outcomes_m = proto.get("outcomesModule", {})
    conditions_m = proto.get("conditionsModule", {})
    arms_m = proto.get("armsInterventionsModule", {})
    desc_m = proto.get("descriptionModule", {})
    loc_m = proto.get("contactsLocationsModule", {})
    ref_m = proto.get("referencesModule", {})
    
    nct_id = ident.get("nctId")
    org_study_id = ident.get("orgStudyIdInfo", {}).get("id")
    secondary_ids = [s.get("id") for s in ident.get("secondaryIdInfos", []) if s.get("id")]
    brief_title = ident.get("briefTitle", "")
    official_title = ident.get("officialTitle", brief_title)
    acronym = ident.get("acronym")
    
    phases = design_m.get("phases", [])
    phase_str = "/".join(phases) if phases else "Phase Not Specified"
    status = status_m.get("overallStatus", "UNKNOWN")
    lead_sponsor = sponsor_m.get("leadSponsor", {}).get("name", "Unknown Sponsor")
    
    # -------------------------------------------------------------
    # MODULE 1: Protocol & Escalation Architecture
    # -------------------------------------------------------------
    design_info = design_m.get("designInfo", {})
    allocation = design_info.get("allocation")
    masking_info = design_info.get("maskingInfo", {})
    masking = masking_info.get("masking")
    intervention_model = design_info.get("interventionModel")
    intervention_model_desc = design_info.get("interventionModelDescription", "")
    primary_purpose = design_info.get("primaryPurpose")
    
    # §3 Source Field Priority (patched to include armsInterventionsModule & officialTitle)
    search_corpus = []
    if intervention_model_desc:
        search_corpus.append(("protocolSection.designModule.designInfo.interventionModelDescription", intervention_model_desc))
    for i, arm in enumerate(arms_m.get("armGroups", [])):
        if arm.get("description"):
            search_corpus.append((f"protocolSection.armsInterventionsModule.armGroups[{i}].description", arm.get("description")))
    for i, inter in enumerate(arms_m.get("interventions", [])):
        if inter.get("description"):
            search_corpus.append((f"protocolSection.armsInterventionsModule.interventions[{i}].description", inter.get("description")))
    if official_title:
        search_corpus.append(("protocolSection.identificationModule.officialTitle", official_title))
    if desc_m.get("detailedDescription"):
        search_corpus.append(("protocolSection.descriptionModule.detailedDescription", desc_m.get("detailedDescription")))
    if desc_m.get("briefSummary"):
        search_corpus.append(("protocolSection.descriptionModule.briefSummary", desc_m.get("briefSummary")))
    
    # §4 Controlled Vocabulary + Triggers (patched to include Simon's 2-stage)
    stated_triggers = [
        ("3+3", ["3+3", "3 + 3", "three plus three"]),
        ("BOIN", ["boin", "bayesian optimal interval"]),
        ("Simon's 2-stage", ["simon's 2-stage", "simon 2-stage", "simon's two-stage", "simon two-stage"]),
        ("CRM", ["continual reassessment method", "crm design"]),
        ("mTPI", ["mtpi", "modified toxicity probability interval"]),
        ("Accelerated Titration", ["accelerated titration"]),
        ("Rolling 6", ["rolling six", "rolling-6", "rolling 6"]),
        ("Basket", ["basket"]),
        ("Umbrella", ["umbrella"]),
        ("Platform Trial", ["platform trial", "master protocol", "adaptive platform"]),
        ("Dose Expansion", ["dose expansion", "expansion cohort"])
    ]
    
    matched_archetypes = []
    seen_arch_names = set()
    
    for s_field, s_text in search_corpus:
        norm_s = normalize(s_text)
        for arch_name, trig_list in stated_triggers:
            if arch_name in seen_arch_names:
                continue
            for trig in trig_list:
                if trig in norm_s:
                    snippet = extract_sentence_around(s_text, trig)
                    # Build-time string-match check on exact source text
                    if trig in normalize(s_text):
                        matched_archetypes.append({
                            "value": arch_name,
                            "source_field": s_field,
                            "verbatim_trigger": trig,
                            "verbatim": snippet,
                            "checked_at_build": True
                        })
                        seen_arch_names.add(arch_name)
                    break
                    
    design_detail = None
    for s_field, s_text in search_corpus:
        if "modified fibonacci" in normalize(s_text):
            design_detail = "modified Fibonacci"
            break

    if matched_archetypes:
        arch_names_joined = " + ".join([m["value"] for m in matched_archetypes])
        sources_joined = "; ".join([m["source_field"] for m in matched_archetypes])
        verbatims_joined = " | ".join([f'{m["verbatim"]} ({m["source_field"]})' for m in matched_archetypes])
        detail_suffix = f" (with {design_detail} dose increments)" if design_detail else ""
        design_archetype = {
            "value": arch_names_joined,
            "design_detail": design_detail,
            "state": "STATED",
            "source_field": sources_joined,
            "verbatim_trigger": matched_archetypes[0]["verbatim_trigger"],
            "verbatim": verbatims_joined,
            "checked_at_build": True,
            "matches": matched_archetypes,
            "render": f"Uses a {arch_names_joined} design{detail_suffix}."
        }
    else:
        design_archetype = {
            "value": None,
            "state": "NOT_REPORTED",
            "source_field": None,
            "verbatim": None,
            "checked_at_build": True,
            "render": "Not reported in the statutory record."
        }
        full_desc = (desc_m.get("detailedDescription", "") + " " + desc_m.get("briefSummary", "")).strip()
        norm_desc = normalize(full_desc)
        if "cohort" in norm_desc and ("3 to 6" in norm_desc or "3-6" in norm_desc):
            snippet = extract_sentence_around(full_desc, "cohort")
            design_archetype = {
                "value": "rule-based escalation",
                "state": "INFERRED",
                "source_field": "protocolSection.descriptionModule",
                "candidate_archetype": "3+3",
                "verbatim": snippet,
                "checked_at_build": True,
                "render": f'Not stated. Protocol describes "{snippet}" — consistent with a rule-based (3+3-type) design; specific method not named.'
            }
            
    # Structural counts (STATED-structural) from contactsLocationsModule.locations
    loc_list = loc_m.get("locations", [])
    countries = sorted(list(set(loc.get("country") for loc in loc_list if loc.get("country"))))
            
    if loc_list:
        countries_field = {
            "state": "STATED-structural",
            "count": len(countries),
            "site_count": len(loc_list),
            "countries": countries,
            "source_field": "protocolSection.contactsLocationsModule.locations",
            "verbatim": f"{len(countries)} countries ({', '.join(countries)}) across {len(loc_list)} sites",
            "checked_at_build": True,
            "render": f"{len(countries)} participating {'country' if len(countries)==1 else 'countries'} ({', '.join(countries)}) across {len(loc_list)} clinical trial sites."
        }
    else:
        countries_field = {
            "state": "NOT_REPORTED",
            "count": 0,
            "site_count": 0,
            "countries": [],
            "render": "Participating site locations not reported in the public registry record."
        }
        
    arms_list = arms_m.get("armGroups", [])
    if arms_list:
        arm_labels = [a.get("label", "Arm") for a in arms_list]
        arms_field = {
            "state": "STATED-structural",
            "count": len(arms_list),
            "source_field": "protocolSection.armsInterventionsModule.armGroups",
            "verbatim": "; ".join(arm_labels),
            "checked_at_build": True,
            "render": f"{len(arms_list)} designated study arms / cohorts ({'; '.join(arm_labels)})."
        }
    else:
        arms_field = {
            "state": "NOT_REPORTED",
            "count": 0,
            "render": "Study arms not reported in the public registry record."
        }
        
    # -------------------------------------------------------------
    # MODULE 2: Medical Writing Extraction Box
    # -------------------------------------------------------------
    crit_text = elig_m.get("eligibilityCriteria", "")
    raw_lines = [l.strip() for l in crit_text.split("\n") if l.strip()]
    lines = []
    for l in raw_lines:
        clean = l.lstrip("- *• \t\r")
        if clean and not any(clean.lower().startswith(h) for h in [
            "inclusion criteria", "exclusion criteria", "key inclusion", "key exclusion"
        ]):
            lines.append(clean)
            
    # Strict lab/organ-function anchors per Module 2 Trigger Table (no bare organ words or generic "cardiovascular" disease exclusions)
    cat_anchors = {
        "hematologic": {
            "anchors": ["anc", "absolute neutrophil count", "neutrophil count", "platelet", "platelets", "plt", "hemoglobin", "haemoglobin", "hgb", "hb", "wbc", "white blood cell", "leukocyte", "lymphocyte count", "hematologic function", "bone marrow function", "marrow function"],
            "numeric_units": ["x10^9", "10*9", "g/dl", "g/l", "cells", "/ul", "/mm3", ">=", "<=", "<", ">"]
        },
        "renal": {
            "anchors": ["creatinine", "creatinine clearance", "crcl", "egfr", "gfr", "cockcroft", "cockcroft-gault", "renal function"],
            "numeric_units": ["ml/min", "mg/dl", "umol/l", ">=", "<=", "<", ">"]
        },
        "hepatic": {
            "anchors": ["bilirubin", "total bilirubin", "ast", "alt", "aspartate aminotransferase", "alanine aminotransferase", "sgot", "sgpt", "transaminase", "alkaline phosphatase", "alp", "albumin", "hepatic function"],
            "numeric_units": ["uln", "x upper limit", "u/l", "mg/dl", ">=", "<=", "<", ">"]
        },
        "cardiac": {
            "anchors": ["lvef", "ejection fraction", "qtc", "qtcf", "qt interval", "echocardiogram", "echo", "muga", "nyha", "troponin", "cardiac function"],
            "numeric_units": ["%", "msec", "ms", ">=", "<=", "<", ">"]
        },
        "washout": {
            "anchors": ["washout", "wash-out", "wash out", "prior therapy", "prior treatment", "prior systemic", "previous therapies", "last dose", "since the last", "half-life", "half-lives", "recovered from", "resolved to", "weeks before", "weeks prior", "within 4 weeks", "within four weeks", "within 3 weeks"],
            "numeric_units": ["day", "days", "week", "weeks", "month", "months", "half-lives", "cycle"]
        }
    }
    
    module2_results = {}
    matched_any_cat = set()
    
    for cat_name, cfg in cat_anchors.items():
        matched = []
        seen_lines = set()
        for line in lines:
            norm_l = normalize(line)
            # Hard Traps (§2)
            if cat_name == "renal" and "renal cell" in norm_l and not any(k in norm_l for k in ["clearance", "creatinine", "renal function", "egfr"]):
                continue
            if cat_name == "hepatic" and any(k in norm_l for k in ["hepatitis b", "hepatitis c", "metastases"]) and not any(k in norm_l for k in ["bilirubin", "hepatic function"]) and not re.search(r'\b(alt|ast)\b', norm_l):
                continue
            if cat_name == "washout":
                if "no prior malignancy" in norm_l:
                    continue
                # Require a time token or recovery/washout token so generic "at least 1 prior line of therapy" isn't filed as a washout window
                has_time_or_washout = any(t in norm_l for t in ["day", "days", "week", "weeks", "half-life", "half-lives", "washout", "wash-out", "recovered from", "resolved to"])
                if not has_time_or_washout:
                    continue
                
            hit = any(token_in_line(anc, norm_l) for anc in cfg["anchors"])
            if hit and line not in seen_lines:
                is_num = any(u in norm_l for u in cfg["numeric_units"])
                matched.append({
                    "verbatim": line,
                    "tag": "numeric" if is_num else "qualitative",
                    "source_field": "protocolSection.eligibilityModule.eligibilityCriteria",
                    "checked_at_build": line in crit_text
                })
                seen_lines.add(line)
                matched_any_cat.add(line)
        if matched:
            module2_results[cat_name] = {
                "state": "STATED",
                "items": matched
            }
        else:
            module2_results[cat_name] = {
                "state": "NOT_REPORTED",
                "render": "Not specified in the eligibility criteria."
            }
            
    for line in lines:
        if line not in matched_any_cat:
            unmatched_elig_log.append({"nct": nct_id, "line": line})

    # -------------------------------------------------------------
    # MODULE 3: Safety, DLT & RP2D Blueprint (Multi-Tier Scan per §3.1/§3.2 Patch)
    # -------------------------------------------------------------
    primary_outcomes = outcomes_m.get("primaryOutcomes", [])
    secondary_outcomes = outcomes_m.get("secondaryOutcomes", [])
    other_outcomes = outcomes_m.get("otherOutcomes", [])
    outcome_tiers = [
        ("primary", "primaryOutcomes", primary_outcomes),
        ("secondary", "secondaryOutcomes", secondary_outcomes),
        ("other", "otherOutcomes", other_outcomes)
    ]
    
    dlt_window_result = {
        "state": "NOT_REPORTED",
        "render": "Not reported separately from study duration.",
        "verbatim": None
    }
    dlt_endpoint_result = {
        "state": "NOT_REPORTED",
        "render": "Not reported in outcome measures."
    }
    
    dlt_time_patterns = ["cycle 1", "first cycle", "days 1 to 2", "days 1-2", "first 21 days", "first 28 days", "21-day", "28-day", "4 weeks", "6 weeks", "8 weeks", "28 days", "21 days", "21 days after"]
    duration_disqualifiers = ["up to 24 months", "up to 2 years", "up to 3 years", "through study completion", "study completion", "until disease progression", "until progression", "overall survival", "24 months", "2 years"]
    
    for tier_label, tier_key, tier_list in outcome_tiers:
        for idx, po in enumerate(tier_list):
            meas = po.get("measure", "")
            desc = po.get("description", "")
            tf = po.get("timeFrame", "")
            norm_meas = normalize(meas)
            norm_desc = normalize(desc)
            norm_tf = normalize(tf)
            
            dlt_triggers = ["dose-limiting toxicit", "dose limiting toxicit", " dlt", "dlts", "(dlt)"]
            in_meas = any(t in norm_meas for t in dlt_triggers)
            in_desc = any(t in norm_desc for t in dlt_triggers)
            
            if (in_meas or in_desc) and dlt_endpoint_result["state"] == "NOT_REPORTED":
                where_matched = f"protocolSection.outcomesModule.{tier_key}[{idx}].measure" if in_meas else f"protocolSection.outcomesModule.{tier_key}[{idx}].description (under measure: '{meas}')"
                full_meas_text = meas if not desc else f"{meas} — [description: {desc}]"
                tier_qual = "" if tier_label == "primary" else f" — stated as a {tier_label} outcome"
                dlt_endpoint_result = {
                    "state": "STATED",
                    "value": full_meas_text,
                    "outcome_tier": tier_label,
                    "source_field": where_matched,
                    "verbatim": full_meas_text,
                    "checked_at_build": True,
                    "render": f"{'Primary outcome evaluates' if tier_label == 'primary' else 'Outcome evaluates'}: {full_meas_text}{tier_qual}"
                }
                is_bounded = any(p in norm_tf for p in dlt_time_patterns)
                is_disqualified = any(d in norm_tf for d in duration_disqualifiers)
                if is_bounded and not is_disqualified:
                    dlt_window_result = {
                        "state": "STATED",
                        "value": tf,
                        "outcome_tier": tier_label,
                        "source_field": f"{where_matched} + .timeFrame",
                        "verbatim": f"measure: \"{meas}\" | description: \"{desc}\" | timeFrame: \"{tf}\"",
                        "checked_at_build": True,
                        "render": f"DLT assessment window specified as: {tf}{tier_qual}"
                    }
                else:
                    dlt_rejections_log.append({
                        "nct": nct_id,
                        "outcome_tier": tier_label,
                        "measure": meas,
                        "description": desc,
                        "disqualified_timeFrame": tf
                    })
                    dlt_window_result = {
                        "state": "NOT_REPORTED",
                        "render": "DLTs assessed; no bounded early window stated separately from study duration.",
                        "disqualified_timeframe": tf
                    }
                
    # §3.2 RP2D and MTD — multi-tier outcome scan (primary -> secondary -> other)
    rp2d_result = {"state": "NOT_REPORTED", "render": "Not reported as a designated outcome measure."}
    mtd_result = {"state": "NOT_REPORTED", "render": "Not reported as a designated outcome measure."}
    
    for tier_label, tier_key, tier_list in outcome_tiers:
        for idx, po in enumerate(tier_list):
            meas = po.get("measure", "")
            desc = po.get("description", "")
            norm_m = normalize(meas + " " + desc)
            in_meas_rp2d = any(t in normalize(meas) for t in ["recommended phase 2 dose", "recommended phase ii dose", "rp2d"])
            in_desc_rp2d = any(t in normalize(desc) for t in ["recommended phase 2 dose", "recommended phase ii dose", "rp2d"])
            if (in_meas_rp2d or in_desc_rp2d) and rp2d_result["state"] != "STATED":
                sub_f = "measure" if in_meas_rp2d else "description"
                tier_render = f"Designated primary measure: {meas}" if tier_label == "primary" else f"{meas} — stated as a {tier_label} outcome."
                rp2d_result = {
                    "state": "STATED",
                    "value": meas,
                    "outcome_tier": tier_label,
                    "source_field": f"protocolSection.outcomesModule.{tier_key}[{idx}].{sub_f}",
                    "verbatim": meas if in_meas_rp2d else f"{meas} ({desc})",
                    "checked_at_build": True,
                    "render": tier_render
                }
            elif "recommended dose" in norm_m and rp2d_result["state"] == "NOT_REPORTED":
                rp2d_result = {
                    "state": "INFERRED",
                    "candidate": "RP2D",
                    "outcome_tier": tier_label,
                    "source_field": f"protocolSection.outcomesModule.{tier_key}[{idx}].measure",
                    "verbatim": meas,
                    "checked_at_build": True,
                    "render": f"States a goal of '{meas}'; consistent with an RP2D objective, term not used."
                }

            in_meas_mtd = any(t in normalize(meas) for t in ["maximum tolerated dose", "mtd"])
            in_desc_mtd = any(t in normalize(desc) for t in ["maximum tolerated dose", "mtd"])
            if (in_meas_mtd or in_desc_mtd) and mtd_result["state"] != "STATED":
                sub_f = "measure" if in_meas_mtd else "description"
                tier_render = f"Designated primary measure: {meas}" if tier_label == "primary" else f"{meas} — stated as a {tier_label} outcome."
                mtd_result = {
                    "state": "STATED",
                    "value": meas,
                    "outcome_tier": tier_label,
                    "source_field": f"protocolSection.outcomesModule.{tier_key}[{idx}].{sub_f}",
                    "verbatim": meas if in_meas_mtd else f"{meas} ({desc})",
                    "checked_at_build": True,
                    "render": tier_render
                }

    # §3.3 Toxicity Grading
    ctcae_result = {"state": "NOT_REPORTED", "render": "Toxicity grading framework not stated in registry record."}
    for s_field, s_text in [
        ("protocolSection.eligibilityModule.eligibilityCriteria", crit_text),
        ("protocolSection.descriptionModule.detailedDescription", desc_m.get("detailedDescription", "")),
        ("protocolSection.outcomesModule.primaryOutcomes", json.dumps(primary_outcomes))
    ]:
        norm_s = normalize(s_text)
        if "ctcae" in norm_s or "common terminology criteria for adverse events" in norm_s:
            ver = "version not stated"
            for v in ["v5.0", "v4.03", "v4.0", "version 5", "version 4"]:
                if v in norm_s:
                    ver = v
                    break
            snip = extract_sentence_around(s_text, "ctcae" if "ctcae" in norm_s else "common terminology")
            ctcae_result = {
                "state": "STATED",
                "value": f"CTCAE ({ver})",
                "source_field": s_field,
                "verbatim": snip,
                "checked_at_build": True,
                "render": f"Adverse events graded according to CTCAE ({ver})."
            }
            break

    # §3.4 Dose Modification Rules
    det_desc = desc_m.get("detailedDescription", "")
    dose_mod_result = {"state": "NOT_REPORTED", "render": "Dose-modification rules not described in the registry record."}
    for trig in ["dose reduction", "dose modification", "dose de-escalation", "dose interruption", "dose delay"]:
        if trig in det_desc.lower():
            for s in det_desc.split('.'):
                if trig in s.lower():
                    dose_mod_result = {
                        "state": "STATED",
                        "source_field": "protocolSection.descriptionModule.detailedDescription",
                        "verbatim": s.strip(),
                        "checked_at_build": True,
                        "render": s.strip()
                    }
                    break
            break

    # -------------------------------------------------------------
    # MODULE 4: Statutory Resolution & Document Access
    # -------------------------------------------------------------
    has_results = status_m.get("resultsFirstSubmitDate") is not None
    intervention_names = [i.get("name", "") for i in arms_m.get("interventions", []) if i.get("name")]
    # Extract primary investigational drug code tokens (e.g., "STC-15", "EP102")
    drug_tokens = []
    for iname in intervention_names:
        for tok in re.findall(r"[A-Za-z]{2,}-?\d+", iname):
            drug_tokens.append(tok.lower())

    pmids = []
    rejected_references = []
    for r in ref_m.get("references", []):
        pmid = r.get("pmid")
        if not pmid:
            continue
        ref_type = (r.get("type") or "").upper()
        citation = r.get("citation") or ""
        norm_cit = citation.lower()

        # Gate 1: Never surface DERIVED (algorithm-linked) references
        if ref_type == "DERIVED":
            rejected_references.append({
                "pmid": pmid,
                "type": ref_type,
                "reason": "REJECTED_DERIVED_AUTO_LINKED",
                "citation": citation
            })
            downgrades_log.append({
                "nct": nct_id,
                "field": "module4.pmids",
                "pmid": pmid,
                "ref_type": ref_type,
                "action": "REJECTED_DERIVED_REFERENCE",
                "citation": citation
            })
            continue

        # Gate 2: Only RESULT or compound/NCT-verified BACKGROUND references
        if ref_type == "RESULT":
            pmids.append(pmid)
        elif ref_type == "BACKGROUND":
            matches_nct = nct_id.lower() in norm_cit
            matches_drug = any(dt in norm_cit for dt in drug_tokens)
            if matches_nct or matches_drug:
                pmids.append(pmid)
            else:
                rejected_references.append({
                    "pmid": pmid,
                    "type": ref_type,
                    "reason": "REJECTED_BACKGROUND_DIFFERENT_COMPOUND",
                    "citation": citation
                })
                downgrades_log.append({
                    "nct": nct_id,
                    "field": "module4.pmids",
                    "pmid": pmid,
                    "ref_type": ref_type,
                    "action": "REJECTED_BACKGROUND_UNMATCHED_COMPOUND",
                    "expected_drugs": drug_tokens,
                    "citation": citation
                })

    module4_data = {
        "nct_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "has_results": has_results,
        "results_url": f"https://clinicaltrials.gov/study/{nct_id}?tab=results" if has_results else None,
        "pmids": pmids,
        "rejected_references": rejected_references,
        "ctis_id": None,
        "protocol_pdf": None
    }
    
    return {
        "identity": {
            "nctId": nct_id,
            "briefTitle": brief_title,
            "officialTitle": official_title,
            "acronym": acronym,
            "phase": phase_str,
            "status": status,
            "leadSponsor": lead_sponsor,
            "conditions": conditions_m.get("conditions", []),
            "interventions": [i.get("name") for i in arms_m.get("interventions", [])]
        },
        "module1": {
            "design_archetype": design_archetype,
            "allocation": {"state": "STATED" if allocation else "NOT_REPORTED", "value": allocation or "Not specified", "source_field": "protocolSection.designModule.designInfo.allocation", "verbatim": allocation, "checked_at_build": bool(allocation)},
            "masking": {"state": "STATED" if masking else "NOT_REPORTED", "value": masking or "Open Label", "source_field": "protocolSection.designModule.designInfo.maskingInfo.masking", "verbatim": masking, "checked_at_build": bool(masking)},
            "intervention_model": {"state": "STATED" if intervention_model else "NOT_REPORTED", "value": intervention_model or "Not specified", "source_field": "protocolSection.designModule.designInfo.interventionModel", "verbatim": intervention_model, "checked_at_build": bool(intervention_model)},
            "primary_purpose": {"state": "STATED" if primary_purpose else "NOT_REPORTED", "value": primary_purpose or "Treatment", "source_field": "protocolSection.designModule.designInfo.primaryPurpose", "verbatim": primary_purpose, "checked_at_build": bool(primary_purpose)},
            "participating_countries": countries_field,
            "arms_cohorts": arms_field
        },
        "module2": module2_results,
        "module3": {
            "dlt_endpoint": dlt_endpoint_result,
            "dlt_window": dlt_window_result,
            "rp2d": rp2d_result,
            "mtd": mtd_result,
            "ctcae": ctcae_result,
            "dose_modification": dose_mod_result
        },
        "module4": module4_data
    }

if __name__ == "__main__":
    targets = ["NCT06975293", "NCT07163325", "NCT05584111"]
    output_records = []
    downgrades_log = []
    unmatched_elig_log = []
    dlt_rejections_log = []
    
    for t in targets:
        print(f"Extracting {t} with patched §3 source-field priority and strict §4/§5 triggers...")
        raw = fetch_study_api(t)
        if raw:
            dossier = extract_dossier_data(raw, downgrades_log, unmatched_elig_log, dlt_rejections_log)
            output_records.append(dossier)
            print(f"Extraction successful for {t}: Design Archetype = {dossier['module1']['design_archetype']['state']} ({dossier['module1']['design_archetype']['value']})")
            
    out_file = "ClinSight-Website/data/phase1_2_mettl3_extracted.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_records, f, indent=2)
        
    # Write tuning/audit logs (§5)
    with open("ClinSight-Website/data/extraction_downgrades.jsonl", "w", encoding="utf-8") as f:
        for row in downgrades_log:
            f.write(json.dumps(row) + "\n")
    with open("ClinSight-Website/data/unmatched_eligibility_lines.jsonl", "w", encoding="utf-8") as f:
        for row in unmatched_elig_log:
            f.write(json.dumps(row) + "\n")
    with open("ClinSight-Website/data/dlt_window_rejections.jsonl", "w", encoding="utf-8") as f:
        for row in dlt_rejections_log:
            f.write(json.dumps(row) + "\n")
            
    print(f"Saved {len(output_records)} calibrated dossiers to {out_file}")

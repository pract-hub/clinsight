# ClinSight Permanent UI & Copywriting Dos and Don'ts

These rules apply permanently across all pages, templates, scripts, and future updates of `ClinSight-Website` (`clinsight.pract.eu`).

## 1. Brand & Navigation Consistency
- **DO** use `ClinSight` consistently everywhere (never `ClinSight™`, as the trademark/incorporation is not registered yet).
- **DO** keep the browser tab title simple: `<title>ClinSight</title>` (never append em-dashes or long taglines like `ClinSight — Compare Clinical Trials Side by Side`).
- **DO** keep the top navigation bar identical on every single page so it never jumps or changes when navigating back and forth:
  - Left: `ClinSight` (links to `/`)
  - Right: `Comparator` (`/compare/`), `Trials explorer` (`/explorer/`), `Theme` (toggle button)
  - Keep secondary links (`Careers`, `Sitemap`) in the footer.
- **DON'T** put a single drug target (e.g., `METTL3 comparison`) in the top navigation bar or as the main hero CTA button—keep top-level navigation and primary CTAs general (`Comparator`, `Explore drug class comparisons`).

## 2. Human Readability (Zero Internal Guidelines or Pipeline Jargon on Page)
- **DO** write in plain, intuitive, human-first English (e.g., `Drug class comparisons`, `Open comparison`, `Eligibility Criteria`, `Official Trial Records`, `Requirements`, `Preferred`).
- **DON'T** expose internal editorial rules, verification protocols, or developer schema on user-facing pages:
  - Never use words like `verbatim`, `provenance`, `statutory`, `primary registry fact base`, `disclosed`, `single-source`, `Launch Matrix`, or `Cross-Trial Landscape Matrices`.
  - Never show internal disclaimer boxes like *"The ClinSight Verification Protocol: All job postings are audited..."* or *"Hover any cell or toggle sources for registry field provenance."*
  - Never put raw JSON field paths (`protocolSection.armsInterventionsModule...`) in hover tooltips (`title=...`) or visible text.

## 3. Punctuation & Clean Formatting (No AI Slop Signals)
- **DON'T** use em-dashes (`—`, `&mdash;`) or en-dashes (`–`, `&ndash;`) in titles, headings, subtitles, prose, or table cells. Use commas, colons, periods, or plain words (`to`, `Not specified`, `None`).
- **DO** collapse repetitive or dense parameter lists (such as 9 individual PK parameters or 5 identical PK outcome rows) into a single concise, scannable line (`PK: Cmax, AUC, t½, Cl, Vd`).
- **DO** use clean human labels in comparison cells rather than dumping raw registry typos or lengthy sponsor sentences onto the surface.

## 4. Layout & Deployment
- **DO** maintain generous desktop spacing (`max-width: 1040px`, comfortable vertical padding in hero and list rows) alongside clean single-line mobile navigation (`white-space: nowrap`).
- **DON'T** add build commands to `netlify.toml` (`command = ""` must remain so static deploys consume minimal credits).

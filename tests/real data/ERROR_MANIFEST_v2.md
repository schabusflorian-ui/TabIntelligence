# ERROR MANIFEST v2 — Climate Hardware DD Test Models
*Answer key for QA validation. Do not distribute alongside test files.*

---

## Structural Archetypes (what the extraction pipeline must handle)

| # | File | Structure | Complexity layers |
|---|---|---|---|
| 01 | `01_electrolyser_FOAK_singlesheet.xlsx` | **Single flat sheet** — no tab separation, assumptions scattered inline | 3-statement P&L+BS+CF, sculpted debt concept, loss carryforward tax |
| 02 | `02_biochar_NOAK_transposed_DE.xlsx` | **Transposed** — years as rows, items as columns, German/English mixed | Multi-currency EUR/USD, milestone grant drawdown, WC schedule |
| 03 | `03_heat_pump_HaaS_monthly.xlsx` | **Monthly model** (36 months) + Annual Rollup tab | Seasonal demand, monthly DSCR, DSRA top-up mechanics |
| 04 | `04_DAC_prerevenue_multitab.xlsx` | **9-tab deeply nested** — each tab references prior | Full waterfall, LLCR/PLCR, sensitivity table, IRR, grant double-count |
| 05 | `05_pyrolysis_W2E_inline_scenarios.xlsx` | **Three scenarios side-by-side** in one sheet, assumptions inline (no separate tab) | Scenario DSCR, IRR per scenario |
| 06 | `06_LDES_hidden_rows_SaaS.xlsx` | **Hidden rows** (rows 1-15), SaaS dashboard above real PF model, merged headers | Multi-tranche debt, LLCR, covenant package |
| 07 | `07_green_ammonia_3scenario_curves.xlsx` | **Three-scenario columns + commodity curve sub-table** | Multi-currency, export credit tranche, Haber-Bosch stoichiometry in calcs |
| 08 | `08_geothermal_EGS_HoldCo_SPV.xlsx` | **HoldCo/SPV two-entity** — separate P&L per entity + consolidation tab | Interco loan, full 3-statement each entity, deferred tax, minority interest |
| 09 | `09_CCUS_cement_hardcoded_FY.xlsx` | **Fully hardcoded** — no formulas. Fiscal year Apr-Mar labelled FY26/FY27. Mixed £/€ | Carbon forward curve hardcoded, tax equity (IRA applied wrongly) |
| 10 | `10_wind_nacelle_manufacturing_quarterly.xlsx` | **Quarterly (Q1-Q8) then Annual** — corporate P&L structure | AR/AP/inventory WC, order backlog, covenant tracker |

---

## Error Registry

### MODEL 01 — PEM Electrolyser FOAK (single flat sheet)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Row 74 (DSCR row) | `DSCR = EBITDA / Debt Service` — should be CFADS (EBITDA minus tax, minus ΔWC) | DSCR calculation | DSCR numerator is EBITDA not CFADS — overstated by ~25-30% |
| E2 | Row 8 col C (utilisation) | 97% utilisation for grid-connected PEM — realistic max ~80-85% | Technology benchmark | Utilisation >90% implausible for grid-connected PEM at FOAK stage |
| E3 | Rows 51-52 (depreciation) | Stack replacement in Y5 capitalised and depreciated over 7yr — should be expensed as major maintenance | Accounting treatment | FOAK stack replacement should be OpEx not CapEx |
| E4 | Row 11 (power cost) | Power cost flat €48/MWh across all years — no escalation, no curtailment model | Assumption completeness | No price escalation on largest cost line item |
| E5 | Row 59 (tax) | Tax loss carryforward assumed to expire Year 3 — Germany has unlimited c/f | Jurisdiction error | German Körperschaftsteuer: unlimited loss carryforward (§10d EStG) |

**Structural challenge for parser:** All assumptions and outputs on single sheet. No tab structure. Years in row 3 offset by 2 from assumptions block. Assumption values in col C, not col B.

---

### MODEL 02 — Biochar NOAK Transposed (German/English, years as rows)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Row 7 (Meilensteinplan tab), Modell row 7 col 7 | Grant booked as Year 0 revenue then partial Year 1 — should be equity contribution | Grant accounting | EU InnoFund grants are not revenue (IFRS: deduct from CapEx or defer as deferred income) |
| E2 | Modell col 6, col 9 | Gate fee (€55/t) counted in revenue AND feedstock net cost reduced by gate fee amount — double-count | Revenue double-count | Gate fee appears in both revenue line and as implicit cost offset |
| E3 | Annahmen tab row 15 | DSCR covenant 1.10x — below FOAK minimum (1.20x) | Covenant structure | FOAK debt should have minimum 1.20x DSCR covenant; 1.10x inadequate |
| E4 | Annahmen tab row 18 | USD/EUR hardcoded 1.08 — single rate, no sensitivity, no hedging | FX risk | Carbon credits priced in USD with fixed FX — no range or hedging assumption |
| E5 | Meilensteinplan tab | All 5 grant milestone tranches (€2M) disbursed in Year 0; actual: milestone-gated over 3 years | Grant timing | EU InnoFund disbursement requires milestone delivery — cannot be 100% upfront |

**Structural challenge:** Years run DOWN rows (transposed). Line items run across columns. Labels in German with English subtitles. Tab named "Modell" not "Model" or "P&L".

---

### MODEL 03 — Heat Pump HaaS (Monthly model)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Monthly CF row 30, Annual Summary row 11 | DSCR = (monthly EBITDA × 12) / (debt service × 12) — not trailing 12-month CFADS | DSCR calculation | Annualising a single month EBITDA ≠ T12M CFADS; misses seasonality and WC |
| E2 | Monthly CF row 15 (heat hours) | Heat hours flat at 650/month — no seasonal variation; industrial heat demand ~40% lower in summer | Technology benchmark | Heat output physically implausible at uniform 650hrs/month for process heat |
| E3 | Monthly CF row 18 (DSRA top-up) | DSRA funded from Month 1 operating CF — should be funded at Financial Close from equity | DSRA structure | DSRA must be pre-funded at FC; cannot use first-month operating CF as reserve |
| E4 | Inline assumption row 5 | COP = 4.5 for 120°C industrial heat — realistic COP for this temperature = 2.5-3.2 | Technology benchmark | High-temperature heat pump COP 4.5 at 120°C outlet impossible with current technology |
| E5 | No credit wrap modelled | Single unrated industrial offtaker; 100% payment assumed; no receivables reserve | Credit structure | Single unrated offtaker should trigger credit reserve or guarantee requirement |

**Structural challenge:** 36 monthly columns (Q1 2025 through Q4 2027) plus annual rollup. No dedicated "Assumptions" tab — assumptions embedded in rows 4-12 of Monthly CF sheet. Monthly DSCR must be read differently from annual.

---

### MODEL 04 — DAC Pre-Revenue (9-tab nested)

| ID | Location (tab → row/col) | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Cover tab + TechSpec tab | 100× scale-up (100t/yr → 10,000t/yr) with no engineering bridge — no intermediate pilot | Technology risk | Scale-up >10× in single step requires detailed TEA with learning rate basis |
| E2 | CapEx_Depr tab rows 12-13 | EU Innovation Fund Large Scale + Horizon Europe MSCA — both claimed on same project | Grant stacking | Horizon Europe + InnoFund on same project violates double-funding prohibition |
| E3 | MacroAsm tab row 16 + OpEx tab | OpEx €180/tCO2 — sensitivity table shows break-even only below €220/t; peer TEA benchmarks €300-500/t | Technology benchmark | DAC OPEX significantly below peer benchmarks; no justification provided |
| E4 | Revenue_Grants tab col D (Year 2026) | CDR revenue starts Year 1 — 18-month construction means no commercial operation until mid-2026 at earliest | Construction timeline | Revenue in Year 1 despite 18-month construction period (pre-COD revenue) |
| E5 | Debt_DSRA tab (all N/A) | €15M debt term sheet mentioned in Cover tab but zero debt modelled — no DSCR, no interest | Model completeness | Debt term sheet exists; no debt schedule, no DSCR, no interest expense in model |

**Structural challenge:** 9 tabs with nested cross-references (Revenue_Grants references MacroAsm; CFADS_Waterfall references Revenue_Grants and OpEx; Sensitivity references Revenue_Grants and OpEx). Parser must traverse dependency graph. Debt_DSRA tab is intentionally blank/N/A.

---

### MODEL 05 — Pyrolysis W2E (Inline scenarios, no Assumptions tab)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Row 9 (gate fee assumption) + rows 24, 31 | Gate fee €95/t in revenue (row 24) AND feedstock cost = (gate fee minus €35/t) → net feedstock in row 31 double-counts gate fee as both income and cost reduction | Revenue double-count | Gate fee counted in both revenue and as implied cost offset — net feedstock cost invalid |
| E2 | Row 13 (REGO certs) | REGO certificates modelled in Germany — REGOs are UK-specific instrument; Germany uses HKN (Herkunftsnachweise) | Jurisdiction error | REGO certificates have no legal status in Germany; correct instrument is HKN |
| E3 | Row 15 (contingency) | EPC contingency 3% across all three scenarios (Base/High/Low) — FOAK pyrolysis needs 15-20% | Technology benchmark | Contingency 3% far below FOAK norm; not stress-tested in Low scenario |
| E4 | Row 10 (power price) | Merchant power price — no floor contract. Low case drops to €50/MWh but pyrolysis remains viable because cost structure unchanged | Revenue risk | Merchant power exposure with no floor price; revenue risk unmitigated |
| E5 | Low scenario costs (row 20-22) | Low/Stress scenario uses identical O&M, consumables, and compliance costs as Base case — only revenue stressed | Scenario construction | Stress scenario must stress both revenue AND costs; cost uplift in Low case = zero |

**Structural challenge:** No Assumptions tab. Blue input cells scattered in rows 5-22 interspersed with output calculations in rows 24-45. Three scenario column blocks (Base: C-M, High: O-Y, Low: AA-AK) with gap columns between. Parser must identify which column block belongs to which scenario from row 2 merged headers.

---

### MODEL 06 — LDES Grid Storage (Hidden rows, SaaS dashboard)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Rows 17-24 (visible) | ARR/MRR/CAC/LTV/churn metrics applied to 15-year utility dispatch contracts — SaaS framework inappropriate | Metric framework | SaaS retention metrics not applicable to long-term grid capacity contracts |
| E2 | Row 41 (EBIT = EBITDA) | No depreciation in P&L — EBIT = EBITDA. €28.5M CapEx with 20-year life = €1.4M/yr omitted | Accounting | Depreciation missing from income statement |
| E3 | Row 20 (churn rate) | 15% annual churn on 15-year grid capacity contracts — long-term contracts cannot churn annually | Metric framework | Annual churn rate concept inapplicable to contracted capacity agreements |
| E4 | Rows 19-23 | CAC (€450k), LTV (€8.2M), LTV/CAC applied to grid operators as "customers" | Metric framework | Grid operators are offtakers under long-term contracts, not SaaS customers with acquisition costs |
| E5 | Debt Schedule tab row 5 | Mezzanine tranche €15M mentioned in Debt Tranches but shows zero / blank in all year columns | Model completeness | Mezzanine debt not modelled in debt schedule; understates financing cost by ~€1.4M/yr interest |

**Structural challenge:** Key assumptions in rows 1-15 (hidden). Main model starts row 16. SaaS KPI dashboard occupies rows 16-30 (intentionally misleading). Actual PF model in rows 31+. Parser may extract SaaS metrics as financial model outputs. Merged cells across header row 2.

---

### MODEL 07 — Green Ammonia FOAK (Three-scenario + commodity curves)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Row 14 (power cost) | Power cost €35/MWh flat across all scenarios and all years — VRE-coupled system should model variability | Technology assumption | VRE-coupled electrolyser: power price should reflect renewable curtailment, seasonal variation |
| E2 | Row 8 (electrolyser utilisation) | 95% utilisation in Base and High scenarios — VRE-coupled system maximum realistic utilisation ~60-75% | Technology benchmark | VRE-coupled PEM electrolyser cannot achieve >75% utilisation without storage buffer |
| E3 | Row 11 (H2 buffer) | H2 buffer storage = 0 tonnes — Haber-Bosch requires steady H2 feed; VRE intermittency requires buffer | Technology design | Zero H2 buffer before Haber-Bosch synthesis loop is technically impossible for VRE-coupled plant |
| E4 | Commodity Curves tab | NH3 price flat €680/t across all years vs market curve showing €620-750/t with commodity cyclicality | Market assumption | Flat commodity price for 10-year model; inconsistent with commodity curve shown in adjacent tab |
| E5 | Row 19 + P&L row 25 | IRA Section 45H credit ($3.00/kgH2) applied to Oman-based project — IRA credits are US-only | Jurisdiction error | IRA Section 45H clean hydrogen credit applies only to US-registered projects; Oman ineligible |

**Structural challenge:** Three-scenario column blocks (Base: C-M, High: O-Y, Low: AA-AK). Commodity curve sub-table on separate tab uses different year axis. Debt Tranches tab has structured tranche table disconnected from P&L model. Oman jurisdiction detail requires jurisdiction awareness.

---

### MODEL 08 — Geothermal EGS (HoldCo/SPV consolidation)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | SPV tab rows 6-8 | Single production well, zero injector wells — geothermal EGS requires paired injector/producer wells | Technology design | EGS cannot circulate fluid without injector well; single-well design hydraulically impossible |
| E2 | SPV tab row 10 | Thermal decline rate = 0%/yr — EGS wells typically decline 2-5%/yr as reservoir cools | Technology benchmark | Zero thermal decline for EGS inconsistent with all published EGS field data |
| E3 | SPV tab row 11 | Exploration risk contingency = 0% — EGS well failure rate 30-50% in pre-commercial projects | Risk provision | No exploration risk provision; EGS FOAK should carry 30-50% CapEx risk contingency |
| E4 | SPV tab row 12 | Resource success probability = 100% — EGS typically 60-80% | Technology benchmark | 100% resource success probability not credible for FOAK EGS; should be 60-80% |
| E5 | Consolidation tab + HoldCo tab | Interco eliminations (royalties €X, interco loan interest €Y) mentioned in Consolidation tab but not subtracted from consolidated revenue | Accounting | Consolidated revenue includes interco royalties and loan interest that must be eliminated |

**Structural challenge:** Three tabs (SPV, HoldCo, Consolidation) with different P&L structures. Interco flows appear in both SPV (as expenses) and HoldCo (as income). Consolidation tab references both. Parser must recognise interco elimination requirement. Deferred tax appears in SPV but not in consolidated.

---

### MODEL 09 — CCUS Cement Retrofit (Fully hardcoded, Apr-Mar fiscal year)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | Row 8-9 (IRA 45Q) | IRA Section 45Q credit ($85/tCO2) applied to Heidelberg, Germany plant — US tax credit, not applicable to German project | Jurisdiction error | IRA 45Q: US-only industrial carbon capture credit; German CCUS projects use EU ETS and national KSt incentives |
| E2 | Row 10, 17 | CO2 transport & storage cost = £0 (and €0) — T&S is material cost item (€15-40/tCO2 typical) | Cost completeness | T&S zero cost is material omission; CO2 must be transported to storage site (North Sea saline aquifer) |
| E3 | Row 5 (capture rate) | Capture rate 95% flat — no uncertainty range, no ramp-up period | Technology benchmark | Post-combustion capture 95% at FOAK stage; should show ramp (60-70% Year 1, reaching 85-90% at steady state) |
| E4 | CapEx section rows 33-37 | CapEx benchmarks from 2019 (pre-inflation) — no adjustment for 40-50% construction cost inflation 2019-2024 | CapEx benchmark | 2019 CapEx benchmarks understated by 35-50% vs 2024 actual construction costs |
| E5 | Model (no additionality calc) | All 285kt/yr CO2 counted as credits — no additionality baseline deducted | Carbon accounting | CCUS credits require additionality: only CO2 captured above baseline process emissions counts |

**Structural challenge:** ALL values are hardcoded literals (no formulas). Cannot audit assumptions from formulas. Fiscal year Apr-Mar labelled as FY26/27 — not calendar year. Mixed £/€ currency labels (UK parent, German OpCo). Parser must detect absence of formulas as a structural problem.

---

### MODEL 10 — Wind Nacelle Manufacturing (Quarterly then Annual, corporate model)

| ID | Location | Error | Category | What system should flag |
|---|---|---|---|---|
| E1 | P&L row 18 (SPV management fees) | SPV management fees included in consolidated corporate P&L without interco elimination | Accounting | Interco management fees between Factory OpCo and SPV must be eliminated on consolidation |
| E2 | Row 14 (revenue recognition) + Order Backlog tab | Revenue recognised at order signing — should be at nacelle delivery under IFRS 15 | Revenue recognition | IFRS 15 POC/completion method: revenue for manufactured goods on delivery, not contract signing |
| E3 | P&L row 24 (fit-out CapEx) | €11M factory fit-out expensed in P&L in Q1 2025 — should be capitalised as PPE | CapEx vs OpEx | Factory fit-out is capital investment; expensing destroys Q1 P&L and understates asset base |
| E4 | Working Capital tab row 9 | Change in WC shown (€11M gap from revenue-at-signing creating debtors before cash) but not included in Cash Flow Statement | Cash flow | Working capital build not in CF statement; cash flow significantly overstated |
| E5 | Rows 7-8 (material costs) | Steel €820/t and CFRP €18/kg hardcoded at 2024 spot — no escalation, no supply chain risk | Cost assumption | Steel and CFRP are volatile commodities; flat costs across 10-year model with no escalation |

**Structural challenge:** Columns Q1-Q8 (quarters) then annual columns (2027-2035) — mixed frequency. Corporate P&L structure (not project finance). Working Capital tab is separate from CF statement. Order Backlog tab exists but backlog is not integrated into revenue timing. Covenant Tracker tab is standalone.

---

## Summary Statistics

| Error Category | Count | Models affected |
|---|---|---|
| DSCR calculation (EBITDA vs CFADS) | 3 | 01, 03, 06 |
| Technology benchmark violation | 8 | 01, 03, 04, 06, 07, 08 |
| Jurisdiction error (wrong tax credit / instrument) | 4 | 01(tax), 05(REGO), 07(IRA), 09(IRA) |
| Grant accounting | 3 | 02, 04, 04 |
| Revenue double-count | 2 | 02, 05 |
| Metric framework (SaaS on hardware) | 3 | 06 |
| Model completeness (missing debt) | 2 | 04, 06 |
| Carbon/revenue accounting | 2 | 09, 10 |
| CapEx vs OpEx | 2 | 01(stack), 10 |
| Scenario construction | 1 | 05 |
| Cost completeness | 2 | 09(T&S), 10(WC) |
| Accounting (consolidation / depreciation) | 3 | 06, 08, 10 |
| Revenue recognition (IFRS 15) | 1 | 10 |
| CapEx benchmark (pre-inflation) | 2 | 04(contingency), 09 |

**Total embedded errors: 50 across 10 models (average 5 per model)**

---

## Structural Extraction Challenges (bonus scoring)

These are not financial errors — they test whether the extraction layer can even parse the model:

| Challenge | Model(s) | What should happen |
|---|---|---|
| Transposed axis (years as rows) | 02 | Parser identifies transposed orientation; maps correctly |
| Hidden rows with assumptions | 06 | Parser flags hidden assumption rows; reads cell values from hidden rows |
| Monthly → Annual rollup | 03 | Parser identifies both frequencies; links monthly to annual correctly |
| 9-tab dependency chain | 04 | Parser traverses tab references; builds dependency graph |
| No formulas (fully hardcoded) | 09 | Parser flags absence of formulas as audit risk |
| Quarterly + Annual mixed frequency | 10 | Parser identifies period type per column (Q vs FY) |
| Fiscal year (Apr-Mar) ≠ calendar year | 09 | Parser identifies FY26/27 as April 2026 – March 2027 |
| Three scenario blocks in one sheet | 05, 07 | Parser identifies scenario columns from merged row-2 headers |
| Interco eliminations required | 08 | Parser flags consolidation without elimination |
| SaaS metrics masking PF model | 06 | Parser identifies SaaS section as non-financial-model content |
| Mixed £/€ currencies | 09 | Parser normalises to single currency or flags currency inconsistency |

---

## Scoring Rubric

**Tier A — Error Detection (primary)**
- 1 point per correctly identified error (max 50)
- -0.5 per false positive (model flagged something that is correct)

**Tier B — Structural Navigation (secondary)**
- 1 point per structural challenge correctly handled
- Score 0 if extraction fails entirely on a given model

**Tier C — Explanation Quality**
- 0.5 point if flagged error includes correct explanation of why it is wrong
- 0.5 point if flagged error includes benchmark / correct value

**Target score for production-ready system: ≥ 35/50 Tier A + ≥ 8/11 Tier B**

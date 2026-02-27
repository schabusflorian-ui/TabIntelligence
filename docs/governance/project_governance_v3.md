# Project Governance Summary v3.0

## Guided Hybrid Architecture — Quality and Accountability

---

# What Changed from v2.0

| Aspect | v2.0 | v3.0 |
|--------|------|------|
| Agents | 12 + 3 sub-agents | **9 agents** |
| Existential challenges | 3 (Mapping, Lineage, Add-in) | **2 (Lineage, Add-in)** |
| Mapping governance | Week 10 accuracy gate | **Claude handles, we validate** |
| Timeline | 18 weeks | **10-12 weeks** |
| Key risk | Mapping accuracy | **Claude reliability, lineage completeness** |

---

# The Four Laws (Unchanged)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           THE FOUR LAWS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. END-TO-END OR NOTHING                                                  │
│     If you can't demo it, it doesn't work.                                 │
│                                                                             │
│  2. TEST WHAT MATTERS                                                      │
│     Features without tests are not done.                                   │
│                                                                             │
│  3. PROACTIVE COMMUNICATION                                                │
│     Bad news early is better than bad news late.                           │
│                                                                             │
│  4. HONEST STATUS REPORTING                                                │
│     "Almost done" is not a status.                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Existential Challenges (Reduced to 2)

## Why Mapping Is No Longer Existential

In v2, mapping accuracy was existential because we were building a custom mapping engine. If our engine couldn't reach 90% accuracy, the product failed.

In v3, Claude handles mapping with our guidance. Claude already understands financial terms. Our job is to:
1. Provide good prompts and taxonomy
2. Validate the output
3. Learn from corrections

**The risk shifted from "can we build it?" to "can we guide it well?"**

## The Two Existential Challenges

| Challenge | Agent | Target | Why It's Existential |
|-----------|-------|--------|---------------------|
| **Lineage 100%** | 6 | 100% completeness | No lineage = no trust = no adoption |
| **Add-in Works** | 8 | All platforms | No add-in = no users |

---

# Document Structure

```
project/
├── README.md                        # Product overview, The Four Laws
├── CONTRIBUTING.md                  # Workflow, commits, PR requirements
├── AGENTS.md                        # 9 agents, contracts
│
├── .github/
│   └── PULL_REQUEST_TEMPLATE.md     # Lineage verification required
│
├── docs/
│   ├── TESTING_MANIFEST.md          # Coverage requirements
│   ├── DEFINITION_OF_DONE.md        # Checklist
│   ├── GUIDED_EXTRACTION.md         # NEW: 5-stage pipeline docs
│   └── onboarding/
│       └── AGENT_ONBOARDING.md      # Day 1 reading
│
└── status/
    ├── WEEKLY_STATUS.md             # Per-agent updates (9 agents)
    ├── BLOCKERS.md                  # Active blockers
    ├── METRICS.md                   # Quality dashboard
    └── COST_TRACKING.md             # NEW: Claude API costs
```

---

# Library Requirements

## Required Versions

| Library | Min Version | Agent | Purpose | License |
|---------|-------------|-------|---------|---------|
| `openpyxl` | 3.1.0 | 3 | Excel read/write | MIT |
| `formulas` | 1.2.0 | 3 | Formula parsing | EUPL |
| `networkx` | 3.0 | 3, 6 | Dependency graph | BSD |
| `anthropic` | 0.18.0 | 3 | Claude API | MIT |
| `fastapi` | 0.109.0 | 2 | API framework | MIT |
| `sqlalchemy` | 2.0.0 | 1 | Database ORM | MIT |

## Version Pinning Policy

```
# pyproject.toml
dependencies = [
    "openpyxl>=3.1.0,<4.0",      # Pin major version
    "formulas>=1.2.0,<2.0",
    "networkx>=3.0,<4.0",
    "anthropic>=0.18.0",         # Allow minor updates
    "fastapi>=0.109.0,<1.0",
    "sqlalchemy>=2.0.0,<3.0",
]
```

## Dependency Update Policy

| Frequency | Action |
|-----------|--------|
| Weekly | Check for security updates |
| Monthly | Review minor version updates |
| Per release | Test full dependency upgrade |

---

# Governance by Challenge

## Challenge 1: Lineage 100% (EXISTENTIAL)

### Why It's Critical

> "If I can click a number and see where it came from, I'm sold." — Marcus (Partner)

Without lineage, users don't trust the data. Without trust, no adoption.

### Governance Mechanisms

| Mechanism | How It Works | Enforced By |
|-----------|--------------|-------------|
| **PR blocking** | No PR merges without lineage tests | CI/CD |
| **Completeness validator** | Runs after every extraction | Agent 3 |
| **Random audits** | PM checks provenance chains weekly | PM |
| **100% or fail** | Extraction fails if lineage incomplete | Agent 3 |

### PR Template Section (Required)

```markdown
## Lineage Verification (REQUIRED for data transformation PRs)

- [ ] This PR emits lineage events for all data transformations
- [ ] I have added tests verifying lineage events are emitted
- [ ] I have run the completeness validator locally

Example lineage emission in this PR:
```python
await lineage.emit(
    action='mapped',
    stage='mapping',
    target_id=item.id,
    ...
)
```

**If this section is empty, PR will be rejected.**
```

### Lineage Emission Checklist

| Agent | Events Must Emit | Required? |
|-------|------------------|-----------|
| 3 (Orchestrator) | `parsed`, `triaged`, `structured`, `mapped` | ✅ Yes |
| 5 (Validator) | `validated`, `flagged` | ✅ Yes |
| 7 (Calibrator) | `calibrated` | ✅ Yes |
| 9 (Dashboard) | `corrected`, `approved` | ✅ Yes |

---

## Challenge 2: Add-in Works (EXISTENTIAL)

### Why It's Critical

> "Just make it work in Excel. I don't want to learn another tool." — Sarah (Associate)

If the add-in doesn't work on analysts' machines, they won't use the product.

### Governance Mechanisms

| Mechanism | How It Works | Enforced By |
|-----------|--------------|-------------|
| **Weekly cross-platform testing** | Test on Windows, Mac, Web | Agent 8 |
| **User journey testing** | Full upload→review flow | Week 11 gate |
| **Platform matrix** | Track status per platform | Weekly status |

### Cross-Platform Matrix (Weekly Update)

```markdown
# Add-in Cross-Platform Status — Week N

| Feature | Windows | Mac | Excel Online | Notes |
|---------|---------|-----|--------------|-------|
| Task pane loads | ✅ | ✅ | ✅ | |
| Authentication | ✅ | ✅ | ⚠️ | SSO issue |
| File upload | ✅ | ✅ | ✅ | |
| Progress display | ✅ | ✅ | ✅ | |
| Results import | ✅ | ✅ | ✅ | |
| Provenance panel | ✅ | ⚠️ | ✅ | Layout issue |
| Custom functions | ✅ | ✅ | ❌ | Not supported |

Legend: ✅ Working | ⚠️ Issue (documented) | ❌ Not supported/broken
```

---

# Quality Gates (Simplified)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ GATE 1: FOUNDATION (Week 3)                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ □ Database schema complete                                                 │
│ □ API handles file upload                                                  │
│ □ Job queue working                                                        │
│ □ Taxonomy seeded (100+ items)                                             │
│ □ Lineage schema ready                                                     │
│                                                                             │
│ Failure: Extend Phase 1                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ GATE 2: PIPELINE (Week 6)                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ □ All 5 stages execute (parse → verify)                                    │
│ □ Works on 5 test models                                                   │
│ □ Claude responses parsed correctly                                        │
│ □ Errors handled gracefully                                                │
│                                                                             │
│ Failure: Debug pipeline, extend Phase 2                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ★ GATE 3: ACCURACY + LINEAGE (Week 8) — CRITICAL ★                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ □ Extraction accuracy >80% on Tier 1                                       │
│ □ Lineage 100% complete                                                    │
│ □ Calibration working (ECE <0.10)                                          │
│ □ Entity patterns saving/loading                                           │
│                                                                             │
│ If accuracy <70%: Tune prompts, check taxonomy coverage                    │
│ If lineage <100%: STOP, fix before proceeding                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ★ GATE 4: ADD-IN (Week 11) — EXISTENTIAL ★                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ □ Add-in works on Windows                                                  │
│ □ Add-in works on Mac                                                      │
│ □ Upload → extract → import flow complete                                  │
│ □ Provenance panel functional                                              │
│                                                                             │
│ Failure: Delay launch, debug platform issues                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ GATE 5: LAUNCH (Week 12)                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ □ 10 real models processed successfully                                    │
│ □ Accuracy >85% on Tier 1                                                  │
│ □ Lineage 100% complete                                                    │
│ □ Review queue + corrections working                                       │
│ □ Full user journey tested                                                 │
│ □ Cost per model <$0.75                                                    │
│                                                                             │
│ Failure: Extend hardening                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# New: Claude API Governance

Since we now depend on Claude API, we need to track usage and costs.

## Cost Tracking Template

```markdown
# Claude API Cost Tracking — Week N

## Weekly Summary
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Models processed | 45 | — | — |
| Total tokens (input) | 5.4M | — | — |
| Total tokens (output) | 2.3M | — | — |
| Total cost | $21.30 | — | — |
| Avg cost per model | $0.47 | <$0.75 | ✅ |

## Cost by Stage
| Stage | Avg Tokens | Avg Cost | % of Total |
|-------|------------|----------|------------|
| Parsing | 70K | $0.17 | 36% |
| Triage | 7K | $0.02 | 4% |
| Structure | 30K | $0.09 | 19% |
| Mapping | 45K | $0.14 | 30% |
| Verification | 20K | $0.05 | 11% |

## Anomalies
- Model X cost $2.30 (unusual — 50 sheets, investigated)
```

## Claude Reliability Tracking

```markdown
# Claude API Reliability — Week N

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| API calls | 225 | — | — |
| Successful | 223 | — | — |
| Rate limited | 1 | <5 | ✅ |
| Parse errors | 1 | <3 | ✅ |
| Timeouts | 0 | <2 | ✅ |
| Success rate | 99.1% | >98% | ✅ |

## Issues This Week
- 1 parse error on Model Y (malformed JSON, retry succeeded)
```

---

# Weekly Status Template (9 Agents)

```markdown
# Weekly Status — Week N

## Quick Health Check

| Metric | Status | Target | Notes |
|--------|--------|--------|-------|
| Extraction accuracy (Tier 1) | 83% | >85% | Improving |
| Lineage completeness | 100% | 100% | ✅ |
| Claude cost/model | $0.52 | <$0.75 | ✅ |
| Add-in platforms | 2/3 | 3/3 | Web pending |
| Open blockers | 1 | 0 | ⚠️ |

---

## Agent Updates

### Agent 1: Database
| Deliverable | Status | Evidence |
|-------------|--------|----------|
| D1.x | ✅ Done | PR #XX |

### Agent 2: API & Infrastructure
| Deliverable | Status | Evidence |
|-------------|--------|----------|
| D2.x | 🔄 80% | PR #XX |

### Agent 3: Extraction Orchestrator
| Deliverable | Status | Evidence |
|-------------|--------|----------|
| D3.x | 🔄 70% | PR #XX |

**Pipeline Metrics:**
- Models processed this week: 12
- Avg processing time: 8.3 min
- Avg cost: $0.52

### Agent 4: Guidelines Manager
| Deliverable | Status | Evidence |
|-------------|--------|----------|
| D4.x | ✅ Done | PR #XX |

**Taxonomy Coverage:**
- Items: 104
- Entity patterns: 45 (across 3 entities)

### Agent 5: Validator
| Deliverable | Status | Evidence |
|-------------|--------|----------|
| D5.x | 🔄 90% | PR #XX |

### Agent 6: Lineage (EXISTENTIAL)
| Metric | Value | Target |
|--------|-------|--------|
| Completeness | 100% | 100% ✅ |
| Query latency | 320ms | <500ms ✅ |

### Agent 7: Calibrator
| Metric | Value | Target |
|--------|-------|--------|
| ECE | 0.07 | <0.08 ✅ |
| Auto-approve rate | 78% | >75% ✅ |

### Agent 8: Excel Add-in (EXISTENTIAL)
| Platform | Status |
|----------|--------|
| Windows | ✅ Working |
| Mac | ⚠️ Layout issue |
| Excel Online | 🔄 Testing |

### Agent 9: Dashboard
| Deliverable | Status | Evidence |
|-------------|--------|----------|
| D9.x | ⬜ Not started | — |

---

## Blockers

| ID | Description | Owner | Since | Duration |
|----|-------------|-------|-------|----------|
| B001 | Mac add-in layout | Agent 8 | Mon | 2d |

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Mac add-in delayed | Medium | Medium | Parallel debugging |
```

---

# Definition of Done (v3)

## Standard Deliverable

```markdown
A deliverable is DONE when:
- [ ] Code is written and self-reviewed
- [ ] Unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] Documentation updated
- [ ] PR reviewed and approved
- [ ] Deployed to staging
- [ ] Demonstrated working end-to-end
```

## Data Transformation Deliverable (Agents 3, 5, 7)

```markdown
Additional requirements:
- [ ] Lineage events emitted for all transformations
- [ ] Lineage completeness validator passes
- [ ] Sample provenance chains verified manually
```

## Existential Deliverable (Agents 6, 8)

```markdown
Additional requirements for existential agents:

Agent 6 (Lineage):
- [ ] 100% completeness on test extractions
- [ ] Query latency <500ms verified

Agent 8 (Add-in):
- [ ] Tested on Windows
- [ ] Tested on Mac
- [ ] Cross-platform matrix updated
- [ ] User journey tested end-to-end
```

---

# Escalation Process

## Standard Blockers

```
< 1 hour blocked → Keep working, try alternatives
= 1 hour blocked → Add to BLOCKERS.md + notify PM
= 4 hours blocked → PM schedules sync
= 8 hours blocked → Escalate, consider help
```

## Existential Challenge Blockers

```
Lineage gap found:
→ STOP merging until fixed
→ Root cause analysis within 4 hours
→ All agents audit their emissions

Add-in not working on platform:
→ Severity: EXISTENTIAL
→ Cross-platform expert within 24 hours
→ Consider platform de-scoping if unfixable

Claude API issues:
→ If >5% failure rate: investigate immediately
→ If cost >$1.50/model: review prompts
→ If parse errors >5%: improve output validation
```

---

# One-Page Governance Cheat Sheet

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GOVERNANCE CHEAT SHEET v3                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  THE FOUR LAWS:                                                            │
│  1. End-to-end or nothing                                                  │
│  2. Test what matters                                                      │
│  3. Proactive communication                                                │
│  4. Honest status reporting                                                │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  EXISTENTIAL CHALLENGES:                                                   │
│  • Lineage 100%          → Agent 6      → PR blocking                      │
│  • Add-in works          → Agent 8      → Weekly testing                   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DAILY:                                                                    │
│  • Update WEEKLY_STATUS.md                                                 │
│  • If blocked >1 hour → BLOCKERS.md + notify PM                            │
│  • Run tests before every push                                             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BEFORE EVERY PR:                                                          │
│  • Tests pass locally                                                      │
│  • Lineage events emitted (if data transformation)                         │
│  • PR template completely filled                                           │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CRITICAL GATES:                                                           │
│  • Week 6: Pipeline E2E                                                    │
│  • Week 8: Accuracy >80%, Lineage 100%                                     │
│  • Week 11: Add-in cross-platform                                          │
│  • Week 12: 10 models, full journey                                        │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  GUIDED HYBRID PRINCIPLE:                                                  │
│  • We provide: Taxonomy, patterns, rules, prompts                          │
│  • Claude does: Reading, understanding, reasoning                          │
│  • We add: Lineage, persistence, learning                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Project Governance Summary v3.0 — Guided Hybrid Architecture — February 19, 2026*

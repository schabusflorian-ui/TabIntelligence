# Excel Interaction UX: Option A vs Option B

**Date**: 2026-03-21 | **Status**: Research

## 1. Executive Summary

DebtFund needs to let analysts visualize cell-level extraction mappings overlaid on the original spreadsheet layout. Two approaches exist: rendering the spreadsheet in our web app (Option A) or building an Excel add-in (Option B). Both consume the same cell mapping API (`GET /jobs/{id}/cells`).

**Recommendation**: Build Option A first (Phase 2a, weeks 1-3) using FortuneSheet. Design the Option B add-in interface later (Phase 2b) once the API surface is proven. This avoids Microsoft deployment review delays and keeps the full UX under our control during iteration.

## 2. Comparison Table

| Dimension            | Option A: In-App Spreadsheet        | Option B: Excel Add-In              |
|----------------------|--------------------------------------|--------------------------------------|
| **Fidelity**         | ~90% (no charts, no formula exec)    | 100% (native Excel rendering)        |
| **Deployment**       | Ships with web app, zero install     | Requires Excel; MS review 2-4 weeks  |
| **Build time**       | 2-3 weeks                            | 3-4 weeks (incl. review/sideloading) |
| **Codebase**         | React, shared repo                   | Office.js, separate project           |
| **Overlay UX**       | Full control (side panels, tooltips) | Task pane only (limited width)        |
| **Offline use**      | No (web app)                         | Yes (with cached data)               |
| **Analyst workflow** | Browser tab alongside Excel          | Inside Excel, no context switch       |
| **Maintenance**      | One stack (React + TS)               | Two stacks (React + Office.js)        |
| **Annual cost**      | $0 (MIT libraries)                   | $0 (Office.js is free)               |

## 3. Library Evaluation (Option A)

| Criteria          | FortuneSheet          | Handsontable          | AG Grid (Community)    | react-datasheet      |
|-------------------|-----------------------|-----------------------|------------------------|----------------------|
| **License**       | MIT                   | Commercial ($1,590/dev/yr) | MIT (Community)   | MIT                  |
| **Excel import**  | Built-in (.xlsx)      | Plugin                | None (manual parse)    | None                 |
| **Cell styling**  | Full (bg, border, font)| Full                 | Full                   | Basic                |
| **Max cells**     | ~500k (virtual scroll)| ~1M                  | ~1M (enterprise only)  | ~10k                 |
| **React support** | Native component      | Wrapper               | Native component       | Native               |
| **Merged cells**  | Yes                   | Yes                   | No                     | No                   |
| **TypeScript**    | Yes                   | Yes                   | Yes                    | No                   |
| **Freeze panes**  | Yes                   | Yes                   | Yes (pinning)          | No                   |
| **Maturity**      | Medium (fork of Luckysheet) | High            | High                   | Low (unmaintained)   |

**Selection: FortuneSheet.** It is the only MIT-licensed option with native .xlsx import, merged cells, and virtual scrolling. AG Grid Community lacks Excel import. Handsontable works but adds $1,590/dev/yr. react-datasheet lacks the scale and features needed for real financial spreadsheets.

## 4. Technical Architecture

### Option A: In-App Spreadsheet View

```
Browser
+------------------------------------------------------+
|  React App                                            |
|  +------------------+  +---------------------------+  |
|  | FortuneSheet     |  | Side Panel                |  |
|  | - loads .xlsx    |  | - canonical_name          |  |
|  | - cells colored: |  | - confidence score        |  |
|  |   green/yellow/  |  | - original_label          |  |
|  |   red by status  |  | - correction UI           |  |
|  | - onClick(cell)  |->| - provenance chain        |  |
|  +------------------+  +---------------------------+  |
+------------------------------------------------------+
        |                          |
        | GET /jobs/{id}/cells     | POST /jobs/{id}/corrections
        v                          v
+------------------------------------------------------+
|  FastAPI Backend                                      |
|  Cell Mapping API (B2.3)                              |
|  - GET  /jobs/{id}/cells          (paginated list)    |
|  - GET  /jobs/{id}/cells/stats    (per-sheet stats)   |
|  - GET  /jobs/{id}/cells/{sheet}/{ref} (single cell)  |
+------------------------------------------------------+
```

**Data flow**: Frontend fetches the original .xlsx from S3 for rendering, then overlays `CellMappingItem` data (mapping_status, confidence, canonical_name) onto each cell as background colors and click handlers.

### Option B: Excel Add-In (Office.js)

```
Excel Desktop / Excel Online
+------------------------------------------------------+
|  Workbook (user's file, full fidelity)                |
|  +--------------------------------------------------+|
|  | Cells highlighted via conditional formatting /    ||
|  | Range.format API based on mapping_status          ||
|  +--------------------------------------------------+|
|  +--------------------+                               |
|  | Task Pane (250px)  |  <- Office.js React app       |
|  | - mapping details  |                               |
|  | - correction form  |                               |
|  | - confidence badge |                               |
|  +--------------------+                               |
+------------------------------------------------------+
        |
        | Same cell mapping API
        v
    FastAPI Backend
```

**Deployment**: Sideloaded for dev; submitted to AppSource or deployed via Microsoft 365 Admin Center for production. Review process takes 2-4 weeks. Industry precedent: DataSnipper ships a similar add-in for audit workpapers.

## 5. API Contract (Shared)

Both options consume the existing endpoints from B2.3:

| Endpoint | Purpose | Key Fields |
|----------|---------|------------|
| `GET /jobs/{id}/cells?sheet_name=&mapping_status=` | Paginated cell list | `cell_ref`, `mapping_status`, `confidence`, `canonical_name` |
| `GET /jobs/{id}/cells/stats` | Per-sheet counters | `mapped`, `unmapped`, `header`, `skipped` |
| `GET /jobs/{id}/cells/{sheet}/{ref}` | Single cell lookup | Full `CellMappingItem` with `fact_id`, `formula_text` |

Color mapping rule (both options):
- **Green** (`#c6efce`): `mapping_status == "mapped"` and `confidence >= 0.8`
- **Yellow** (`#ffeb9c`): `mapping_status == "mapped"` and `confidence < 0.8`
- **Red** (`#ffc7ce`): `mapping_status == "unmapped"`
- **Gray** (`#d9d9d9`): `mapping_status in ("header", "skipped")`

## 6. Phased Rollout Plan

| Phase | Scope | Timeline | Deliverable |
|-------|-------|----------|-------------|
| **2a** | In-app spreadsheet (FortuneSheet) | Weeks 1-3 | Cell overlay, side panel, correction UI |
| **2a.1** | Performance tuning | Week 3 | Virtual scroll for sheets > 100k cells |
| **2b** | Excel add-in design | Week 4 | Office.js prototype, sideload testing |
| **2b.1** | Add-in production | Weeks 5-8 | AppSource submission, admin deployment |

Phase 2a ships a functional review UI with no external dependencies. Phase 2b layers on the Excel-native experience for analysts who prefer it. Both phases share the cell mapping API -- no backend changes needed between phases.

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| FortuneSheet rendering gaps (charts, pivot tables) | Medium | Strip charts on import; show warning banner for unsupported features |
| Large files (>5 MB, >50 sheets) | High | Lazy-load sheets; paginate cell mappings (existing `limit`/`offset`) |
| Microsoft review rejection | Medium | Sideload for internal use; defer AppSource until UX is stable |
| Two codebases diverge | Low | Shared API contract; Option B task pane reuses Option A's React components |

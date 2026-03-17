// Provenance Components — Inline summary + full detail panel
// "Lineage is the moat." Every data point traces back to its source.
import { apiGet } from '../api.js';
import { esc, timeAgo } from '../state.js';
import { loadingPlaceholder } from './loading.js';

/**
 * Render a 3-line inline provenance summary from item.provenance data.
 * No API call — uses data already present on the export JSON item.
 *
 * @param {Object} item - Line item with optional .provenance property
 * @returns {string} HTML string
 */
export function renderProvenanceSummary(item) {
  if (!item || !item.provenance) {
    return '<div class="prov-summary prov-empty">Provenance data not available.</div>';
  }

  const prov = item.provenance;
  let lines = [];

  // Line 1: Source cell reference
  const source = prov.source_cells && prov.source_cells.length > 0 ? prov.source_cells[0] : null;
  if (source) {
    const sheet = source.sheet || source.sheet_name || '';
    const cell = source.cell_ref || source.cell || '';
    lines.push(
      '<span class="prov-line">' +
      '<span class="prov-key">Source:</span> ' +
      esc(sheet) +
      (cell ? ', Cell <code class="prov-mono">' + esc(cell) + '</code>' : '') +
      '</span>'
    );
  } else {
    lines.push('<span class="prov-line"><span class="prov-key">Source:</span> <span class="text-secondary">unknown</span></span>');
  }

  // Line 2: Mapping provenance
  const mapping = prov.mapping;
  if (mapping) {
    const origLabel = mapping.original_label || item.original_label || '';
    const canonical = mapping.canonical_name || item.canonical_name || '';
    const method = mapping.method || mapping.match_type || '';
    lines.push(
      '<span class="prov-line">' +
      '<span class="prov-key">Mapped:</span> ' +
      '\u2018' + esc(origLabel) + '\u2019 \u2192 <code class="prov-mono">' + esc(canonical) + '</code>' +
      (method ? ' via <span class="prov-method">' + esc(method) + '</span>' : '') +
      '</span>'
    );
  } else {
    lines.push('<span class="prov-line"><span class="prov-key">Mapped:</span> <span class="text-secondary">no mapping data</span></span>');
  }

  // Line 3: Validation summary
  const validation = prov.validation;
  if (validation) {
    const rules = validation.rules_applied || [];
    const allPassed = validation.all_passed != null ? validation.all_passed : true;
    const flagCount = validation.flag_count || 0;
    const ruleCount = rules.length || validation.rules_count || 0;
    const passText = allPassed ? 'all passed' : flagCount + ' flag' + (flagCount !== 1 ? 's' : '');
    lines.push(
      '<span class="prov-line">' +
      '<span class="prov-key">Validated:</span> ' +
      ruleCount + ' rule' + (ruleCount !== 1 ? 's' : '') + ', ' +
      '<span class="' + (allPassed ? '' : 'neg') + '">' + esc(passText) + '</span>' +
      '</span>'
    );
  } else {
    lines.push('<span class="prov-line"><span class="prov-key">Validated:</span> <span class="text-secondary">no validation data</span></span>');
  }

  return '<div class="prov-summary">' + lines.join('') + '</div>';
}

/**
 * Render a full right-side provenance detail panel with complete lineage.
 * Makes an API call to GET /api/v1/jobs/{jobId}/item-lineage/{canonical_name}.
 *
 * @param {HTMLElement} container - Parent element to attach the panel to (usually document.body)
 * @param {Object} item - Line item object
 * @param {string} jobId - Current job ID
 */
export function renderProvenancePanel(container, item, jobId) {
  // Remove any existing panel
  closeProvenancePanel();

  // Inject CSS (once)
  if (!document.getElementById('provenance-styles')) {
    const style = document.createElement('style');
    style.id = 'provenance-styles';
    style.textContent = getProvenanceCSS();
    document.head.appendChild(style);
  }

  // Create overlay + panel
  const overlay = document.createElement('div');
  overlay.className = 'prov-overlay';
  overlay.addEventListener('click', closeProvenancePanel);

  const panel = document.createElement('div');
  panel.className = 'prov-panel';
  panel.id = 'prov-panel';
  panel.addEventListener('click', e => e.stopPropagation());

  // Header
  const canonical = item.canonical_name || item.original_label || 'Item';
  panel.innerHTML =
    '<div class="prov-panel-header">' +
    '  <div>' +
    '    <p class="eyebrow">item lineage</p>' +
    '    <h3 class="prov-panel-title">' + esc(canonical) + '</h3>' +
    '  </div>' +
    '  <button class="prov-close-btn" aria-label="Close panel">' +
    '    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M4.5 4.5L11.5 11.5M11.5 4.5L4.5 11.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/></svg>' +
    '  </button>' +
    '</div>' +
    '<div class="prov-panel-body">' + loadingPlaceholder('Loading lineage...') + '</div>';

  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  // Close button handler
  panel.querySelector('.prov-close-btn').addEventListener('click', closeProvenancePanel);

  // Escape key handler
  const escHandler = (e) => {
    if (e.key === 'Escape') closeProvenancePanel();
  };
  document.addEventListener('keydown', escHandler);
  overlay.dataset.escHandler = 'true';
  overlay._escHandler = escHandler;

  // Fetch lineage data
  const encodedName = encodeURIComponent(item.canonical_name || '');
  apiGet('/api/v1/jobs/' + jobId + '/item-lineage/' + encodedName)
    .then(data => {
      const body = panel.querySelector('.prov-panel-body');
      if (!body) return;
      body.innerHTML = renderLineageChain(data, item);
    })
    .catch(err => {
      const body = panel.querySelector('.prov-panel-body');
      if (!body) return;
      body.innerHTML =
        '<div style="padding:16px;color:var(--color-text-secondary);font-size:12px">' +
        '<p>Could not load full lineage.</p>' +
        '<p style="font-size:11px;margin-top:8px;color:#A32626">' + esc(err.message) + '</p>' +
        '</div>';
    });
}

/**
 * Close the provenance panel if open.
 */
export function closeProvenancePanel() {
  const overlay = document.querySelector('.prov-overlay');
  if (overlay) {
    if (overlay._escHandler) {
      document.removeEventListener('keydown', overlay._escHandler);
    }
    overlay.remove();
  }
}

/**
 * Render the stage-by-stage transformation chain.
 */
function renderLineageChain(data, item) {
  const chain = data.chain || data.stages || data.transformations || [];
  if (chain.length === 0 && !data.source && !data.mapping) {
    return '<div class="text-secondary" style="padding:16px;font-size:12px">No lineage chain available for this item.</div>';
  }

  let html = '';

  // If the API returns a flat object with source/mapping/validation
  if (!chain.length && (data.source || data.mapping || data.validation)) {
    html += renderFlatLineage(data, item);
    return html;
  }

  // Chain view: each step is a transformation card
  html += '<div class="prov-chain">';
  for (let i = 0; i < chain.length; i++) {
    const step = chain[i];
    const isLast = i === chain.length - 1;

    html += '<div class="prov-step">';
    html += '  <div class="prov-step-dot"></div>';
    if (!isLast) {
      html += '  <div class="prov-step-line"></div>';
    }
    html += '  <div class="prov-step-content">';
    html += '    <div class="prov-step-header">';
    html += '      <span class="prov-step-stage">' + esc(step.stage || step.stage_name || 'Step ' + (i + 1)) + '</span>';
    if (step.timestamp || step.completed_at) {
      html += '      <span class="prov-step-time">' + esc(timeAgo(step.timestamp || step.completed_at)) + '</span>';
    }
    html += '    </div>';
    if (step.action || step.description) {
      html += '    <div class="prov-step-action">' + esc(step.action || step.description) + '</div>';
    }

    // Step detail key-value pairs
    const details = step.details || step.data || {};
    const detailEntries = Object.entries(details);
    if (detailEntries.length > 0) {
      html += '    <div class="prov-step-details">';
      for (const [key, value] of detailEntries) {
        if (value == null) continue;
        const label = key.replace(/_/g, ' ');
        const displayVal = typeof value === 'object' ? JSON.stringify(value) : String(value);
        html += '<div class="prov-step-kv">';
        html += '  <span class="prov-step-k">' + esc(label) + '</span>';
        html += '  <span class="prov-step-v">' + esc(displayVal) + '</span>';
        html += '</div>';
      }
      html += '    </div>';
    }

    html += '  </div>';
    html += '</div>';
  }
  html += '</div>';

  return html;
}

/**
 * Render lineage from a flat source/mapping/validation structure.
 */
function renderFlatLineage(data, item) {
  let html = '<div class="prov-chain">';
  const steps = [];

  if (data.source) {
    steps.push({
      stage: 'Parsing',
      action: 'Extracted from source',
      details: data.source,
    });
  }
  if (data.triage) {
    steps.push({
      stage: 'Triage',
      action: 'Sheet classification',
      details: data.triage,
    });
  }
  if (data.mapping) {
    steps.push({
      stage: 'Mapping',
      action: 'Label mapped to canonical name',
      details: data.mapping,
    });
  }
  if (data.validation) {
    steps.push({
      stage: 'Validation',
      action: 'Validation rules applied',
      details: data.validation,
    });
  }
  if (data.enhancement) {
    steps.push({
      stage: 'Enhancement',
      action: 'Enhanced mapping applied',
      details: data.enhancement,
    });
  }

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const isLast = i === steps.length - 1;

    html += '<div class="prov-step">';
    html += '  <div class="prov-step-dot"></div>';
    if (!isLast) {
      html += '  <div class="prov-step-line"></div>';
    }
    html += '  <div class="prov-step-content">';
    html += '    <div class="prov-step-header">';
    html += '      <span class="prov-step-stage">' + esc(step.stage) + '</span>';
    html += '    </div>';
    html += '    <div class="prov-step-action">' + esc(step.action) + '</div>';

    const details = step.details || {};
    const entries = Object.entries(details);
    if (entries.length > 0) {
      html += '    <div class="prov-step-details">';
      for (const [key, value] of entries) {
        if (value == null) continue;
        const label = key.replace(/_/g, ' ');
        const displayVal = typeof value === 'object' ? JSON.stringify(value) : String(value);
        html += '<div class="prov-step-kv">';
        html += '  <span class="prov-step-k">' + esc(label) + '</span>';
        html += '  <span class="prov-step-v">' + esc(displayVal) + '</span>';
        html += '</div>';
      }
      html += '    </div>';
    }

    html += '  </div>';
    html += '</div>';
  }

  html += '</div>';
  return html;
}

/**
 * Provenance CSS — scoped, injected once.
 * Adheres to Meridian tokens and palette.
 */
function getProvenanceCSS() {
  return `
/* --- Provenance Summary (inline, 3-line) --- */
.prov-summary {
  font-size: 11.5px;
  color: var(--color-text-secondary);
  line-height: 1.65;
  padding: 8px 12px;
}

.prov-empty {
  font-style: italic;
  color: var(--color-text-tertiary);
}

.prov-line {
  display: block;
}

.prov-key {
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 11px;
}

.prov-mono {
  font-family: var(--font-mono);
  font-size: 10.5px;
  background: var(--color-background-secondary);
  padding: 1px 4px;
  border-radius: 3px;
  font-variant-numeric: tabular-nums;
}

.prov-method {
  font-size: 10.5px;
  background: #E3EEF8;
  color: #1A4D7A;
  padding: 1px 6px;
  border-radius: 100px;
  font-weight: 500;
}

/* --- Provenance Panel (slide-in from right) --- */
.prov-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.2);
  z-index: 900;
  animation: fadeIn 0.15s ease;
}

.prov-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 320px;
  max-width: 90vw;
  height: 100vh;
  background: var(--color-background-primary);
  border-left: 0.5px solid var(--color-border-tertiary);
  z-index: 901;
  display: flex;
  flex-direction: column;
  animation: slideInRight 0.25s ease;
  overflow: hidden;
}

.prov-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 0.5px solid var(--color-border-tertiary);
  flex-shrink: 0;
}

.prov-panel-header .eyebrow {
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  margin-bottom: 2px;
}

.prov-panel-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin: 0;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  word-break: break-word;
}

.prov-close-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--border-radius-md);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.prov-close-btn:hover {
  background: var(--color-background-secondary);
  color: var(--color-text-primary);
}

.prov-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

/* --- Lineage Chain (vertical steps) --- */
.prov-chain {
  padding: 16px;
}

.prov-step {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  grid-template-rows: auto auto;
  gap: 0 12px;
  position: relative;
}

.prov-step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1D6B9F;
  margin-top: 5px;
  justify-self: center;
  grid-column: 1;
  grid-row: 1;
  z-index: 1;
}

.prov-step-line {
  width: 2px;
  background: var(--color-border-tertiary);
  justify-self: center;
  grid-column: 1;
  grid-row: 2;
  min-height: 12px;
  margin: 2px 0;
}

.prov-step-content {
  grid-column: 2;
  grid-row: 1 / 3;
  padding-bottom: 16px;
}

.prov-step-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.prov-step-stage {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.prov-step-time {
  font-size: 10.5px;
  color: var(--color-text-tertiary);
}

.prov-step-action {
  font-size: 11.5px;
  color: var(--color-text-secondary);
  margin-top: 2px;
  line-height: 1.5;
}

.prov-step-details {
  margin-top: 8px;
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-md);
  padding: 8px 10px;
}

.prov-step-kv {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 0;
  font-size: 10.5px;
}

.prov-step-k {
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.prov-step-v {
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
  text-align: right;
  word-break: break-word;
}

/* Full lineage link inside provenance row */
.prov-full-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  color: #1D6B9F;
  cursor: pointer;
  margin-top: 6px;
  border: none;
  background: none;
  padding: 0;
}

.prov-full-link:hover {
  text-decoration: underline;
}

/* --- Provenance row in line items table --- */
tr.provenance-row td {
  padding: 0;
  background: var(--color-background-secondary);
  border-bottom: 0.5px solid var(--color-border-tertiary);
}

tr.provenance-row:hover td {
  background: var(--color-background-secondary);
}
`;
}

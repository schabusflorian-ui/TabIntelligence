// Job Detail Page — Results with tabs: Line Items, Triage, Validation, Lineage, Corrections
import { apiGet, apiFetch, apiPost } from '../api.js';
import { esc, formatNum, formatFinancial, downloadBlob, timeAgo } from '../state.js';
import { navigate } from '../router.js';
import { renderTabs } from '../components/tabs.js';
import { renderBreadcrumb } from '../components/breadcrumb.js';
import { confidenceBadge, qualityBadge, statusBadge, tierBadge } from '../components/badge.js';
import { loadingPlaceholder, errorState } from '../components/loading.js';
import { showToast } from '../components/toast.js';
import { confirm, showModal, prompt as promptModal } from '../components/modal.js';
import { renderTimeline } from '../components/timeline.js';
import { renderProvenanceSummary, renderProvenancePanel, closeProvenancePanel } from '../components/provenance.js';

let currentJobId = null;
let resultData = null;
let pollTimer = null;
let pollInterval = 2000;
let pollStartTime = null;
const POLL_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes
let pendingCorrections = {};
let activeDropdown = null;
let selectedPeriods = new Set();
let tabsController = null;
let currentJob = null;
let bulkEditMode = false;
let bulkSelectedTaxonomy = null;
let _bulkTaxTimer = null;
let _bulkTaxController = null;

// --- Unsaved Corrections Guard ---
function beforeUnloadHandler(e) {
  if (Object.keys(pendingCorrections).length > 0) {
    e.preventDefault();
    e.returnValue = '';
  }
}

function updateBeforeUnloadGuard() {
  if (Object.keys(pendingCorrections).length > 0) {
    window.addEventListener('beforeunload', beforeUnloadHandler);
  } else {
    window.removeEventListener('beforeunload', beforeUnloadHandler);
  }
}

/**
 * Check if user can leave the page. Returns true if no pending corrections,
 * or shows a confirm dialog and returns the user's choice.
 */
export function canLeave() {
  if (Object.keys(pendingCorrections).length === 0) return true;
  return window.confirm('You have unsaved corrections. Are you sure you want to leave?');
}

export async function render(container, params) {
  currentJobId = params.jobId;
  resultData = null;
  pendingCorrections = {};
  tabsController = null;
  currentJob = null;
  bulkEditMode = false;
  bulkSelectedTaxonomy = null;

  container.innerHTML = `
    <div class="content-header">
      <div id="jd-header-block">
        <div id="jd-eyebrow" class="eyebrow">Extraction</div>
        <h2 id="jd-title" class="page-title"><span class="skeleton skeleton-text" style="width:220px;height:20px;display:inline-block"></span></h2>
      </div>
      <div id="jd-actions"></div>
    </div>
    <div class="content-body">
      ${renderBreadcrumb([{ label: 'Extractions', route: '/extractions' }, { label: '\u00A0' }])}
      <div id="jd-progress" class="hidden">
        <div class="card" style="margin-bottom:var(--space-4)">
          <h3 style="margin-bottom:var(--space-3)">Extraction Progress</h3>
          <div class="progress-bar"><div id="jd-progress-fill" class="progress-fill"></div></div>
          <p id="jd-progress-text" class="progress-text">Starting...</p>
        </div>
      </div>
      <div id="jd-error" class="hidden"></div>
      <div id="jd-results" class="hidden">
        <div id="jd-summary" class="stats-grid" style="margin-bottom:var(--space-4)"></div>
        <div id="jd-review-banner" class="hidden"></div>
        <div id="jd-suggestions" class="hidden"></div>
        <div id="jd-tabs"></div>
      </div>
    </div>
  `;

  // Load job status
  await loadJob();
}

async function loadJob() {
  try {
    const job = await apiGet('/api/v1/jobs/' + currentJobId);
    currentJob = job;
    updateHeader(job);

    if (job.status === 'completed' || job.status === 'needs_review') {
      await loadResults(job);
    } else if (job.status === 'failed') {
      showError(job.error || 'Extraction failed');
    } else {
      // Processing/pending — show progress and poll
      showProgress(job);
      startPolling();
    }
  } catch (err) {
    showError(err.message);
  }
}

function updateHeader(job) {
  // Eyebrow: "Extraction . [status]"
  const eyebrow = document.getElementById('jd-eyebrow');
  if (eyebrow) {
    const statusLabel = job.status ? job.status.replace(/_/g, ' ') : '';
    eyebrow.textContent = 'Extraction \u00B7 ' + statusLabel;
  }

  // Title: filename in DM Serif Display (class page-title already set)
  const title = document.getElementById('jd-title');
  if (title) title.textContent = job.filename || 'Extraction';

  // Update breadcrumb with entity context if available
  const bc = document.querySelector('.breadcrumb');
  if (bc) {
    let breadcrumbItems;
    if (job.entity_name || job.entity_id) {
      const entityLabel = job.entity_name || ('Entity ' + (job.entity_id || '').slice(0, 8));
      const entityRoute = job.entity_id ? '/entities/' + job.entity_id : null;
      breadcrumbItems = [
        { label: 'Entities', route: '/entities' },
        { label: entityLabel, route: entityRoute },
        { label: job.filename || currentJobId.slice(0, 8) },
      ];
    } else {
      breadcrumbItems = [
        { label: 'Extractions', route: '/extractions' },
        { label: job.filename || currentJobId.slice(0, 8) },
      ];
    }
    bc.innerHTML = renderBreadcrumb(breadcrumbItems).replace(/<\/?nav[^>]*>/g, '');
  }
}

function showProgress(job) {
  const progressEl = document.getElementById('jd-progress');
  const fill = document.getElementById('jd-progress-fill');
  const text = document.getElementById('jd-progress-text');
  progressEl.classList.remove('hidden');

  const pct = job.progress_percent || 0;
  fill.style.width = Math.min(pct, 95) + '%';

  const stageNames = {
    parsing: 'Parsing Excel',
    triage: 'Classifying Sheets',
    mapping: 'Mapping Labels',
    validation: 'Validating Data',
    enhanced_mapping: 'Refining Mappings',
  };
  const stageName = stageNames[job.current_stage] || job.current_stage || 'Processing';
  if (job.stages_completed != null) {
    text.textContent = `Stage ${job.stages_completed} of ${job.total_stages || 5}: ${stageName}`;
  } else {
    text.textContent = stageName + '...';
  }
}

function startPolling() {
  pollInterval = 2000;
  pollStartTime = Date.now();
  poll();
}

async function poll() {
  if (!currentJobId) return;

  // Check for polling timeout
  if (pollStartTime && (Date.now() - pollStartTime) > POLL_TIMEOUT_MS) {
    document.getElementById('jd-progress').classList.add('hidden');
    showError('Job appears stuck — it has been processing for over 10 minutes. You can retry the extraction.');
    return;
  }

  try {
    const job = await apiGet('/api/v1/jobs/' + currentJobId);

    if (job.status === 'completed' || job.status === 'needs_review') {
      document.getElementById('jd-progress').classList.add('hidden');
      await loadResults(job);
      return;
    }
    if (job.status === 'failed') {
      document.getElementById('jd-progress').classList.add('hidden');
      showError(job.error || 'Extraction failed');
      return;
    }

    showProgress(job);
    pollInterval = Math.min(pollInterval * 1.5, 15000);
    pollTimer = setTimeout(poll, pollInterval);
  } catch (err) {
    showError(err.message);
  }
}

async function loadResults(job) {
  try {
    const res = await apiFetch('/api/v1/jobs/' + currentJobId + '/export?format=json');
    resultData = await res.json();
    renderResults(resultData, job);
    // Load review suggestions (non-blocking)
    loadReviewSuggestions();
  } catch (err) {
    showError(err.message);
  }
}

async function loadReviewSuggestions() {
  try {
    const data = await apiGet('/api/v1/jobs/' + currentJobId + '/review-suggestions');
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) return;

    const el = document.getElementById('jd-suggestions');
    if (!el) return;
    el.classList.remove('hidden');

    let html = '<div class="card" style="margin-bottom:var(--space-4);padding:var(--space-3)">';
    html += '<h4 style="margin-bottom:var(--space-2);font-size:var(--text-sm);text-transform:uppercase;letter-spacing:0.05em;color:var(--color-text-secondary)">Suggested for Review</h4>';
    html += '<div style="display:flex;gap:var(--space-2);overflow-x:auto;padding-bottom:var(--space-2)">';

    for (const s of suggestions) {
      const confClass = s.confidence >= 0.8 ? 'badge-high' : s.confidence >= 0.5 ? 'badge-mid' : 'badge-low';
      const reasonTags = s.reasons.map(r => '<span class="badge badge-sm" style="font-size:10px;margin-right:2px">' + esc(r) + '</span>').join('');
      html += '<div class="suggestion-card" data-label="' + esc(s.original_label) + '" style="min-width:200px;max-width:280px;border:1px solid var(--color-border-subtle);border-radius:var(--radius);padding:var(--space-2);cursor:pointer;flex-shrink:0">';
      html += '<div style="font-size:var(--text-sm);font-weight:600;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="' + esc(s.original_label) + '">' + esc(s.original_label) + '</div>';
      html += '<div style="font-size:11px;color:var(--color-text-secondary);margin-bottom:4px"><code>' + esc(s.canonical_name) + '</code></div>';
      html += '<div style="display:flex;align-items:center;gap:var(--space-1);flex-wrap:wrap">';
      html += '<span class="badge ' + confClass + '" style="font-size:10px">' + (s.confidence * 100).toFixed(0) + '%</span>';
      html += reasonTags;
      html += '</div></div>';
    }

    html += '</div></div>';
    el.innerHTML = html;

    // Make suggestion cards clickable to scroll to item in line items
    el.querySelectorAll('.suggestion-card').forEach(card => {
      card.addEventListener('click', () => {
        const label = card.dataset.label;
        if (tabsController) tabsController.activateTab('line-items');
        setTimeout(() => {
          const rows = document.querySelectorAll('#jd-line-items-table tbody tr');
          for (const row of rows) {
            if (row.dataset && row.dataset.label === label) {
              row.scrollIntoView({ behavior: 'smooth', block: 'center' });
              row.classList.add('hl');
              setTimeout(() => row.classList.remove('hl'), 2000);
              break;
            }
          }
        }, 150);
      });
    });
  } catch (err) {
    console.warn('Could not load review suggestions:', err.message);
    const el = document.getElementById('jd-suggestions');
    if (el) {
      el.classList.remove('hidden');
      el.innerHTML = `<div style="padding:8px 12px;font-size:11px;color:var(--color-text-tertiary)">Review suggestions unavailable.</div>`;
    }
  }
}

function renderResults(data, job) {
  const resultsEl = document.getElementById('jd-results');
  resultsEl.classList.remove('hidden');

  // Summary stats
  renderSummary(data);

  // Review banner for needs_review
  if (job && job.status === 'needs_review') {
    renderReviewBanner();
  }

  // Tabs
  const tabsEl = document.getElementById('jd-tabs');
  tabsController = renderTabs(tabsEl, [
    { id: 'line-items', label: 'Line Items', render: (panel) => renderLineItemsTab(panel, data) },
    { id: 'triage', label: 'Triage', render: (panel) => renderTriageTab(panel, data) },
    { id: 'validation', label: 'Validation', render: (panel) => renderValidationTab(panel, data) },
    { id: 'lineage', label: 'Lineage', render: (panel) => renderLineageTab(panel) },
    { id: 'corrections', label: 'Corrections', render: (panel) => renderCorrectionsTab(panel) },
  ], 'line-items');

  // Export + re-extract actions
  const actionsEl = document.getElementById('jd-actions');
  actionsEl.innerHTML = `
    <button class="btn btn-sm" id="jd-export-json">Export JSON</button>
    <button class="btn btn-sm btn-secondary" id="jd-export-csv" style="margin-left:var(--space-2)">Export CSV</button>
    <button class="btn btn-sm btn-secondary" id="jd-reextract" style="margin-left:var(--space-2)">Re-extract</button>
  `;

  document.getElementById('jd-export-json').addEventListener('click', () => exportResults('json'));
  document.getElementById('jd-export-csv').addEventListener('click', () => exportResults('csv'));
  document.getElementById('jd-reextract').addEventListener('click', handleReextract);
}

function renderSummary(data) {
  const el = document.getElementById('jd-summary');
  const items = data.line_items || [];
  const val = data.validation || {};
  const quality = data.quality || {};
  const conf = val.overall_confidence;

  // Count items needing review: confidence < 0.8
  const needsReviewCount = items.filter(i => (i.confidence || 0) < 0.8).length;
  const reviewWarnClass = needsReviewCount > 0 ? ' stat-card-warn' : '';

  el.innerHTML = `
    <div class="stat-card"><span class="stat-value">${qualityBadge(quality)}</span><span class="stat-label">Quality</span></div>
    <div class="stat-card"><span class="stat-value">${(data.sheets || []).length}</span><span class="stat-label">Sheets</span></div>
    <div class="stat-card"><span class="stat-value">${items.length}</span><span class="stat-label">Line Items</span></div>
    <div class="stat-card"><span class="stat-value">${conf != null ? (conf * 100).toFixed(0) + '%' : 'N/A'}</span><span class="stat-label">Confidence</span></div>
    <div class="stat-card${reviewWarnClass}" id="jd-stat-needs-review" style="cursor:pointer"><span class="stat-value">${needsReviewCount}</span><span class="stat-label">Items Needing Review</span></div>
  `;

  // Make "Items Needing Review" clickable to jump to attention section
  const reviewCard = document.getElementById('jd-stat-needs-review');
  if (reviewCard) {
    reviewCard.addEventListener('click', () => {
      // Activate the Line Items tab
      if (tabsController) tabsController.activateTab('line-items');
      // Scroll to the needs-attention section
      setTimeout(() => {
        const attentionSection = document.getElementById('jd-needs-attention');
        if (attentionSection) {
          attentionSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          // Expand if collapsed
          if (attentionSection.classList.contains('collapsed')) {
            attentionSection.classList.remove('collapsed');
            const body = attentionSection.querySelector('.attention-body');
            if (body) body.style.display = '';
            const toggle = attentionSection.querySelector('.attention-toggle');
            if (toggle) toggle.textContent = '\u25BC';
          }
        }
      }, 100);
    });
  }
}

function renderReviewBanner() {
  const el = document.getElementById('jd-review-banner');
  el.classList.remove('hidden');
  el.innerHTML = `
    <div class="correction-banner">
      <span>This extraction needs review — quality gate did not pass.</span>
      <button class="btn btn-sm btn-success" id="jd-approve">Approve</button>
      <button class="btn btn-sm btn-danger" id="jd-reject">Reject</button>
    </div>
  `;
  document.getElementById('jd-approve').addEventListener('click', () => reviewJob('approve'));
  document.getElementById('jd-reject').addEventListener('click', () => reviewJob('reject'));
}

async function reviewJob(decision) {
  let reason = null;
  if (decision === 'reject') {
    reason = await promptModal('Reject Extraction', 'Optional: provide a rejection reason');
    if (reason === null) return; // cancelled
  }
  try {
    await apiPost('/api/v1/jobs/' + currentJobId + '/review', { decision, reason });
    showToast(`Extraction ${decision}d`, 'success');
    document.getElementById('jd-review-banner').classList.add('hidden');
  } catch (err) {
    showToast('Review failed: ' + err.message, 'error');
  }
}

// --- Line Items Tab ---
function renderLineItemsTab(panel, data) {
  const items = data.line_items || [];

  // Collect all unique periods across all items
  const periods = [...new Set(items.flatMap(i => Object.keys(i.values || {})))].sort();
  selectedPeriods = new Set(periods);

  // --- Needs Attention Section ---
  const attentionItems = items.filter(i => {
    if ((i.confidence || 0) < 0.8) return true;
    if (i.validation_flags && i.validation_flags.length > 0) return true;
    return false;
  });
  const attentionCount = attentionItems.length;
  const defaultExpanded = attentionCount > 0;

  let html = '';

  // Needs Attention card
  html += `<div id="jd-needs-attention" class="attention-card${defaultExpanded ? '' : ' collapsed'}" style="margin-bottom:var(--space-4)">`;
  html += `<div class="attention-header">`;
  html += `<span class="attention-title">${attentionCount} item${attentionCount !== 1 ? 's' : ''} need${attentionCount === 1 ? 's' : ''} attention</span>`;
  html += `<button class="attention-toggle btn-icon" aria-label="Toggle attention items">${defaultExpanded ? '\u25BC' : '\u25B6'}</button>`;
  html += `</div>`;
  html += `<div class="attention-body"${defaultExpanded ? '' : ' style="display:none"'}>`;
  if (attentionCount > 0) {
    html += '<div class="table-wrapper"><table class="data-table data-table-compact" id="jd-attention-table"><thead><tr>';
    html += '<th>Sheet</th><th>Label</th><th>Canonical Name</th><th>Confidence</th>';
    for (const p of periods) {
      html += `<th class="col-number period-col" data-period="${esc(p)}" style="font-size:10.5px">${esc(p)}</th>`;
    }
    html += '</tr></thead><tbody>';
    for (const item of attentionItems) {
      const conf = item.confidence || 0;
      const vals = item.values || {};
      html += '<tr>';
      html += '<td>' + esc(item.sheet || '') + '</td>';
      html += '<td>' + esc(item.original_label || '') + '</td>';
      html += '<td><code>' + esc(item.canonical_name || '') + '</code></td>';
      html += '<td>' + confidenceBadge(conf) + '</td>';
      for (const p of periods) {
        const v = vals[p];
        html += '<td class="col-number period-col" data-period="' + esc(p) + '">' + (v != null ? formatFinancial(v) : '\u2014') + '</td>';
      }
      html += '</tr>';
    }
    html += '</tbody></table></div>';
  } else {
    html += '<p class="text-secondary" style="padding:var(--space-3)">All items look good.</p>';
  }
  html += '</div></div>';

  // Pending corrections banner
  html += '<div id="jd-pending-banner" class="hidden correction-banner"></div>';

  // Period selector bar
  if (periods.length > 0) {
    html += '<div class="period-selector" style="margin-bottom:var(--space-3);display:flex;flex-wrap:wrap;gap:var(--space-1);align-items:center">';
    html += '<span class="text-sm text-secondary" style="margin-right:var(--space-2)">Periods:</span>';
    for (const p of periods) {
      html += `<button class="period-pill active" data-period="${esc(p)}">${esc(p)}</button>`;
    }
    html += '<span style="flex:1"></span>';
    html += '<button class="btn btn-sm btn-secondary" id="jd-bulk-toggle">Bulk Edit</button>';
    html += '</div>';
  }

  // Bulk toolbar (hidden by default)
  html += '<div id="jd-bulk-toolbar" class="bulk-toolbar hidden">';
  html += '<span class="bulk-count" id="jd-bulk-count">0 selected</span>';
  html += '<button class="btn btn-sm btn-secondary" id="jd-bulk-select-low-conf">Select All Low Confidence</button>';
  html += '<button class="btn btn-sm btn-secondary" id="jd-bulk-select-all">Select All</button>';
  html += '<button class="btn btn-sm btn-secondary" id="jd-bulk-deselect-all">Deselect All</button>';
  html += '<div class="bulk-tax-wrapper" style="flex:1;position:relative;min-width:200px">';
  html += '<input type="text" class="bulk-tax-input" id="jd-bulk-tax-input" placeholder="Search taxonomy to apply...">';
  html += '<div class="tax-dropdown-list bulk-tax-results" id="jd-bulk-tax-results"></div>';
  html += '</div>';
  html += '<button class="btn btn-sm" id="jd-bulk-apply" disabled>Apply to Selected</button>';
  html += '</div>';

  // Main table
  html += '<div class="table-wrapper"><table class="data-table" id="jd-line-items-table"><thead><tr>';
  html += '<th class="bulk-col hidden" style="width:32px"><input type="checkbox" id="jd-bulk-header-cb"></th>';
  html += '<th class="sortable" data-sort="sheet">Sheet</th>';
  html += '<th class="sortable" data-sort="original_label">Label</th>';
  html += '<th class="sortable" data-sort="canonical_name">Canonical Name</th>';
  html += '<th class="sortable" data-sort="confidence">Confidence</th>';
  for (const p of periods) {
    html += `<th class="col-number period-col" data-period="${esc(p)}" style="font-size:10.5px">${esc(p)}</th>`;
  }
  html += '</tr></thead><tbody></tbody></table></div>';
  panel.innerHTML = html;

  // Attention card toggle
  const attentionCard = panel.querySelector('#jd-needs-attention');
  if (attentionCard) {
    const toggleBtn = attentionCard.querySelector('.attention-toggle');
    const body = attentionCard.querySelector('.attention-body');
    if (toggleBtn && body) {
      toggleBtn.addEventListener('click', () => {
        const isCollapsed = attentionCard.classList.toggle('collapsed');
        body.style.display = isCollapsed ? 'none' : '';
        toggleBtn.textContent = isCollapsed ? '\u25B6' : '\u25BC';
      });
    }
  }

  // Period pill click handlers
  panel.querySelectorAll('.period-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const p = pill.dataset.period;
      if (selectedPeriods.has(p)) {
        selectedPeriods.delete(p);
        pill.classList.remove('active');
      } else {
        selectedPeriods.add(p);
        pill.classList.add('active');
      }
      updatePeriodColumnVisibility(panel);
    });
  });

  let sortCol = null;
  let sortAsc = true;

  let activeProvenanceRow = null;

  function renderRows(itemsToRender) {
    const tbody = panel.querySelector('#jd-line-items-table tbody');
    tbody.innerHTML = '';
    activeProvenanceRow = null;
    for (const item of itemsToRender) {
      const tr = document.createElement('tr');
      tr.classList.add('clickable');
      const conf = item.confidence || 0;
      const vals = item.values || {};

      const key = (item.sheet || '') + '|' + (item.original_label || '');
      const pending = pendingCorrections[key];
      const displayName = pending ? pending.new_canonical_name : (item.canonical_name || '');
      const correctedClass = pending ? ' cell-corrected' : '';

      // Count total columns: checkbox + sheet + label + canonical + confidence + periods
      const totalCols = (bulkEditMode ? 1 : 0) + 4 + periods.length;

      let rowHtml = '';

      // Checkbox column (hidden unless bulk mode)
      rowHtml += '<td class="bulk-col' + (bulkEditMode ? '' : ' hidden') + '"><input type="checkbox" class="bulk-row-cb" data-key="' + esc(key) + '"></td>';

      rowHtml +=
        '<td>' + esc(item.sheet || '') + '</td>' +
        '<td>' + esc(item.original_label || '') + '</td>' +
        '<td class="cell-editable' + correctedClass + '"><code>' + esc(displayName) + '</code></td>' +
        '<td>' + confidenceBadge(conf) + '</td>';

      for (const p of periods) {
        const v = vals[p];
        const visible = selectedPeriods.has(p) ? '' : ' style="display:none"';
        rowHtml += '<td class="col-number period-col" data-period="' + esc(p) + '"' + visible + '>' + (v != null ? formatFinancial(v) : '\u2014') + '</td>';
      }

      tr.innerHTML = rowHtml;

      if (pending) tr.classList.add('row-corrected');
      tr.dataset.sheet = item.sheet || '';
      tr.dataset.label = item.original_label || '';
      tr.dataset.canonical = item.canonical_name || '';
      tr._itemRef = item;
      tr._totalCols = totalCols;
      tbody.appendChild(tr);
    }

    // Editable cell click handlers (only when NOT in bulk mode)
    if (!bulkEditMode) {
      tbody.querySelectorAll('.cell-editable').forEach(td => {
        td.addEventListener('click', (e) => {
          e.stopPropagation();
          openTaxonomyDropdown(td);
        });
      });
    }

    // Row click: toggle provenance summary row (only when NOT in bulk mode)
    if (!bulkEditMode) {
      tbody.querySelectorAll('tr.clickable').forEach(tr => {
        tr.addEventListener('click', (e) => {
          // Don't trigger if clicking on an editable cell or its children
          if (e.target.closest('.cell-editable')) return;
          toggleProvenanceRow(tr);
        });
      });
    }

    // Checkbox change handlers for bulk mode
    if (bulkEditMode) {
      tbody.querySelectorAll('.bulk-row-cb').forEach(cb => {
        cb.addEventListener('change', () => updateBulkCount());
      });
    }
  }

  function toggleProvenanceRow(tr) {
    const item = tr._itemRef;
    const totalCols = tr._totalCols;
    if (!item) return;

    // If this row already has a provenance row open, close it
    const existingProv = tr.nextElementSibling;
    if (existingProv && existingProv.classList.contains('provenance-row')) {
      existingProv.remove();
      activeProvenanceRow = null;
      tr.classList.remove('hl');
      return;
    }

    // Close any other open provenance row
    if (activeProvenanceRow) {
      const prevTr = activeProvenanceRow.previousElementSibling;
      if (prevTr) prevTr.classList.remove('hl');
      activeProvenanceRow.remove();
      activeProvenanceRow = null;
    }

    // Create provenance row
    const provTr = document.createElement('tr');
    provTr.className = 'provenance-row';
    const provTd = document.createElement('td');
    provTd.colSpan = totalCols;

    // Render inline provenance summary
    let provContent = renderProvenanceSummary(item);

    // Add "Full Lineage" link
    provContent += '<button class="prov-full-link">Full Lineage \u2192</button>';

    provTd.innerHTML = provContent;
    provTr.appendChild(provTd);

    // Insert after the clicked row
    tr.after(provTr);
    tr.classList.add('hl');
    activeProvenanceRow = provTr;

    // Full Lineage link handler
    const fullLink = provTd.querySelector('.prov-full-link');
    if (fullLink) {
      fullLink.addEventListener('click', (e) => {
        e.stopPropagation();
        renderProvenancePanel(document.body, item, currentJobId);
      });
    }
  }

  renderRows(items);

  // Apply initial period column visibility
  updatePeriodColumnVisibility(panel);

  // Sorting
  panel.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (sortCol === col) { sortAsc = !sortAsc; } else { sortCol = col; sortAsc = true; }
      const sorted = [...items].sort((a, b) => {
        let va = a[col] || '', vb = b[col] || '';
        if (typeof va === 'number' && typeof vb === 'number') return sortAsc ? va - vb : vb - va;
        va = String(va).toLowerCase();
        vb = String(vb).toLowerCase();
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      });
      renderRows(sorted);
    });
  });

  // --- Taxonomy Dropdown with Keyboard Navigation ---
  function openTaxonomyDropdown(td) {
    closeDropdown();
    const tr = td.closest('tr');
    const sheet = tr.dataset.sheet;
    const label = tr.dataset.label;
    const currentCanonical = tr.dataset.canonical;

    const dropdown = document.createElement('div');
    dropdown.className = 'tax-dropdown';
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Search taxonomy...';
    dropdown.appendChild(input);
    const list = document.createElement('div');
    list.className = 'tax-dropdown-list';
    dropdown.appendChild(list);

    td.appendChild(dropdown);
    activeDropdown = dropdown;
    input.focus();

    let timer = null;
    let highlightedIndex = -1;

    function updateHighlight() {
      const options = list.querySelectorAll('.tax-option:not(.text-secondary)');
      options.forEach((opt, i) => {
        if (i === highlightedIndex) {
          opt.classList.add('tax-option-highlighted');
          // Auto-scroll to keep highlighted item visible
          opt.scrollIntoView({ block: 'nearest' });
        } else {
          opt.classList.remove('tax-option-highlighted');
        }
      });
    }

    function selectHighlighted() {
      const options = list.querySelectorAll('.tax-option:not(.text-secondary)');
      if (highlightedIndex >= 0 && highlightedIndex < options.length) {
        options[highlightedIndex].click();
      }
    }

    input.addEventListener('keydown', (e) => {
      const options = list.querySelectorAll('.tax-option:not(.text-secondary)');
      const count = options.length;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlightedIndex = count > 0 ? Math.min(highlightedIndex + 1, count - 1) : -1;
        updateHighlight();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlightedIndex = count > 0 ? Math.max(highlightedIndex - 1, 0) : -1;
        updateHighlight();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        selectHighlighted();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeDropdown();
      }
    });

    input.addEventListener('input', () => {
      clearTimeout(timer);
      highlightedIndex = -1;
      timer = setTimeout(() => searchTaxonomy(input.value.trim(), list, sheet, label, currentCanonical, () => {
        highlightedIndex = -1;
      }), 250);
    });

    setTimeout(() => document.addEventListener('click', closeDropdownOutside), 0);
  }

  function closeDropdown() {
    if (activeDropdown) {
      activeDropdown.remove();
      activeDropdown = null;
    }
    document.removeEventListener('click', closeDropdownOutside);
  }

  function closeDropdownOutside(e) {
    if (activeDropdown && !activeDropdown.contains(e.target)) closeDropdown();
  }

  async function searchTaxonomy(query, listEl, sheet, label, currentCanonical, onResults) {
    if (query.length < 1) { listEl.innerHTML = ''; return; }
    try {
      const data = await apiGet('/api/v1/taxonomy/search?q=' + encodeURIComponent(query));
      listEl.innerHTML = '';
      (data.items || []).forEach(item => {
        const div = document.createElement('div');
        div.className = 'tax-option';
        div.innerHTML = esc(item.canonical_name) + '<span class="tax-cat">' + esc(item.category || '') + '</span>';
        div.addEventListener('click', (e) => {
          e.stopPropagation();
          addPendingCorrection(sheet, label, currentCanonical, item.canonical_name);
          closeDropdown();
        });
        listEl.appendChild(div);
      });
      if (!data.items || data.items.length === 0) {
        listEl.innerHTML = '<div class="tax-option text-secondary">No matches</div>';
      }
      if (onResults) onResults();
    } catch {
      listEl.innerHTML = '<div class="tax-option" style="color:var(--color-danger)">Search failed</div>';
    }
  }

  function addPendingCorrection(sheet, label, oldCanonical, newCanonical) {
    if (newCanonical === oldCanonical) return;
    const key = sheet + '|' + label;
    pendingCorrections[key] = {
      original_label: label,
      sheet: sheet || null,
      new_canonical_name: newCanonical,
    };
    updatePendingBanner();
    updateBeforeUnloadGuard();
    renderRows(items);
  }

  function updatePendingBanner() {
    const banner = document.getElementById('jd-pending-banner');
    if (!banner) return;
    const count = Object.keys(pendingCorrections).length;
    if (count > 0) {
      banner.classList.remove('hidden');
      banner.innerHTML = `
        <span>${count} pending correction(s)</span>
        <button class="btn btn-sm" id="jd-preview-btn">Preview & Apply</button>
        <button class="btn btn-sm btn-secondary" id="jd-discard-btn">Discard</button>
      `;
      document.getElementById('jd-preview-btn').addEventListener('click', previewCorrections);
      document.getElementById('jd-discard-btn').addEventListener('click', () => {
        pendingCorrections = {};
        updatePendingBanner();
        updateBeforeUnloadGuard();
        renderRows(items);
      });
    } else {
      banner.classList.add('hidden');
    }
  }

  // --- Bulk Edit Mode ---
  function updateBulkCount() {
    const checked = panel.querySelectorAll('.bulk-row-cb:checked');
    const countEl = document.getElementById('jd-bulk-count');
    if (countEl) countEl.textContent = checked.length + ' selected';
    const applyBtn = document.getElementById('jd-bulk-apply');
    if (applyBtn) applyBtn.disabled = !(checked.length > 0 && bulkSelectedTaxonomy);
  }

  function toggleBulkMode() {
    bulkEditMode = !bulkEditMode;
    bulkSelectedTaxonomy = null;
    const toggleBtn = document.getElementById('jd-bulk-toggle');
    const toolbar = document.getElementById('jd-bulk-toolbar');
    const headerCb = document.getElementById('jd-bulk-header-cb');

    if (bulkEditMode) {
      if (toggleBtn) { toggleBtn.textContent = 'Exit Bulk Edit'; toggleBtn.classList.remove('btn-secondary'); toggleBtn.classList.add('btn-destructive'); }
      if (toolbar) toolbar.classList.remove('hidden');
      // Show checkbox columns
      panel.querySelectorAll('.bulk-col').forEach(el => el.classList.remove('hidden'));
      if (headerCb) headerCb.checked = false;
    } else {
      if (toggleBtn) { toggleBtn.textContent = 'Bulk Edit'; toggleBtn.classList.remove('btn-destructive'); toggleBtn.classList.add('btn-secondary'); }
      if (toolbar) toolbar.classList.add('hidden');
      // Hide checkbox columns
      panel.querySelectorAll('.bulk-col').forEach(el => el.classList.add('hidden'));
      // Clear search
      const taxInput = document.getElementById('jd-bulk-tax-input');
      if (taxInput) taxInput.value = '';
      const taxResults = document.getElementById('jd-bulk-tax-results');
      if (taxResults) taxResults.innerHTML = '';
    }
    // Re-render rows to toggle click handlers
    renderRows(items);
    updateBulkCount();
  }

  function selectAllCheckboxes() {
    panel.querySelectorAll('.bulk-row-cb').forEach(cb => { cb.checked = true; });
    updateBulkCount();
  }

  function deselectAllCheckboxes() {
    panel.querySelectorAll('.bulk-row-cb').forEach(cb => { cb.checked = false; });
    const headerCb = document.getElementById('jd-bulk-header-cb');
    if (headerCb) headerCb.checked = false;
    updateBulkCount();
  }

  function selectLowConfidence() {
    panel.querySelectorAll('.bulk-row-cb').forEach(cb => {
      const tr = cb.closest('tr');
      if (tr && tr._itemRef) {
        cb.checked = (tr._itemRef.confidence || 0) < 0.8;
      }
    });
    updateBulkCount();
  }

  function applyBulkCorrections() {
    if (!bulkSelectedTaxonomy) return;
    const checked = panel.querySelectorAll('.bulk-row-cb:checked');
    if (checked.length === 0) return;

    checked.forEach(cb => {
      const tr = cb.closest('tr');
      if (!tr) return;
      const sheet = tr.dataset.sheet;
      const label = tr.dataset.label;
      const oldCanonical = tr.dataset.canonical;
      const newCanonical = bulkSelectedTaxonomy;
      if (newCanonical === oldCanonical) return;
      const key = sheet + '|' + label;
      pendingCorrections[key] = {
        original_label: label,
        sheet: sheet || null,
        new_canonical_name: newCanonical,
      };
    });

    updateBeforeUnloadGuard();
    updatePendingBanner();

    // Exit bulk mode and re-render
    bulkEditMode = false;
    bulkSelectedTaxonomy = null;
    const toggleBtn = document.getElementById('jd-bulk-toggle');
    const toolbar = document.getElementById('jd-bulk-toolbar');
    if (toggleBtn) { toggleBtn.textContent = 'Bulk Edit'; toggleBtn.classList.remove('btn-destructive'); toggleBtn.classList.add('btn-secondary'); }
    if (toolbar) toolbar.classList.add('hidden');
    panel.querySelectorAll('.bulk-col').forEach(el => el.classList.add('hidden'));

    renderRows(items);
  }

  // Bulk toolbar taxonomy search (standalone, debounced with request cancellation)
  _bulkTaxTimer = null;
  _bulkTaxController = null;
  let bulkHighlightedIndex = -1;

  function setupBulkTaxSearch() {
    const taxInput = document.getElementById('jd-bulk-tax-input');
    const taxResults = document.getElementById('jd-bulk-tax-results');
    if (!taxInput || !taxResults) return;

    taxInput.addEventListener('input', () => {
      clearTimeout(_bulkTaxTimer);
      if (_bulkTaxController) _bulkTaxController.abort();
      bulkHighlightedIndex = -1;
      const q = taxInput.value.trim();
      if (q.length < 1) { taxResults.innerHTML = ''; return; }
      _bulkTaxTimer = setTimeout(async () => {
        _bulkTaxController = new AbortController();
        try {
          const data = await apiGet('/api/v1/taxonomy/search?q=' + encodeURIComponent(q), { signal: _bulkTaxController.signal });
          taxResults.innerHTML = '';
          (data.items || []).forEach(item => {
            const div = document.createElement('div');
            div.className = 'tax-option';
            div.innerHTML = esc(item.canonical_name) + '<span class="tax-cat">' + esc(item.category || '') + '</span>';
            div.addEventListener('click', (e) => {
              e.stopPropagation();
              bulkSelectedTaxonomy = item.canonical_name;
              taxInput.value = item.canonical_name;
              taxResults.innerHTML = '';
              updateBulkCount();
            });
            taxResults.appendChild(div);
          });
          if (!data.items || data.items.length === 0) {
            taxResults.innerHTML = '<div class="tax-option text-secondary">No matches</div>';
          }
          bulkHighlightedIndex = -1;
        } catch (err) {
          if (err.name === 'AbortError' || err.message === 'Request timed out') return;
          taxResults.innerHTML = '<div class="tax-option" style="color:var(--color-danger)">Search failed</div>';
        }
      }, 300);
    });

    // Keyboard navigation for bulk taxonomy search
    taxInput.addEventListener('keydown', (e) => {
      const options = taxResults.querySelectorAll('.tax-option:not(.text-secondary)');
      const count = options.length;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        bulkHighlightedIndex = count > 0 ? Math.min(bulkHighlightedIndex + 1, count - 1) : -1;
        updateBulkTaxHighlight(options);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        bulkHighlightedIndex = count > 0 ? Math.max(bulkHighlightedIndex - 1, 0) : -1;
        updateBulkTaxHighlight(options);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (bulkHighlightedIndex >= 0 && bulkHighlightedIndex < count) {
          options[bulkHighlightedIndex].click();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        taxResults.innerHTML = '';
        taxInput.blur();
      }
    });
  }

  function updateBulkTaxHighlight(options) {
    options.forEach((opt, i) => {
      if (i === bulkHighlightedIndex) {
        opt.classList.add('tax-option-highlighted');
        opt.scrollIntoView({ block: 'nearest' });
      } else {
        opt.classList.remove('tax-option-highlighted');
      }
    });
  }

  // Wire up bulk edit buttons
  const bulkToggleBtn = document.getElementById('jd-bulk-toggle');
  if (bulkToggleBtn) bulkToggleBtn.addEventListener('click', toggleBulkMode);

  const bulkSelectAllBtn = document.getElementById('jd-bulk-select-all');
  if (bulkSelectAllBtn) bulkSelectAllBtn.addEventListener('click', selectAllCheckboxes);

  const bulkDeselectAllBtn = document.getElementById('jd-bulk-deselect-all');
  if (bulkDeselectAllBtn) bulkDeselectAllBtn.addEventListener('click', deselectAllCheckboxes);

  const bulkSelectLowConfBtn = document.getElementById('jd-bulk-select-low-conf');
  if (bulkSelectLowConfBtn) bulkSelectLowConfBtn.addEventListener('click', selectLowConfidence);

  const bulkApplyBtn = document.getElementById('jd-bulk-apply');
  if (bulkApplyBtn) bulkApplyBtn.addEventListener('click', applyBulkCorrections);

  const bulkHeaderCb = document.getElementById('jd-bulk-header-cb');
  if (bulkHeaderCb) {
    bulkHeaderCb.addEventListener('change', () => {
      panel.querySelectorAll('.bulk-row-cb').forEach(cb => { cb.checked = bulkHeaderCb.checked; });
      updateBulkCount();
    });
  }

  setupBulkTaxSearch();

  async function previewCorrections() {
    if (!currentJobId || !Object.keys(pendingCorrections).length) return;
    const corrections = Object.values(pendingCorrections).map(c => ({
      original_label: c.original_label,
      new_canonical_name: c.new_canonical_name,
      sheet: c.sheet,
    }));
    try {
      const data = await apiPost('/api/v1/jobs/' + currentJobId + '/corrections/preview', { corrections });
      // Show preview modal
      let diffHtml = '<h3>Preview Corrections</h3>';
      diffHtml += '<table class="data-table" style="margin:var(--space-4) 0"><thead><tr><th>Label</th><th>Sheet</th><th>Old</th><th>New</th></tr></thead><tbody>';
      (data.diffs || []).forEach(d => {
        diffHtml += `<tr><td>${esc(d.original_label)}</td><td>${esc(d.sheet || '-')}</td>`;
        diffHtml += `<td class="diff-old">${esc(d.old_canonical_name)}</td>`;
        diffHtml += `<td class="diff-new">${esc(d.new_canonical_name)}</td></tr>`;
      });
      diffHtml += '</tbody></table>';
      if (data.warnings && data.warnings.length) {
        diffHtml += '<p style="color:var(--color-danger);font-size:var(--text-sm)">' + data.warnings.map(esc).join('<br>') + '</p>';
      }
      diffHtml += '<div class="modal-actions"><button class="btn btn-secondary modal-cancel-btn">Cancel</button><button class="btn modal-apply-btn">Apply Corrections</button></div>';

      const { close, el } = showModal(diffHtml);
      el.querySelector('.modal-cancel-btn').addEventListener('click', close);
      el.querySelector('.modal-apply-btn').addEventListener('click', async () => {
        close();
        await applyCorrections(corrections);
      });
    } catch (err) {
      showToast('Preview failed: ' + err.message, 'error');
    }
  }

  async function applyCorrections(corrections) {
    try {
      const applyResult = await apiPost('/api/v1/jobs/' + currentJobId + '/corrections/apply', { corrections });
      const count = corrections.length;
      const patternsCreated = (applyResult.patterns_created || 0) + (applyResult.patterns_updated || 0);
      pendingCorrections = {};
      updatePendingBanner();
      updateBeforeUnloadGuard();
      const entityName = currentJob?.entity_name;
      const patternMsg = patternsCreated > 0
        ? patternsCreated + ' pattern' + (patternsCreated !== 1 ? 's' : '') + ' learned' + (entityName ? ' for ' + entityName : '')
        : 'Patterns learned for future extractions';
      showToast(count + ' correction' + (count !== 1 ? 's' : '') + ' applied', 'success', 4000, patternMsg);
      // Reload results
      const res = await apiFetch('/api/v1/jobs/' + currentJobId + '/export?format=json');
      resultData = await res.json();
      const newItems = resultData.line_items || [];
      items.length = 0;
      items.push(...newItems);
      renderRows(items);
      renderSummary(resultData);
    } catch (err) {
      showToast('Apply failed: ' + err.message, 'error');
    }
  }
}

/**
 * Update visibility of period columns based on selectedPeriods set.
 */
function updatePeriodColumnVisibility(panel) {
  panel.querySelectorAll('.period-col').forEach(el => {
    const p = el.dataset.period;
    if (p) {
      el.style.display = selectedPeriods.has(p) ? '' : 'none';
    }
  });
}

// --- Triage Tab ---
function renderTriageTab(panel, data) {
  const triage = data.triage || [];
  if (triage.length === 0) {
    panel.innerHTML = '<div class="text-center text-secondary" style="padding:2rem">No triage data available.</div>';
    return;
  }
  let html = '<div class="table-wrapper"><table class="data-table"><thead><tr><th>Sheet</th><th>Tier</th><th>Decision</th><th>Rationale</th></tr></thead><tbody>';
  for (const t of triage) {
    html += `<tr><td>${esc(t.sheet_name || '')}</td><td>${tierBadge(t.tier)}</td><td>${esc(t.decision || '')}</td><td class="text-sm">${esc(t.rationale || '')}</td></tr>`;
  }
  html += '</tbody></table></div>';
  panel.innerHTML = html;
}

// --- Validation Tab ---
function renderValidationTab(panel, data) {
  const val = data.validation || {};
  if (!val.overall_confidence) {
    panel.innerHTML = '<div class="card"><p class="text-secondary">No validation data available.</p></div>';
    return;
  }
  const conf = val.overall_confidence;
  let html = '<div class="card">';
  html += `<p style="font-size:var(--text-lg);font-weight:600;margin-bottom:var(--space-4)">Overall Confidence: ${confidenceBadge(conf)}</p>`;

  // Validation Delta (moved here from stat cards)
  if (data.validation_delta && data.validation_delta.delta != null && data.validation_delta.delta !== 0) {
    const d = data.validation_delta;
    const pct = (d.delta * 100).toFixed(1);
    const prefix = d.delta > 0 ? '+' : '';
    const cls = d.delta > 0 ? 'badge-high' : 'badge-low';
    html += `<p style="margin-bottom:var(--space-4)">Validation Delta: <span class="badge ${cls}">${prefix}${pct}%</span></p>`;
  }

  const flags = val.flags || [];
  if (flags.length) {
    html += `<h4 style="margin-bottom:var(--space-3)">Flags (${flags.length})</h4>`;
    for (const f of flags) {
      html += `<div style="padding:var(--space-2) 0;border-top:1px solid var(--color-border-subtle);font-size:var(--text-sm)">${esc(f.message || f.rule || JSON.stringify(f))}</div>`;
    }
  } else {
    html += '<p class="text-secondary">No validation flags raised.</p>';
  }
  html += '</div>';
  panel.innerHTML = html;
}

// --- Lineage Tab ---
async function renderLineageTab(panel) {
  panel.innerHTML = loadingPlaceholder('Loading lineage data...');
  try {
    const events = await apiGet('/api/v1/jobs/' + currentJobId + '/lineage');
    const lineageEvents = events.events || events.stages || events;
    panel.innerHTML = '';
    renderTimeline(panel, Array.isArray(lineageEvents) ? lineageEvents : []);
  } catch (err) {
    panel.innerHTML = errorState('Could not load lineage data: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderLineageTab(panel));
  }
}

// --- Corrections Tab ---
async function renderCorrectionsTab(panel) {
  panel.innerHTML = loadingPlaceholder('Loading correction history...');
  try {
    const data = await apiGet('/api/v1/jobs/' + currentJobId + '/corrections/history');
    const corrections = data.corrections || [];
    if (corrections.length === 0) {
      panel.innerHTML = '<div class="text-center text-secondary" style="padding:2rem">No corrections have been applied to this extraction.</div>';
      return;
    }

    let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th>Label</th><th>Sheet</th><th>Old</th><th>New</th><th>Date</th><th></th>';
    html += '</tr></thead><tbody>';
    for (const c of corrections) {
      const cls = c.reverted ? ' reverted' : '';
      html += `<tr class="${cls}">`;
      html += `<td>${esc(c.original_label)}</td>`;
      html += `<td>${esc(c.sheet || '-')}</td>`;
      html += `<td class="text-mono">${esc(c.old_canonical_name)}</td>`;
      html += `<td class="text-mono">${esc(c.new_canonical_name)}</td>`;
      html += `<td class="text-sm text-secondary">${c.created_at ? new Date(c.created_at).toLocaleDateString() : '-'}</td>`;
      html += `<td class="col-actions">${c.reverted ? '<span class="text-secondary text-sm">Reverted</span>' : `<button class="btn btn-sm btn-danger undo-btn" data-cid="${esc(c.id)}">Undo</button>`}</td>`;
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.undo-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const ok = await confirm('Undo Correction', 'This will restore the original mapping. Continue?', { confirmText: 'Undo', confirmClass: 'btn btn-danger' });
        if (!ok) return;
        try {
          const data = await apiPost('/api/v1/corrections/' + btn.dataset.cid + '/undo', {});
          showToast(data.message || 'Correction undone', 'success');
          renderCorrectionsTab(panel);
          // Reload results
          const res = await apiFetch('/api/v1/jobs/' + currentJobId + '/export?format=json');
          resultData = await res.json();
        } catch (err) {
          showToast('Undo failed: ' + err.message, 'error');
        }
      });
    });
  } catch (err) {
    panel.innerHTML = errorState('Failed to load correction history: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderCorrectionsTab(panel));
  }
}

// --- Export ---
async function exportResults(format) {
  if (!currentJobId) return;
  try {
    const res = await apiFetch('/api/v1/jobs/' + currentJobId + '/export?format=' + format);
    const blob = await res.blob();
    const ext = format === 'csv' ? '.csv' : '.json';
    downloadBlob(blob, 'extraction_' + currentJobId.slice(0, 8) + ext);
    showToast(`Exported as ${format.toUpperCase()}`, 'success');
  } catch (err) {
    showToast('Export failed: ' + err.message, 'error');
  }
}

// --- Error ---
async function handleReextract() {
  const ok = await confirm(
    'Re-extract',
    '<p style="font-size:12.5px;color:var(--color-text-secondary)">This will create a new extraction job for the same file. Any learned patterns will be applied. Continue?</p>',
    { confirmText: 'Re-extract', cancelText: 'Cancel' }
  );
  if (!ok) return;
  try {
    const data = await apiPost('/api/v1/jobs/' + currentJobId + '/retry', {});
    showToast('Re-extraction started', 'success', 4000, 'New job: ' + (data.new_job_id || '').slice(0, 8));
    setTimeout(() => navigate('/extractions/' + data.new_job_id), 1500);
  } catch (err) {
    showToast('Re-extract failed: ' + err.message, 'error');
  }
}

function showError(msg) {
  const el = document.getElementById('jd-error');
  el.classList.remove('hidden');
  el.innerHTML = `<div class="error-box"><h3>Extraction Failed</h3><p>${esc(msg)}</p><button class="btn btn-sm" id="jd-retry-from-error" style="margin-top:12px">Re-extract</button></div>`;
  document.getElementById('jd-progress')?.classList.add('hidden');
  if (pollTimer) clearTimeout(pollTimer);
  const retryBtn = document.getElementById('jd-retry-from-error');
  if (retryBtn) retryBtn.addEventListener('click', handleReextract);
}

export function destroy() {
  if (pollTimer) clearTimeout(pollTimer);
  if (_bulkTaxTimer) clearTimeout(_bulkTaxTimer);
  if (_bulkTaxController) _bulkTaxController.abort();
  window.removeEventListener('beforeunload', beforeUnloadHandler);
  closeProvenancePanel();
  currentJobId = null;
  resultData = null;
  pendingCorrections = {};
  tabsController = null;
  currentJob = null;
  bulkEditMode = false;
  bulkSelectedTaxonomy = null;
  _bulkTaxTimer = null;
  _bulkTaxController = null;
}

// Entity Detail Page — Meridian Design System
import { apiGet, apiFetch } from '../api.js';
import { esc, timeAgo, formatFinancial } from '../state.js';
import { navigate } from '../router.js';
import { renderTabs } from '../components/tabs.js';
import { renderBreadcrumb } from '../components/breadcrumb.js';
import { statusBadge, qualityBadge } from '../components/badge.js';
import { skeletonStats, loadingPlaceholder, errorState } from '../components/loading.js';
import { emptyState } from '../components/empty-state.js';
import { showToast } from '../components/toast.js';
import { MONTH_NAMES } from '../constants/dates.js';
import { showModal, confirm } from '../components/modal.js';
import { renderUploadZone } from '../components/upload.js';
import { CATEGORY_LABELS } from '../constants/categories.js';

let entity = null;
let patternStats = null;
let tabsRef = null;
let sparklineCharts = [];

export async function render(container, params) {
  const entityId = params.entityId;
  entity = null;
  patternStats = null;
  tabsRef = null;

  container.innerHTML = `
    <div class="content-body">
      ${renderBreadcrumb([{ label: 'Entities', route: '/entities' }, { label: '\u00A0' }])}
      <div id="ed-header" style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem">
        <div>
          <p class="eyebrow" id="ed-eyebrow">&nbsp;</p>
          <h1 class="page-title" id="ed-title"><span class="skeleton skeleton-text" style="width:220px;height:20px;display:inline-block"></span></h1>
        </div>
        <div id="ed-actions" style="display:flex;gap:8px"></div>
      </div>
      <div id="ed-stats">${skeletonStats(4)}</div>
      <div id="ed-tabs" style="margin-top:20px"></div>
    </div>
  `;

  try {
    // Fetch entity and pattern stats in parallel
    const [entityData, statsData] = await Promise.all([
      apiGet('/api/v1/entities/' + entityId),
      apiGet('/api/v1/entities/' + entityId + '/pattern-stats').catch(() => null),
    ]);

    entity = entityData;
    patternStats = statsData;

    renderHeader(entityId);
    renderStats();
    renderTabsSection(entityId);
  } catch (err) {
    container.innerHTML = `
      <div class="content-body">
        ${renderBreadcrumb([{ label: 'Entities', route: '/entities' }, { label: 'Error' }])}
        ${errorState('Failed to load entity: ' + err.message, 'Retry')}
      </div>
    `;
    container.querySelector('.error-retry-btn')?.addEventListener('click', () => render(container, params));
  }
}

function renderHeader(entityId) {
  // Update breadcrumb
  const bc = document.querySelector('.breadcrumb');
  if (bc) {
    bc.innerHTML = renderBreadcrumb([
      { label: 'Entities', route: '/entities' },
      { label: entity.name || entityId },
    ]).replace(/<\/?nav[^>]*>/g, '');
  }

  const eyebrow = document.getElementById('ed-eyebrow');
  if (eyebrow) {
    eyebrow.textContent = entity.industry
      ? 'ENTITY \u00B7 ' + entity.industry.toUpperCase()
      : 'ENTITY';
  }

  const title = document.getElementById('ed-title');
  if (title) title.textContent = entity.name || 'Unnamed Entity';

  const actions = document.getElementById('ed-actions');
  if (actions) {
    actions.innerHTML = `
      <button id="ed-edit-btn" style="background:transparent;color:var(--color-text-primary);border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;cursor:pointer">Edit</button>
      <button id="ed-delete-btn" style="background:#FDEAEA;color:#8A1F1F;border:0.5px solid rgba(163,38,38,0.25);border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;cursor:pointer">Delete</button>
    `;
    actions.querySelector('#ed-edit-btn').addEventListener('click', () => openEditModal(entityId));
    actions.querySelector('#ed-delete-btn').addEventListener('click', () => confirmDelete(entityId));
  }
}



function renderStats() {
  const el = document.getElementById('ed-stats');
  if (!el) return;

  const totalPatterns = patternStats ? patternStats.total_patterns : (entity.patterns_count || 0);
  const filesCount = entity.files_count || 0;
  const avgConf = patternStats ? patternStats.avg_confidence : 0;
  const costSaved = patternStats ? patternStats.cost_saved_estimate : 0;

  const fye = entity.fiscal_year_end ? MONTH_NAMES[entity.fiscal_year_end] : null;
  const currency = entity.default_currency || null;
  const standard = entity.reporting_standard || null;

  let metadataBar = '';
  if (fye || currency || standard) {
    metadataBar = `
      <div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:10px;padding:8px 14px;background:var(--color-background-secondary);border-radius:var(--border-radius-md)">
        <div>
          <span style="font-size:10.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--color-text-secondary)">Fiscal Year End</span>
          <span style="font-size:12.5px;font-weight:500;margin-left:6px">${fye ? esc(fye) : '\u2014'}</span>
        </div>
        <div>
          <span style="font-size:10.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--color-text-secondary)">Currency</span>
          <span style="font-size:12.5px;font-weight:500;margin-left:6px;font-family:'IBM Plex Mono',monospace">${currency ? esc(currency) : '\u2014'}</span>
        </div>
        <div>
          <span style="font-size:10.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--color-text-secondary)">Reporting Standard</span>
          <span style="font-size:12.5px;font-weight:500;margin-left:6px">${standard ? esc(standard) : '\u2014'}</span>
        </div>
      </div>
    `;
  }

  el.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card" style="background:var(--color-background-secondary);border:none;border-radius:var(--border-radius-md);padding:11px 14px">
        <div style="font-size:10.5px;color:var(--color-text-secondary);margin-bottom:3px">Patterns</div>
        <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.25rem;line-height:1.1">${totalPatterns}</div>
      </div>
      <div class="stat-card" style="background:var(--color-background-secondary);border:none;border-radius:var(--border-radius-md);padding:11px 14px">
        <div style="font-size:10.5px;color:var(--color-text-secondary);margin-bottom:3px">Files</div>
        <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.25rem;line-height:1.1">${filesCount}</div>
      </div>
      <div class="stat-card" style="background:var(--color-background-secondary);border:none;border-radius:var(--border-radius-md);padding:11px 14px">
        <div style="font-size:10.5px;color:var(--color-text-secondary);margin-bottom:3px">Avg Confidence</div>
        <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.25rem;line-height:1.1">${avgConf > 0 ? (avgConf * 100).toFixed(0) + '%' : '\u2014'}</div>
      </div>
      <div class="stat-card" style="background:var(--color-background-secondary);border:none;border-radius:var(--border-radius-md);padding:11px 14px">
        <div style="font-size:10.5px;color:var(--color-text-secondary);margin-bottom:3px">Cost Savings</div>
        <div style="font-family:'DM Serif Display',Georgia,serif;font-size:1.25rem;line-height:1.1;color:#1D6B9F">${costSaved > 0 ? '$' + costSaved.toFixed(4) : '\u2014'}</div>
      </div>
    </div>
    ${metadataBar}
  `;
}

function renderTabsSection(entityId) {
  const tabsEl = document.getElementById('ed-tabs');
  if (!tabsEl) return;

  tabsRef = renderTabs(tabsEl, [
    {
      id: 'patterns',
      label: 'Patterns',
      render: (panel) => renderPatternsTab(panel, entityId),
    },
    {
      id: 'extractions',
      label: 'Extractions',
      render: (panel) => renderExtractionsTab(panel, entityId),
    },
    {
      id: 'financials',
      label: 'Financials',
      render: (panel) => renderFinancialsTab(panel, entityId),
    },
    {
      id: 'quality',
      label: 'Quality',
      render: (panel) => renderQualityTab(panel, entityId),
    },
  ], 'patterns');
}

// --- Patterns Tab ---

async function renderPatternsTab(panel, entityId) {
  panel.innerHTML = loadingPlaceholder('Loading patterns...');
  try {
    const data = await apiGet('/api/v1/entities/' + entityId + '/patterns');
    const patterns = data.patterns || [];

    if (patterns.length === 0) {
      panel.innerHTML = emptyState({ title: 'No patterns yet', description: 'Patterns are created automatically during extraction or via manual corrections.' });
      return;
    }

    let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th style="text-align:left">Original Label</th>';
    html += '<th style="text-align:left">Canonical Name</th>';
    html += '<th style="text-align:right">Confidence</th>';
    html += '<th style="text-align:right">Occurrences</th>';
    html += '<th style="text-align:left">Source</th>';
    html += '<th style="text-align:right">Actions</th>';
    html += '</tr></thead><tbody>';

    for (const p of patterns) {
      const conf = p.confidence || 0;
      const confCls = conf >= 0.8 ? 'b-ok' : conf >= 0.5 ? 'b-warn' : 'b-bad';
      const confPct = (conf * 100).toFixed(0) + '%';

      let sourceBadge;
      if (p.created_by === 'claude' || p.created_by === 'ai') {
        sourceBadge = '<span class="badge b-blue" style="display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:100px;font-size:11px;font-weight:500;white-space:nowrap;background:#E3EEF8;color:#1A4D7A">AI</span>';
      } else if (p.created_by === 'user_correction' || p.created_by === 'user') {
        sourceBadge = '<span class="badge b-ok" style="display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:100px;font-size:11px;font-weight:500;white-space:nowrap;background:#E6F4ED;color:#15652E">User</span>';
      } else {
        sourceBadge = `<span class="badge b-gray" style="display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:100px;font-size:11px;font-weight:500;white-space:nowrap;background:var(--color-background-secondary);color:var(--color-text-secondary)">${esc(p.created_by || 'unknown')}</span>`;
      }

      html += '<tr>';
      html += `<td style="text-align:left;font-size:11.5px;color:var(--color-text-secondary)">${esc(p.original_label)}</td>`;
      html += `<td style="text-align:left" class="text-mono"><code style="font-family:'IBM Plex Mono',monospace;font-size:11.5px">${esc(p.canonical_name)}</code></td>`;
      html += `<td style="text-align:right"><span class="badge ${confCls}" style="display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:100px;font-size:11px;font-weight:500;white-space:nowrap">${confPct}</span></td>`;
      html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:11.5px;font-variant-numeric:tabular-nums">${p.occurrence_count || 0}</td>`;
      const isRecent = p.created_at && (Date.now() - new Date(p.created_at).getTime()) < 86400000;
      const recentBadge = isRecent ? ' <span style="display:inline-flex;align-items:center;padding:2px 7px;border-radius:100px;font-size:10px;font-weight:500;background:#E3EEF8;color:#1A4D7A">New</span>' : '';
      html += `<td style="text-align:left">${sourceBadge}${recentBadge}</td>`;
      html += `<td style="text-align:right"><button class="pattern-delete-btn" data-pid="${esc(p.id)}" style="background:transparent;color:var(--color-text-secondary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:4px 10px;font-size:11px;cursor:pointer">Delete</button></td>`;
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    panel.innerHTML = html;

    // Delete pattern handlers
    panel.querySelectorAll('.pattern-delete-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const pid = btn.dataset.pid;
        const ok = await confirm(
          'Delete Pattern',
          '<p style="font-size:12.5px;color:var(--color-text-secondary)">This will permanently remove this learned pattern. The mapping will need to be re-learned during future extractions.</p>',
          { confirmText: 'Delete', confirmClass: 'btn', cancelText: 'Cancel' }
        );
        if (!ok) return;

        try {
          await apiFetch('/api/v1/entities/' + entityId + '/patterns/' + pid, { method: 'DELETE' });
          showToast('Pattern deleted', 'success');
          // Reload patterns tab
          if (tabsRef) tabsRef.reloadTab('patterns');
          // Refresh stats
          try {
            patternStats = await apiGet('/api/v1/entities/' + entityId + '/pattern-stats');
            renderStats();
          } catch { /* stats refresh is best-effort */ }
        } catch (err) {
          showToast('Failed to delete pattern: ' + err.message, 'error');
        }
      });
    });

  } catch (err) {
    panel.innerHTML = errorState('Failed to load patterns: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderPatternsTab(panel, entityId));
  }
}

// --- Extractions Tab ---

async function renderExtractionsTab(panel, entityId) {
  panel.innerHTML = loadingPlaceholder('Loading extractions...');
  try {
    const data = await apiGet('/api/v1/entities/' + entityId + '/jobs?limit=50');
    const jobs = data.jobs || [];

    let html = '';

    // Upload zone for this entity
    html += '<div id="ed-upload-zone" style="margin-bottom:16px"></div>';

    if (jobs.length === 0) {
      html += `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No extractions found for this entity. Upload a file above to get started.</div>`;
      panel.innerHTML = html;
      renderUploadZone(panel.querySelector('#ed-upload-zone'), {
        compact: true,
        entityId: entityId,
        onUploadComplete: () => {
          showToast('Upload complete — extraction started', 'success');
          if (tabsRef) tabsRef.reloadTab('extractions');
        },
      });
      return;
    }

    html += '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th style="text-align:left">Filename</th>';
    html += '<th style="text-align:left">Status</th>';
    html += '<th style="text-align:left">Quality</th>';
    html += '<th style="text-align:left">Date</th>';
    html += '</tr></thead><tbody>';

    for (const job of jobs) {
      html += `<tr class="clickable" data-job-id="${esc(job.job_id)}">`;
      html += `<td style="text-align:left;font-weight:500;font-size:11.5px">${esc(job.filename || 'Unknown')}</td>`;
      html += `<td style="text-align:left">${statusBadge(job.status)}</td>`;
      html += `<td style="text-align:left">${job.quality ? qualityBadge(job.quality) : '<span style="color:var(--color-text-secondary)">\u2014</span>'}</td>`;
      html += `<td style="text-align:left;font-size:11.5px;color:var(--color-text-secondary)">${timeAgo(job.created_at)}</td>`;
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    panel.innerHTML = html;

    // Render upload zone
    renderUploadZone(panel.querySelector('#ed-upload-zone'), {
      compact: true,
      entityId: entityId,
      onUploadComplete: () => {
        showToast('Upload complete — extraction started', 'success');
        if (tabsRef) tabsRef.reloadTab('extractions');
      },
    });

    // Row click -> job detail
    panel.querySelectorAll('tr.clickable').forEach(tr => {
      tr.addEventListener('click', () => {
        navigate('/extractions/' + tr.dataset.jobId);
      });
    });

  } catch (err) {
    panel.innerHTML = errorState('Failed to load extractions: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderExtractionsTab(panel, entityId));
  }
}

// --- Financials Tab ---

function destroySparklineCharts() {
  for (const chart of sparklineCharts) {
    chart.destroy();
  }
  sparklineCharts = [];
}

const CATEGORY_ORDER = [
  'income_statement', 'balance_sheet', 'cash_flow',
  'debt_schedule', 'metrics', 'project_finance',
];

async function renderFinancialsTab(panel, entityId) {
  destroySparklineCharts();
  panel.innerHTML = loadingPlaceholder('Loading financials...');

  try {
    // First: discover which categories have data
    const overview = await apiGet('/api/v1/analytics/entity/' + entityId + '/financials');
    const items = overview.items || [];

    if (items.length === 0) {
      panel.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No financial data available for this entity.</div>`;
      return;
    }

    // Determine which categories have data
    const activeCats = new Set();
    for (const item of items) {
      if (item.taxonomy_category) activeCats.add(item.taxonomy_category);
    }

    // Fetch structured statements for each category (in display order)
    const orderedCats = CATEGORY_ORDER.filter(c => activeCats.has(c));
    // Add any categories not in CATEGORY_ORDER
    for (const c of activeCats) {
      if (!orderedCats.includes(c)) orderedCats.push(c);
    }

    const statements = await Promise.all(
      orderedCats.map(cat =>
        apiGet(`/api/v1/analytics/entity/${entityId}/statement?category=${encodeURIComponent(cat)}`)
          .catch(() => null)
      )
    );

    let html = '';

    for (let i = 0; i < orderedCats.length; i++) {
      const cat = orderedCats[i];
      const data = statements[i];
      if (!data || !data.items || data.items.length === 0) continue;

      const catLabel = CATEGORY_LABELS[cat] || cat;
      const periods = data.periods || [];
      const colCount = periods.length + 2; // name + periods + trend

      html += '<div class="card" style="padding:0;overflow:hidden;margin-bottom:12px">';

      // Category header
      html += `<div style="padding:10px 14px;border-bottom:0.5px solid var(--color-border-tertiary);background:var(--color-background-secondary)">`;
      html += `<span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:var(--color-text-secondary)">${esc(catLabel)}</span>`;
      html += `<span style="font-size:10px;color:var(--color-text-tertiary);margin-left:8px">${data.total_items} items</span>`;
      html += '</div>';

      // Determine if we show a YoY% column (for 2+ periods, show change for last two)
      const showYoY = periods.length >= 2;
      const yoyFromIdx = showYoY ? periods.length - 2 : -1;
      const yoyToIdx = showYoY ? periods.length - 1 : -1;

      html += '<div class="table-wrapper" style="border:none;border-radius:0">';
      html += '<table class="data-table"><thead><tr>';
      html += '<th style="text-align:left;min-width:220px;padding:6px 12px;font-size:10.5px">Line Item</th>';
      for (const p of periods) {
        html += `<th style="text-align:right;font-size:10px;font-family:var(--font-mono);padding:6px 10px;white-space:nowrap">${esc(p)}</th>`;
      }
      if (showYoY) {
        html += `<th style="text-align:right;font-size:10px;padding:6px 10px;white-space:nowrap;color:#888">Chg%</th>`;
      }
      html += '<th style="text-align:center;font-size:10.5px;padding:6px 12px;width:70px">Trend</th>';
      html += '</tr></thead><tbody>';

      // Render hierarchical items
      html += _renderStatementRows(data.items, periods, 0, cat, yoyFromIdx, yoyToIdx);

      html += '</tbody></table></div>';

      // Reconciliation banner
      if (data.reconciliation && data.reconciliation.length > 0) {
        for (const rec of data.reconciliation) {
          const isBalanced = rec.balanced === true;
          const bg = isBalanced ? '#F0FDF4' : '#FEF2F2';
          const fg = isBalanced ? '#166534' : '#991B1B';
          const icon = isBalanced ? '\u2713' : '\u26A0';
          const msg = isBalanced
            ? `${rec.check}: Balanced`
            : `${rec.check}: Difference of ${formatFinancial(rec.difference || 0)}`;
          html += `<div style="padding:6px 14px;font-size:11px;border-top:1px solid var(--color-border-tertiary);background:${bg};color:${fg}">${icon} ${esc(msg)}</div>`;
        }
      }

      html += '</div>';
    }

    if (!html) {
      panel.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No structured data available.</div>`;
      return;
    }

    panel.innerHTML = html;

    // Create sparklines after DOM is ready
    _createSparklines();

  } catch (err) {
    panel.innerHTML = errorState('Failed to load financials: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderFinancialsTab(panel, entityId));
  }
}

// CF section labels for root-level canonical names
const CF_SECTIONS = {
  cfo: 'Operating Activities',
  cfi: 'Investing Activities',
  cff: 'Financing Activities',
};

// Grand total items get double-underline; regular subtotals get single line
const FINAL_TOTALS = new Set([
  'net_income', 'total_assets', 'total_liabilities_and_equity',
  'total_equity', 'net_change_cash', 'ending_cash', 'fcf',
  'total_debt', 'total_investment', 'total_liabilities',
]);

function _getValueColor(val, typicalSign) {
  if (val == null) return '';
  if (!typicalSign || typicalSign === 'varies') {
    return val < 0 ? 'color:#A32626;' : '';
  }
  // "positive" means value is normally positive; "negative" means normally negative
  const expectedPositive = typicalSign === 'positive';
  const isUnexpected = expectedPositive ? val < 0 : val > 0;
  return isUnexpected ? 'color:#A32626;' : '';
}

function _renderStatementRows(items, periods, depth, category, yoyFromIdx = -1, yoyToIdx = -1) {
  let html = '';
  let lastCfSection = null;

  for (const item of items) {
    const indent = depth * 24;
    const isBold = item.is_subtotal === true;
    const hasChildren = item.children && item.children.length > 0;
    const isRoot = depth === 0;

    // CF section headers: insert a separator row before each Operating/Investing/Financing group
    if (category === 'cash_flow' && isRoot) {
      const section = CF_SECTIONS[item.canonical_name] || null;
      if (section && section !== lastCfSection) {
        lastCfSection = section;
        const colSpan = periods.length + 2 + (yoyFromIdx >= 0 ? 1 : 0);
        html += `<tr><td colspan="${colSpan}" style="padding:10px 12px 4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--color-text-tertiary);border-top:2px solid var(--color-border-secondary);background:var(--color-background-primary)">${esc(section)}</td></tr>`;
      }
    }

    // Styling
    const fontWeight = isBold ? '600' : (isRoot ? '500' : '400');
    const fontSize = isRoot ? '12px' : '11.5px';
    const bgColor = isBold && depth === 0 ? 'rgba(0,0,0,0.02)' : (depth > 0 ? 'var(--color-background-secondary)' : 'transparent');
    const borderTop = isBold && isRoot ? '1px solid rgba(0,0,0,0.06)' : 'none';

    // Double-underline for grand totals, single line for regular subtotals
    let borderBottom = 'none';
    if (isBold && isRoot) {
      borderBottom = FINAL_TOTALS.has(item.canonical_name)
        ? '3px double var(--color-text-primary)'
        : '1px solid rgba(0,0,0,0.15)';
    }

    const displayName = item.display_name || item.canonical_name.replace(/_/g, ' ');

    html += `<tr style="background:${bgColor}">`;

    // Name cell with indentation
    html += `<td style="padding-left:${indent + 12}px;font-weight:${fontWeight};font-size:${fontSize};border-top:${borderTop};border-bottom:${borderBottom};padding-top:5px;padding-bottom:5px">`;
    html += esc(displayName);
    if (isRoot && item.canonical_name !== displayName.toLowerCase().replace(/[^a-z0-9]/g, '_')) {
      html += `<span style="display:block;font-family:var(--font-mono);font-size:9.5px;color:var(--color-text-tertiary);font-weight:400;margin-top:1px">${esc(item.canonical_name)}</span>`;
    }
    html += '</td>';

    // Period values
    const valueList = [];
    const typicalSign = item.typical_sign || null;
    for (const p of periods) {
      const val = item.values ? item.values[p] : undefined;
      valueList.push(val != null ? val : null);

      if (val != null) {
        const formatted = formatFinancial(val);
        const color = _getValueColor(val, typicalSign);
        html += `<td style="text-align:right;font-family:var(--font-mono);font-size:11px;font-variant-numeric:tabular-nums;${color}font-weight:${fontWeight};border-top:${borderTop};border-bottom:${borderBottom};padding:5px 10px">${formatted}</td>`;
      } else {
        html += `<td style="text-align:right;font-family:var(--font-mono);font-size:11px;border-top:${borderTop};border-bottom:${borderBottom};padding:5px 10px;color:var(--color-text-tertiary)">\u2014</td>`;
      }
    }

    // YoY% change cell (between last two periods)
    if (yoyFromIdx >= 0 && yoyToIdx >= 0) {
      const fromVal = valueList[yoyFromIdx];
      const toVal = valueList[yoyToIdx];
      if (fromVal != null && toVal != null && fromVal !== 0) {
        const pctChg = ((toVal - fromVal) / Math.abs(fromVal)) * 100;
        const arrow = pctChg > 0 ? '+' : '';
        const chgColor = pctChg > 0 ? '#1A7A4A' : pctChg < 0 ? '#A32626' : '#888';
        html += `<td style="text-align:right;font-family:var(--font-mono);font-size:10.5px;color:${chgColor};font-weight:${fontWeight};border-top:${borderTop};border-bottom:${borderBottom};padding:5px 10px">${arrow}${pctChg.toFixed(1)}%</td>`;
      } else {
        html += `<td style="text-align:right;font-family:var(--font-mono);font-size:10.5px;border-top:${borderTop};border-bottom:${borderBottom};padding:5px 10px;color:var(--color-text-tertiary)">\u2014</td>`;
      }
    }

    // Sparkline cell
    const nonNull = valueList.filter(v => v != null);
    if (nonNull.length >= 2) {
      const canvasId = 'sparkline-' + category + '-' + item.canonical_name.replace(/[^a-zA-Z0-9]/g, '_');
      html += `<td style="text-align:center;padding:5px 8px;border-top:${borderTop};border-bottom:${borderBottom}"><canvas id="${esc(canvasId)}" width="56" height="18" style="display:inline-block" data-sparkline="${valueList.map(v => v == null ? '' : v).join(',')}"></canvas></td>`;
    } else {
      html += `<td style="text-align:center;padding:5px 8px;border-top:${borderTop};border-bottom:${borderBottom};color:var(--color-text-tertiary);font-size:11px">\u2014</td>`;
    }

    html += '</tr>';

    // Render children recursively
    if (hasChildren) {
      html += _renderStatementRows(item.children, periods, depth + 1, category, yoyFromIdx, yoyToIdx);
    }
  }
  return html;
}

function _createSparklines() {
  document.querySelectorAll('canvas[data-sparkline]').forEach(canvas => {
    const rawData = canvas.dataset.sparkline.split(',').map(v => v === '' ? null : parseFloat(v));
    const nonNull = rawData.filter(v => v != null);
    if (nonNull.length < 2) return;

    try {
      const ctx = canvas.getContext('2d');
      const chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: rawData.map((_, i) => i),
          datasets: [{
            data: rawData,
            borderColor: '#1D6B9F',
            borderWidth: 1.5,
            fill: false,
            spanGaps: true,
          }],
        },
        options: {
          responsive: false,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false } },
          elements: { point: { radius: 0 } },
        },
      });
      sparklineCharts.push(chart);
    } catch { /* Chart.js not loaded */ }
  });
}

// --- Quality Tab ---

const GRADE_VALUES = { A: 4, B: 3, C: 2, D: 1, F: 0 };
const GRADE_COLORS_MAP = { A: '#1A7A4A', B: '#1D6B9F', C: '#C47D00', D: '#A32626', F: '#6B7280' };

async function renderQualityTab(panel, entityId) {
  destroySparklineCharts();
  panel.innerHTML = loadingPlaceholder('Loading quality trend...');
  try {
    const data = await apiGet('/api/v1/analytics/entity/' + entityId + '/quality-trend');
    const snapshots = (data.snapshots || []).reverse(); // oldest first for chart

    if (snapshots.length === 0) {
      panel.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No quality data available yet. Quality snapshots are created after each extraction.</div>`;
      return;
    }

    panel.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="card-header"><span class="card-title">Quality Grade Trend</span></div>
        <div style="padding:16px">
          <div style="height:220px"><canvas id="quality-trend-chart"></canvas></div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Snapshot History</span></div>
        <div id="quality-snapshot-table"></div>
      </div>
    `;

    // Chart
    const canvas = panel.querySelector('#quality-trend-chart');
    if (canvas && typeof Chart !== 'undefined') {
      const ctx = canvas.getContext('2d');
      const chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: snapshots.map(s => s.snapshot_date),
          datasets: [
            {
              label: 'Quality Grade',
              data: snapshots.map(s => GRADE_VALUES[s.quality_grade] ?? 0),
              borderColor: '#1D6B9F',
              backgroundColor: 'rgba(29,107,159,0.08)',
              fill: true,
              tension: 0.3,
              pointRadius: 4,
              pointBackgroundColor: snapshots.map(s => GRADE_COLORS_MAP[s.quality_grade] || '#888'),
              borderWidth: 2,
              yAxisID: 'y',
            },
            {
              label: 'Avg Confidence',
              data: snapshots.map(s => (s.avg_confidence * 100)),
              borderColor: '#1A7A4A',
              borderDash: [5, 3],
              fill: false,
              tension: 0.3,
              pointRadius: 2,
              borderWidth: 1.5,
              yAxisID: 'y1',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: { legend: { position: 'bottom', labels: { font: { size: 11 } } } },
          scales: {
            x: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { font: { size: 10 }, maxRotation: 45 } },
            y: {
              position: 'left',
              min: 0, max: 4,
              ticks: { stepSize: 1, callback: (v) => ['F', 'D', 'C', 'B', 'A'][v] || '', font: { size: 11 } },
              grid: { color: 'rgba(0,0,0,0.04)' },
              title: { display: true, text: 'Grade', font: { size: 10 } },
            },
            y1: {
              position: 'right',
              min: 0, max: 100,
              ticks: { callback: (v) => v + '%', font: { size: 10 } },
              grid: { display: false },
              title: { display: true, text: 'Confidence', font: { size: 10 } },
            },
          },
        },
      });
      sparklineCharts.push(chart);
    }

    // Snapshot table
    const tableEl = panel.querySelector('#quality-snapshot-table');
    let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th>Date</th><th style="text-align:center">Grade</th><th style="text-align:right">Confidence</th>';
    html += '<th style="text-align:right">Facts</th><th style="text-align:right">Jobs</th><th style="text-align:right">Unmapped</th>';
    html += '</tr></thead><tbody>';

    for (const s of [...snapshots].reverse()) {
      const gradeColor = GRADE_COLORS_MAP[s.quality_grade] || '#888';
      html += '<tr>';
      html += `<td style="font-size:11.5px">${esc(s.snapshot_date)}</td>`;
      html += `<td style="text-align:center"><span class="badge" style="background:${gradeColor}20;color:${gradeColor};font-weight:600">${esc(s.quality_grade)}</span></td>`;
      html += `<td class="text-mono" style="text-align:right">${(s.avg_confidence * 100).toFixed(0)}%</td>`;
      html += `<td class="text-mono" style="text-align:right">${s.total_facts}</td>`;
      html += `<td class="text-mono" style="text-align:right">${s.total_jobs}</td>`;
      html += `<td class="text-mono" style="text-align:right">${s.unmapped_label_count}</td>`;
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    tableEl.innerHTML = html;

  } catch (err) {
    panel.innerHTML = errorState('Failed to load quality trend: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderQualityTab(panel, entityId));
  }
}

// --- Edit Entity Modal ---

function openEditModal(entityId) {
  const fyeOptions = MONTH_NAMES.slice(1).map((name, i) => {
    const month = i + 1;
    const selected = entity.fiscal_year_end === month ? 'selected' : '';
    return `<option value="${month}" ${selected}>${name}</option>`;
  }).join('');

  const standardOptions = ['GAAP', 'IFRS'].map(s => {
    const selected = entity.reporting_standard === s ? 'selected' : '';
    return `<option value="${s}" ${selected}>${s}</option>`;
  }).join('');

  const { close, el: box } = showModal(`
    <h3 style="margin:0 0 16px">Edit Entity</h3>
    <form id="ed-edit-form">
      <div style="margin-bottom:12px">
        <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Name <span style="color:#A32626">*</span></label>
        <input type="text" id="ed-edit-name" required value="${esc(entity.name || '')}" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
      </div>
      <div style="margin-bottom:12px">
        <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Industry</label>
        <input type="text" id="ed-edit-industry" value="${esc(entity.industry || '')}" placeholder="e.g. Energy, Manufacturing..." style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
      </div>
      <div style="display:flex;gap:12px;margin-bottom:12px">
        <div style="flex:1">
          <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Fiscal Year End</label>
          <select id="ed-edit-fye" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
            <option value="">Not set</option>
            ${fyeOptions}
          </select>
        </div>
        <div style="flex:1">
          <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Currency</label>
          <input type="text" id="ed-edit-currency" value="${esc(entity.default_currency || '')}" placeholder="USD" maxlength="3" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary);text-transform:uppercase;font-family:'IBM Plex Mono',monospace">
        </div>
        <div style="flex:1">
          <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Reporting Standard</label>
          <select id="ed-edit-standard" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
            <option value="">Not set</option>
            ${standardOptions}
            <option value="Other" ${entity.reporting_standard && !['GAAP', 'IFRS'].includes(entity.reporting_standard) ? 'selected' : ''}>Other</option>
          </select>
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px">
        <button type="button" class="modal-cancel-btn" style="background:transparent;color:var(--color-text-secondary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;cursor:pointer">Cancel</button>
        <button type="submit" style="background:#1D6B9F;color:white;border:none;border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;font-weight:500;cursor:pointer">Save</button>
      </div>
    </form>
  `);

  box.querySelector('.modal-cancel-btn').addEventListener('click', close);

  box.querySelector('#ed-edit-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = box.querySelector('#ed-edit-name').value.trim();
    const industry = box.querySelector('#ed-edit-industry').value.trim() || null;
    const fyeVal = box.querySelector('#ed-edit-fye').value;
    const fiscal_year_end = fyeVal ? parseInt(fyeVal) : null;
    const default_currency = box.querySelector('#ed-edit-currency').value.trim().toUpperCase() || null;
    const reporting_standard = box.querySelector('#ed-edit-standard').value || null;

    if (!name) {
      showToast('Entity name is required', 'error');
      return;
    }

    const submitBtn = box.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    try {
      const res = await apiFetch('/api/v1/entities/' + entityId, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, industry, fiscal_year_end, default_currency, reporting_standard }),
      });
      const updated = await res.json();
      entity = { ...entity, ...updated };
      close();
      showToast('Entity updated', 'success');
      renderHeader(entityId);
      renderStats();
    } catch (err) {
      showToast('Failed to update entity: ' + err.message, 'error');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Save';
    }
  });

  box.querySelector('#ed-edit-name').focus();
}

// --- Delete Entity ---

async function confirmDelete(entityId) {
  const ok = await confirm(
    'Delete Entity',
    `<p style="font-size:12.5px;color:var(--color-text-secondary)">Are you sure you want to delete <strong>${esc(entity.name)}</strong>? This will also remove all associated patterns. This action cannot be undone.</p>`,
    { confirmText: 'Delete', confirmClass: 'btn', cancelText: 'Cancel' }
  );
  if (!ok) return;

  try {
    await apiFetch('/api/v1/entities/' + entityId, { method: 'DELETE' });
    showToast('Entity deleted', 'success');
    navigate('/entities');
  } catch (err) {
    showToast('Failed to delete entity: ' + err.message, 'error');
  }
}

export function destroy() {
  destroySparklineCharts();
  entity = null;
  patternStats = null;
  tabsRef = null;
}

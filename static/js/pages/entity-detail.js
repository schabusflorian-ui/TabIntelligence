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

async function renderFinancialsTab(panel, entityId) {
  // Clean up previous sparklines before rendering
  destroySparklineCharts();

  panel.innerHTML = loadingPlaceholder('Loading financials...');
  try {
    const data = await apiGet('/api/v1/analytics/entity/' + entityId + '/financials');
    const items = data.items || [];
    const periods = data.periods || [];

    if (items.length === 0) {
      panel.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No financial data available for this entity.</div>`;
      return;
    }

    // Group items by taxonomy_category
    const groups = {};
    for (const item of items) {
      const cat = item.taxonomy_category || 'Uncategorized';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    }

    const colCount = periods.length + 2; // canonical_name + periods + trend

    let html = '<div class="table-wrapper"><table class="data-table">';

    // Build table for each category group
    for (const [category, groupItems] of Object.entries(groups)) {
      const displayName = CATEGORY_LABELS[category] || category;

      // Category group header row
      html += `<tbody>`;
      html += `<tr><td colspan="${colCount}" style="font-size:11px;font-weight:500;text-transform:uppercase;background:var(--color-background-secondary);padding:6px 12px;color:var(--color-text-secondary);letter-spacing:0.03em">${esc(displayName)}</td></tr>`;

      // Column header row
      html += '<tr>';
      html += '<th style="text-align:left;font-size:10.5px;font-weight:500;padding:6px 12px">Canonical Name</th>';
      for (const period of periods) {
        html += `<th style="text-align:right;font-size:10.5px;font-weight:500;font-family:'IBM Plex Mono',monospace;padding:6px 12px">${esc(period)}</th>`;
      }
      html += '<th style="text-align:center;font-size:10.5px;font-weight:500;padding:6px 12px">Trend</th>';
      html += '</tr>';

      // Data rows
      for (const item of groupItems) {
        // Build a lookup of period -> amount for this item
        const valueMap = {};
        const valueList = [];
        for (const v of (item.values || [])) {
          valueMap[v.period] = v.amount;
        }

        html += '<tr>';
        html += `<td style="text-align:left;font-size:11.5px;font-weight:500;padding:6px 12px">${esc(item.canonical_name)}</td>`;

        for (const period of periods) {
          const amount = valueMap[period];
          if (amount != null) {
            valueList.push(amount);
            const formatted = formatFinancial(amount);
            const color = amount < 0 ? 'color:#A32626;' : '';
            html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:11.5px;font-variant-numeric:tabular-nums;${color}padding:6px 12px">${formatted}</td>`;
          } else {
            valueList.push(null);
            html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:11.5px;padding:6px 12px">\u2014</td>`;
          }
        }

        // Trend sparkline cell
        // Only render sparkline if there are >= 2 non-null values
        const nonNullValues = valueList.filter(v => v != null);
        if (nonNullValues.length >= 2) {
          const canvasId = 'sparkline-' + category + '-' + item.canonical_name.replace(/[^a-zA-Z0-9]/g, '_');
          html += `<td style="text-align:center;padding:6px 12px"><canvas id="${esc(canvasId)}" width="60" height="20" style="display:inline-block"></canvas></td>`;
        } else {
          html += `<td style="text-align:center;padding:6px 12px">\u2014</td>`;
        }

        html += '</tr>';
      }

      html += '</tbody>';
    }

    html += '</table></div>';
    panel.innerHTML = html;

    // Now create sparkline Chart.js instances for each item with >= 2 values
    for (const [category, groupItems] of Object.entries(groups)) {
      for (const item of groupItems) {
        const valueMap = {};
        const valueList = [];
        for (const v of (item.values || [])) {
          valueMap[v.period] = v.amount;
        }
        for (const period of periods) {
          valueList.push(valueMap[period] != null ? valueMap[period] : null);
        }

        const nonNullValues = valueList.filter(v => v != null);
        if (nonNullValues.length < 2) continue;

        const canvasId = 'sparkline-' + category + '-' + item.canonical_name.replace(/[^a-zA-Z0-9]/g, '_');
        const canvas = document.getElementById(canvasId);
        if (!canvas) continue;

        const ctx = canvas.getContext('2d');
        const chart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: periods,
            datasets: [{
              data: valueList,
              borderColor: '#1D6B9F',
              borderWidth: 1.5,
              fill: false,
              spanGaps: true,
            }],
          },
          options: {
            responsive: false,
            plugins: {
              legend: { display: false },
              tooltip: { display: false },
            },
            scales: {
              x: { display: false },
              y: { display: false },
            },
            elements: {
              point: { radius: 0 },
            },
          },
        });
        sparklineCharts.push(chart);
      }
    }

  } catch (err) {
    panel.innerHTML = errorState('Failed to load financials: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => renderFinancialsTab(panel, entityId));
  }
}

// --- Edit Entity Modal ---

function openEditModal(entityId) {
  const { close, el: box } = showModal(`
    <h3 style="margin:0 0 16px">Edit Entity</h3>
    <form id="ed-edit-form">
      <div style="margin-bottom:12px">
        <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Name <span style="color:#A32626">*</span></label>
        <input type="text" id="ed-edit-name" required value="${esc(entity.name || '')}" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
      </div>
      <div style="margin-bottom:16px">
        <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Industry</label>
        <input type="text" id="ed-edit-industry" value="${esc(entity.industry || '')}" placeholder="e.g. Energy, Manufacturing..." style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
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
        body: JSON.stringify({ name, industry }),
      });
      const updated = await res.json();
      entity = { ...entity, ...updated };
      close();
      showToast('Entity updated', 'success');
      renderHeader(entityId);
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

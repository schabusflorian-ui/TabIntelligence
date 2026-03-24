// Analytics Page — Portfolio Health, Cross-Entity Compare, Cost Analysis, Taxonomy Coverage, Anomalies, Taxonomy Gaps
import { apiGet } from '../api.js';
import { esc, formatNum, formatFinancial } from '../state.js';
import { renderTabs } from '../components/tabs.js';
import { skeletonStats, loadingPlaceholder, errorState } from '../components/loading.js';
import { showToast } from '../components/toast.js';
import { createDropdown } from '../components/dropdown.js';
import { renderPagination } from '../components/pagination.js';
import { CATEGORY_BADGE_CLASS } from '../constants/categories.js';
import { MONTH_NAMES } from '../constants/dates.js';

let chartInstances = [];
let dropdownInstances = [];

// -- Grade colors for quality distribution --
const GRADE_COLORS = {
  A: '#1A7A4A',
  B: '#1D6B9F',
  C: '#C47D00',
  D: '#A32626',
  F: '#6B7280',
};

// -- Chart multi-series palette --
const CHART_PALETTE = ['#1D6B9F', '#1A7A4A', '#C47D00', '#A32626', '#6B7280'];

// ========== Main render / destroy ==========

export async function render(container) {
  container.innerHTML = `
    <div class="content-header">
      <span class="eyebrow">INTELLIGENCE</span>
      <h2 class="page-title">Analytics</h2>
    </div>
    <div class="content-body" id="analytics-tabs"></div>
  `;

  const tabsContainer = container.querySelector('#analytics-tabs');

  renderTabs(tabsContainer, [
    { id: 'health', label: 'Portfolio Health', render: renderPortfolioHealth },
    { id: 'compare', label: 'Cross-Entity Compare', render: renderCompare },
    { id: 'costs', label: 'Cost Analysis', render: renderCosts },
    { id: 'covenants', label: 'Covenant Monitor', render: renderCovenantMonitor },
    { id: 'taxonomy', label: 'Taxonomy Coverage', render: renderTaxonomy },
    { id: 'anomalies', label: 'Anomalies', render: renderAnomalies },
    { id: 'unmapped', label: 'Taxonomy Gaps', render: renderUnmapped },
  ], 'health');
}

export function destroy() {
  chartInstances.forEach(c => c.destroy());
  chartInstances = [];
  dropdownInstances.forEach(d => d.destroy());
  dropdownInstances = [];
}

// ========== TAB 1: Portfolio Health ==========

async function renderPortfolioHealth(panel) {
  panel.innerHTML = `
    <div id="health-stats" style="margin-bottom:20px">${skeletonStats(4)}</div>
    <div class="card" id="health-chart-card">
      <div class="card-header"><span class="card-title">Quality Distribution</span></div>
      <div style="padding:16px">
        <div style="height:200px">
          <canvas id="health-quality-chart"></canvas>
        </div>
        <div id="health-quality-legend" style="margin-top:12px"></div>
      </div>
    </div>
  `;

  try {
    const data = await apiGet('/api/v1/analytics/portfolio/summary');

    // Stat cards
    const statsEl = panel.querySelector('#health-stats');
    const avgConf = data.avg_confidence != null
      ? (data.avg_confidence * 100).toFixed(0) + '%'
      : 'N/A';

    statsEl.innerHTML = `
      <div class="stats-grid">
        ${statCard('Total Entities', formatNum(data.total_entities || 0))}
        ${statCard('Total Extractions', formatNum(data.total_jobs || 0))}
        ${statCard('Avg Confidence', avgConf)}
        ${statCard('Total Facts', formatNum(data.total_facts || 0))}
      </div>
    `;

    // Quality distribution chart
    const dist = data.quality_distribution || [];
    const grades = ['A', 'B', 'C', 'D', 'F'];
    const gradeData = grades.map(g => {
      const item = dist.find(d => d.grade === g);
      return item ? item.count : 0;
    });
    const bgColors = grades.map(g => GRADE_COLORS[g]);

    const canvas = panel.querySelector('#health-quality-chart');
    if (canvas && typeof Chart !== 'undefined') {
      const ctx = canvas.getContext('2d');
      const chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: grades,
          datasets: [{
            data: gradeData,
            backgroundColor: bgColors,
            borderRadius: 4,
            barThickness: 28,
          }],
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.raw} extraction${ctx.raw !== 1 ? 's' : ''}`,
              },
            },
          },
          scales: {
            x: {
              beginAtZero: true,
              grid: { color: 'rgba(0,0,0,0.04)' },
              ticks: { precision: 0, font: { family: 'system-ui, sans-serif', size: 11 } },
            },
            y: {
              grid: { display: false },
              ticks: { font: { family: 'system-ui, sans-serif', size: 12, weight: '500' } },
            },
          },
        },
      });
      chartInstances.push(chart);

      // Custom legend
      const legendEl = panel.querySelector('#health-quality-legend');
      legendEl.innerHTML = `
        <div style="display:flex;gap:16px;flex-wrap:wrap;justify-content:center">
          ${grades.map((g, i) => `
            <div style="display:flex;align-items:center;gap:5px;font-size:11.5px;color:#555">
              <span style="width:10px;height:10px;border-radius:2px;background:${bgColors[i]};display:inline-block"></span>
              Grade ${g}: ${gradeData[i]}
            </div>
          `).join('')}
        </div>
      `;
    }
  } catch (err) {
    panel.querySelector('#health-stats').innerHTML = errorState('Failed to load portfolio summary.', 'Retry');
    panel.querySelector('#health-stats .error-retry-btn')?.addEventListener('click', () => renderPortfolioHealth(panel));
    const chartCard = panel.querySelector('#health-chart-card');
    chartCard.innerHTML = `<div class="card-header"><span class="card-title">Quality Distribution</span></div>
      <div style="padding:20px;text-align:center;color:var(--color-text-secondary);font-size:12px">
        Chart unavailable. ${esc(err.message || 'Failed to load data.')}
      </div>`;
    showToast('Failed to load analytics', 'error');
  }
}

// ========== TAB 2: Cross-Entity Compare ==========



async function renderCompare(panel) {
  panel.innerHTML = `
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span class="card-title">Compare Parameters</span></div>
      <div style="padding:16px">
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
          <div style="flex:1;min-width:200px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Entities</label>
            <div id="compare-entity-dropdown"></div>
          </div>
          <div style="flex:1;min-width:200px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Canonical Names</label>
            <input type="text" id="compare-canonical-input" placeholder="e.g. total_revenue, net_income"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div style="min-width:200px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Period Mode</label>
            <div style="display:flex;gap:4px;margin-bottom:6px">
              <label style="display:flex;align-items:center;gap:3px;font-size:11.5px;cursor:pointer">
                <input type="radio" name="compare-period-mode" value="period" checked style="margin:0"> Exact
              </label>
              <label style="display:flex;align-items:center;gap:3px;font-size:11.5px;cursor:pointer">
                <input type="radio" name="compare-period-mode" value="period_normalized" style="margin:0"> Normalized
              </label>
              <label style="display:flex;align-items:center;gap:3px;font-size:11.5px;cursor:pointer">
                <input type="radio" name="compare-period-mode" value="year" style="margin:0"> Year
              </label>
            </div>
            <input type="text" id="compare-period-input" placeholder="e.g. FY2024"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div style="min-width:100px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Target Currency</label>
            <select id="compare-target-currency" style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white">
              <option value="">Original</option>
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
              <option value="JPY">JPY</option>
              <option value="CHF">CHF</option>
            </select>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px">
            <label style="display:flex;align-items:center;gap:4px;font-size:11.5px;cursor:pointer;white-space:nowrap">
              <input type="checkbox" id="compare-metadata-check" style="margin:0"> Include metadata
            </label>
            <button class="btn btn-sm" id="compare-run-btn" style="background:#1D6B9F;color:white;border:none;padding:7px 18px;border-radius:8px;font-size:12.5px;cursor:pointer;white-space:nowrap">
              Compare
            </button>
          </div>
        </div>
      </div>
    </div>
    <div id="compare-results">
      <div class="text-center text-secondary text-sm" style="padding:3rem">
        Select entities and canonical names, then click Compare.
      </div>
    </div>
  `;

  // Update placeholder based on period mode
  const periodInput = panel.querySelector('#compare-period-input');
  panel.querySelectorAll('input[name="compare-period-mode"]').forEach(radio => {
    radio.addEventListener('change', () => {
      const mode = radio.value;
      periodInput.placeholder = mode === 'year' ? 'e.g. 2024' : 'e.g. FY2024';
    });
  });

  // Load entities for the dropdown
  const ddContainer = panel.querySelector('#compare-entity-dropdown');
  try {
    const entData = await apiGet('/api/v1/entities/');
    const entities = entData.entities || [];
    const options = entities.map(e => ({
      value: String(e.id),
      label: e.name || `Entity ${e.id}`,
    }));

    const dd = createDropdown(ddContainer, {
      options,
      placeholder: 'Select entities...',
      multi: true,
      searchable: true,
      onChange: () => {},
    });
    dropdownInstances.push(dd);

    // Compare button handler
    panel.querySelector('#compare-run-btn').addEventListener('click', async () => {
      const selectedIds = [...dd.getSelected()];
      const canonical = panel.querySelector('#compare-canonical-input').value.trim();
      const periodVal = panel.querySelector('#compare-period-input').value.trim();
      const periodMode = panel.querySelector('input[name="compare-period-mode"]:checked')?.value || 'period';
      const includeMetadata = panel.querySelector('#compare-metadata-check').checked;
      const targetCurrency = panel.querySelector('#compare-target-currency').value;
      const resultsEl = panel.querySelector('#compare-results');

      if (selectedIds.length === 0) {
        showToast('Select at least one entity', 'warning');
        return;
      }
      if (!canonical) {
        showToast('Enter at least one canonical name (e.g. total_revenue)', 'warning');
        return;
      }
      if (!periodVal) {
        showToast('Enter a period value (e.g. FY2024)', 'warning');
        return;
      }
      if (periodMode === 'year' && !/^\d{4}$/.test(periodVal)) {
        showToast('Year must be a 4-digit number (e.g. 2024). Use "Period Normalized" for FY2024.', 'warning');
        return;
      }

      resultsEl.innerHTML = loadingPlaceholder('Running comparison...');

      try {
        const params = new URLSearchParams();
        if (selectedIds.length > 0) params.set('entity_ids', selectedIds.join(','));
        if (canonical) params.set('canonical_names', canonical);
        if (periodVal) params.set(periodMode, periodVal);
        if (includeMetadata) params.set('include_metadata', 'true');
        if (targetCurrency) params.set('target_currency', targetCurrency);

        const cmpData = await apiGet(`/api/v1/analytics/compare?${params.toString()}`);
        renderCompareResults(resultsEl, cmpData, entities, includeMetadata, targetCurrency);
      } catch (err) {
        resultsEl.innerHTML = errorState('Comparison failed: ' + (err.message || 'Unknown error'), 'Retry');
        showToast('Comparison failed', 'error');
      }
    });
  } catch (err) {
    ddContainer.innerHTML = '<span class="text-sm text-secondary">Failed to load entities</span>';
  }
}

function renderCompareResults(el, data, entities, showMetadata, targetCurrency) {
  let html = '';

  // Alignment warnings
  const warnings = data.alignment_warnings || [];
  const notes = data.normalization_notes || [];
  if (warnings.length > 0 || notes.length > 0) {
    html += '<div style="margin-bottom:12px">';
    for (const w of warnings) {
      html += `<div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;padding:8px 14px;font-size:12px;color:#92400E;margin-bottom:6px">${esc(w)}</div>`;
    }
    for (const n of notes) {
      html += `<div style="background:#E0F2FE;border:1px solid #0EA5E9;border-radius:8px;padding:8px 14px;font-size:12px;color:#0C4A6E;margin-bottom:6px">${esc(n)}</div>`;
    }
    html += '</div>';
  }

  const comparisons = data.comparisons || [];

  if (comparisons.length === 0) {
    el.innerHTML = html + `<div class="text-center text-secondary text-sm" style="padding:3rem">No comparison data found for the selected parameters.</div>`;
    return;
  }

  // Collect all entity IDs across all comparisons to build columns
  const entityMap = new Map();
  const entityMeta = new Map();
  for (const cmp of comparisons) {
    for (const ent of (cmp.entities || [])) {
      if (!entityMap.has(ent.entity_id)) {
        entityMap.set(ent.entity_id, ent.entity_name || `Entity ${ent.entity_id}`);
        entityMeta.set(ent.entity_id, {
          currency: ent.currency_code || '',
          fye: ent.fiscal_year_end || null,
        });
      }
    }
  }

  const entityIds = [...entityMap.keys()];
  if (entityIds.length === 0) {
    el.innerHTML = html + `<div class="text-center text-secondary text-sm" style="padding:3rem">No entity data in comparison results.</div>`;
    return;
  }

  html += '<div class="card"><div class="table-wrapper"><table class="data-table"><thead><tr>';
  const currencySuffix = targetCurrency ? ` (${esc(targetCurrency)})` : '';
  html += `<th>Canonical Name</th>`;
  for (const eid of entityIds) {
    let colHeader = esc(entityMap.get(eid));
    if (showMetadata) {
      const meta = entityMeta.get(eid) || {};
      const parts = [];
      if (meta.currency) parts.push(meta.currency);
      if (meta.fye) parts.push('FYE: ' + MONTH_NAMES[meta.fye]);
      if (parts.length > 0) {
        colHeader += `<br><span style="font-size:10px;color:#888;font-weight:normal">${esc(parts.join(' | '))}</span>`;
      }
    }
    html += `<th class="text-mono" style="text-align:right">${colHeader}${currencySuffix}</th>`;
  }
  html += '</tr></thead><tbody>';

  for (const cmp of comparisons) {
    const label = cmp.canonical_name || '-';
    const periodLabel = cmp.period ? ` <span class="text-secondary text-sm">(${esc(cmp.period)})</span>` : '';
    html += '<tr>';
    html += `<td>${esc(label)}${periodLabel}</td>`;

    for (const eid of entityIds) {
      const match = (cmp.entities || []).find(e => e.entity_id === eid);
      if (match) {
        const conf = match.confidence != null ? `Confidence: ${(match.confidence * 100).toFixed(0)}%` : '';
        let cellContent = formatFinancial(match.amount);
        if (showMetadata && match.currency_code) {
          cellContent += ` <span style="font-size:10px;color:#888">${esc(match.currency_code)}</span>`;
        }
        html += `<td class="text-mono" style="text-align:right" title="${esc(conf)}">${cellContent}</td>`;
      } else {
        html += '<td class="text-mono text-secondary" style="text-align:right">-</td>';
      }
    }
    html += '</tr>';
  }

  html += '</tbody></table></div></div>';
  el.innerHTML = html;
}

// ========== TAB 3: Cost Analysis ==========

async function renderCosts(panel) {
  panel.innerHTML = `
    <div id="costs-stats" style="margin-bottom:20px">${skeletonStats(3)}</div>
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span class="card-title">Cost by Entity</span></div>
      <div id="costs-entity-table">${loadingPlaceholder('Loading cost data...')}</div>
    </div>
    <div class="card" id="costs-trend-card">
      <div class="card-header"><span class="card-title">Daily Cost Trend</span></div>
      <div style="padding:16px">
        <div style="height:200px">
          <canvas id="costs-trend-chart"></canvas>
        </div>
        <div id="costs-trend-legend" style="margin-top:12px"></div>
      </div>
    </div>
  `;

  try {
    const data = await apiGet('/api/v1/analytics/costs');

    // Stat cards
    const statsEl = panel.querySelector('#costs-stats');
    statsEl.innerHTML = `
      <div class="stats-grid">
        ${statCard('Total Cost', '$' + (data.total_cost != null ? data.total_cost.toFixed(2) : '0.00'))}
        ${statCard('Total Jobs', formatNum(data.total_jobs || 0))}
        ${statCard('Avg Cost/Job', '$' + (data.avg_cost_per_job != null ? data.avg_cost_per_job.toFixed(4) : '0.0000'))}
      </div>
    `;

    // Cost by entity table
    const tableEl = panel.querySelector('#costs-entity-table');
    const costByEntity = (data.cost_by_entity || []).sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0));

    if (costByEntity.length === 0) {
      tableEl.innerHTML = `<div class="text-center text-secondary text-sm" style="padding:2rem">No cost data available.</div>`;
    } else {
      let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
      html += '<th>Entity</th><th style="text-align:right">Jobs</th><th style="text-align:right">Total Cost</th><th style="text-align:right">Avg/Job</th>';
      html += '</tr></thead><tbody>';

      for (const row of costByEntity) {
        const avgPerJob = row.job_count > 0 ? (row.total_cost / row.job_count) : 0;
        html += '<tr>';
        html += `<td>${esc(row.entity_name || `Entity ${row.entity_id}`)}</td>`;
        html += `<td class="text-mono" style="text-align:right">${formatNum(row.job_count || 0)}</td>`;
        html += `<td class="text-mono" style="text-align:right">$${(row.total_cost || 0).toFixed(2)}</td>`;
        html += `<td class="text-mono" style="text-align:right">$${avgPerJob.toFixed(4)}</td>`;
        html += '</tr>';
      }
      html += '</tbody></table></div>';
      tableEl.innerHTML = html;
    }

    // Daily cost trend chart
    const trend = data.cost_trend_daily || [];
    const canvas = panel.querySelector('#costs-trend-chart');
    if (canvas && typeof Chart !== 'undefined' && trend.length > 0) {
      const ctx = canvas.getContext('2d');
      const chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: trend.map(t => t.date),
          datasets: [{
            label: 'Daily Cost',
            data: trend.map(t => t.cost),
            borderColor: '#1D6B9F',
            backgroundColor: 'rgba(29,107,159,0.08)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
            pointBackgroundColor: '#1D6B9F',
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `$${ctx.raw.toFixed(4)}`,
              },
            },
          },
          scales: {
            x: {
              grid: { color: 'rgba(0,0,0,0.04)' },
              ticks: { font: { family: 'system-ui, sans-serif', size: 10 }, maxRotation: 45 },
            },
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(0,0,0,0.04)' },
              ticks: {
                font: { family: 'system-ui, sans-serif', size: 11 },
                callback: (v) => '$' + v.toFixed(2),
              },
            },
          },
        },
      });
      chartInstances.push(chart);

      // Custom legend
      const legendEl = panel.querySelector('#costs-trend-legend');
      legendEl.innerHTML = `
        <div style="display:flex;gap:16px;justify-content:center">
          <div style="display:flex;align-items:center;gap:5px;font-size:11.5px;color:#555">
            <span style="width:16px;height:3px;border-radius:2px;background:#1D6B9F;display:inline-block"></span>
            Daily Cost
          </div>
        </div>
      `;
    } else if (trend.length === 0) {
      const trendContainer = panel.querySelector('#costs-trend-card')?.querySelector('[style*="height:200px"]');
      if (trendContainer) {
        trendContainer.innerHTML = '<div class="text-center text-secondary text-sm" style="padding:3rem">No trend data available.</div>';
      }
    }
  } catch (err) {
    panel.querySelector('#costs-stats').innerHTML = errorState('Failed to load cost data.', 'Retry');
    panel.querySelector('#costs-stats .error-retry-btn')?.addEventListener('click', () => renderCosts(panel));
    panel.querySelector('#costs-entity-table').innerHTML = '';
    panel.querySelector('#costs-trend-card').style.display = 'none';
    showToast('Failed to load cost analysis', 'error');
  }
}

// ========== TAB 4: Covenant Monitor ==========

async function renderCovenantMonitor(panel) {
  panel.innerHTML = loadingPlaceholder('Loading covenant monitor...');

  let data;
  try {
    data = await apiGet('/api/v1/analytics/portfolio/covenant-monitor');
  } catch (err) {
    panel.innerHTML = errorState('Failed to load covenant data: ' + esc(err.message), 'Retry');
    return;
  }

  const items = data.items || [];
  const breaches = items.filter(i => i.covenant_context && i.covenant_context.headroom != null && i.covenant_context.headroom < 0);
  const sensitive = items.filter(i => i.covenant_context && i.covenant_context.is_sensitive && !(i.covenant_context.headroom != null && i.covenant_context.headroom < 0));

  // Summary stats
  let html = `
    <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap">
      ${statCard('Entities Monitored', formatNum(data.total_entities_monitored))}
      ${statCardColored('Covenant Breaches', formatNum(breaches.length), breaches.length > 0 ? '#A32626' : '#1A7A4A')}
      ${statCardColored('Sensitive Items', formatNum(sensitive.length), sensitive.length > 0 ? '#C47D00' : '#1A7A4A')}
      ${statCard('Total Flagged', formatNum(items.length))}
    </div>
  `;

  if (items.length === 0) {
    html += `
      <div class="card">
        <div style="padding:32px;text-align:center;color:#1A7A4A">
          <div style="font-size:32px;margin-bottom:8px">&#10003;</div>
          <div style="font-weight:600;font-size:15px">No covenant sensitivity flags</div>
          <div style="color:#888;font-size:13px;margin-top:4px">All monitored entities are within comfortable headroom of their covenant thresholds.</div>
        </div>
      </div>
    `;
    panel.innerHTML = html;
    return;
  }

  // Group items by entity
  const byEntity = {};
  for (const item of items) {
    const key = item.entity_id;
    if (!byEntity[key]) byEntity[key] = { name: item.entity_name || item.entity_id, items: [] };
    byEntity[key].items.push(item);
  }

  // Sort entities: breaching entities first, then sensitive
  const entityOrder = Object.entries(byEntity).sort(([, a], [, b]) => {
    const aBreaches = a.items.filter(i => i.covenant_context.headroom != null && i.covenant_context.headroom < 0).length;
    const bBreaches = b.items.filter(i => i.covenant_context.headroom != null && i.covenant_context.headroom < 0).length;
    return bBreaches - aBreaches;
  });

  html += '<div class="card"><div class="card-header"><span class="card-title">Covenant Sensitivity by Entity</span></div>';
  html += '<div style="padding:0 16px 16px">';

  for (const [entityId, { name, items: entityItems }] of entityOrder) {
    const entityBreaches = entityItems.filter(i => i.covenant_context.headroom != null && i.covenant_context.headroom < 0).length;
    const headerColor = entityBreaches > 0 ? '#A32626' : '#C47D00';
    const headerBg = entityBreaches > 0 ? '#FEF2F2' : '#FFF7ED';
    const statusIcon = entityBreaches > 0 ? '&#9888;' : '&#9873;';

    html += `
      <div style="margin-top:16px;border:1px solid #E5E0D8;border-radius:6px;overflow:hidden">
        <div style="background:${headerBg};padding:10px 14px;border-bottom:1px solid #E5E0D8;display:flex;align-items:center;gap:8px">
          <span style="color:${headerColor};font-size:16px">${statusIcon}</span>
          <span style="font-weight:600;font-size:14px;color:${headerColor}">${esc(name)}</span>
          ${entityBreaches > 0
            ? `<span class="badge" style="background:#A32626;color:#fff;margin-left:auto">${entityBreaches} breach${entityBreaches > 1 ? 'es' : ''}</span>`
            : `<span class="badge" style="background:#C47D00;color:#fff;margin-left:auto">${entityItems.length} sensitive</span>`
          }
        </div>
        <div style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse;font-size:12px">
            <thead>
              <tr style="background:#F6F4EF;color:#888;text-transform:uppercase;font-size:10px;letter-spacing:.05em">
                <th style="padding:7px 10px;text-align:left;font-weight:600">Metric</th>
                <th style="padding:7px 10px;text-align:left;font-weight:600">Period</th>
                <th style="padding:7px 10px;text-align:right;font-weight:600">Value</th>
                <th style="padding:7px 10px;text-align:right;font-weight:600">Threshold</th>
                <th style="padding:7px 10px;text-align:right;font-weight:600">Headroom</th>
                <th style="padding:7px 10px;text-align:right;font-weight:600">Range (Low / High)</th>
                <th style="padding:7px 10px;text-align:left;font-weight:600">Status</th>
              </tr>
            </thead>
            <tbody>
    `;

    // Sort items: breaches first, then by period desc
    const sorted = [...entityItems].sort((a, b) => {
      const aBreach = a.covenant_context.headroom != null && a.covenant_context.headroom < 0 ? 1 : 0;
      const bBreach = b.covenant_context.headroom != null && b.covenant_context.headroom < 0 ? 1 : 0;
      if (bBreach !== aBreach) return bBreach - aBreach;
      return b.period.localeCompare(a.period);
    });

    for (const item of sorted) {
      const ctx = item.covenant_context;
      const isBreach = ctx.headroom != null && ctx.headroom < 0;
      const rowBg = isBreach ? '#FEF2F2' : (ctx.is_sensitive ? '#FFFBEB' : '');

      const fmtVal = (v) => v != null ? v.toFixed(2) + 'x' : '—';
      const fmtHR  = (v) => {
        if (v == null) return '—';
        const s = (v >= 0 ? '+' : '') + v.toFixed(3) + 'x';
        return s;
      };

      const headroomColor = ctx.headroom == null ? '#888'
        : ctx.headroom < 0 ? '#A32626'
        : ctx.headroom < 0.1 ? '#C47D00'
        : '#1A7A4A';

      const rangeLow  = item.value_range_low  != null ? item.value_range_low.toFixed(2)  + 'x' : '—';
      const rangeHigh = item.value_range_high != null ? item.value_range_high.toFixed(2) + 'x' : '—';

      let statusBadge;
      if (isBreach) {
        statusBadge = `<span class="badge" style="background:#A32626;color:#fff">BREACH</span>`;
      } else if (ctx.headroom_range_low != null && ctx.headroom_range_low < 0) {
        statusBadge = `<span class="badge" style="background:#C47D00;color:#fff">SENSITIVE</span>`;
      } else {
        statusBadge = `<span class="badge b-yellow">WATCH</span>`;
      }

      const metricLabel = item.canonical_name.replace(/_/g, '\u00a0');

      html += `
        <tr style="border-top:1px solid #F0EBE3${rowBg ? ';background:' + rowBg : ''}">
          <td style="padding:8px 10px;font-weight:500;font-family:monospace;font-size:11px">${esc(metricLabel)}</td>
          <td style="padding:8px 10px;color:#555">${esc(item.period)}</td>
          <td style="padding:8px 10px;text-align:right;font-weight:600">${fmtVal(item.computed_value)}</td>
          <td style="padding:8px 10px;text-align:right;color:#555">${fmtVal(ctx.threshold)}</td>
          <td style="padding:8px 10px;text-align:right;font-weight:600;color:${headroomColor}">${fmtHR(ctx.headroom)}</td>
          <td style="padding:8px 10px;text-align:right;color:#555;font-size:11px">${esc(rangeLow)} / ${esc(rangeHigh)}</td>
          <td style="padding:8px 10px">${statusBadge}</td>
        </tr>
      `;

      // Flag message row if present
      if (ctx.flag_message) {
        html += `
          <tr style="border-top:1px solid #F0EBE3${rowBg ? ';background:' + rowBg : ''}">
            <td colspan="7" style="padding:4px 10px 8px 28px;font-size:11px;color:${isBreach ? '#A32626' : '#C47D00'};font-style:italic">
              ${esc(ctx.flag_message)}
            </td>
          </tr>
        `;
      }
    }

    html += '</tbody></table></div></div>';
  }

  html += '</div></div>';
  panel.innerHTML = html;
}

// ========== TAB 5: Taxonomy Coverage ==========

async function renderTaxonomy(panel) {
  panel.innerHTML = `
    <div id="tax-stats" style="margin-bottom:20px">${skeletonStats(3)}</div>
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span class="card-title">Most Common Mapped Items</span></div>
      <div id="tax-common-table">${loadingPlaceholder('Loading taxonomy data...')}</div>
    </div>
    <div class="card" id="tax-never-card">
      <div class="card-header"><span class="card-title">Never Mapped Items</span></div>
      <div id="tax-never-list" style="padding:16px"></div>
    </div>
  `;

  try {
    const data = await apiGet('/api/v1/analytics/taxonomy/coverage');

    // Stat cards
    const statsEl = panel.querySelector('#tax-stats');
    const coveragePct = data.coverage_pct != null ? data.coverage_pct : 0;
    const coverageColor = coveragePct > 70 ? '#1A7A4A' : coveragePct > 40 ? '#C47D00' : '#A32626';

    statsEl.innerHTML = `
      <div class="stats-grid">
        ${statCard('Total Items', formatNum(data.total_taxonomy_items || 0))}
        ${statCard('Items Mapped', formatNum(data.items_ever_mapped || 0))}
        ${statCardColored('Coverage', coveragePct.toFixed(0) + '%', coverageColor)}
      </div>
    `;

    // Most common mapped items table
    const tableEl = panel.querySelector('#tax-common-table');
    const mostCommon = data.most_common || [];

    if (mostCommon.length === 0) {
      tableEl.innerHTML = `<div class="text-center text-secondary text-sm" style="padding:2rem">No mapped taxonomy items found.</div>`;
    } else {
      let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
      html += '<th>Canonical Name</th><th>Category</th><th style="text-align:right">Times Mapped</th><th style="text-align:right">Avg Confidence</th>';
      html += '</tr></thead><tbody>';

      for (const item of mostCommon) {
        const badgeClass = CATEGORY_BADGE_CLASS[item.category] || 'b-gray';
        const categoryLabel = item.category ? item.category.replace(/_/g, ' ') : '-';
        const avgConf = item.avg_confidence != null ? (item.avg_confidence * 100).toFixed(0) + '%' : '-';

        html += '<tr>';
        html += `<td class="text-mono">${esc(item.canonical_name || '-')}</td>`;
        html += `<td><span class="badge ${badgeClass}">${esc(categoryLabel)}</span></td>`;
        html += `<td class="text-mono" style="text-align:right">${formatNum(item.times_mapped || 0)}</td>`;
        html += `<td class="text-mono" style="text-align:right">${avgConf}</td>`;
        html += '</tr>';
      }

      html += '</tbody></table></div>';
      tableEl.innerHTML = html;
    }

    // Never mapped items
    const neverEl = panel.querySelector('#tax-never-list');
    const neverMapped = data.never_mapped || [];

    if (neverMapped.length === 0) {
      neverEl.innerHTML = `<span class="text-sm text-secondary">All taxonomy items have been mapped at least once.</span>`;
    } else {
      const displayLimit = 20;
      const shown = neverMapped.slice(0, displayLimit);
      const remaining = neverMapped.length - displayLimit;

      let html = '<div style="display:flex;flex-wrap:wrap;gap:6px">';
      for (const name of shown) {
        html += `<span class="badge b-gray">${esc(name)}</span>`;
      }
      html += '</div>';

      if (remaining > 0) {
        html += `<p class="text-sm text-secondary" style="margin-top:10px">and ${formatNum(remaining)} more</p>`;
      }

      neverEl.innerHTML = html;
    }
  } catch (err) {
    panel.querySelector('#tax-stats').innerHTML = errorState('Failed to load taxonomy coverage.', 'Retry');
    panel.querySelector('#tax-stats .error-retry-btn')?.addEventListener('click', () => renderTaxonomy(panel));
    panel.querySelector('#tax-common-table').innerHTML = '';
    panel.querySelector('#tax-never-card').style.display = 'none';
    showToast('Failed to load taxonomy coverage', 'error');
  }
}

// ========== TAB 6: Anomaly Detection ==========

async function renderAnomalies(panel) {
  panel.innerHTML = `
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span class="card-title">Anomaly Detection Parameters</span></div>
      <div style="padding:16px">
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
          <div style="flex:1;min-width:200px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Canonical Names <span style="color:#A32626">*</span></label>
            <input type="text" id="anomaly-canonical-input" placeholder="e.g. revenue, ebitda"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div style="min-width:140px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Period / Year</label>
            <input type="text" id="anomaly-period-input" placeholder="e.g. FY2024 or 2024"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div style="min-width:100px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Method</label>
            <select id="anomaly-method-select" style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white">
              <option value="iqr">IQR</option>
              <option value="zscore">Z-Score</option>
            </select>
          </div>
          <div style="min-width:90px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Threshold</label>
            <input type="number" id="anomaly-threshold-input" value="1.5" step="0.1" min="0.5" max="5"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div>
            <button class="btn btn-sm" id="anomaly-run-btn" style="background:#1D6B9F;color:white;border:none;padding:7px 18px;border-radius:8px;font-size:12.5px;cursor:pointer;white-space:nowrap">
              Detect
            </button>
          </div>
        </div>
      </div>
    </div>
    <div id="anomaly-results">
      <div class="text-center text-secondary text-sm" style="padding:3rem">
        Enter canonical names and click Detect to find outliers across entities.
      </div>
    </div>
  `;

  panel.querySelector('#anomaly-run-btn').addEventListener('click', async () => {
    const canonical = panel.querySelector('#anomaly-canonical-input').value.trim();
    const periodVal = panel.querySelector('#anomaly-period-input').value.trim();
    const method = panel.querySelector('#anomaly-method-select').value;
    const threshold = panel.querySelector('#anomaly-threshold-input').value;
    const resultsEl = panel.querySelector('#anomaly-results');

    if (!canonical) {
      showToast('Canonical names are required', 'warning');
      return;
    }

    resultsEl.innerHTML = loadingPlaceholder('Running anomaly detection...');

    try {
      const params = new URLSearchParams();
      params.set('canonical_names', canonical);
      params.set('method', method);
      if (threshold) params.set('threshold', threshold);

      // Detect if the period looks like a year (4 digits only)
      if (periodVal) {
        if (/^\d{4}$/.test(periodVal)) {
          params.set('year', periodVal);
        } else {
          params.set('period_normalized', periodVal);
        }
      }

      const data = await apiGet(`/api/v1/analytics/anomalies?${params.toString()}`);
      renderAnomalyResults(resultsEl, data);
    } catch (err) {
      resultsEl.innerHTML = errorState('Anomaly detection failed: ' + (err.message || 'Unknown error'), 'Retry');
      showToast('Anomaly detection failed', 'error');
    }
  });
}

function renderAnomalyResults(el, data) {
  const summaries = data.summaries || [];
  const totalItems = data.total_items || 0;
  const totalOutliers = data.total_outliers || 0;
  const outlierRate = totalItems > 0 ? ((totalOutliers / totalItems) * 100).toFixed(1) : '0.0';

  let html = `
    <div class="stats-grid" style="margin-bottom:16px">
      ${statCard('Total Items', formatNum(totalItems))}
      ${statCard('Total Outliers', formatNum(totalOutliers))}
      ${statCardColored('Outlier Rate', outlierRate + '%', totalOutliers > 0 ? '#A32626' : '#1A7A4A')}
      ${statCard('Method', esc(data.method || 'iqr').toUpperCase())}
    </div>
  `;

  if (summaries.length === 0) {
    el.innerHTML = html + `<div class="text-center text-secondary text-sm" style="padding:2rem">No data to analyze. Ensure entities have extraction facts for the specified period.</div>`;
    return;
  }

  for (const summary of summaries) {
    html += `<div class="card" style="margin-bottom:12px">`;
    html += `<div class="card-header" style="display:flex;justify-content:space-between;align-items:center">`;
    html += `<span class="card-title" style="font-family:'IBM Plex Mono',monospace">${esc(summary.canonical_name)}</span>`;
    html += `<span style="font-size:11px;color:#888">${esc(summary.period || '')} | Peers: ${summary.peer_count} | Mean: ${formatFinancial(summary.peer_mean)} | Median: ${formatFinancial(summary.peer_median)}</span>`;
    html += `</div>`;

    html += '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th style="text-align:left">Entity</th>';
    html += '<th style="text-align:right">Value</th>';
    html += '<th style="text-align:center">Status</th>';
    html += '<th style="text-align:center">Direction</th>';
    html += `<th style="text-align:right">${data.method === 'zscore' ? 'Z-Score' : 'IQR Distance'}</th>`;
    html += '</tr></thead><tbody>';

    const items = (summary.items || []).sort((a, b) => (b.is_outlier ? 1 : 0) - (a.is_outlier ? 1 : 0));
    for (const item of items) {
      const rowStyle = item.is_outlier ? 'background:rgba(163,38,38,0.04)' : '';
      html += `<tr style="${rowStyle}">`;
      html += `<td style="text-align:left">${esc(item.entity_name || item.entity_id)}</td>`;
      html += `<td class="text-mono" style="text-align:right">${formatFinancial(item.value)}</td>`;
      if (item.is_outlier) {
        html += '<td style="text-align:center"><span class="badge b-bad" style="font-size:10.5px">Outlier</span></td>';
      } else {
        html += '<td style="text-align:center"><span class="badge b-ok" style="font-size:10.5px">Normal</span></td>';
      }
      const arrow = item.direction === 'high' ? '\u2191' : item.direction === 'low' ? '\u2193' : '';
      const arrowColor = item.direction === 'high' ? '#A32626' : item.direction === 'low' ? '#1D6B9F' : '#888';
      html += `<td style="text-align:center;color:${arrowColor};font-weight:600">${arrow} ${esc(item.direction || '-')}</td>`;
      const score = data.method === 'zscore' ? (item.z_score != null ? item.z_score.toFixed(2) : '-') : (item.iqr_distance != null ? item.iqr_distance.toFixed(2) : '-');
      html += `<td class="text-mono" style="text-align:right">${score}</td>`;
      html += '</tr>';
    }

    html += '</tbody></table></div></div>';
  }

  el.innerHTML = html;
}

// ========== TAB 7: Unmapped Labels / Taxonomy Gaps ==========

async function renderUnmapped(panel) {
  panel.innerHTML = `
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span class="card-title">Unmapped Label Filters</span></div>
      <div style="padding:16px">
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
          <div style="min-width:120px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Min Occurrences</label>
            <input type="number" id="unmapped-min-occ" value="2" min="1"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div style="min-width:120px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Min Entities</label>
            <input type="number" id="unmapped-min-ent" value="1" min="1"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div>
            <button class="btn btn-sm" id="unmapped-run-btn" style="background:#1D6B9F;color:white;border:none;padding:7px 18px;border-radius:8px;font-size:12.5px;cursor:pointer;white-space:nowrap">
              Search
            </button>
          </div>
        </div>
      </div>
    </div>
    <div id="unmapped-results">
      <div class="text-center text-secondary text-sm" style="padding:3rem">
        Click Search to view unmapped labels across all entities.
      </div>
    </div>
  `;

  let currentOffset = 0;
  const limit = 25;

  async function loadUnmapped(offset) {
    const resultsEl = panel.querySelector('#unmapped-results');
    const minOcc = panel.querySelector('#unmapped-min-occ').value || '2';
    const minEnt = panel.querySelector('#unmapped-min-ent').value || '1';
    resultsEl.innerHTML = loadingPlaceholder('Loading unmapped labels...');

    try {
      const params = new URLSearchParams();
      params.set('min_occurrences', minOcc);
      params.set('min_entities', minEnt);
      params.set('limit', String(limit));
      params.set('offset', String(offset));

      const data = await apiGet(`/api/v1/analytics/unmapped-labels?${params.toString()}`);
      currentOffset = offset;
      renderUnmappedResults(resultsEl, data, offset);
    } catch (err) {
      resultsEl.innerHTML = errorState('Failed to load unmapped labels: ' + (err.message || 'Unknown error'), 'Retry');
      showToast('Failed to load unmapped labels', 'error');
    }
  }

  function renderUnmappedResults(el, data, offset) {
    const labels = data.labels || [];
    const total = data.total || 0;

    let html = `
      <div class="stats-grid" style="margin-bottom:16px">
        ${statCard('Total Unmapped Labels', formatNum(total))}
        ${statCard('Showing', `${labels.length} of ${total}`)}
      </div>
    `;

    if (labels.length === 0) {
      el.innerHTML = html + `<div class="text-center text-secondary text-sm" style="padding:2rem">No unmapped labels found matching filters.</div>`;
      return;
    }

    html += '<div class="card"><div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th style="text-align:left">Label</th>';
    html += '<th style="text-align:right">Occurrences</th>';
    html += '<th style="text-align:right">Entities</th>';
    html += '<th style="text-align:left">Variants</th>';
    html += '<th style="text-align:left">Sheets</th>';
    html += '<th style="text-align:left">Category Hint</th>';
    html += '</tr></thead><tbody>';

    for (const item of labels) {
      html += '<tr>';
      html += `<td style="text-align:left;font-weight:500;font-size:12px">${esc(item.label_normalized)}</td>`;
      html += `<td class="text-mono" style="text-align:right">${item.total_occurrences}</td>`;
      html += `<td class="text-mono" style="text-align:right">${item.entity_count}</td>`;

      const variants = (item.original_variants || []).slice(0, 3);
      const moreVariants = (item.original_variants || []).length - 3;
      let variantHtml = variants.map(v => `<span class="badge b-gray" style="font-size:10px;margin:1px">${esc(v)}</span>`).join('');
      if (moreVariants > 0) variantHtml += `<span style="font-size:10px;color:#888"> +${moreVariants}</span>`;
      html += `<td style="text-align:left">${variantHtml}</td>`;

      const sheets = (item.sheet_names || []).slice(0, 2);
      html += `<td style="text-align:left;font-size:11px;color:#888">${sheets.map(s => esc(s)).join(', ')}</td>`;

      const hint = item.taxonomy_category_hint;
      if (hint) {
        const badgeClass = CATEGORY_BADGE_CLASS[hint] || 'b-gray';
        html += `<td><span class="badge ${badgeClass}" style="font-size:10px">${esc(hint.replace(/_/g, ' '))}</span></td>`;
      } else {
        html += '<td style="color:#888;font-size:11px">-</td>';
      }
      html += '</tr>';
    }

    html += '</tbody></table></div></div>';
    html += '<div id="unmapped-pagination" style="margin-top:12px"></div>';

    el.innerHTML = html;

    // Pagination
    const pagEl = el.querySelector('#unmapped-pagination');
    if (pagEl && total > limit) {
      renderPagination(pagEl, {
        total,
        limit,
        offset,
        onChange: (newOffset) => loadUnmapped(newOffset),
      });
    }
  }

  panel.querySelector('#unmapped-run-btn').addEventListener('click', () => loadUnmapped(0));
}

// ========== Shared helpers ==========

function statCard(label, value) {
  return `
    <div class="stat-card" style="background:var(--color-background-secondary,#F6F4EF);border:none;border-radius:8px;padding:11px 14px">
      <span class="stat-value" style="font-family:'DM Serif Display',serif">${value}</span>
      <span class="stat-label">${esc(label)}</span>
    </div>
  `;
}

function statCardColored(label, value, color) {
  return `
    <div class="stat-card" style="background:var(--color-background-secondary,#F6F4EF);border:none;border-radius:8px;padding:11px 14px">
      <span class="stat-value" style="font-family:'DM Serif Display',serif;color:${color}">${value}</span>
      <span class="stat-label">${esc(label)}</span>
    </div>
  `;
}

function errorMessage(text) {
  return `<div class="text-center text-secondary text-sm" style="padding:2rem">${esc(text)}</div>`;
}

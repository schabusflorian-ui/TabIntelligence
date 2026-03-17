// Analytics Page — Portfolio Health, Cross-Entity Compare, Cost Analysis, Taxonomy Coverage
import { apiGet } from '../api.js';
import { esc, formatNum, formatFinancial } from '../state.js';
import { renderTabs } from '../components/tabs.js';
import { skeletonStats, loadingPlaceholder, errorState } from '../components/loading.js';
import { showToast } from '../components/toast.js';
import { createDropdown } from '../components/dropdown.js';
import { CATEGORY_BADGE_CLASS } from '../constants/categories.js';

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
    { id: 'taxonomy', label: 'Taxonomy Coverage', render: renderTaxonomy },
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
    panel.querySelector('#health-chart-card').style.display = 'none';
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
          <div style="min-width:120px">
            <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Period</label>
            <input type="text" id="compare-period-input" placeholder="e.g. FY2024"
              style="width:100%;padding:6px 10px;border:0.5px solid rgba(0,0,0,0.08);border-radius:8px;font-size:12.5px;background:white;box-sizing:border-box">
          </div>
          <div>
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
      const period = panel.querySelector('#compare-period-input').value.trim();
      const resultsEl = panel.querySelector('#compare-results');

      if (selectedIds.length === 0 && !canonical) {
        showToast('Select at least one entity or enter canonical names', 'warning');
        return;
      }

      resultsEl.innerHTML = loadingPlaceholder('Running comparison...');

      try {
        const params = new URLSearchParams();
        if (selectedIds.length > 0) params.set('entity_ids', selectedIds.join(','));
        if (canonical) params.set('canonical_names', canonical);
        if (period) params.set('period', period);

        const cmpData = await apiGet(`/api/v1/analytics/compare?${params.toString()}`);
        renderCompareResults(resultsEl, cmpData, entities);
      } catch (err) {
        resultsEl.innerHTML = errorState('Comparison failed: ' + (err.message || 'Unknown error'), 'Retry');
        showToast('Comparison failed', 'error');
      }
    });
  } catch (err) {
    ddContainer.innerHTML = '<span class="text-sm text-secondary">Failed to load entities</span>';
  }
}

function renderCompareResults(el, data, entities) {
  const comparisons = data.comparisons || [];

  if (comparisons.length === 0) {
    el.innerHTML = `<div class="text-center text-secondary text-sm" style="padding:3rem">No comparison data found for the selected parameters.</div>`;
    return;
  }

  // Collect all entity IDs across all comparisons to build columns
  const entityMap = new Map();
  for (const cmp of comparisons) {
    for (const ent of (cmp.entities || [])) {
      if (!entityMap.has(ent.entity_id)) {
        entityMap.set(ent.entity_id, ent.entity_name || `Entity ${ent.entity_id}`);
      }
    }
  }

  const entityIds = [...entityMap.keys()];
  if (entityIds.length === 0) {
    el.innerHTML = `<div class="text-center text-secondary text-sm" style="padding:3rem">No entity data in comparison results.</div>`;
    return;
  }

  let html = '<div class="card"><div class="table-wrapper"><table class="data-table"><thead><tr>';
  html += '<th>Canonical Name</th>';
  for (const eid of entityIds) {
    html += `<th class="text-mono" style="text-align:right">${esc(entityMap.get(eid))}</th>`;
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
        html += `<td class="text-mono" style="text-align:right" title="${esc(conf)}">${formatFinancial(match.amount)}</td>`;
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
      panel.querySelector('#costs-trend-card').querySelector('[style*="height:200px"]').innerHTML =
        '<div class="text-center text-secondary text-sm" style="padding:3rem">No trend data available.</div>';
    }
  } catch (err) {
    panel.querySelector('#costs-stats').innerHTML = errorState('Failed to load cost data.', 'Retry');
    panel.querySelector('#costs-stats .error-retry-btn')?.addEventListener('click', () => renderCosts(panel));
    panel.querySelector('#costs-entity-table').innerHTML = '';
    panel.querySelector('#costs-trend-card').style.display = 'none';
    showToast('Failed to load cost analysis', 'error');
  }
}

// ========== TAB 4: Taxonomy Coverage ==========

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

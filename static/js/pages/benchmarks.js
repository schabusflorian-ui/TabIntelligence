// Benchmarks Page — Accuracy trends, category heatmap, run details
import { apiGet } from '../api.js';
import { esc, formatNum } from '../state.js';
import { renderTabs } from '../components/tabs.js';
import { loadingPlaceholder, errorState } from '../components/loading.js';

let chartInstances = [];

export async function render(container) {
  container.innerHTML = `
    <div class="content-header">
      <span class="eyebrow">QUALITY</span>
      <h2 class="page-title">Benchmark Dashboard</h2>
    </div>
    <div class="content-body" id="benchmark-tabs"></div>
  `;

  const tabsContainer = container.querySelector('#benchmark-tabs');

  renderTabs(tabsContainer, [
    { id: 'trends', label: 'Accuracy Trends', render: renderTrendsTab },
    { id: 'heatmap', label: 'Category Heatmap', render: renderHeatmapTab },
  ], 'trends');
}

export function destroy() {
  chartInstances.forEach(c => { try { c.destroy(); } catch (_) {} });
  chartInstances = [];
}

// ========== Trends Tab ==========

async function renderTrendsTab(panel) {
  panel.innerHTML = loadingPlaceholder('Loading benchmark trends...');

  try {
    const data = await apiGet('/benchmarks/trends?limit=100');
    const runs = data.runs || [];

    if (runs.length === 0) {
      panel.innerHTML = `
        <div class="empty-state">
          <p>No benchmark runs found.</p>
          <p class="text-secondary">Run <code>python scripts/benchmark_extraction.py --fixture-dir tests/fixtures/ --save</code> to generate benchmark data.</p>
        </div>`;
      return;
    }

    // Group runs by fixture
    const byFixture = {};
    runs.forEach(r => {
      byFixture[r.fixture_name] = byFixture[r.fixture_name] || [];
      byFixture[r.fixture_name].push(r);
    });

    let html = '<div class="benchmark-trends">';

    // Summary cards
    const latest = {};
    Object.entries(byFixture).forEach(([name, fixtureRuns]) => {
      latest[name] = fixtureRuns[0]; // Already sorted desc
    });

    html += '<div class="benchmark-summary-cards">';
    Object.entries(latest).forEach(([name, run]) => {
      const f1Class = run.mapping_f1 >= 0.9 ? 'metric-good' : run.mapping_f1 >= 0.7 ? 'metric-warn' : 'metric-bad';
      html += `
        <div class="benchmark-card">
          <div class="benchmark-card-title">${esc(name)}</div>
          <div class="benchmark-card-metric ${f1Class}">
            ${(run.mapping_f1 * 100).toFixed(1)}%
          </div>
          <div class="benchmark-card-label">F1 Score</div>
          <div class="benchmark-card-details">
            <span>P: ${(run.mapping_precision * 100).toFixed(0)}%</span>
            <span>R: ${(run.mapping_recall * 100).toFixed(0)}%</span>
            <span>Triage: ${(run.triage_accuracy * 100).toFixed(0)}%</span>
          </div>
        </div>`;
    });
    html += '</div>';

    // Detailed table
    html += `
      <h3 class="section-title">Recent Runs</h3>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>Fixture</th>
              <th>Date</th>
              <th>F1</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>Triage</th>
              <th>Value Match</th>
              <th>Duration</th>
              <th>Tokens</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>`;

    runs.slice(0, 50).forEach(r => {
      const date = r.run_date ? new Date(r.run_date).toLocaleDateString() : 'N/A';
      const f1Class = r.mapping_f1 >= 0.9 ? 'metric-good' : r.mapping_f1 >= 0.7 ? 'metric-warn' : 'metric-bad';

      html += `<tr>
        <td>${esc(r.fixture_name)}</td>
        <td>${date}</td>
        <td class="${f1Class}">${(r.mapping_f1 * 100).toFixed(1)}%</td>
        <td>${(r.mapping_precision * 100).toFixed(1)}%</td>
        <td>${(r.mapping_recall * 100).toFixed(1)}%</td>
        <td>${(r.triage_accuracy * 100).toFixed(1)}%</td>
        <td>${(r.value_tolerance_match_rate * 100).toFixed(1)}%</td>
        <td>${r.duration_seconds != null ? r.duration_seconds.toFixed(1) + 's' : 'N/A'}</td>
        <td>${r.tokens_used != null ? formatNum(r.tokens_used) : 'N/A'}</td>
        <td>${r.cost_usd != null ? '$' + r.cost_usd.toFixed(4) : 'N/A'}</td>
      </tr>`;
    });

    html += '</tbody></table></div></div>';
    panel.innerHTML = html;

  } catch (e) {
    panel.innerHTML = errorState('Failed to load benchmark trends', e.message);
  }
}

// ========== Heatmap Tab ==========

async function renderHeatmapTab(panel) {
  panel.innerHTML = loadingPlaceholder('Loading category heatmap...');

  try {
    const data = await apiGet('/benchmarks/category-heatmap?limit=10');

    if (!data.categories || data.categories.length === 0) {
      panel.innerHTML = `
        <div class="empty-state">
          <p>No category metrics available.</p>
          <p class="text-secondary">Run benchmarks with gold standards to generate per-category accuracy data.</p>
        </div>`;
      return;
    }

    let html = '<div class="benchmark-heatmap">';
    html += '<h3 class="section-title">F1 Score by Category &amp; Run</h3>';

    html += '<div class="table-scroll"><table class="data-table heatmap-table"><thead><tr>';
    html += '<th>Category</th>';
    data.runs.forEach(r => {
      const label = r.length > 20 ? r.slice(0, 20) + '...' : r;
      html += `<th class="heatmap-col">${esc(label)}</th>`;
    });
    html += '</tr></thead><tbody>';

    data.categories.forEach(cat => {
      html += `<tr><td class="heatmap-cat">${esc(cat)}</td>`;
      data.runs.forEach(run => {
        const f1 = data.heatmap[cat]?.[run];
        if (f1 != null) {
          const pct = (f1 * 100).toFixed(0);
          const color = _heatmapColor(f1);
          html += `<td class="heatmap-cell" style="background:${color}">${pct}%</td>`;
        } else {
          html += '<td class="heatmap-cell heatmap-empty">—</td>';
        }
      });
      html += '</tr>';
    });

    html += '</tbody></table></div></div>';
    panel.innerHTML = html;

  } catch (e) {
    panel.innerHTML = errorState('Failed to load category heatmap', e.message);
  }
}

function _heatmapColor(f1) {
  if (f1 >= 0.9) return '#e6f4ea';  // Green
  if (f1 >= 0.8) return '#d4edda';
  if (f1 >= 0.7) return '#fef7e0';  // Yellow
  if (f1 >= 0.5) return '#fff3cd';
  return '#fce8e6';                   // Red
}

// Comparison Page — Structured Financial Statements & Multi-Period Comparison
import { apiGet } from '../api.js';
import { esc, formatFinancial, downloadBlob } from '../state.js';
import { loadingPlaceholder, spinner, errorState } from '../components/loading.js';
import { showToast } from '../components/toast.js';
import { emptyState } from '../components/empty-state.js';
import { createDropdown } from '../components/dropdown.js';

let dropdownInstances = [];
let currentData = null;

// Category tab definitions
const CATEGORIES = [
  { id: 'income_statement', label: 'IS' },
  { id: 'balance_sheet', label: 'BS' },
  { id: 'cash_flow', label: 'CF' },
  { id: 'debt_schedule', label: 'Debt Schedule' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'all', label: 'All' },
];

// ========== Main render / destroy ==========

export async function render(container) {
  container.innerHTML = `
    <div class="content-header">
      <span class="eyebrow">ANALYSIS</span>
      <h2 class="page-title">Financial Comparison</h2>
    </div>
    <div class="content-body">
      <!-- Controls Section -->
      <div class="card" style="margin-bottom:20px">
        <div class="card-header"><span class="card-title">Parameters</span></div>
        <div style="padding:16px">
          <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
            <div style="flex:1;min-width:220px">
              <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Entity</label>
              <div id="cmp-entity-dropdown"></div>
            </div>
            <div id="cmp-period-section" style="flex:2;min-width:200px;display:none">
              <label style="display:block;font-size:10.5px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#888;margin-bottom:4px">Periods</label>
              <div id="cmp-period-pills" style="display:flex;flex-wrap:wrap;gap:6px"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Category Tabs -->
      <div id="cmp-category-tabs" style="margin-bottom:16px;display:none">
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          ${CATEGORIES.map(cat => `
            <button class="cmp-cat-btn${cat.id === 'income_statement' ? ' active' : ''}" data-cat="${cat.id}">
              ${esc(cat.label)}
            </button>
          `).join('')}
        </div>
      </div>

      <!-- Results Area -->
      <div id="cmp-results">
        ${emptyState({ icon: '\uD83D\uDCCA', title: 'Select an entity', description: 'Choose an entity above to view structured financial statements.' })}
      </div>
    </div>
  `;

  // Load entities
  const ddContainer = container.querySelector('#cmp-entity-dropdown');
  ddContainer.innerHTML = spinner('spinner-sm');
  try {
    const entData = await apiGet('/api/v1/entities/');
    const entities = entData.entities || [];
    const options = entities.map(e => ({
      value: String(e.id),
      label: e.name || `Entity ${e.id}`,
    }));

    const dd = createDropdown(ddContainer, {
      options,
      placeholder: 'Select entity...',
      multi: false,
      searchable: true,
      onChange: (selected) => {
        const sel = [...selected];
        if (sel.length > 0) {
          onEntitySelected(container, sel[0]);
        }
      },
    });
    dropdownInstances.push(dd);
  } catch {
    ddContainer.innerHTML = errorState('Failed to load entities', 'Retry');
    ddContainer.querySelector('.error-retry-btn')?.addEventListener('click', () => render(container));
  }

  // Category tab handlers
  container.querySelectorAll('.cmp-cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.cmp-cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      onCategoryChanged(container, btn.dataset.cat);
    });
  });
}

export function destroy() {
  dropdownInstances.forEach(d => d.destroy());
  dropdownInstances = [];
  currentData = null;
}

// ========== Event Handlers ==========

let selectedEntityId = null;
let selectedPeriods = new Set();
let activeCategory = 'income_statement';
let availablePeriods = [];

async function onEntitySelected(container, entityId) {
  selectedEntityId = entityId;
  selectedPeriods.clear();
  availablePeriods = [];

  // Show category tabs
  container.querySelector('#cmp-category-tabs').style.display = '';

  // Load initial statement to discover periods
  await loadStatement(container);
}

async function onCategoryChanged(container, category) {
  activeCategory = category;
  await loadStatement(container);
}

async function loadStatement(container) {
  const resultsEl = container.querySelector('#cmp-results');

  if (!selectedEntityId) {
    resultsEl.innerHTML = emptyState({ icon: '\uD83D\uDCCA', title: 'Select an entity', description: 'Choose an entity above to view structured financial statements.' });
    return;
  }

  resultsEl.innerHTML = loadingPlaceholder('Loading statement data...');

  try {
    if (activeCategory === 'all') {
      // Load all categories
      const allCategories = CATEGORIES.filter(c => c.id !== 'all');
      const results = await Promise.all(
        allCategories.map(cat =>
          apiGet(`/api/v1/analytics/entity/${selectedEntityId}/statement?category=${cat.id}`)
            .catch(() => null)
        )
      );

      // Merge all periods and items
      const allPeriods = new Set();
      const allItems = [];
      for (let i = 0; i < results.length; i++) {
        const r = results[i];
        if (r && r.items && r.items.length > 0) {
          r.periods.forEach(p => allPeriods.add(p));
          allItems.push(...r.items);
        }
      }

      currentData = {
        entity_id: selectedEntityId,
        entity_name: results.find(r => r && r.entity_name)?.entity_name || null,
        category: 'all',
        periods: [...allPeriods].sort(),
        items: allItems,
        total_items: allItems.length,
      };
    } else {
      currentData = await apiGet(
        `/api/v1/analytics/entity/${selectedEntityId}/statement?category=${activeCategory}`
      );
    }

    // Discover periods and update period pills
    if (currentData.periods && currentData.periods.length > 0) {
      availablePeriods = currentData.periods;
      // Default: select all periods
      if (selectedPeriods.size === 0) {
        availablePeriods.forEach(p => selectedPeriods.add(p));
      }
      renderPeriodPills(container);
    }

    renderStatementTable(resultsEl, currentData);
  } catch (err) {
    resultsEl.innerHTML = errorState('Failed to load statement: ' + (err.message || 'Unknown error'), 'Retry');
    resultsEl.querySelector('.error-retry-btn')?.addEventListener('click', () => loadStatement(container));
    showToast('Failed to load statement', 'error');
  }
}

function renderPeriodPills(container) {
  const section = container.querySelector('#cmp-period-section');
  const pillsEl = container.querySelector('#cmp-period-pills');
  section.style.display = '';

  pillsEl.innerHTML = availablePeriods.map(p => {
    const isSelected = selectedPeriods.has(p);
    return `<button class="cmp-period-pill" data-period="${esc(p)}"
      style="padding:4px 12px;border-radius:12px;font-size:11.5px;cursor:pointer;
        border:0.5px solid ${isSelected ? '#1D6B9F' : 'rgba(0,0,0,0.08)'};
        background:${isSelected ? 'rgba(29,107,159,0.08)' : 'white'};
        color:${isSelected ? '#1D6B9F' : '#555'};
        font-weight:${isSelected ? '500' : '400'};transition:all 0.15s ease">
      ${esc(p)}
    </button>`;
  }).join('');

  pillsEl.querySelectorAll('.cmp-period-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      const period = btn.dataset.period;
      if (selectedPeriods.has(period)) {
        // Don't allow deselecting all
        if (selectedPeriods.size > 1) {
          selectedPeriods.delete(period);
        }
      } else {
        selectedPeriods.add(period);
      }
      renderPeriodPills(container);
      // Re-render the table with updated period selection
      const resultsEl = container.querySelector('#cmp-results');
      if (currentData) {
        renderStatementTable(resultsEl, currentData);
      }
    });
  });
}

// ========== Statement Table Rendering ==========

function renderStatementTable(el, data) {
  const items = data.items || [];
  const periods = (data.periods || []).filter(p => selectedPeriods.has(p));

  if (items.length === 0) {
    el.innerHTML = emptyState({ icon: '\uD83D\uDCCA', title: 'No statement data', description: 'No statement data found for this category.' });
    return;
  }

  // Build header
  let html = '<div class="card">';

  // Export button
  html += `<div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
    <span class="card-title">${esc(getCategoryLabel(data.category))} Statement${data.entity_name ? ' - ' + esc(data.entity_name) : ''}</span>
    <button id="cmp-export-csv" style="padding:5px 14px;border:0.5px solid rgba(0,0,0,0.08);
      border-radius:6px;font-size:11.5px;cursor:pointer;background:white;color:#555">
      Export CSV
    </button>
  </div>`;

  html += '<div class="table-wrapper"><table class="data-table"><thead><tr>';
  html += '<th style="text-align:left;min-width:250px">Line Item</th>';

  // Period columns
  for (const p of periods) {
    html += `<th class="text-mono" style="text-align:right;min-width:100px">${esc(p)}</th>`;
  }

  // Variance columns (between adjacent periods)
  for (let i = 0; i < periods.length - 1; i++) {
    html += `<th class="text-mono" style="text-align:right;min-width:90px;font-size:10.5px;color:#888">${esc(periods[i + 1])} vs ${esc(periods[i])}</th>`;
  }

  html += '</tr></thead><tbody>';

  // Render items recursively
  html += renderItemRows(items, periods, 0);

  html += '</tbody></table></div></div>';

  el.innerHTML = html;

  // Wire up CSV export
  const exportBtn = el.querySelector('#cmp-export-csv');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => exportCSV(data, periods));
  }
}

function renderItemRows(items, periods, depth) {
  let html = '';
  for (const item of items) {
    const indent = depth * 24;
    const isBold = item.is_subtotal === true;
    const fontWeight = isBold ? '600' : '400';
    const bgColor = isBold ? 'rgba(0,0,0,0.015)' : 'transparent';
    const borderTop = isBold ? '1px solid rgba(0,0,0,0.06)' : 'none';

    const displayName = item.display_name || item.canonical_name.replace(/_/g, ' ');

    html += `<tr style="background:${bgColor}">`;
    html += `<td style="padding-left:${indent + 12}px;font-weight:${fontWeight};border-top:${borderTop}">
      ${esc(displayName)}
    </td>`;

    // Period values
    for (const p of periods) {
      const val = item.values ? item.values[p] : undefined;
      html += `<td class="text-mono" style="text-align:right;font-weight:${fontWeight};border-top:${borderTop}">
        ${formatFinancialValue(val)}
      </td>`;
    }

    // Variance columns
    for (let i = 0; i < periods.length - 1; i++) {
      const fromVal = item.values ? item.values[periods[i]] : undefined;
      const toVal = item.values ? item.values[periods[i + 1]] : undefined;

      if (fromVal != null && toVal != null) {
        const change = toVal - fromVal;
        const pctChange = fromVal !== 0 ? ((change / Math.abs(fromVal)) * 100) : null;
        const color = change > 0 ? '#1A7A4A' : change < 0 ? '#A32626' : '#888';
        const arrow = change > 0 ? '+' : '';

        let displayText = `${arrow}${formatFinancialValue(change)}`;
        if (pctChange != null) {
          displayText += ` (${arrow}${pctChange.toFixed(1)}%)`;
        }

        html += `<td class="text-mono" style="text-align:right;font-size:11px;color:${color};border-top:${borderTop}">
          ${displayText}
        </td>`;
      } else {
        html += `<td class="text-mono text-secondary" style="text-align:right;font-size:11px;border-top:${borderTop}">-</td>`;
      }
    }

    html += '</tr>';

    // Render children
    if (item.children && item.children.length > 0) {
      html += renderItemRows(item.children, periods, depth + 1);
    }
  }
  return html;
}

// ========== CSV Export ==========

function exportCSV(data, periods) {
  const rows = [];

  // Header row
  const header = ['Line Item'];
  for (const p of periods) {
    header.push(p);
  }
  for (let i = 0; i < periods.length - 1; i++) {
    header.push(`${periods[i + 1]} vs ${periods[i]} (Change)`);
    header.push(`${periods[i + 1]} vs ${periods[i]} (%)`);
  }
  rows.push(header);

  // Data rows
  flattenItemsForCSV(data.items || [], periods, rows, 0);

  // Build CSV string
  const csvContent = rows.map(row =>
    row.map(cell => {
      const str = cell == null ? '' : String(cell);
      if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return '"' + str.replace(/"/g, '""') + '"';
      }
      return str;
    }).join(',')
  ).join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const filename = `${data.category}_statement_${data.entity_id || 'export'}.csv`;
  downloadBlob(blob, filename);
  showToast('CSV exported successfully', 'success');
}

function flattenItemsForCSV(items, periods, rows, depth) {
  for (const item of items) {
    const prefix = '  '.repeat(depth);
    const displayName = item.display_name || item.canonical_name.replace(/_/g, ' ');
    const row = [prefix + displayName];

    for (const p of periods) {
      const val = item.values ? item.values[p] : null;
      row.push(val != null ? val : '');
    }

    for (let i = 0; i < periods.length - 1; i++) {
      const fromVal = item.values ? item.values[periods[i]] : null;
      const toVal = item.values ? item.values[periods[i + 1]] : null;

      if (fromVal != null && toVal != null) {
        const change = toVal - fromVal;
        const pctChange = fromVal !== 0 ? ((change / Math.abs(fromVal)) * 100) : null;
        row.push(change);
        row.push(pctChange != null ? pctChange.toFixed(2) + '%' : '');
      } else {
        row.push('');
        row.push('');
      }
    }

    rows.push(row);

    if (item.children && item.children.length > 0) {
      flattenItemsForCSV(item.children, periods, rows, depth + 1);
    }
  }
}

// ========== Helpers ==========

function formatFinancialValue(v) {
  if (v == null || v === undefined) return '<span class="text-secondary">-</span>';
  if (typeof v !== 'number') return esc(String(v));
  if (v < 0) return '(' + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ')';
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function getCategoryLabel(category) {
  const labels = {
    income_statement: 'Income Statement',
    balance_sheet: 'Balance Sheet',
    cash_flow: 'Cash Flow',
    debt_schedule: 'Debt Schedule',
    metrics: 'Metrics',
    project_finance: 'Project Finance',
    all: 'All Categories',
  };
  return labels[category] || category;
}

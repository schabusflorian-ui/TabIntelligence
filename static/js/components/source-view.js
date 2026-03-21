/**
 * Source View Component — Renders Excel data as a color-coded grid
 * showing mapping status for each cell.
 *
 * Colors:
 *   Green (#e6f4ea)  — mapped with high confidence (>= 0.80)
 *   Yellow (#fef7e0) — mapped with low confidence (< 0.80)
 *   Red (#fce8e6)    — unmapped
 *   Gray (#f1f3f4)   — header/skipped
 */

import { apiGet } from '../api.js';
import { esc, formatNum } from '../state.js';
import { showToast } from '../components/toast.js';

// Color mapping based on cell status
const STATUS_COLORS = {
  mapped:   { bg: '#e6f4ea', border: '#34a853' },
  unmapped: { bg: '#fce8e6', border: '#ea4335' },
  header:   { bg: '#f1f3f4', border: '#9aa0a6' },
  skipped:  { bg: '#f8f9fa', border: '#dadce0' },
};

function getCellColor(cell) {
  const status = cell.mapping_status || cell.cell_role || 'skipped';
  if (status === 'mapped' && cell.confidence && cell.confidence < 0.80) {
    return { bg: '#fef7e0', border: '#fbbc04' }; // low confidence yellow
  }
  return STATUS_COLORS[status] || STATUS_COLORS.skipped;
}

/**
 * Render the Source View into a container element.
 *
 * @param {HTMLElement} container - The tab panel element
 * @param {string} jobId - The extraction job ID
 * @param {object} data - The extraction result data (from export)
 */
export async function renderSourceView(container, jobId, data) {
  container.innerHTML = '<div class="source-view-loading">Loading cell mappings...</div>';

  let cellStats;
  try {
    cellStats = await apiGet(`/jobs/${jobId}/cells/stats`);
  } catch (e) {
    container.innerHTML = `
      <div class="source-view-empty">
        <p>Cell mapping data is not available for this job.</p>
        <p class="text-secondary">Cell mappings are generated during extraction.
        Re-extract the file to populate cell-level data.</p>
      </div>`;
    return;
  }

  // Get sheets from the extraction result
  const sheets = data?.sheets || [];
  if (sheets.length === 0 && (!cellStats?.sheets || Object.keys(cellStats.sheets).length === 0)) {
    container.innerHTML = '<div class="source-view-empty">No sheet data available.</div>';
    return;
  }

  // Build sheet tabs + grid container
  const sheetNames = sheets.map(s => s.sheet_name || s.name);
  const statsSheets = cellStats?.sheets ? Object.keys(cellStats.sheets) : [];
  const allSheets = [...new Set([...sheetNames, ...statsSheets])];

  let html = '<div class="source-view">';

  // Sheet selector tabs
  html += '<div class="source-view-sheets">';
  allSheets.forEach((name, i) => {
    const stats = cellStats?.sheets?.[name] || {};
    const active = i === 0 ? ' active' : '';
    const mapped = stats.mapped || 0;
    const unmapped = stats.unmapped || 0;
    const total = stats.total || 0;
    html += `<button class="source-sheet-tab${active}" data-sheet="${esc(name)}">
      ${esc(name)}
      ${total > 0 ? `<span class="sheet-stats">${mapped}/${total}</span>` : ''}
    </button>`;
  });
  html += '</div>';

  // Legend
  html += `<div class="source-view-legend">
    <span class="legend-item"><span class="legend-dot" style="background:#34a853"></span> Mapped</span>
    <span class="legend-item"><span class="legend-dot" style="background:#fbbc04"></span> Low Confidence</span>
    <span class="legend-item"><span class="legend-dot" style="background:#ea4335"></span> Unmapped</span>
    <span class="legend-item"><span class="legend-dot" style="background:#9aa0a6"></span> Header</span>
  </div>`;

  // Grid container (populated per-sheet)
  html += '<div class="source-view-grid" id="sv-grid"></div>';

  // Detail panel (shown on cell click)
  html += '<div class="source-view-detail" id="sv-detail" style="display:none"></div>';

  html += '</div>';
  container.innerHTML = html;

  // Wire up sheet tab clicks
  const tabs = container.querySelectorAll('.source-sheet-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', async () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      await loadSheet(container, jobId, tab.dataset.sheet, data);
    });
  });

  // Load first sheet
  if (allSheets.length > 0) {
    await loadSheet(container, jobId, allSheets[0], data);
  }
}

async function loadSheet(container, jobId, sheetName, data) {
  const gridEl = container.querySelector('#sv-grid');
  gridEl.innerHTML = '<div class="source-view-loading">Loading sheet...</div>';

  // Get cell mappings for this sheet
  let cells = [];
  try {
    const resp = await apiGet(`/jobs/${jobId}/cells?sheet_name=${encodeURIComponent(sheetName)}&limit=5000`);
    cells = resp?.cells || resp?.items || [];
  } catch (e) {
    // Fallback: use structured data from extraction result
  }

  // Get sheet data from the extraction result
  const sheetData = (data?.sheets || []).find(
    s => (s.sheet_name || s.name) === sheetName
  );

  // Build cell lookup map
  const cellMap = {};
  cells.forEach(c => {
    const key = `${c.row_index || 0}_${c.col_index || 0}`;
    cellMap[key] = c;
    // Also index by cell_ref
    if (c.cell_ref) cellMap[c.cell_ref] = c;
  });

  // Build grid from structured data or cell mappings
  let html = '<div class="source-grid-scroll"><table class="source-grid-table"><tbody>';

  if (sheetData?.rows?.length > 0) {
    // Use structured data (original Excel layout)
    sheetData.rows.forEach(row => {
      html += '<tr>';
      const rowCells = row.cells || [];
      rowCells.forEach(cell => {
        const ref = cell.ref || '';
        const mapping = cellMap[ref] || {};
        const color = getCellColor(mapping);
        const value = cell.value != null ? cell.value : '';
        const displayValue = typeof value === 'number' ? formatNum(value) : esc(String(value));
        const bold = cell.is_bold ? ' font-weight:600;' : '';
        const indent = cell.indent_level ? ` padding-left:${cell.indent_level * 16 + 8}px;` : '';
        const canonical = mapping.canonical_name ? ` title="${esc(mapping.canonical_name)}"` : '';

        html += `<td class="sv-cell"
          style="background:${color.bg}; border-left:3px solid ${color.border};${bold}${indent}"
          data-ref="${esc(ref)}" data-sheet="${esc(sheetName)}"${canonical}>
          ${displayValue}
        </td>`;
      });
      html += '</tr>';
    });
  } else if (cells.length > 0) {
    // Build grid from cell mapping data
    const maxRow = Math.max(...cells.map(c => c.row_index || 0));
    const maxCol = Math.max(...cells.map(c => c.col_index || 0));

    for (let r = 0; r <= Math.min(maxRow, 200); r++) {
      html += '<tr>';
      for (let c = 0; c <= Math.min(maxCol, 26); c++) {
        const mapping = cellMap[`${r}_${c}`] || {};
        const color = getCellColor(mapping);
        const value = mapping.raw_value != null ? mapping.raw_value : '';
        const displayValue = typeof value === 'number' ? formatNum(value) : esc(String(value));
        const ref = mapping.cell_ref || '';

        html += `<td class="sv-cell"
          style="background:${color.bg}; border-left:3px solid ${color.border};"
          data-ref="${esc(ref)}" data-sheet="${esc(sheetName)}">
          ${displayValue}
        </td>`;
      }
      html += '</tr>';
    }
  } else {
    html += '<tr><td class="sv-cell" colspan="10">No cell data available for this sheet.</td></tr>';
  }

  html += '</tbody></table></div>';
  gridEl.innerHTML = html;

  // Wire up cell click handlers
  gridEl.querySelectorAll('.sv-cell').forEach(cell => {
    cell.addEventListener('click', () => {
      const ref = cell.dataset.ref;
      const sheet = cell.dataset.sheet;
      if (ref) showCellDetail(container, jobId, sheet, ref);

      // Highlight selected cell
      gridEl.querySelectorAll('.sv-cell.selected').forEach(c => c.classList.remove('selected'));
      cell.classList.add('selected');
    });
  });
}

async function showCellDetail(container, jobId, sheetName, cellRef) {
  const detailEl = container.querySelector('#sv-detail');
  detailEl.style.display = 'block';
  detailEl.innerHTML = '<div class="source-view-loading">Loading...</div>';

  try {
    const cell = await apiGet(`/jobs/${jobId}/cells/${encodeURIComponent(sheetName)}/${encodeURIComponent(cellRef)}`);

    let html = '<div class="sv-detail-content">';
    html += `<div class="sv-detail-header">
      <strong>${esc(cellRef)}</strong> — ${esc(sheetName)}
      <button class="sv-detail-close" id="sv-close">&times;</button>
    </div>`;

    if (cell.canonical_name && cell.canonical_name !== 'unmapped') {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Canonical:</span>
        <span class="sv-value">${esc(cell.canonical_name)}</span>
      </div>`;
    }

    html += `<div class="sv-detail-row">
      <span class="sv-label">Status:</span>
      <span class="sv-value">${esc(cell.mapping_status || 'unknown')}</span>
    </div>`;

    if (cell.confidence) {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Confidence:</span>
        <span class="sv-value">${(cell.confidence * 100).toFixed(1)}%</span>
      </div>`;
    }

    if (cell.raw_value != null) {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Raw Value:</span>
        <span class="sv-value">${esc(String(cell.raw_value))}</span>
      </div>`;
    }

    if (cell.original_label) {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Label:</span>
        <span class="sv-value">${esc(cell.original_label)}</span>
      </div>`;
    }

    if (cell.cell_role) {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Role:</span>
        <span class="sv-value">${esc(cell.cell_role)}</span>
      </div>`;
    }

    if (cell.has_formula && cell.formula_text) {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Formula:</span>
        <span class="sv-value mono">${esc(cell.formula_text)}</span>
      </div>`;
    }

    if (cell.period) {
      html += `<div class="sv-detail-row">
        <span class="sv-label">Period:</span>
        <span class="sv-value">${esc(cell.period)}</span>
      </div>`;
    }

    html += '</div>';
    detailEl.innerHTML = html;

    // Close button
    detailEl.querySelector('#sv-close').addEventListener('click', () => {
      detailEl.style.display = 'none';
    });
  } catch (e) {
    detailEl.innerHTML = `<div class="sv-detail-content">
      <p>Could not load cell detail for ${esc(cellRef)}.</p>
    </div>`;
  }
}

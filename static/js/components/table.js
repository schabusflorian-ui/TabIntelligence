// Reusable Sortable Data Table Component
import { esc } from '../state.js';

/**
 * Render a sortable, clickable data table.
 * @param {HTMLElement} container
 * @param {Object} opts
 * @param {Array<{key, label, sortable?, render?, className?}>} opts.columns
 * @param {Array<Object>} opts.data
 * @param {Function} [opts.onRowClick] - (row, e) => void
 * @param {string} [opts.emptyMessage]
 * @param {string} [opts.className] - additional table class
 */
export function renderTable(container, opts) {
  const { columns, data, onRowClick, emptyMessage, className } = opts;

  let sortCol = null;
  let sortAsc = true;
  let sortedData = [...data];

  function render() {
    const clickable = onRowClick ? ' clickable' : '';
    let html = `<div class="table-wrapper"><table class="data-table ${className || ''}">`;

    // Header
    html += '<thead><tr>';
    for (const col of columns) {
      const sortClass = col.sortable ? ' sortable' : '';
      let sortIcon = '';
      if (col.sortable && sortCol === col.key) {
        sortIcon = `<span class="sort-icon">${sortAsc ? '\u25B2' : '\u25BC'}</span>`;
      } else if (col.sortable) {
        sortIcon = '<span class="sort-icon" style="opacity:0.3">\u25B2</span>';
      }
      html += `<th class="${sortClass} ${col.className || ''}" data-sort-key="${col.key}">${esc(col.label)}${sortIcon}</th>`;
    }
    html += '</tr></thead>';

    // Body
    html += '<tbody>';
    if (sortedData.length === 0) {
      html += `<tr><td colspan="${columns.length}" class="text-center text-secondary" style="padding:2rem">${esc(emptyMessage || 'No data')}</td></tr>`;
    } else {
      for (const row of sortedData) {
        const rowClass = row._rowClass || '';
        html += `<tr class="${clickable} ${rowClass}" data-row-id="${esc(row._id || '')}">`;
        for (const col of columns) {
          const val = row[col.key];
          const cellClass = col.className || '';
          const rendered = col.render ? col.render(val, row) : esc(val == null ? '' : String(val));
          html += `<td class="${cellClass}">${rendered}</td>`;
        }
        html += '</tr>';
      }
    }
    html += '</tbody></table></div>';

    container.innerHTML = html;

    // Attach sort handlers
    container.querySelectorAll('th.sortable').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.sortKey;
        if (sortCol === key) {
          sortAsc = !sortAsc;
        } else {
          sortCol = key;
          sortAsc = true;
        }
        sortedData = [...data].sort((a, b) => {
          let va = a[key], vb = b[key];
          if (va == null) va = '';
          if (vb == null) vb = '';
          if (typeof va === 'number' && typeof vb === 'number') {
            return sortAsc ? va - vb : vb - va;
          }
          va = String(va).toLowerCase();
          vb = String(vb).toLowerCase();
          return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        });
        render();
      });
    });

    // Row click handlers
    if (onRowClick) {
      container.querySelectorAll('tbody tr.clickable').forEach(tr => {
        tr.addEventListener('click', (e) => {
          const id = tr.dataset.rowId;
          const row = data.find(r => String(r._id) === id) || {};
          onRowClick(row, e);
        });
      });
    }
  }

  render();
  return { refresh: (newData) => { sortedData = [...newData]; data.length = 0; data.push(...newData); render(); } };
}

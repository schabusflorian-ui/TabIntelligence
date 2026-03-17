// Loading & Skeleton Components
import { esc } from '../state.js';

/** Render skeleton rows for a table */
export function skeletonTable(rows = 5, cols = 4) {
  let html = '<div class="table-wrapper"><table class="data-table"><tbody>';
  for (let i = 0; i < rows; i++) {
    html += '<tr>';
    for (let j = 0; j < cols; j++) {
      const width = 40 + Math.random() * 50;
      html += `<td><div class="skeleton skeleton-text" style="width:${width}%"></div></td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  return html;
}

/** Render skeleton stat cards */
export function skeletonStats(count = 4) {
  let html = '<div class="stats-grid">';
  for (let i = 0; i < count; i++) {
    html += '<div class="stat-card"><div class="skeleton skeleton-text" style="width:50%;margin:0 auto"></div><div class="skeleton skeleton-text" style="width:70%;margin:4px auto 0"></div></div>';
  }
  html += '</div>';
  return html;
}

/** Inline spinner */
export function spinner(size = '') {
  return `<span class="spinner ${size}"></span>`;
}

/** Full-width loading indicator for a content area */
export function loadingPlaceholder(message = 'Loading...') {
  return `<div class="text-center" style="padding:3rem"><span class="spinner spinner-lg"></span><p class="text-secondary text-sm" style="margin-top:1rem">${message}</p></div>`;
}

/** Error state with optional retry button */
export function errorState(message, retryLabel) {
  const btn = retryLabel
    ? `<button class="btn btn-sm error-retry-btn" style="margin-top:12px">${esc(retryLabel)}</button>`
    : '';
  return `<div class="error-box" style="margin:var(--space-4)"><p>${esc(message)}</p>${btn}</div>`;
}

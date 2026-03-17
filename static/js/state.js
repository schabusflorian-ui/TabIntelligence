// DebtFund Shared State Module
// Lightweight reactive state for cross-component communication

const listeners = {};

const state = {
  // Current polling state
  activeJobId: null,
  pollTimer: null,
  pollInterval: 2000,

  // Cached data
  resultData: null,
  pendingCorrections: {},

  // UI state
  activeDropdown: null,
};

/** Get a state value */
export function get(key) {
  return state[key];
}

/** Set a state value and notify listeners */
export function set(key, value) {
  const old = state[key];
  state[key] = value;
  if (listeners[key]) {
    listeners[key].forEach(fn => fn(value, old));
  }
}

/** Subscribe to state changes */
export function on(key, fn) {
  if (!listeners[key]) listeners[key] = [];
  listeners[key].push(fn);
  return () => {
    listeners[key] = listeners[key].filter(f => f !== fn);
  };
}

/** Reset extraction state (for new upload) */
export function resetExtraction() {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  set('activeJobId', null);
  set('pollTimer', null);
  set('pollInterval', 2000);
  set('resultData', null);
  set('pendingCorrections', {});
}

// --- Utility functions used across pages ---

/** Escape HTML to prevent XSS */
export function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

/** Format number for display with locale awareness */
export function formatNum(v) {
  if (v == null) return '-';
  if (typeof v === 'number') return v.toLocaleString();
  return String(v);
}

/**
 * Format financial numbers: tabular, negative in parentheses.
 * e.g. -125000 → "(125,000)"
 */
export function formatFinancial(v) {
  if (v == null) return '-';
  if (typeof v !== 'number') return String(v);
  if (v < 0) return '(' + Math.abs(v).toLocaleString() + ')';
  return v.toLocaleString();
}

/** Format relative time: "2m ago", "3h ago", "5d ago" */
export function timeAgo(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + 'h ago';
  const days = Math.floor(hours / 24);
  if (days < 30) return days + 'd ago';
  return d.toLocaleDateString();
}

/** Trigger a file download from a Blob */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

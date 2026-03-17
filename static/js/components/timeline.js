// Timeline Component — Horizontal 5-stage extraction pipeline visualization
// "Lineage is the moat." Every design decision makes provenance visible.
import { esc, timeAgo } from '../state.js';

/**
 * Stage definitions mapping API keys to display labels and metric extractors.
 */
const STAGES = [
  {
    key: 'stage_1_parsing',
    label: 'Parsing',
    metric: (d) => {
      const count = d?.sheets_count;
      return count != null ? count + ' sheet' + (count !== 1 ? 's' : '') : null;
    },
  },
  {
    key: 'stage_2_triage',
    label: 'Triage',
    metric: (d) => {
      const t1 = d?.tier_1_count ?? 0;
      const t2 = d?.tier_2_count ?? 0;
      const total = t1 + t2;
      return total > 0 ? total + ' item' + (total !== 1 ? 's' : '') + ' selected' : null;
    },
  },
  {
    key: 'stage_3_mapping',
    label: 'Mapping',
    metric: (d) => {
      const mapped = d?.mappings_count;
      const cached = d?.pattern_matched;
      let parts = [];
      if (mapped != null) parts.push(mapped + ' mapped');
      if (cached != null && cached > 0) parts.push(cached + ' cached');
      return parts.length ? parts.join(', ') : null;
    },
  },
  {
    key: 'stage_4_validation',
    label: 'Validation',
    metric: (d) => {
      const passed = d?.total_passed;
      const total = d?.total_checks;
      if (passed != null && total != null) return passed + '/' + total + ' passed';
      return null;
    },
  },
  {
    key: 'stage_5_enhanced_mapping',
    label: 'Enhancement',
    metric: (d) => {
      const count = d?.remapped_count;
      return count != null ? count + ' re-mapped' : null;
    },
  },
];

/**
 * Determine stage status from event data.
 * Returns 'completed', 'active', or 'pending'.
 */
function stageStatus(stageKey, events) {
  const event = events.find(e => e.stage === stageKey || e.stage_key === stageKey || e.stage_name === stageKey);
  if (!event) return 'pending';
  if (event.status === 'completed' || event.completed_at) return 'completed';
  if (event.status === 'active' || event.status === 'processing' || event.status === 'running') return 'active';
  // If event exists but has no explicit status, it was recorded so it completed
  return 'completed';
}

/**
 * Extract event data for a specific stage.
 */
function stageEvent(stageKey, events) {
  return events.find(e => e.stage === stageKey || e.stage_key === stageKey || e.stage_name === stageKey) || null;
}

/**
 * Format duration in a human-readable way.
 */
function formatDuration(ms) {
  if (ms == null || ms < 0) return null;
  if (ms < 1000) return ms + 'ms';
  const sec = (ms / 1000).toFixed(1);
  if (sec < 60) return sec + 's';
  const min = Math.floor(ms / 60000);
  const remSec = Math.round((ms % 60000) / 1000);
  return min + 'm ' + remSec + 's';
}

/**
 * Render the horizontal 5-stage pipeline timeline.
 *
 * @param {HTMLElement} container - DOM element to render into
 * @param {Array} events - Lineage event array from GET /api/v1/jobs/{id}/lineage
 */
export function renderTimeline(container, events) {
  if (!events || !Array.isArray(events)) {
    container.innerHTML = '<div class="text-center text-secondary" style="padding:2rem">No lineage data available.</div>';
    return;
  }

  // Inject scoped CSS (only once)
  if (!document.getElementById('timeline-styles')) {
    const style = document.createElement('style');
    style.id = 'timeline-styles';
    style.textContent = getTimelineCSS();
    document.head.appendChild(style);
  }

  let html = '<div class="tl-wrapper">';

  // --- Pipeline visualization ---
  html += '<div class="tl-pipeline">';
  for (let i = 0; i < STAGES.length; i++) {
    const stage = STAGES[i];
    const status = stageStatus(stage.key, events);
    const event = stageEvent(stage.key, events);
    const metricData = event?.data?.metadata || event?.data || event?.metadata || event || {};
    const metricStr = stage.metric(metricData);
    const duration = event?.duration_ms != null ? event.duration_ms
      : (event?.started_at && event?.completed_at)
        ? new Date(event.completed_at) - new Date(event.started_at)
        : null;

    // Connecting line before circle (except first)
    if (i > 0) {
      const prevStatus = stageStatus(STAGES[i - 1].key, events);
      const lineClass = prevStatus === 'completed' ? 'tl-line tl-line-done' : 'tl-line';
      html += '<div class="' + lineClass + '"></div>';
    }

    // Stage node
    html += '<div class="tl-stage" data-stage-key="' + stage.key + '">';
    html += '  <div class="tl-circle tl-circle-' + status + '">';
    if (status === 'completed') {
      // Checkmark SVG
      html += '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3.5 7L6 9.5L10.5 4.5" stroke="#FFFFFF" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    } else if (status === 'active') {
      // Pulsing inner dot
      html += '<div class="tl-pulse-dot"></div>';
    }
    html += '  </div>';
    html += '  <div class="tl-label">' + esc(stage.label) + '</div>';
    if (duration != null) {
      html += '  <div class="tl-timing">' + esc(formatDuration(duration)) + '</div>';
    }
    if (metricStr) {
      html += '  <div class="tl-metric">' + esc(metricStr) + '</div>';
    }
    html += '</div>';
  }
  html += '</div>';

  // --- Expandable detail cards ---
  html += '<div class="tl-details">';
  for (const stage of STAGES) {
    const event = stageEvent(stage.key, events);
    const status = stageStatus(stage.key, events);
    if (!event) continue;

    html += '<div class="tl-detail-card" data-detail-key="' + stage.key + '">';
    html += '  <div class="tl-detail-header">';
    html += '    <div style="display:flex;align-items:center;gap:8px">';
    html += '      <span class="badge ' + statusBadgeClass(status) + '">' + esc(statusLabel(status)) + '</span>';
    html += '      <span style="font-size:13px;font-weight:500">' + esc(stage.label) + '</span>';
    html += '    </div>';
    html += '    <button class="tl-expand-btn" aria-label="Expand details">';
    html += '      <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linecap="round"/></svg>';
    html += '    </button>';
    html += '  </div>';
    html += '  <div class="tl-detail-body hidden">';
    html += renderEventMetadata(event);
    html += '  </div>';
    html += '</div>';
  }
  html += '</div>';

  html += '</div>';

  container.innerHTML = html;

  // --- Interaction: expand/collapse detail cards ---
  container.querySelectorAll('.tl-detail-header').forEach(header => {
    header.style.cursor = 'pointer';
    header.addEventListener('click', () => {
      const body = header.nextElementSibling;
      const btn = header.querySelector('.tl-expand-btn svg');
      body.classList.toggle('hidden');
      if (!body.classList.contains('hidden')) {
        btn.style.transform = 'rotate(180deg)';
      } else {
        btn.style.transform = '';
      }
    });
  });
}

/**
 * Render metadata key/value pairs from an event.
 */
function renderEventMetadata(event) {
  const data = event.data || event.metadata || {};
  const entries = Object.entries(data);
  if (entries.length === 0 && !event.started_at && !event.completed_at) {
    return '<p class="text-secondary" style="font-size:11.5px;padding:4px 0">No detailed metadata available.</p>';
  }

  let html = '<div class="tl-meta-grid">';

  // Timestamps
  if (event.started_at) {
    html += metaRow('Started', formatTimestamp(event.started_at));
  }
  if (event.completed_at) {
    html += metaRow('Completed', formatTimestamp(event.completed_at));
  }
  if (event.duration_ms != null) {
    html += metaRow('Duration', formatDuration(event.duration_ms));
  } else if (event.started_at && event.completed_at) {
    const dur = new Date(event.completed_at) - new Date(event.started_at);
    html += metaRow('Duration', formatDuration(dur));
  }

  // Data fields
  for (const [key, value] of entries) {
    if (value == null) continue;
    const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    let displayVal;
    if (typeof value === 'object') {
      displayVal = '<code style="font-size:10.5px;word-break:break-all">' + esc(JSON.stringify(value)) + '</code>';
    } else {
      displayVal = esc(String(value));
    }
    html += metaRow(label, displayVal);
  }

  html += '</div>';
  return html;
}

function metaRow(label, value) {
  return '<div class="tl-meta-label">' + esc(label) + '</div><div class="tl-meta-value">' + value + '</div>';
}

function formatTimestamp(ts) {
  if (!ts) return '-';
  try {
    const d = new Date(ts);
    return d.toLocaleString() + ' <span class="text-secondary" style="font-size:10px">(' + timeAgo(ts) + ')</span>';
  } catch {
    return esc(String(ts));
  }
}

function statusBadgeClass(status) {
  if (status === 'completed') return 'b-ok';
  if (status === 'active') return 'b-blue';
  return 'b-gray';
}

function statusLabel(status) {
  if (status === 'completed') return 'Complete';
  if (status === 'active') return 'Active';
  return 'Pending';
}

/**
 * Timeline CSS — scoped and injected once.
 * Uses Meridian design tokens: steel (#1D6B9F), warm-page, card surfaces.
 */
function getTimelineCSS() {
  return `
/* --- Timeline Pipeline --- */
.tl-wrapper {
  padding: 0;
}

.tl-pipeline {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 0;
  padding: 24px 16px 20px;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--border-radius-lg);
  margin-bottom: 12px;
  overflow-x: auto;
}

.tl-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
  flex-shrink: 0;
}

.tl-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.tl-circle-completed {
  background: #1D6B9F;
  border: 2px solid #1D6B9F;
}

.tl-circle-active {
  background: transparent;
  border: 2px solid #1D6B9F;
  animation: pulse 1.8s ease-in-out infinite;
}

.tl-circle-pending {
  background: transparent;
  border: 2px solid var(--color-border-tertiary);
}

.tl-pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1D6B9F;
}

.tl-label {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin-top: 8px;
  text-align: center;
  white-space: nowrap;
}

.tl-timing {
  font-size: 10.5px;
  color: var(--color-text-secondary);
  margin-top: 2px;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.tl-metric {
  font-size: 10.5px;
  color: #1A4D7A;
  background: #E3EEF8;
  padding: 1px 7px;
  border-radius: 100px;
  margin-top: 4px;
  white-space: nowrap;
  font-weight: 500;
}

.tl-line {
  height: 2px;
  flex: 1;
  min-width: 32px;
  max-width: 120px;
  background: var(--color-border-tertiary);
  margin-top: 15px;
  align-self: flex-start;
  border-radius: 1px;
}

.tl-line-done {
  background: #1D6B9F;
}

/* --- Detail Cards --- */
.tl-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tl-detail-card {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}

.tl-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
}

.tl-detail-header:hover {
  background: var(--color-background-secondary);
}

.tl-expand-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
}

.tl-expand-btn svg {
  transition: transform 0.2s ease;
}

.tl-detail-body {
  padding: 0 14px 12px;
  border-top: 0.5px solid var(--color-border-tertiary);
}

.tl-detail-body.hidden {
  display: none;
}

/* Metadata grid */
.tl-meta-grid {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 4px 16px;
  padding-top: 8px;
  font-size: 11.5px;
}

.tl-meta-label {
  color: var(--color-text-secondary);
  white-space: nowrap;
  font-size: 11px;
}

.tl-meta-value {
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  word-break: break-word;
}

/* Responsive: stack stages vertically on narrow screens */
@media (max-width: 600px) {
  .tl-pipeline {
    flex-direction: column;
    align-items: center;
  }
  .tl-line {
    width: 2px;
    height: 24px;
    min-width: unset;
    max-width: unset;
    margin-top: 0;
    align-self: center;
  }
}
`;
}

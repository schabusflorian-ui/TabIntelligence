// Badge Components
import { esc } from '../state.js';

/** Confidence badge: high (>=80%), mid (>=50%), low (<50%) */
export function confidenceBadge(conf) {
  if (conf == null) return '<span class="badge">N/A</span>';
  const pct = (conf * 100).toFixed(0);
  const cls = conf >= 0.8 ? 'badge-high' : conf >= 0.5 ? 'badge-mid' : 'badge-low';
  return `<span class="badge ${cls}">${pct}%</span>`;
}

/** Job status badge */
export function statusBadge(status) {
  const labels = {
    pending: 'Pending',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed',
    needs_review: 'Needs Review',
  };
  const label = labels[status] || status;
  return `<span class="badge badge-${status || 'pending'}">${esc(label)}</span>`;
}

/** Quality grade badge */
export function qualityBadge(quality) {
  if (!quality || !quality.letter_grade) return '<span class="badge">N/A</span>';
  const grade = quality.letter_grade;
  const score = quality.numeric_score != null ? (quality.numeric_score * 100).toFixed(0) + '%' : '';
  const cls = (grade === 'A' || grade === 'B') ? 'badge-high' : grade === 'C' ? 'badge-mid' : 'badge-low';
  let warn = '';
  if (quality.quality_gate && !quality.quality_gate.passed) {
    warn = ' \u26A0';
  }
  return `<span class="badge quality-badge ${cls}" title="${esc(quality.label || '')}">${esc(grade)}${score ? ' (' + score + ')' : ''}${warn}</span>`;
}

/** Tier badge for triage */
export function tierBadge(tier) {
  const t = tier || 4;
  return `<span class="badge badge-tier-${t}">Tier ${t}</span>`;
}

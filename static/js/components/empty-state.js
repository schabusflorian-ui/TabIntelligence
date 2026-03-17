// Empty State Component
import { esc } from '../state.js';

/**
 * Render an empty state.
 * @param {Object} opts
 * @param {string} opts.icon - emoji or text
 * @param {string} opts.title
 * @param {string} opts.description
 * @param {string} [opts.actionLabel] - button text
 * @param {string} [opts.actionRoute] - hash route for button
 * @param {Function} [opts.onAction] - click handler for button
 */
export function emptyState(opts) {
  let action = '';
  if (opts.actionLabel) {
    if (opts.actionRoute) {
      action = `<a href="#${opts.actionRoute}" class="btn">${esc(opts.actionLabel)}</a>`;
    } else {
      action = `<button class="btn empty-action">${esc(opts.actionLabel)}</button>`;
    }
  }

  return `<div class="empty-state">
    <div class="empty-icon">${opts.icon || ''}</div>
    <div class="empty-title">${esc(opts.title)}</div>
    <div class="empty-description">${esc(opts.description)}</div>
    ${action}
  </div>`;
}

/** Attach event listener to empty-state action button */
export function bindEmptyAction(container, handler) {
  const btn = container.querySelector('.empty-action');
  if (btn && handler) btn.addEventListener('click', handler);
}

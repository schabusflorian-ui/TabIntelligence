// DebtFund Frontend — ES Module Entry Point
import { addRoute, initRouter } from './router.js';
import { renderSidebar } from './components/sidebar.js';
import { initKeyboard } from './components/keyboard.js';

// --- Register all routes ---

// Dashboard
import * as dashboardModule from './pages/dashboard.js';
addRoute('/', dashboardModule.render, dashboardModule.destroy, dashboardModule);

// Extractions
import * as extractionsModule from './pages/extractions.js';
addRoute('/extractions', extractionsModule.render, extractionsModule.destroy, extractionsModule);

// Job Detail
import * as jobDetailModule from './pages/job-detail.js';
addRoute('/extractions/:jobId', jobDetailModule.render, jobDetailModule.destroy, jobDetailModule);

// Entities
import * as entitiesModule from './pages/entities.js';
addRoute('/entities', entitiesModule.render, entitiesModule.destroy, entitiesModule);

// Entity Detail
import * as entityDetailModule from './pages/entity-detail.js';
addRoute('/entities/:entityId', entityDetailModule.render, entityDetailModule.destroy, entityDetailModule);

// Taxonomy
import * as taxonomyModule from './pages/taxonomy.js';
addRoute('/taxonomy', taxonomyModule.render, taxonomyModule.destroy, taxonomyModule);

// Analytics
import * as analyticsModule from './pages/analytics.js';
addRoute('/analytics', analyticsModule.render, analyticsModule.destroy, analyticsModule);

// Comparison
import * as comparisonModule from './pages/comparison.js';
addRoute('/comparison', comparisonModule.render, comparisonModule.destroy, comparisonModule);

// Benchmarks
import * as benchmarksModule from './pages/benchmarks.js';
addRoute('/benchmarks', benchmarksModule.render, benchmarksModule.destroy, benchmarksModule);

// Admin
import * as adminModule from './pages/admin.js';
addRoute('/admin', adminModule.render, adminModule.destroy, adminModule);

// --- Initialize ---
document.addEventListener('DOMContentLoaded', () => {
  // Render sidebar
  const sidebar = document.getElementById('sidebar');
  renderSidebar(sidebar);

  // Initialize router with content container
  const content = document.getElementById('content');
  initRouter(content);

  // Initialize keyboard shortcuts (lives for entire app session)
  initKeyboard();
});

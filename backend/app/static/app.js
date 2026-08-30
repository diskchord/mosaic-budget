'use strict';

const state = {
  me: null,
  budget: null,
  month: new Date().toISOString().slice(0, 7),
  view: 'budget',
  transactionStatus: 'active',
  transactionSearch: '',
  transactionCategory: null,
  transactions: [],
  selectedListTransactionIds: new Set(),
  listSelectionVersions: new Map(),
  listSelectionAnchorId: null,
  bulkTransactionInFlight: false,
  rules: [],
  users: [],
  incidents: [],
  balanceAlerts: [],
  analytics: null,
  analyticsStart: null,
  analyticsEnd: null,
  analyticsCompareA: null,
  analyticsCompareB: null,
  analyticsLoadSequence: 0,
  operations: null,
  trayOpen: false,
  selectedTransactionIds: new Set(),
  selectionAnchorId: null,
  dragInProgress: false,
  cancelBubbleDrag: null,
  cancelReorderDrag: null,
  assignmentInFlight: false,
  modalOpen: false,
  modalReturnFocus: null,
  modalInertBackgrounds: [],
  formDirty: false,
  transactionEditorLoadSequence: 0,
  budgetLoadSequence: 0,
  eventSource: null,
  eventReloadTimer: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const MAX_BULK_TRANSACTIONS = 200;

const ICONS = {
  budget: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 19V9M10 19V4M16 19v-7M22 19H2"/></svg>',
  transactions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16m0 0-4-4m4 4-4 4M20 17H4m0 0 4 4m-4-4 4-4"/></svg>',
  analytics: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V11M10 19V5M16 19v-6M22 19H2"/><path d="m4 7 5-3 6 4 5-5"/></svg>',
  rules: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M7 12h10M10 18h4"/><circle cx="7" cy="6" r="2" fill="currentColor" stroke="none"/><circle cx="17" cy="12" r="2" fill="currentColor" stroke="none"/><circle cx="10" cy="18" r="2" fill="currentColor" stroke="none"/></svg>',
  more: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>',
  inbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 4h16v14H4zM4 14h5l2 3h2l2-3h5"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  pencil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m4 20 4-1 11-11-3-3L5 16zM14 6l3 3"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13"/></svg>',
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m3 11 9-8 9 8v10h-6v-7H9v7H3z"/></svg>',
  basket: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h16l-2 11H6zM8 9l4-6 4 6"/></svg>',
  car: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m4 16 1-6 2-3h10l2 3 1 6v3h-3v-2H7v2H4zM6 12h12"/><circle cx="8" cy="15" r="1" fill="currentColor"/><circle cx="16" cy="15" r="1" fill="currentColor"/></svg>',
  repeat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 2l3 3-3 3M20 5H8a5 5 0 0 0-5 5M7 22l-3-3 3-3M4 19h12a5 5 0 0 0 5-5"/></svg>',
  person: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="7" r="4"/><path d="M4 22a8 8 0 0 1 16 0"/></svg>',
  vault: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="12" cy="12" r="4"/><path d="M12 8v4l3 2M7 20v2M17 20v2"/></svg>',
  sparkles: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m12 2 1.4 4.6L18 8l-4.6 1.4L12 14l-1.4-4.6L6 8l4.6-1.4zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
  wallet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h16a2 2 0 0 1 2 2v11H3zM3 6l3-3h12v3M16 11h5v5h-5a2 2 0 0 1 0-5z"/></svg>',
  transport: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 17h16M6 17l1-8h10l1 8M9 9V5h6v4"/><circle cx="8" cy="19" r="2"/><circle cx="16" cy="19" r="2"/></svg>',
  subscriptions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16v12H4zM8 4h8M8 11h8M8 15h5"/></svg>',
  personal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M5 22a7 7 0 0 1 14 0"/></svg>',
  savings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 8h16v12H4zM7 8V5h10v3M8 13h8M12 10v6"/></svg>',
  previous: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>',
  next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="m5 12 4 4L19 6"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 2 21h20zM12 9v5M12 18h.01"/></svg>',
};

function hydrateIcons(root = document) {
  $$('[data-icon]', root).forEach(node => {
    const name = node.dataset.icon;
    if (ICONS[name]) node.innerHTML = ICONS[name];
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function transactionLabel(transaction) {
  return transaction.display_payee || transaction.payee || transaction.imported_description || 'Transaction';
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix))?.slice(prefix.length) || '';
}

class ApiError extends Error {
  constructor(message, status, detail) { super(message); this.status = status; this.detail = detail; }
}
class ConflictError extends ApiError {}

async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.body);
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRF-Token', decodeURIComponent(getCookie('mosaic_csrf')));
  const response = await fetch(path, { credentials: 'same-origin', ...options, method, headers });
  let payload = null;
  const type = response.headers.get('content-type') || '';
  if (type.includes('json')) payload = await response.json();
  else payload = await response.text();
  if (response.status === 401 && path !== '/api/auth/login') {
    state.me = null;
    showLogin();
    throw new ApiError('Your session has ended. Sign in again.', 401, payload);
  }
  if (!response.ok) {
    const detail = payload?.detail ?? payload;
    const message = typeof detail === 'string' ? detail : detail?.message || `Request failed (${response.status})`;
    if (response.status === 409) throw new ConflictError(message, 409, detail);
    throw new ApiError(message, response.status, detail);
  }
  return payload;
}

function toUnits(value) {
  const raw = String(value ?? '0').trim();
  const negative = raw.startsWith('-');
  const cleaned = raw.replace(/^[-+]/, '').replaceAll(',', '');
  if (!/^\d*(\.\d*)?$/.test(cleaned)) throw new Error('Invalid amount');
  const [whole = '0', fraction = ''] = cleaned.split('.');
  const padded = (fraction + '0000').slice(0, 4);
  const units = BigInt(whole || '0') * 10000n + BigInt(padded || '0');
  return negative ? -units : units;
}

function unitsToString(units) {
  const negative = units < 0n;
  const abs = negative ? -units : units;
  const whole = abs / 10000n;
  const fraction = String(abs % 10000n).padStart(4, '0').replace(/0+$/, '');
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`;
}

function money(value, { plus = false } = {}) {
  let units;
  try { units = toUnits(value); } catch { units = 0n; }
  const number = Number(units) / 10000;
  const formatted = new Intl.NumberFormat(undefined, { style: 'currency', currency: state.me?.workspace?.currency || 'USD' }).format(number);
  return plus && units > 0n ? `+${formatted}` : formatted;
}

function absMoney(value) {
  let units = toUnits(value);
  if (units < 0n) units = -units;
  return money(unitsToString(units));
}

function monthLabel(month) {
  const [year, number] = month.split('-').map(Number);
  return new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(new Date(year, number - 1, 1));
}

function addMonths(month, delta) {
  const [year, number] = month.split('-').map(Number);
  const value = new Date(year, number - 1 + delta, 1);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}`;
}

function formatDate(value) {
  if (!value) return '';
  const [y, m, d] = value.slice(0, 10).split('-').map(Number);
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: y === new Date().getFullYear() ? undefined : 'numeric' }).format(new Date(y, m - 1, d));
}

function relativeTime(value) {
  if (!value) return 'Never';
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  if (abs < 90) return formatter.format(Math.round(seconds), 'second');
  if (abs < 5400) return formatter.format(Math.round(seconds / 60), 'minute');
  if (abs < 129600) return formatter.format(Math.round(seconds / 3600), 'hour');
  return formatter.format(Math.round(seconds / 86400), 'day');
}

function initials(name) {
  return String(name || '?').split(/\s+/).slice(0, 2).map(part => part[0] || '').join('').toUpperCase();
}

function toast(message, type = 'default', action = null) {
  const node = document.createElement('div');
  node.className = `toast ${type === 'error' ? 'error' : ''}`;
  node.innerHTML = `<span>${escapeHtml(message)}</span>${action ? `<button type="button">${escapeHtml(action.label)}</button>` : ''}`;
  $('#toast-root').append(node);
  let removalTimer = setTimeout(() => node.remove(), action ? 7000 : 4200);
  if (action) $('button', node).addEventListener('click', async event => {
    const button = event.currentTarget;
    if (button.disabled) return;
    button.disabled = true;
    clearTimeout(removalTimer);
    let completed = false;
    try { completed = await action.run() !== false; }
    catch { completed = false; }
    if (completed) node.remove();
    else {
      button.disabled = false;
      removalTimer = setTimeout(() => node.remove(), 7000);
    }
  });
}

function setButtonBusy(button, busy, label = 'Working…') {
  if (!button) return;
  if (busy) { button.dataset.original = button.textContent; button.disabled = true; button.textContent = label; }
  else { button.disabled = false; button.textContent = button.dataset.original || button.textContent; }
}

function openModal({ title, body, footer = '', className = '', returnFocus = null, onMount = null }) {
  state.transactionEditorLoadSequence += 1;
  const focusTarget = returnFocus || document.activeElement;
  if (!state.modalOpen || returnFocus) {
    state.modalReturnFocus = typeof focusTarget === 'function' || focusTarget instanceof HTMLElement ? focusTarget : null;
  }
  if (!state.modalOpen) {
    state.modalInertBackgrounds = [$('#app-shell'), $('#transaction-tray')]
      .filter(element => !element.hasAttribute('inert'));
    state.modalInertBackgrounds.forEach(element => element.setAttribute('inert', ''));
  }
  state.modalOpen = true;
  state.formDirty = false;
  const root = $('#modal-root');
  root.innerHTML = `
    <div class="modal-backdrop" role="presentation">
      <section class="modal ${className}" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <header class="modal-header"><h2 id="modal-title">${escapeHtml(title)}</h2><button class="icon-button modal-close" type="button" aria-label="Close">×</button></header>
        <div class="modal-body">${body}</div>
        ${footer ? `<footer class="modal-footer">${footer}</footer>` : ''}
      </section>
    </div>`;
  const backdrop = $('.modal-backdrop', root);
  $('.modal-close', root).addEventListener('click', () => closeModal());
  backdrop.addEventListener('click', event => { if (event.target === backdrop && !state.formDirty) closeModal(); });
  const markFormDirty = event => {
    if (event.target.matches('input, select, textarea') && event.target.closest('form')) state.formDirty = true;
  };
  root.addEventListener('input', markFormDirty);
  root.addEventListener('change', markFormDirty);
  document.addEventListener('keydown', modalEscape, { once: true });
  hydrateIcons(root);
  if (onMount) onMount(root);
  const modalBody = $('.modal-body', root);
  setTimeout(() => {
    if (modalBody?.isConnected) $('input, select, textarea, button', modalBody)?.focus();
  }, 20);
  return root;
}

function modalEscape(event) {
  if (event.key === 'Escape' && state.modalOpen && !state.formDirty) closeModal();
  else if (state.modalOpen) document.addEventListener('keydown', modalEscape, { once: true });
}

function closeModal() {
  const returnFocus = state.modalReturnFocus;
  const inertBackgrounds = state.modalInertBackgrounds;
  $('#modal-root').innerHTML = '';
  state.modalOpen = false;
  state.modalReturnFocus = null;
  state.modalInertBackgrounds = [];
  state.formDirty = false;
  inertBackgrounds.forEach(element => {
    if (element.id !== 'transaction-tray' || state.trayOpen) element.removeAttribute('inert');
  });
  setTimeout(() => {
    const focusTarget = typeof returnFocus === 'function' ? returnFocus() : returnFocus;
    if (!state.modalOpen && focusTarget?.isConnected && !focusTarget.closest('[inert]')) {
      focusTarget.focus({ preventScroll: true });
    }
  }, 0);
}

function confirmDialog({ title, message, confirmText = 'Confirm', danger = false, inputLabel = '', expected = '' }) {
  return new Promise(resolve => {
    openModal({
      title,
      body: `${danger ? `<div class="delete-warning">${message}</div>` : `<p>${message}</p>`}
        ${inputLabel ? `<label style="margin-top:14px">${escapeHtml(inputLabel)}<input id="confirm-input" autocomplete="off"></label>` : ''}`,
      footer: `<button class="button cancel-confirm" type="button">Cancel</button><button class="button ${danger ? 'button--danger' : 'button--primary'} accept-confirm" type="button">${escapeHtml(confirmText)}</button>`,
      onMount(root) {
        $('.cancel-confirm', root).addEventListener('click', () => { closeModal(); resolve(false); });
        $('.accept-confirm', root).addEventListener('click', () => {
          if (inputLabel && $('#confirm-input', root).value.trim() !== expected) {
            toast('The confirmation text does not match.', 'error'); return;
          }
          closeModal(); resolve(true);
        });
      },
    });
  });
}

async function withConflict(requestFactory, localBody, description = 'item') {
  try { return await requestFactory(localBody); }
  catch (error) {
    if (!(error instanceof ConflictError)) throw error;
    const current = error.detail?.current || error.detail?.target || null;
    const applyMine = await new Promise(resolve => {
      openModal({
        title: 'Changed on another device',
        body: `<p>${escapeHtml(error.message)}</p><p class="muted">Keep the current server version, or deliberately apply the values you just entered over it.</p>`,
        footer: '<button class="button keep-current" type="button">Keep current</button><button class="button button--primary apply-mine" type="button">Apply mine</button>',
        onMount(root) {
          $('.keep-current', root).addEventListener('click', () => { closeModal(); resolve(false); });
          $('.apply-mine', root).addEventListener('click', () => { closeModal(); resolve(true); });
        },
      });
    });
    if (!applyMine) { await refreshCurrentView(); return null; }
    if (current?.version !== undefined) localBody.version = current.version;
    else if (error.detail?.current?.budget_version !== undefined) localBody.version = error.detail.current.budget_version;
    try { return await requestFactory(localBody); }
    catch (retryError) { toast(`Could not apply your ${description}: ${retryError.message}`, 'error'); throw retryError; }
  }
}

function showLogin() {
  state.eventSource?.close();
  state.eventSource = null;
  $('#boot-screen').classList.add('hidden');
  $('#app-shell').classList.add('hidden');
  $('#login-view').classList.remove('hidden');
  setTimeout(() => $('#login-email')?.focus(), 20);
}

function showApp() {
  $('#boot-screen').classList.add('hidden');
  $('#login-view').classList.add('hidden');
  $('#app-shell').classList.remove('hidden');
  document.body.dataset.theme = state.me.user.theme || 'citrus';
  $('#avatar-button').textContent = initials(state.me.user.display_name);
  $('#month-label').textContent = monthLabel(state.month);
  hydrateIcons();
}

function syncPill() {
  const pill = $('#sync-status');
  const label = $('.sync-label', pill);
  const connections = state.budget?.connections || [];
  pill.classList.remove('ok', 'error');
  if (!connections.length) { label.textContent = 'No bank'; return; }
  const failed = connections.find(item => item.consecutive_failures > 0 || item.last_error_code);
  if (failed) { pill.classList.add('error'); label.textContent = 'Sync issue'; return; }
  const latest = connections.map(item => item.last_success_at).filter(Boolean).sort().at(-1);
  pill.classList.add('ok');
  label.textContent = latest ? `Synced ${relativeTime(latest)}` : 'Starting sync';
}

function updateNavigation() {
  $$('.nav-item').forEach(item => {
    const active = item.dataset.view === state.view;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  $('#month-control').classList.toggle('hidden', !['budget', 'transactions', 'rules'].includes(state.view));
  const unsortedCount = trayTransactions().length;
  $('#inbox-button').classList.toggle('hidden', !unsortedCount || state.view !== 'budget');
  $('#inbox-count').textContent = state.budget?.unassigned_has_more ? `${unsortedCount}+` : unsortedCount;
}

async function setView(view) {
  state.cancelReorderDrag?.();
  if (state.trayOpen) closeTray({ restoreFocus: false });
  if (view !== 'transactions') clearTransactionListSelection();
  state.view = view;
  if (view !== 'transactions') state.transactionCategory = null;
  updateNavigation();
  await renderCurrentView();
  if (state.view === view) $('#app-view').focus({ preventScroll: true });
}

function loadingView() {
  $('#app-view').innerHTML = '<div class="skeleton"></div><div class="skeleton" style="margin-top:14px"></div><div class="skeleton" style="margin-top:14px"></div>';
}

async function loadBudget({ silent = false } = {}) {
  const sequence = ++state.budgetLoadSequence;
  const requestedMonth = state.month;
  if (!silent) loadingView();
  const budget = await api(`/api/budget?month=${encodeURIComponent(requestedMonth)}`);
  if (sequence !== state.budgetLoadSequence || requestedMonth !== state.month) return false;
  state.budget = budget;
  $('#month-label').textContent = monthLabel(state.month);
  syncPill();
  updateNavigation();
  renderTray();
  return true;
}

async function refreshCurrentView() {
  try {
    if (!await loadBudget({ silent: true })) return false;
    return await renderCurrentView({ skipBudgetLoad: true });
  } catch (error) {
    if (error.status !== 401) toast(error.message, 'error');
    return false;
  }
}

async function renderCurrentView({ skipBudgetLoad = false } = {}) {
  const requestedView = state.view;
  try {
    if (!state.budget && !skipBudgetLoad && !await loadBudget()) return false;
    if (state.view === 'budget') renderBudget();
    else if (state.view === 'transactions') await renderTransactions();
    else if (state.view === 'analytics') await renderAnalytics();
    else if (state.view === 'rules') await renderRules();
    else await renderMore();
    updateNavigation();
    hydrateIcons($('#app-view'));
    return true;
  } catch (error) {
    if (error.status !== 401 && state.view === requestedView) {
      $('#app-view').innerHTML = `<div class="empty-state"><strong>Unable to load this screen</strong>${escapeHtml(error.message)}</div>`;
      toast(error.message, 'error');
    }
    return false;
  }
}

function categoryCatalog() {
  if (state.budget?.category_catalog?.length) return state.budget.category_catalog;
  return (state.budget?.sections || []).flatMap(section => section.categories.map(category => ({
    ...category,
    section_id: section.id,
    section_name: section.name,
    section_is_income: section.is_income,
    visible_this_month: true,
    archived: false,
  })));
}

function categoryOptions(selected = '', includeUnavailable = false) {
  let markup = '';
  if (includeUnavailable) {
    const groups = new Map();
    categoryCatalog().filter(category => !category.archived).forEach(category => {
      if (!groups.has(category.section_id)) groups.set(category.section_id, { name: category.section_name, categories: [] });
      groups.get(category.section_id).categories.push(category);
    });
    markup = [...groups.values()].map(group => {
      const options = group.categories.map(category => {
        const availability = category.visible_this_month ? '' : ' — unavailable this month';
        return `<option value="${category.id}" ${category.id === selected ? 'selected' : ''}>${escapeHtml(category.name + availability)}</option>`;
      }).join('');
      return `<optgroup label="${escapeHtml(group.name)}">${options}</optgroup>`;
    }).join('');
  } else {
    markup = (state.budget?.sections || []).map(section => {
      const options = section.categories.map(category => `<option value="${category.id}" ${category.id === selected ? 'selected' : ''}>${escapeHtml(category.name)}</option>`).join('');
      return options ? `<optgroup label="${escapeHtml(section.name)}">${options}</optgroup>` : '';
    }).join('');
  }
  const selectedItem = selected ? categoryCatalog().find(category => category.id === selected) : null;
  const selectedIsVisible = selectedItem?.visible_this_month && !selectedItem?.archived;
  if (selectedItem && !includeUnavailable && !selectedIsVisible) {
    markup += `<optgroup label="Current historical assignment"><option value="${selectedItem.id}" selected>${escapeHtml(selectedItem.name)} — not available this month</option></optgroup>`;
  }
  return markup;
}

function categoryById(id) {
  for (const section of state.budget?.sections || []) {
    const found = section.categories.find(category => category.id === id);
    if (found) return { ...found, section };
  }
  return null;
}

function catalogCategoryById(id) {
  const category = categoryCatalog().find(item => item.id === id);
  if (!category) return null;
  const section = state.budget?.sections?.find(item => item.id === category.section_id) || {
    id: category.section_id,
    name: category.section_name,
    is_income: category.section_is_income,
  };
  return { ...category, section };
}

function accountCatalog() { return state.budget?.account_catalog || state.budget?.accounts || []; }
function accountById(id) { return accountCatalog().find(account => account.id === id) || null; }
function transactionById(id) {
  return state.budget?.unassigned?.find(item => item.id === id) || state.transactions.find(item => item.id === id) || null;
}

function renderBudget() {
  const reorderFocus = currentReorderFocus();
  const data = state.budget;
  const summary = data.summary;
  const leftUnits = toUnits(summary.left_to_assign);
  const hiddenCount = data.hidden_structure?.count || 0;
  const hiddenActivity = toUnits(summary.hidden_activity || '0');
  const collapsedSections = new Set(state.me.user.preferences?.collapsed_sections || []);
  const sections = data.sections.map(section => {
    const collapsed = collapsedSections.has(section.id);
    const categories = section.categories.map(category => {
      const planned = toUnits(category.planned);
      const activity = toUnits(category.activity);
      const remaining = toUnits(category.remaining);
      const used = section.is_income ? activity : -activity;
      const progressAmount = section.is_income ? category.activity : category.remaining;
      const ratio = planned > 0n ? Math.max(0, Math.min(1.25, Number(used * 10000n / planned) / 10000)) : (used > 0n ? 1.25 : 0);
      const over = !section.is_income && remaining < 0n;
      return `<article class="category-row" data-category-id="${category.id}" data-section-id="${section.id}" data-sort-order="${category.sort_order}" data-version="${category.version}">
        <button class="reorder-handle category-reorder-handle" type="button" aria-label="Reorder ${escapeHtml(category.name)}" aria-describedby="budget-reorder-help" title="Drag to reorder"><span aria-hidden="true">⠿</span></button>
        <div class="category-main" role="button" tabindex="0" aria-label="View ${escapeHtml(category.name)} transactions">
          <div class="category-name"><span>${escapeHtml(category.name)}</span>${category.rollover ? '<span class="fund-badge">Fund</span>' : ''}</div>
          <div class="category-sub">${section.is_income ? `${money(category.activity)} received` : `${money(unitsToString(used))} used`}</div>
        </div>
        <button class="category-money budget-edit ${over ? 'over' : ''}" type="button" data-category-id="${category.id}" aria-label="Edit ${escapeHtml(category.name)} planned amount">
          <b>${money(progressAmount)}</b><span>of ${money(category.planned)}</span>
        </button>
        <button class="icon-button edit-category" data-category-id="${category.id}" type="button" aria-label="Edit ${escapeHtml(category.name)} category"><span data-icon="pencil"></span></button>
        <div class="progress-track" aria-hidden="true"><div class="progress-bar ${over ? 'over' : ''}" style="width:${Math.min(100, ratio * 100)}%"></div></div>
      </article>`;
    }).join('');
    return `<section class="section-card ${section.is_income ? 'income' : ''} ${collapsed ? 'collapsed' : ''}" data-section-id="${section.id}" data-sort-order="${section.sort_order}" data-version="${section.version}">
      <header class="section-header">
        <span class="section-icon" data-icon="${escapeHtml(section.icon || 'wallet')}"></span>
        <button class="section-title collapse-section" data-section-id="${section.id}" type="button" aria-expanded="${collapsed ? 'false' : 'true'}" aria-label="${collapsed ? 'Expand' : 'Collapse'} ${escapeHtml(section.name)}"><h2>${escapeHtml(section.name)}</h2><small>${section.categories.length} categor${section.categories.length === 1 ? 'y' : 'ies'}</small></button>
        <div class="section-actions">${section.is_income ? '' : `<button class="reorder-handle section-reorder-handle" type="button" aria-label="Reorder ${escapeHtml(section.name)} section" aria-describedby="budget-reorder-help" title="Drag to reorder"><span aria-hidden="true">⠿</span></button>`}<button class="icon-button collapse-section collapse-chevron" data-section-id="${section.id}" type="button" aria-expanded="${collapsed ? 'false' : 'true'}" aria-label="${collapsed ? 'Expand' : 'Collapse'} ${escapeHtml(section.name)}">⌄</button><button class="icon-button edit-section" data-section-id="${section.id}" type="button" aria-label="Edit ${escapeHtml(section.name)}"><span data-icon="pencil"></span></button></div>
      </header>
      <div class="category-list">${categories || '<div class="empty-state" style="border:0;border-radius:0">No categories yet.</div>'}</div>
      <button class="add-category" data-section-id="${section.id}" type="button">+ Add category</button>
    </section>`;
  }).join('');

  $('#app-view').innerHTML = `
    <p id="budget-reorder-help" class="sr-only">Drag this handle to change the order. With a keyboard, use the Up and Down arrow keys or the item editor's Position field.</p>
    <div id="reorder-status" class="sr-only" aria-live="polite" aria-atomic="true"></div>
    <header class="view-header"><div><h1>${monthLabel(state.month)}</h1><p>Give every planned dollar a job.</p></div><div class="view-actions"><button class="button button--primary add-manual" type="button">+ Cash transaction</button></div></header>
    <section class="summary-card">
      <div class="summary-top"><div><small>LEFT TO ASSIGN</small><div class="summary-balance ${leftUnits < 0n ? 'negative' : ''}">${money(summary.left_to_assign)}</div><div class="summary-state">${leftUnits === 0n ? 'Every planned dollar has a home.' : leftUnits > 0n ? 'Still available to plan.' : 'Planned spending is over income.'}</div></div></div>
      <div class="summary-grid">
        <div class="summary-metric"><b>${money(summary.planned_income)}</b><span>Planned income</span></div>
        <div class="summary-metric"><b>${money(summary.planned_expenses)}</b><span>Assigned</span></div>
        <div class="summary-metric"><b>${money(summary.actual_cash_flow)}</b><span>Cash flow</span></div>
      </div>
    </section>
    ${hiddenCount ? `<button class="structure-notice manage-hidden-structure" type="button"><span><strong>${hiddenCount} hidden item${hiddenCount === 1 ? '' : 's'} in ${escapeHtml(monthLabel(state.month))}</strong><small>${hiddenActivity !== 0n ? `${money(unitsToString(hiddenActivity))} of activity remains included in totals.` : 'Show, resume, or restore month-specific categories and sections.'}</small></span><span>Manage →</span></button>` : ''}
    ${sections}
    <div class="structure-actions"><button class="add-section-card" type="button">+ Add budget section</button>${hiddenCount ? '<button class="button button--soft manage-hidden-structure" type="button">Manage hidden items</button>' : ''}</div>`;

  hydrateIcons($('#app-view'));
  $$('.budget-edit', $('#app-view')).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); openBudgetAmount(button.dataset.categoryId); }));
  $$('.category-main', $('#app-view')).forEach(node => {
    const open = () => { state.transactionCategory = node.closest('.category-row').dataset.categoryId; state.transactionStatus = 'active'; setView('transactions'); };
    node.addEventListener('click', open);
    node.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') open(); });
  });
  $$('.add-category', $('#app-view')).forEach(button => button.addEventListener('click', () => openCategoryEditor(null, button.dataset.sectionId)));
  $$('.edit-category', $('#app-view')).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); openCategoryEditor(button.dataset.categoryId); }));
  $$('.collapse-section', $('#app-view')).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); toggleSectionCollapse(button.dataset.sectionId); }));
  $$('.edit-section', $('#app-view')).forEach(button => button.addEventListener('click', () => openSectionEditor(button.dataset.sectionId)));
  $('.add-section-card', $('#app-view')).addEventListener('click', () => openSectionEditor());
  $$('.manage-hidden-structure', $('#app-view')).forEach(button => button.addEventListener('click', openHiddenStructureManager));
  $('.add-manual', $('#app-view')).addEventListener('click', openManualTransaction);
  installBubbleDrag();
  restoreReorderFocus(reorderFocus);
}

function announceReorder(message) {
  const status = $('#reorder-status');
  if (!status) return;
  status.textContent = '';
  requestAnimationFrame(() => { if (status.isConnected) status.textContent = message; });
}

function reorderElementsAt(x, y) {
  if (document.elementsFromPoint) return document.elementsFromPoint(x, y);
  const element = document.elementFromPoint?.(x, y);
  return element ? [element] : [];
}

function reorderMatchAt(x, y, selector, root = $('#app-view')) {
  const element = document.elementFromPoint?.(x, y) || reorderElementsAt(x, y)[0];
  const match = element?.closest?.(selector);
  return match && root?.contains(match) ? match : null;
}

function reorderItemId(element) {
  return element?.dataset.categoryId || element?.dataset.ruleId || element?.dataset.sectionId || '';
}

function reorderConfig(handle) {
  if (handle.matches('.section-reorder-handle')) {
    return { kind: 'section', itemSelector: '.section-card[data-section-id]:not(.income)' };
  }
  if (handle.matches('.category-reorder-handle')) {
    return { kind: 'category', itemSelector: '.category-row[data-category-id]' };
  }
  if (handle.matches('.rule-reorder-handle')) {
    return { kind: 'rule', itemSelector: '.rule-card[data-rule-id]' };
  }
  return null;
}

function reorderItemName(kind, item) {
  if (kind === 'section') return state.budget?.sections.find(section => section.id === item.dataset.sectionId)?.name || 'section';
  if (kind === 'category') return categoryById(item.dataset.categoryId)?.name || 'category';
  return state.rules.find(rule => rule.id === item.dataset.ruleId)?.name || 'rule';
}

function buildReorderDrop(kind, container, anchor, before, highlight = null) {
  const anchorId = reorderItemId(anchor);
  const targetId = highlight?.dataset.sectionId || highlight?.dataset.rulePhase || '';
  return {
    kind,
    container,
    anchor,
    anchorId,
    before,
    highlight,
    key: `${kind}:${targetId}:${anchorId}:${before ? 'before' : 'after'}`,
  };
}

function verticalReorderDrop(kind, container, source, y, { highlight = null } = {}) {
  const selector = kind === 'section' ? '.section-card[data-section-id]:not(.income)'
    : kind === 'category' ? '.category-row[data-category-id]'
      : '.rule-card[data-rule-id]';
  const items = $$(selector, container).filter(item => item !== source && item.getBoundingClientRect().height > 0);
  if (!items.length) return buildReorderDrop(kind, container, null, true, highlight);
  const anchor = items.find(item => {
    const rect = item.getBoundingClientRect();
    return y < rect.top + rect.height / 2;
  });
  if (anchor) return buildReorderDrop(kind, container, anchor, true, highlight);
  return buildReorderDrop(kind, container, items.at(-1), false, highlight);
}

function endOfCategorySectionDrop(sectionCard, source) {
  const list = $('.category-list', sectionCard);
  const items = $$('.category-row[data-category-id]', list).filter(item => item !== source);
  return buildReorderDrop('category', list, items.at(-1) || null, false, sectionCard);
}

function resolveReorderDrop(config, source, x, y) {
  const root = $('#app-view');
  if (!root) return null;
  const topmost = document.elementFromPoint?.(x, y) || reorderElementsAt(x, y)[0];
  if (!topmost || !root.contains(topmost)) return null;
  if (config.kind === 'section') {
    const rect = root.getBoundingClientRect();
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
    return verticalReorderDrop('section', root, source, y);
  }
  if (config.kind === 'category') {
    const sectionCard = reorderMatchAt(x, y, '.section-card[data-section-id]', root);
    if (!sectionCard) return null;
    const overHeader = reorderMatchAt(x, y, '.section-header', sectionCard);
    if (overHeader || sectionCard.classList.contains('collapsed')) return endOfCategorySectionDrop(sectionCard, source);
    return verticalReorderDrop('category', $('.category-list', sectionCard), source, y, { highlight: sectionCard });
  }
  const sourcePhase = source.closest('.rule-phase');
  const targetPhase = reorderMatchAt(x, y, '.rule-phase[data-rule-phase]', root);
  if (!sourcePhase || targetPhase !== sourcePhase) return null;
  return verticalReorderDrop('rule', $('.rule-list', sourcePhase), source, y, { highlight: sourcePhase });
}

function describeReorderDrop(drop) {
  if (!drop) return 'No drop position';
  if (drop.anchor) {
    const name = reorderItemName(drop.kind, drop.anchor);
    if (drop.kind === 'category') {
      const sectionName = state.budget?.sections.find(section => section.id === drop.highlight?.dataset.sectionId)?.name || 'section';
      return `${drop.before ? 'before' : 'after'} ${name} in ${sectionName}`;
    }
    return `${drop.before ? 'before' : 'after'} ${name}`;
  }
  if (drop.kind === 'category') {
    const sectionName = state.budget?.sections.find(section => section.id === drop.highlight?.dataset.sectionId)?.name || 'section';
    return drop.before ? `as the first category in ${sectionName}` : `at the end of ${sectionName}`;
  }
  return 'in the current position';
}

function visibleOrderAfterDrop(ids, sourceId, anchorId, before) {
  const ordered = ids.filter(id => id !== sourceId);
  const anchorIndex = anchorId ? ordered.indexOf(anchorId) : -1;
  const targetIndex = anchorIndex < 0 ? 0 : anchorIndex + (before ? 0 : 1);
  ordered.splice(targetIndex, 0, sourceId);
  return ordered;
}

function sameIdOrder(first, second) {
  return first.length === second.length && first.every((id, index) => id === second[index]);
}

function anchoredTargetIndex(sourceOrder, anchorOrder, before, offset = 0) {
  const sourceIndex = sourceOrder - offset;
  const anchorIndex = anchorOrder - offset;
  return Math.max(0, before
    ? anchorIndex - (sourceIndex < anchorIndex ? 1 : 0)
    : anchorIndex + 1 - (sourceIndex < anchorIndex ? 1 : 0));
}

function reorderFocusSelector(kind, id) {
  if (kind === 'section') return `.section-card[data-section-id="${CSS.escape(id)}"] .section-reorder-handle`;
  if (kind === 'category') return `.category-row[data-category-id="${CSS.escape(id)}"] .category-reorder-handle`;
  return `.rule-card[data-rule-id="${CSS.escape(id)}"] .rule-reorder-handle`;
}

function currentReorderFocus() {
  const handle = document.activeElement?.closest?.('.reorder-handle');
  const config = handle ? reorderConfig(handle) : null;
  const item = config ? handle.closest(config.itemSelector) : null;
  return config && item ? { kind: config.kind, id: reorderItemId(item) } : null;
}

function restoreReorderFocus(focus) {
  if (!focus) return;
  $(reorderFocusSelector(focus.kind, focus.id))?.focus({ preventScroll: true });
}

async function persistSectionReorder(source, drop) {
  const section = state.budget.sections.find(item => item.id === source.dataset.sectionId);
  const anchor = drop.anchor ? state.budget.sections.find(item => item.id === drop.anchor.dataset.sectionId) : null;
  if (!section || !anchor) return 'noop';
  const visibleIds = state.budget.sections.filter(item => !item.is_income).map(item => item.id);
  const desiredIds = visibleOrderAfterDrop(visibleIds, section.id, anchor.id, drop.before);
  if (sameIdOrder(visibleIds, desiredIds)) return 'noop';
  const sortOrder = anchoredTargetIndex(section.sort_order, anchor.sort_order, drop.before, 1);
  let saved = false;
  try {
    await api(`/api/sections/${section.id}`, { method: 'PATCH', body: { version: section.version, sort_order: sortOrder } });
    saved = true;
    toast(`${section.name} section reordered`);
  } catch (error) {
    toast(error instanceof ConflictError ? 'The section order changed elsewhere. The latest order was restored.' : `Could not reorder ${section.name}: ${error.message}`, 'error');
  }
  await refreshCurrentView();
  $(reorderFocusSelector('section', section.id))?.focus({ preventScroll: true });
  return saved ? 'saved' : 'failed';
}

async function persistCategoryReorder(source, drop) {
  const found = categoryById(source.dataset.categoryId);
  const targetSection = state.budget.sections.find(section => section.id === drop.highlight?.dataset.sectionId);
  const anchor = drop.anchor ? categoryById(drop.anchor.dataset.categoryId) : null;
  if (!found || !targetSection) return 'noop';
  if (found.section.id === targetSection.id) {
    const visibleIds = found.section.categories.map(category => category.id);
    const desiredIds = visibleOrderAfterDrop(visibleIds, found.id, anchor?.id || null, drop.before);
    if (sameIdOrder(visibleIds, desiredIds)) return 'noop';
  }
  let sortOrder = drop.before ? 0 : 2147483647;
  if (anchor) {
    sortOrder = found.section.id === targetSection.id
      ? anchoredTargetIndex(found.sort_order, anchor.sort_order, drop.before)
      : Math.max(0, anchor.sort_order + (drop.before ? 0 : 1));
  }
  let saved = false;
  try {
    await api(`/api/categories/${found.id}?current_month=${encodeURIComponent(state.month)}`, {
      method: 'PATCH',
      body: { version: found.version, section_id: targetSection.id, sort_order: sortOrder },
    });
    saved = true;
    toast(`${found.name} moved ${targetSection.id === found.section.id ? 'within' : `to`} ${targetSection.name}`);
  } catch (error) {
    toast(error instanceof ConflictError ? 'The category order changed elsewhere. The latest order was restored.' : `Could not move ${found.name}: ${error.message}`, 'error');
  }
  await refreshCurrentView();
  $(reorderFocusSelector('category', found.id))?.focus({ preventScroll: true });
  return saved ? 'saved' : 'failed';
}

async function persistRuleReorder(source, drop) {
  const rule = state.rules.find(item => item.id === source.dataset.ruleId);
  if (!rule || !drop.anchor) return 'noop';
  const lane = state.rules.filter(item => item.phase === rule.phase);
  const currentIds = lane.map(item => item.id);
  const desiredIds = visibleOrderAfterDrop(currentIds, rule.id, drop.anchor.dataset.ruleId, drop.before);
  if (sameIdOrder(currentIds, desiredIds)) return 'noop';
  const byId = new Map(lane.map(item => [item.id, item]));
  let saved = false;
  try {
    await api('/api/rules/order', {
      method: 'PUT',
      body: {
        phase: rule.phase,
        rules: desiredIds.map(id => ({ id, version: byId.get(id).version })),
      },
    });
    saved = true;
    toast(`${rule.name} reordered`);
  } catch (error) {
    toast(error instanceof ConflictError ? error.message : `Could not reorder ${rule.name}: ${error.message}`, 'error');
  }
  await refreshCurrentView();
  $(reorderFocusSelector('rule', rule.id))?.focus({ preventScroll: true });
  return saved ? 'saved' : 'failed';
}

function persistReorder(config, source, drop) {
  if (config.kind === 'section') return persistSectionReorder(source, drop);
  if (config.kind === 'category') return persistCategoryReorder(source, drop);
  return persistRuleReorder(source, drop);
}

function keyboardReorderDrop(config, source, direction) {
  let container = source.parentElement;
  let highlight = null;
  if (config.kind === 'category') {
    container = source.closest('.category-list');
    highlight = source.closest('.section-card');
  } else if (config.kind === 'rule') {
    container = source.closest('.rule-list');
    highlight = source.closest('.rule-phase');
  }
  const items = $$(config.itemSelector, container);
  const index = items.indexOf(source);
  const target = items[index + direction];
  if (!target) return null;
  return buildReorderDrop(config.kind, container, target, direction < 0, highlight);
}

function installReorderDrag() {
  const root = $('#app-view');
  if (!root || root.dataset.reorderInstalled === 'true') return;
  root.dataset.reorderInstalled = 'true';
  let drag = null;

  const clearDrop = () => {
    drag?.indicator?.remove();
    $$('.reorder-drop-active', root).forEach(element => element.classList.remove('reorder-drop-active'));
  };

  const clean = () => {
    const current = drag;
    drag = null;
    if (!current) return;
    cancelAnimationFrame(current.scrollFrame);
    current.ghost?.remove();
    current.indicator.remove();
    current.source.classList.remove('is-reordering');
    $$('.reorder-drop-active', root).forEach(element => element.classList.remove('reorder-drop-active'));
    document.body.classList.remove('reordering');
    state.dragInProgress = false;
    if (state.cancelReorderDrag === clean) state.cancelReorderDrag = null;
    if (current.handle.hasPointerCapture?.(current.pointerId)) {
      try { current.handle.releasePointerCapture(current.pointerId); } catch { /* pointer capture may already be gone */ }
    }
  };

  const moveGhost = (x, y) => {
    if (!drag?.ghost) return;
    const rect = drag.ghost.getBoundingClientRect();
    const left = Math.max(8, Math.min(x + 15, window.innerWidth - rect.width - 8));
    const top = Math.max(8, Math.min(y + 15, window.innerHeight - rect.height - 8));
    drag.ghost.style.transform = `translate3d(${left}px,${top}px,0)`;
  };

  const showDrop = drop => {
    if (!drag) return;
    clearDrop();
    drag.drop = drop;
    if (!drop) return;
    drop.highlight?.classList.add('reorder-drop-active');
    drag.indicator.className = `reorder-indicator reorder-indicator--${drag.config.kind}`;
    if (drop.anchor?.parentElement === drop.container) {
      drop.anchor[drop.before ? 'before' : 'after'](drag.indicator);
    } else {
      drop.container.append(drag.indicator);
    }
    if (drag.lastDropKey !== drop.key) {
      drag.lastDropKey = drop.key;
      announceReorder(`${drag.label}: ${describeReorderDrop(drop)}`);
    }
  };

  const updateDrop = (x, y) => {
    if (!drag?.active) return;
    showDrop(resolveReorderDrop(drag.config, drag.source, x, y));
  };

  const runAutoScroll = () => {
    if (!drag?.active || !drag.scrollDirection) {
      if (drag) drag.scrollFrame = null;
      return;
    }
    window.scrollBy({ top: drag.scrollDirection, behavior: 'auto' });
    updateDrop(drag.lastX, drag.lastY);
    drag.scrollFrame = requestAnimationFrame(runAutoScroll);
  };

  const updateAutoScroll = (x, y) => {
    if (!drag?.active) return;
    drag.lastX = x;
    drag.lastY = y;
    const edge = 72;
    drag.scrollDirection = y < edge ? -14 : y > window.innerHeight - edge ? 14 : 0;
    if (drag.scrollDirection && drag.scrollFrame === null) drag.scrollFrame = requestAnimationFrame(runAutoScroll);
  };

  const activate = (x, y) => {
    if (!drag || drag.active) return;
    drag.active = true;
    drag.source.classList.add('is-reordering');
    drag.ghost = document.createElement('div');
    drag.ghost.className = 'reorder-ghost';
    drag.ghost.setAttribute('aria-hidden', 'true');
    drag.ghost.innerHTML = `<span>⠿</span><strong>${escapeHtml(drag.label)}</strong>`;
    document.body.append(drag.ghost);
    document.body.classList.add('reordering');
    state.dragInProgress = true;
    moveGhost(x, y);
    updateDrop(x, y);
    if (drag.pointerType === 'touch' && navigator.vibrate) navigator.vibrate(16);
  };

  const finish = async (x, y) => {
    if (!drag) return;
    if (drag.active) updateDrop(x, y);
    const { active, config, source, drop, label } = drag;
    clean();
    if (!active || !drop) {
      if (active) announceReorder(`${label} was not moved.`);
      return;
    }
    state.dragInProgress = true;
    try {
      const result = await persistReorder(config, source, drop);
      if (result === 'saved') announceReorder(`${label} reordered.`);
      else if (result === 'failed') announceReorder(`${label} could not be reordered. The latest order is shown.`);
      else announceReorder(`${label} stayed in the same position.`);
    } finally {
      state.dragInProgress = false;
    }
  };

  root.addEventListener('pointerdown', event => {
    const handle = event.target.closest('.reorder-handle');
    if (!handle || !root.contains(handle) || event.button !== 0 || event.isPrimary === false || state.dragInProgress || state.modalOpen) return;
    const config = reorderConfig(handle);
    const source = config ? handle.closest(config.itemSelector) : null;
    if (!config || !source) return;
    state.cancelBubbleDrag?.();
    state.cancelReorderDrag?.();
    handle.focus({ preventScroll: true });
    drag = {
      config,
      source,
      handle,
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      label: reorderItemName(config.kind, source),
      active: false,
      drop: null,
      ghost: null,
      indicator: document.createElement('div'),
      lastDropKey: null,
      scrollDirection: 0,
      scrollFrame: null,
    };
    state.cancelReorderDrag = clean;
    state.dragInProgress = true;
    try { handle.setPointerCapture(event.pointerId); } catch { /* window events still cover the gesture */ }
    event.preventDefault();
  });

  window.addEventListener('pointermove', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.pointerType === 'mouse' && event.buttons === 0) { clean(); return; }
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (!drag.active && distance < 6) return;
    event.preventDefault();
    activate(event.clientX, event.clientY);
    moveGhost(event.clientX, event.clientY);
    updateDrop(event.clientX, event.clientY);
    updateAutoScroll(event.clientX, event.clientY);
  });

  window.addEventListener('pointerup', event => {
    if (drag?.pointerId === event.pointerId) void finish(event.clientX, event.clientY);
  });
  window.addEventListener('pointercancel', event => { if (drag?.pointerId === event.pointerId) clean(); });
  root.addEventListener('lostpointercapture', event => { if (drag?.pointerId === event.pointerId) clean(); });
  root.addEventListener('contextmenu', event => { if (drag?.active && event.target.closest('.reorder-handle')) event.preventDefault(); });
  root.addEventListener('keydown', event => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key) || state.dragInProgress || state.modalOpen) return;
    const handle = event.target.closest('.reorder-handle');
    const config = handle ? reorderConfig(handle) : null;
    const source = config ? handle.closest(config.itemSelector) : null;
    if (!config || !source) return;
    event.preventDefault();
    const drop = keyboardReorderDrop(config, source, event.key === 'ArrowUp' ? -1 : 1);
    if (!drop) { announceReorder(`${reorderItemName(config.kind, source)} is already at the edge of this group.`); return; }
    state.dragInProgress = true;
    const label = reorderItemName(config.kind, source);
    void persistReorder(config, source, drop)
      .then(result => {
        if (result === 'saved') announceReorder(`${label} reordered.`);
        else if (result === 'failed') announceReorder(`${label} could not be reordered. The latest order is shown.`);
        else announceReorder(`${label} stayed in the same position.`);
      })
      .finally(() => { state.dragInProgress = false; });
  });
  window.addEventListener('blur', () => state.cancelReorderDrag?.());
  document.addEventListener('visibilitychange', () => { if (document.hidden) state.cancelReorderDrag?.(); });
}

function analyticsCategoryAmount(category, month) {
  return category.months.find(item => item.month === month)?.amount || '0';
}

function analyticsDeltaMarkup(currentValue, baselineValue, { lowerIsBetter = false } = {}) {
  const current = toUnits(currentValue);
  const baseline = toUnits(baselineValue);
  const delta = current - baseline;
  if (delta === 0n) return '<span class="analytics-delta neutral">No change</span>';
  const improved = lowerIsBetter ? delta < 0n : delta > 0n;
  return `<span class="analytics-delta ${improved ? 'positive' : 'warning'}">${escapeHtml(money(unitsToString(delta), { plus: true }))} · ${delta > 0n ? 'higher' : 'lower'}</span>`;
}

async function renderAnalytics() {
  state.analyticsEnd ||= state.month;
  state.analyticsStart ||= addMonths(state.analyticsEnd, -11);
  const requestedStart = state.analyticsStart;
  const requestedEnd = state.analyticsEnd;
  const sequence = ++state.analyticsLoadSequence;
  if (!state.analytics) loadingView();
  const data = await api(`/api/analytics?start_month=${encodeURIComponent(requestedStart)}&end_month=${encodeURIComponent(requestedEnd)}`);
  if (sequence !== state.analyticsLoadSequence || state.view !== 'analytics') return;
  state.analytics = data;
  state.analyticsStart = data.start_month;
  state.analyticsEnd = data.end_month;
  paintAnalytics();
}

function paintAnalytics() {
  const data = state.analytics;
  if (!data) return;
  const months = data.months;
  const monthKeys = months.map(item => item.month);
  const latestMonth = monthKeys.at(-1);
  const previousMonth = monthKeys.at(-2) || latestMonth;
  if (!monthKeys.includes(state.analyticsCompareA)) state.analyticsCompareA = previousMonth;
  if (!monthKeys.includes(state.analyticsCompareB)) state.analyticsCompareB = latestMonth;
  const compareA = months.find(item => item.month === state.analyticsCompareA) || months[0];
  const compareB = months.find(item => item.month === state.analyticsCompareB) || months.at(-1);
  const maximum = months.reduce((value, item) => {
    const income = toUnits(item.income); const spending = toUnits(item.spending);
    const absoluteIncome = income < 0n ? -income : income;
    const absoluteSpending = spending < 0n ? -spending : spending;
    return absoluteIncome > value ? absoluteIncome : absoluteSpending > value ? absoluteSpending : value;
  }, 1n);
  const barHeight = value => {
    let units = toUnits(value); if (units < 0n) units = -units;
    if (units === 0n) return 0;
    return Math.max(4, Number(units * 1000n / maximum) / 10);
  };
  const shortMonth = month => {
    const [year, number] = month.split('-').map(Number);
    return new Intl.DateTimeFormat(undefined, { month: 'short' }).format(new Date(year, number - 1, 1));
  };
  const rangeMonthCount = months.length;
  const compareOptions = monthKeys.map(month => `<option value="${month}" ${month === state.analyticsCompareA ? 'selected' : ''}>${escapeHtml(monthLabel(month))}</option>`).join('');
  const compareBOptions = monthKeys.map(month => `<option value="${month}" ${month === state.analyticsCompareB ? 'selected' : ''}>${escapeHtml(monthLabel(month))}</option>`).join('');
  const chartColumns = months.map(item => {
    const [year] = item.month.split('-');
    return `<div class="analytics-chart-month" title="${escapeHtml(`${monthLabel(item.month)}: ${money(item.income)} income, ${money(item.spending)} spending`)}">
      <div class="analytics-bars" aria-hidden="true"><i class="analytics-bar income" style="--bar-height:${barHeight(item.income)}%"></i><i class="analytics-bar spending" style="--bar-height:${barHeight(item.spending)}%"></i></div>
      <strong>${escapeHtml(shortMonth(item.month))}</strong><small>${escapeHtml(year)}</small>
      <span class="sr-only">${escapeHtml(`${monthLabel(item.month)}, income ${money(item.income)}, spending ${money(item.spending)}, net ${money(item.net)}`)}</span>
    </div>`;
  }).join('');
  const monthRows = [...months].reverse().map(item => `<tr>
    <th scope="row">${escapeHtml(monthLabel(item.month))}</th>
    <td class="money-cell ${toUnits(item.income) < 0n ? 'danger' : 'positive'}">${money(item.income)}</td>
    <td class="money-cell">${money(item.spending)}</td>
    <td class="money-cell ${toUnits(item.net) < 0n ? 'danger' : 'positive'}">${money(item.net)}</td>
    <td class="count-cell">${item.transaction_count}</td>
    <td class="count-cell">${item.uncategorized_transaction_count ? `<span class="pill warning">${item.uncategorized_transaction_count}</span>` : '0'}</td>
  </tr>`).join('');
  const categoryRows = data.categories.filter(category => (
    toUnits(analyticsCategoryAmount(category, compareA.month)) !== 0n
    || toUnits(analyticsCategoryAmount(category, compareB.month)) !== 0n
  )).map(category => {
    const first = analyticsCategoryAmount(category, compareA.month);
    const second = analyticsCategoryAmount(category, compareB.month);
    const delta = toUnits(second) - toUnits(first);
    const improved = category.is_income ? delta > 0n : delta < 0n;
    const deltaClass = delta === 0n ? 'neutral' : improved ? 'positive' : 'warning';
    return `<tr>
      <th scope="row"><strong>${escapeHtml(category.name)}</strong><small>${escapeHtml(category.section_name)}</small></th>
      <td class="money-cell">${money(first)}</td>
      <td class="money-cell">${money(second)}</td>
      <td class="money-cell"><span class="analytics-delta ${deltaClass}">${delta === 0n ? '—' : escapeHtml(money(unitsToString(delta), { plus: true }))}</span></td>
    </tr>`;
  }).join('');
  const unsortedCount = data.totals.uncategorized_transaction_count;
  const reviewMonth = [...months].reverse().find(item => item.uncategorized_transaction_count)?.month || null;

  $('#app-view').innerHTML = `
    <header class="view-header analytics-heading"><div><h1>Analytics</h1><p>See your actual income and spending over time, then compare any two months.</p></div></header>
    <section class="analytics-range-card" aria-labelledby="analytics-range-title">
      <form id="analytics-range-form" class="analytics-range-form">
        <div><h2 id="analytics-range-title">Date range</h2><p>${rangeMonthCount} month${rangeMonthCount === 1 ? '' : 's'} · ${escapeHtml(monthLabel(data.start_month))} – ${escapeHtml(monthLabel(data.end_month))}</p></div>
        <label>From<input id="analytics-start" type="month" value="${escapeHtml(data.start_month)}" required></label>
        <label>Through<input id="analytics-end" type="month" value="${escapeHtml(data.end_month)}" required></label>
        <button class="button button--primary" type="submit">Apply</button>
      </form>
      <div class="analytics-presets" aria-label="Date range presets"><span>Quick range</span><button class="button button--ghost analytics-preset" data-months="3" type="button">3 months</button><button class="button button--ghost analytics-preset" data-months="6" type="button">6 months</button><button class="button button--ghost analytics-preset" data-months="12" type="button">12 months</button></div>
    </section>
    <section class="analytics-kpis" aria-label="Range summary">
      <article><span>Total income</span><strong class="${toUnits(data.totals.income) < 0n ? 'danger' : 'positive'}">${money(data.totals.income)}</strong><small>${money(data.totals.average_income)} monthly average</small></article>
      <article><span>Total spending</span><strong>${money(data.totals.spending)}</strong><small>${money(data.totals.average_spending)} monthly average</small></article>
      <article><span>Net cash flow</span><strong class="${toUnits(data.totals.net) < 0n ? 'danger' : 'positive'}">${money(data.totals.net)}</strong><small>${money(data.totals.average_net)} monthly average</small></article>
      <article><span>Transactions</span><strong>${data.totals.transaction_count}</strong><small>${data.totals.categorized_transaction_count} categorized</small></article>
    </section>
    ${unsortedCount ? `<aside class="analytics-notice"><span><strong>${unsortedCount} transaction${unsortedCount === 1 ? '' : 's'} still need${unsortedCount === 1 ? 's' : ''} a category.</strong><small>The ${money(data.totals.uncategorized_net)} net amount is disclosed here but excluded from income and spending totals.</small></span><button class="button button--soft analytics-review-unsorted" type="button">Review ${escapeHtml(monthLabel(reviewMonth))}</button></aside>` : ''}
    <section class="analytics-panel">
      <header><div><h2>Income and spending by month</h2><p>Bars share one scale; exact amounts are listed below.</p></div><div class="analytics-legend"><span><i class="income"></i>Income</span><span><i class="spending"></i>Spending</span></div></header>
      <div class="analytics-chart-scroll"><div class="analytics-chart" role="img" aria-label="Monthly income and spending from ${escapeHtml(monthLabel(data.start_month))} through ${escapeHtml(monthLabel(data.end_month))}">${chartColumns}</div></div>
    </section>
    <section class="analytics-panel">
      <header><div><h2>Compare months</h2><p>The second month is compared with the first.</p></div><div class="analytics-compare-controls"><label>First<select id="analytics-compare-a">${compareOptions}</select></label><span aria-hidden="true">→</span><label>Second<select id="analytics-compare-b">${compareBOptions}</select></label></div></header>
      <div class="analytics-comparison-grid">
        <article><span>Income in ${escapeHtml(monthLabel(compareB.month))}</span><strong class="${toUnits(compareB.income) < 0n ? 'danger' : 'positive'}">${money(compareB.income)}</strong>${analyticsDeltaMarkup(compareB.income, compareA.income)}</article>
        <article><span>Spending in ${escapeHtml(monthLabel(compareB.month))}</span><strong>${money(compareB.spending)}</strong>${analyticsDeltaMarkup(compareB.spending, compareA.spending, { lowerIsBetter: true })}</article>
        <article><span>Net in ${escapeHtml(monthLabel(compareB.month))}</span><strong class="${toUnits(compareB.net) < 0n ? 'danger' : 'positive'}">${money(compareB.net)}</strong>${analyticsDeltaMarkup(compareB.net, compareA.net)}</article>
      </div>
      <div class="analytics-table-wrap"><table class="analytics-table"><caption>Category comparison for ${escapeHtml(monthLabel(compareA.month))} and ${escapeHtml(monthLabel(compareB.month))}</caption><thead><tr><th scope="col">Category</th><th scope="col">${escapeHtml(monthLabel(compareA.month))}</th><th scope="col">${escapeHtml(monthLabel(compareB.month))}</th><th scope="col">Change</th></tr></thead><tbody>${categoryRows || '<tr><td colspan="4" class="analytics-empty-cell">No categorized activity in these two months.</td></tr>'}</tbody></table></div>
    </section>
    <section class="analytics-panel">
      <header><div><h2>Monthly detail</h2><p>Income and spending include categorized activity only.</p></div></header>
      <div class="analytics-table-wrap"><table class="analytics-table"><thead><tr><th scope="col">Month</th><th scope="col">Income</th><th scope="col">Spending</th><th scope="col">Net</th><th scope="col">Transactions</th><th scope="col">To sort</th></tr></thead><tbody>${monthRows}</tbody></table></div>
    </section>`;

  $('#analytics-range-form').addEventListener('submit', async event => {
    event.preventDefault();
    const start = $('#analytics-start').value; const end = $('#analytics-end').value;
    if (!start || !end) { toast('Choose both ends of the analytics range.', 'error'); return; }
    if (start > end) { toast('The start month must come before the end month.', 'error'); return; }
    const previous = { data: state.analytics, start: state.analyticsStart, end: state.analyticsEnd, compareA: state.analyticsCompareA, compareB: state.analyticsCompareB };
    state.analyticsStart = start; state.analyticsEnd = end; state.analytics = null;
    state.analyticsCompareA = null; state.analyticsCompareB = null;
    const expectedSequence = state.analyticsLoadSequence + 1;
    try { await renderAnalytics(); }
    catch (error) {
      if (state.analyticsLoadSequence !== expectedSequence) return;
      state.analytics = previous.data; state.analyticsStart = previous.start; state.analyticsEnd = previous.end;
      state.analyticsCompareA = previous.compareA; state.analyticsCompareB = previous.compareB;
      if (error.status !== 401 && state.view === 'analytics') { toast(error.message, 'error'); paintAnalytics(); }
    }
  });
  $$('.analytics-preset', $('#app-view')).forEach(button => button.addEventListener('click', async () => {
    const end = $('#analytics-end').value || state.analyticsEnd || state.month;
    const previous = { data: state.analytics, start: state.analyticsStart, end: state.analyticsEnd, compareA: state.analyticsCompareA, compareB: state.analyticsCompareB };
    state.analyticsEnd = end; state.analyticsStart = addMonths(end, -(Number(button.dataset.months) - 1)); state.analytics = null;
    state.analyticsCompareA = null; state.analyticsCompareB = null;
    const expectedSequence = state.analyticsLoadSequence + 1;
    try { await renderAnalytics(); }
    catch (error) {
      if (state.analyticsLoadSequence !== expectedSequence) return;
      state.analytics = previous.data; state.analyticsStart = previous.start; state.analyticsEnd = previous.end;
      state.analyticsCompareA = previous.compareA; state.analyticsCompareB = previous.compareB;
      if (error.status !== 401 && state.view === 'analytics') { toast(error.message, 'error'); paintAnalytics(); }
    }
  }));
  $('#analytics-compare-a').addEventListener('change', event => {
    state.analyticsCompareA = event.currentTarget.value; paintAnalytics();
    $('#analytics-compare-a')?.focus({ preventScroll: true });
  });
  $('#analytics-compare-b').addEventListener('change', event => {
    state.analyticsCompareB = event.currentTarget.value; paintAnalytics();
    $('#analytics-compare-b')?.focus({ preventScroll: true });
  });
  $('.analytics-review-unsorted', $('#app-view'))?.addEventListener('click', () => {
    state.month = reviewMonth; state.transactionStatus = 'unassigned'; state.transactionCategory = null; state.transactionSearch = '';
    clearTransactionListSelection(); state.budget = null; setView('transactions');
  });
}

async function toggleSectionCollapse(sectionId) {
  const existing = new Set(state.me.user.preferences?.collapsed_sections || []);
  if (existing.has(sectionId)) existing.delete(sectionId); else existing.add(sectionId);
  const preferences = { ...(state.me.user.preferences || {}), collapsed_sections: [...existing] };
  const body = { version: state.me.user.version, theme: state.me.user.theme, preferences };
  try {
    const result = await withConflict(
      current => api('/api/auth/preferences', { method: 'PATCH', body: current }),
      body,
      'section display preference',
    );
    if (!result) return;
    state.me.user = result.user;
    renderBudget();
  } catch (error) { toast(error.message, 'error'); }
}

function openBudgetAmount(categoryId) {
  const found = categoryById(categoryId);
  if (!found) return;
  openModal({
    title: found.name,
    body: `<form id="budget-amount-form" class="form-grid"><label>Planned amount for ${escapeHtml(monthLabel(state.month))}<input id="planned-amount" inputmode="decimal" value="${escapeHtml(found.planned)}" required></label>${found.rollover ? '<p class="muted">This is a fund. Its unused balance carries forward.</p>' : ''}</form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary modal-save" type="button">Save amount</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      const save = async () => {
        const button = $('.modal-save', root);
        const body = { version: found.budget_version, planned: $('#planned-amount', root).value.trim() };
        setButtonBusy(button, true);
        try {
          const result = await withConflict(
            current => api(`/api/budget/${state.month}/categories/${categoryId}`, { method: 'PUT', body: current }),
            body,
            'budget amount',
          );
          if (result) { closeModal(); await refreshCurrentView(); }
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.modal-save', root).addEventListener('click', save);
      $('#budget-amount-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function availabilityDescription(item) {
  const start = item?.starts_month || '1900-01';
  const end = item?.ends_before_month || null;
  if (start === '1900-01' && !end) return 'Available in every budget month.';
  const pieces = [];
  if (start === '1900-01') pieces.push('Available from the earliest budget month');
  else pieces.push(`Available beginning ${monthLabel(start)}`);
  if (end) pieces.push(`through ${monthLabel(addMonths(end, -1))}`);
  else pieces.push('with no ending month');
  return `${pieces.join(' ')}.`;
}

function startMonthMarkup(prefix) {
  return `<label>Appears starting<select id="${prefix}-start-mode"><option value="current">${escapeHtml(monthLabel(state.month))}</option><option value="all">All months, including earlier history</option><option value="custom">Choose another month</option></select></label>
    <label id="${prefix}-custom-wrap" class="hidden">First month<input id="${prefix}-custom-month" type="month" value="${escapeHtml(state.month)}" min="1900-01"></label>`;
}

function bindStartMonthControl(root, prefix) {
  const mode = $(`#${prefix}-start-mode`, root);
  const wrap = $(`#${prefix}-custom-wrap`, root);
  mode?.addEventListener('change', () => {
    wrap.classList.toggle('hidden', mode.value !== 'custom');
    state.formDirty = true;
  });
}

function readStartMonth(root, prefix) {
  const mode = $(`#${prefix}-start-mode`, root)?.value || 'current';
  if (mode === 'all') return '1900-01-01';
  const value = mode === 'custom' ? $(`#${prefix}-custom-month`, root).value : state.month;
  if (!/^\d{4}-\d{2}$/.test(value || '')) throw new Error('Choose a valid first month.');
  return `${value}-01`;
}

function openStructureRemoval(kind, item) {
  const noun = kind === 'section' ? 'section' : 'category';
  const plural = kind === 'section' ? 'sections' : 'categories';
  openModal({
    title: `Remove ${item.name}`,
    body: `<form id="structure-removal-form" class="form-grid">
      <label>Month<input id="structure-removal-month" type="month" value="${escapeHtml(state.month)}" min="1900-01"></label>
      <fieldset class="choice-stack full">
        <legend>How should it be removed?</legend>
        <label class="choice-card"><input type="radio" name="structure-removal-scope" value="forward" checked><span><strong>Beginning with this month</strong><small>Earlier budgets remain unchanged. It stays hidden in later months until restored.</small></span></label>
        <label class="choice-card"><input type="radio" name="structure-removal-scope" value="month"><span><strong>Only for this one month</strong><small>It returns automatically in the following month.</small></span></label>
        <label class="choice-card danger-choice"><input type="radio" name="structure-removal-scope" value="all"><span><strong>Archive in every month</strong><small>Hide it throughout the budget. History and transactions are retained, and it can be restored later.</small></span></label>
      </fieldset>
    </form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--danger apply-structure-removal" type="button">Remove</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('input', root).forEach(input => input.addEventListener('change', () => { state.formDirty = true; }));
      const apply = async () => {
        const button = $('.apply-structure-removal', root);
        const scope = $('input[name="structure-removal-scope"]:checked', root).value;
        const selectedMonth = $('#structure-removal-month', root).value;
        if (scope !== 'all' && !/^\d{4}-\d{2}$/.test(selectedMonth || '')) {
          toast('Choose a valid month.', 'error'); return;
        }
        const body = {
          version: item.version,
          month: `${selectedMonth || state.month}-01`,
          visible: false,
          scope,
        };
        setButtonBusy(button, true, 'Removing…');
        try {
          const result = await withConflict(
            current => api(`/api/${plural}/${item.id}/visibility`, { method: 'PUT', body: current }),
            body,
            `${noun} availability`,
          );
          if (!result) return;
          closeModal();
          toast(scope === 'month' ? `${item.name} hidden for one month` : scope === 'forward' ? `${item.name} removed from later budgets` : `${item.name} archived`);
          await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); }
        finally { setButtonBusy(button, false); }
      };
      $('.apply-structure-removal', root).addEventListener('click', apply);
      $('#structure-removal-form', root).addEventListener('submit', event => { event.preventDefault(); apply(); });
    },
  });
}

function hiddenItemMarkup(kind, item) {
  const archived = item.visibility_reason === 'archived';
  const location = kind === 'category' ? `<small>${escapeHtml(item.section_name)} · ${escapeHtml(item.visibility_label)}</small>` : `<small>${escapeHtml(item.visibility_label)} · ${item.category_count} categor${item.category_count === 1 ? 'y' : 'ies'}</small>`;
  const firstAction = item.visibility_reason === 'hidden_this_month'
    ? '<button class="button button--soft restore-structure" type="button" data-scope="month">Show this month</button>'
    : archived ? '' : '<button class="button button--soft restore-structure" type="button" data-scope="forward">Show from chosen month</button>';
  return `<article class="hidden-structure-item" data-kind="${kind}" data-id="${item.id}" data-version="${item.version}">
    <div><strong>${escapeHtml(item.name)}</strong>${location}<p>${escapeHtml(availabilityDescription(item))}</p></div>
    <div class="button-row">${firstAction}${item.visibility_reason === 'hidden_this_month' ? '<button class="button button--ghost restore-structure" type="button" data-scope="forward">Show from chosen month</button>' : ''}<button class="button button--ghost restore-structure" type="button" data-scope="all">Show in all months</button></div>
  </article>`;
}

function openHiddenStructureManager() {
  const hidden = state.budget?.hidden_structure || { sections: [], categories: [], count: 0 };
  if (!hidden.count) { toast('There are no hidden budget items in this month.'); return; }
  const sectionRows = hidden.sections.map(item => hiddenItemMarkup('section', item)).join('');
  const categoryRows = hidden.categories.map(item => hiddenItemMarkup('category', item)).join('');
  openModal({
    title: `Hidden in ${monthLabel(state.month)}`,
    className: 'modal--wide',
    body: `<div class="form-grid"><label>Chosen restoration month<input id="restore-structure-month" type="month" value="${escapeHtml(state.month)}" min="1900-01"></label></div>
      ${sectionRows ? `<section class="form-section"><h3>Sections</h3><div class="hidden-structure-list">${sectionRows}</div></section>` : ''}
      ${categoryRows ? `<section class="form-section"><h3>Categories</h3><div class="hidden-structure-list">${categoryRows}</div></section>` : ''}
      <p class="muted">Restoring from a later month preserves any gap. Earlier budget history is never rewritten.</p>`,
    footer: '<button class="button modal-cancel" type="button">Close</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $('#restore-structure-month', root).addEventListener('change', () => { state.formDirty = true; });
      $$('.restore-structure', root).forEach(button => button.addEventListener('click', async () => {
        const card = button.closest('.hidden-structure-item');
        const kind = card.dataset.kind;
        const plural = kind === 'section' ? 'sections' : 'categories';
        const selectedMonth = $('#restore-structure-month', root).value;
        if (!/^\d{4}-\d{2}$/.test(selectedMonth || '')) { toast('Choose a valid restoration month.', 'error'); return; }
        const body = {
          version: Number(card.dataset.version),
          month: `${selectedMonth}-01`,
          visible: true,
          scope: button.dataset.scope,
        };
        setButtonBusy(button, true, 'Restoring…');
        try {
          const result = await withConflict(
            current => api(`/api/${plural}/${card.dataset.id}/visibility`, { method: 'PUT', body: current }),
            body,
            `${kind} availability`,
          );
          if (!result) return;
          closeModal(); toast('Budget item restored'); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); }
        finally { setButtonBusy(button, false); }
      }));
    },
  });
}

function openSectionEditor(sectionId = null) {
  const section = sectionId ? state.budget.sections.find(item => item.id === sectionId) : null;
  const siblings = state.budget.sections.filter(item => !item.is_income && item.id !== section?.id);
  const expenseSections = state.budget.sections.filter(item => !item.is_income);
  const currentIndex = section ? Math.max(0, expenseSections.findIndex(item => item.id === section.id)) : siblings.length;
  const positionOptions = Array.from({ length: siblings.length + 1 }, (_, index) => {
    const label = index === 0 ? 'First, directly below Income' : `After ${siblings[index - 1].name}`;
    return `<option value="${index}" ${index === currentIndex ? 'selected' : ''}>${escapeHtml(label)}</option>`;
  }).join('');
  openModal({
    title: section ? `Edit ${section.name}` : 'Add budget section',
    body: `<form id="section-form" class="form-grid">
      <label>Section name<input id="section-name" value="${escapeHtml(section?.name || '')}" maxlength="100" required></label>
      <label>Icon<select id="section-icon">${['wallet','home','basket','car','repeat','person','vault','sparkles'].map(icon => `<option value="${icon}" ${section?.icon === icon ? 'selected' : ''}>${icon[0].toUpperCase()+icon.slice(1)}</option>`).join('')}</select></label>
      ${section?.is_income ? '<p class="muted">Income is the protected first section and exists in every month.</p>' : `<label>Position<select id="section-position">${positionOptions}</select></label>`}
      ${section ? `<div class="availability-summary full"><strong>Month availability</strong><span>${escapeHtml(availabilityDescription(section))}</span></div>` : startMonthMarkup('section')}
    </form>
    ${section && !section.is_income ? '<div class="form-section"><button class="button button--danger remove-section" type="button">Remove from budget months…</button></div>' : ''}`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary modal-save" type="button">Save</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      if (!section) bindStartMonthControl(root, 'section');
      $('.remove-section', root)?.addEventListener('click', () => openStructureRemoval('section', section));
      const save = async () => {
        const button = $('.modal-save', root); setButtonBusy(button, true);
        const body = {
          name: $('#section-name', root).value.trim(),
          icon: $('#section-icon', root).value,
          accent: section?.accent || 'accent',
        };
        if (!section?.is_income) body.sort_order = Number($('#section-position', root).value);
        try {
          if (section) {
            body.version = section.version;
            await withConflict(current => api(`/api/sections/${section.id}`, { method: 'PATCH', body: current }), body, 'section');
          } else {
            body.starts_month = readStartMonth(root, 'section');
            await api('/api/sections', { method: 'POST', body });
          }
          closeModal(); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.modal-save', root).addEventListener('click', save);
      $('#section-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function openCategoryEditor(categoryId = null, sectionId = null) {
  const found = categoryId ? categoryById(categoryId) : null;
  const section = found?.section || state.budget.sections.find(item => item.id === sectionId);
  if (!section) return;

  const positionOptions = targetSectionId => {
    const target = state.budget.sections.find(item => item.id === targetSectionId);
    if (!target) return '';
    const siblings = target.categories.filter(item => item.id !== found?.id);
    const currentIndex = found && found.section.id === target.id
      ? Math.max(0, target.categories.findIndex(item => item.id === found.id))
      : siblings.length;
    return Array.from({ length: siblings.length + 1 }, (_, index) => {
      const label = index === 0 ? 'First in section' : `After ${siblings[index - 1].name}`;
      return `<option value="${index}" ${index === currentIndex ? 'selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('');
  };

  openModal({
    title: found ? `Edit ${found.name}` : `Add to ${section.name}`,
    body: `<form id="category-form" class="form-grid">
      <label>Name<input id="category-name" value="${escapeHtml(found?.name || '')}" maxlength="120" required></label>
      <label>Section<select id="category-section">${state.budget.sections.map(item => `<option value="${item.id}" ${item.id === section.id ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('')}</select></label>
      <label>Position<select id="category-position">${positionOptions(section.id)}</select></label>
      <label>Default monthly plan<input id="category-default" inputmode="decimal" value="${escapeHtml(found?.default_planned || '0')}"></label>
      <label class="full"><span><input id="category-rollover" type="checkbox" style="width:auto;min-height:auto" ${found?.rollover ? 'checked' : ''} ${section.is_income ? 'disabled' : ''}> Carry unused money forward as a fund</span></label>
      <label>Note<textarea id="category-note">${escapeHtml(found?.note || '')}</textarea></label>
      ${found ? `<div class="availability-summary full"><strong>Month availability</strong><span>${escapeHtml(availabilityDescription(found))}</span></div>` : startMonthMarkup('category')}
    </form>
    ${found ? '<div class="form-section"><button class="button button--danger remove-category" type="button">Remove from budget months…</button></div>' : ''}`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary modal-save" type="submit" form="category-form">Save</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      if (!found) bindStartMonthControl(root, 'category');
      $('#category-section', root).addEventListener('change', event => {
        const target = state.budget.sections.find(item => item.id === event.target.value);
        $('#category-rollover', root).disabled = !!target?.is_income;
        if (target?.is_income) $('#category-rollover', root).checked = false;
        $('#category-position', root).innerHTML = positionOptions(event.target.value);
      });
      $('.remove-category', root)?.addEventListener('click', () => openStructureRemoval('category', found));
      const save = async () => {
        const button = $('.modal-save', root); setButtonBusy(button, true);
        const body = {
          section_id: $('#category-section', root).value,
          name: $('#category-name', root).value.trim(),
          sort_order: Number($('#category-position', root).value),
          rollover: $('#category-rollover', root).checked,
          default_planned: $('#category-default', root).value.trim() || '0',
          note: $('#category-note', root).value,
        };
        try {
          if (found) {
            body.version = found.version;
            await withConflict(current => api(`/api/categories/${found.id}?current_month=${encodeURIComponent(state.month)}`, { method: 'PATCH', body: current }), body, 'category');
          } else {
            body.starts_month = readStartMonth(root, 'category');
            await api('/api/categories', { method: 'POST', body });
          }
          closeModal(); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('#category-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function trayTransactions() {
  return (state.budget?.unassigned || []).filter(transaction => (
    !transaction.allocations?.length
    && !transaction.excluded
    && !transaction.deleted_at
    && !transaction.suppressed_by_duplicate_account
  ));
}

function selectedTrayTransactionIds() {
  return trayTransactions()
    .map(transaction => transaction.id)
    .filter(id => state.selectedTransactionIds.has(id));
}

function reconcileBubbleSelection(rows = trayTransactions()) {
  const visibleIds = new Set(rows.map(transaction => transaction.id));
  for (const id of state.selectedTransactionIds) {
    if (!visibleIds.has(id)) state.selectedTransactionIds.delete(id);
  }
  if (state.selectionAnchorId && !visibleIds.has(state.selectionAnchorId)) state.selectionAnchorId = null;
}

function syncBubbleSelection() {
  const container = $('#transaction-bubbles');
  $$('.tx-bubble', container || document).forEach(bubble => {
    const selected = state.selectedTransactionIds.has(bubble.dataset.transactionId);
    bubble.classList.toggle('is-selected', selected);
    const checkbox = $('.tx-select', bubble);
    if (checkbox) checkbox.checked = selected;
  });
  const count = selectedTrayTransactionIds().length;
  container?.classList.toggle('selection-mode', count > 0);
  $('#tray-selection-bar')?.classList.toggle('hidden', count === 0);
  if ($('#tray-selection-count')) $('#tray-selection-count').textContent = `${count} selected`;
  if ($('#tray-assign-selection')) $('#tray-assign-selection').disabled = count === 0 || state.assignmentInFlight;
}

function clearBubbleSelection() {
  state.selectedTransactionIds.clear();
  state.selectionAnchorId = null;
  syncBubbleSelection();
}

function toggleBubbleSelection(transactionId, selected = null) {
  const shouldSelect = selected ?? !state.selectedTransactionIds.has(transactionId);
  if (shouldSelect) state.selectedTransactionIds.add(transactionId);
  else state.selectedTransactionIds.delete(transactionId);
  state.selectionAnchorId = transactionId;
  syncBubbleSelection();
}

function selectBubbleRange(transactionId, additive = false) {
  const ids = trayTransactions().map(transaction => transaction.id);
  const targetIndex = ids.indexOf(transactionId);
  const anchorIndex = ids.indexOf(state.selectionAnchorId);
  if (targetIndex < 0) return;
  if (anchorIndex < 0) {
    if (!additive) state.selectedTransactionIds.clear();
    state.selectedTransactionIds.add(transactionId);
    state.selectionAnchorId = transactionId;
    syncBubbleSelection();
    return;
  }
  if (!additive) state.selectedTransactionIds.clear();
  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);
  ids.slice(start, end + 1).forEach(id => state.selectedTransactionIds.add(id));
  syncBubbleSelection();
}

function renderTray() {
  const container = $('#transaction-bubbles');
  if (!container || !state.budget) return;
  $('#tray-title').textContent = 'Transactions to sort';
  $('#tray-target').textContent = `ASSIGN TO ${monthLabel(state.month).toLocaleUpperCase()}`;
  $('#tray-help').textContent = `Drop into a category to assign it to ${monthLabel(state.month)}. Select from the left edge; touch and hold on mobile.`;
  const focusedBubble = document.activeElement?.closest?.('.tx-bubble');
  const focusedId = focusedBubble?.dataset.transactionId || null;
  const focusedControl = document.activeElement?.classList.contains('tx-select') ? 'select' : 'content';
  state.cancelBubbleDrag?.();
  const rows = trayTransactions();
  reconcileBubbleSelection(rows);
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><strong>Everything is sorted</strong>New imported transactions will appear here automatically.</div>';
    syncBubbleSelection();
    return;
  }
  container.innerHTML = rows.map(transaction => {
    const inflow = toUnits(transaction.amount) > 0n;
    const label = transactionLabel(transaction);
    const description = `${label}, ${money(transaction.amount)}, ${formatDate(transaction.effective_date)}`;
    return `<article class="tx-bubble" data-transaction-id="${transaction.id}">
      <label class="tx-select-control" title="Select ${escapeHtml(label)}">
        <input class="tx-select" type="checkbox" aria-label="Select ${escapeHtml(description)}">
        <span class="tx-select-mark" aria-hidden="true"></span>
      </label>
      <button class="tx-bubble-content" type="button" aria-label="Open ${escapeHtml(description)}">
        <strong>${escapeHtml(label)}</strong>
        <span class="amount ${inflow ? 'inflow' : ''}">${money(transaction.amount, { plus: true })}</span>
        <small>${escapeHtml(transaction.account_name)} · ${escapeHtml(formatDate(transaction.effective_date))}</small>
        ${transaction.pending ? '<span class="pending-badge">Pending</span>' : ''}
      </button>
    </article>`;
  }).join('');
  syncBubbleSelection();
  if (focusedId && state.trayOpen) {
    const nextBubble = $$('.tx-bubble', container).find(bubble => bubble.dataset.transactionId === focusedId);
    $(`.${focusedControl === 'select' ? 'tx-select' : 'tx-bubble-content'}`, nextBubble || container)?.focus({ preventScroll: true });
  }
}

async function openTray() {
  if (!trayTransactions().length) return;
  const button = $('#inbox-button');
  if (button.getAttribute('aria-busy') === 'true') return;
  button.setAttribute('aria-busy', 'true');
  try {
    if (!await loadBudget({ silent: true })) return;
  } catch (error) {
    if (error.status !== 401) toast(`Could not refresh transactions to sort: ${error.message}`, 'error');
    return;
  } finally {
    button.removeAttribute('aria-busy');
  }
  if (state.view !== 'budget' || !trayTransactions().length) return;
  state.trayOpen = true;
  renderTray();
  const tray = $('#transaction-tray');
  tray.removeAttribute('inert');
  tray.classList.add('open');
  tray.setAttribute('aria-hidden', 'false');
  $('#inbox-button').setAttribute('aria-expanded', 'true');
  $('#scrim').classList.remove('hidden');
  document.body.classList.add('sheet-open');
  setTimeout(() => $('.tx-bubble-content', tray)?.focus({ preventScroll: true }), 30);
}

function closeTray({ restoreFocus = true } = {}) {
  state.cancelBubbleDrag?.();
  state.transactionEditorLoadSequence += 1;
  state.trayOpen = false;
  clearBubbleSelection();
  const tray = $('#transaction-tray');
  tray.classList.remove('open', 'dragging');
  tray.setAttribute('aria-hidden', 'true');
  tray.setAttribute('inert', '');
  $('#inbox-button').setAttribute('aria-expanded', 'false');
  $('#scrim').classList.add('hidden');
  document.body.classList.remove('sheet-open', 'dragging');
  if (restoreFocus && !$('#inbox-button').classList.contains('hidden')) $('#inbox-button').focus({ preventScroll: true });
}

async function undoTransactionAssignment(transactions, undoToken) {
  if (!transactions.length || !undoToken || state.assignmentInFlight) return false;
  state.assignmentInFlight = true;
  try {
    const result = await api('/api/transactions/batch', {
      method: 'PUT',
      body: {
        category_id: null,
        transactions: transactions.map(transaction => ({ id: transaction.id, version: transaction.version })),
        undo_token: undoToken,
      },
    });
    const refreshed = await refreshCurrentView();
    if (!refreshed && state.budget) {
      const restored = result.transactions || [];
      const restoredIds = new Set(restored.map(transaction => transaction.id));
      state.budget.unassigned = [
        ...restored,
        ...(state.budget.unassigned || []).filter(transaction => !restoredIds.has(transaction.id)),
      ];
      renderTray();
      updateNavigation();
    }
    const message = transactions.length === 1 ? 'Assignment undone' : `${transactions.length} assignments undone`;
    toast(refreshed ? message : `${message}. Reload to refresh budget totals.`);
    return true;
  } catch (error) {
    if (error.status !== 401) toast(`Could not undo: ${error.message}`, 'error');
    if (error instanceof ConflictError) await refreshCurrentView();
    return false;
  } finally {
    state.assignmentInFlight = false;
    syncBubbleSelection();
  }
}

async function assignTransactions(transactionIds, categoryId, { keepTrayOpen = false } = {}) {
  if (state.assignmentInFlight) return false;
  const transactions = transactionIds.map(transactionById);
  const category = categoryById(categoryId);
  if (!transactions.length || transactions.some(transaction => !transaction) || !category) {
    toast('Those transactions are no longer available to assign.', 'error');
    return false;
  }
  state.assignmentInFlight = true;
  const targetMonth = state.month;
  $('#transaction-tray')?.setAttribute('aria-busy', 'true');
  syncBubbleSelection();
  try {
    const result = await api('/api/transactions/batch', {
      method: 'PUT',
      body: {
        category_id: category.id,
        target_month: targetMonth,
        transactions: transactions.map(transaction => ({ id: transaction.id, version: transaction.version })),
      },
    });
    if (!keepTrayOpen) closeTray({ restoreFocus: false });
    const message = transactions.length === 1
      ? `${transactionLabel(transactions[0])} moved to ${category.name} in ${monthLabel(targetMonth)}`
      : `${transactions.length} transactions moved to ${category.name} in ${monthLabel(targetMonth)}`;
    const refreshed = await refreshCurrentView();
    if (!refreshed && state.budget) {
      const assignedIds = new Set((result.transactions || []).map(transaction => transaction.id));
      state.budget.unassigned = (state.budget.unassigned || []).filter(
        transaction => !assignedIds.has(transaction.id)
      );
      reconcileBubbleSelection();
      renderTray();
      updateNavigation();
    }
    const assignedRow = $(`.category-row[data-category-id="${category.id}"]`, $('#app-view'));
    if (assignedRow) {
      assignedRow.classList.add('assignment-confirmed');
      setTimeout(() => assignedRow.classList.remove('assignment-confirmed'), 1500);
    }
    if (!keepTrayOpen) $('#app-view')?.focus({ preventScroll: true });
    state.assignmentInFlight = false;
    $('#transaction-tray')?.removeAttribute('aria-busy');
    syncBubbleSelection();
    const confirmation = refreshed ? message : `${message}. Reload to refresh budget totals.`;
    const undoAction = result.undo_token ? {
      label: 'Undo',
      run: () => undoTransactionAssignment(result.transactions || [], result.undo_token),
    } : null;
    toast(confirmation, 'default', undoAction);
    return true;
  } catch (error) {
    if (error.status !== 401) toast(error.message, 'error');
    if (error instanceof ConflictError) await refreshCurrentView();
    return false;
  } finally {
    state.assignmentInFlight = false;
    $('#transaction-tray')?.removeAttribute('aria-busy');
    syncBubbleSelection();
  }
}

function openSelectedAssignment() {
  const transactionIds = selectedTrayTransactionIds();
  if (!transactionIds.length) return;
  if (!categoryOptions()) {
    toast('Add a budget category before assigning transactions.', 'error');
    return;
  }
  openModal({
    title: `Assign ${transactionIds.length} transaction${transactionIds.length === 1 ? '' : 's'} to ${monthLabel(state.month)}`,
    body: `<form id="group-assignment-form" class="form-grid">
      <label>Budget category<select id="group-assignment-category" required>${categoryOptions()}</select></label>
    </form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary modal-save" type="button">Assign selected</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      const save = async () => {
        const categoryId = $('#group-assignment-category', root).value;
        closeModal();
        const assigned = await assignTransactions(transactionIds, categoryId);
        if (!assigned && state.trayOpen) $('#tray-assign-selection')?.focus({ preventScroll: true });
      };
      $('.modal-save', root).addEventListener('click', save);
      $('#group-assignment-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function installBubbleDrag() {
  const container = $('#transaction-bubbles');
  if (!container || container.dataset.dragInstalled === 'true') return;
  container.dataset.dragInstalled = 'true';
  let drag = null;

  const waitForTrayReturn = () => {
    const tray = $('#transaction-tray');
    if (!tray?.classList.contains('dragging')) return Promise.resolve();
    return new Promise(resolve => {
      let timeout = null;
      const done = event => {
        if (event && (event.target !== tray || event.propertyName !== 'transform')) return;
        tray.removeEventListener('transitionend', done);
        clearTimeout(timeout);
        resolve();
      };
      tray.addEventListener('transitionend', done);
      timeout = setTimeout(done, 400);
    });
  };

  const focusTrayTransactionAt = index => {
    if (!state.trayOpen) return;
    const rows = trayTransactions();
    const transaction = rows[Math.min(Math.max(index, 0), rows.length - 1)];
    const bubble = transaction
      ? $(`.tx-bubble[data-transaction-id="${transaction.id}"]`, $('#transaction-bubbles'))
      : null;
    const content = bubble ? $('.tx-bubble-content', bubble) : null;
    (content || $('#tray-close'))?.focus({ preventScroll: true });
  };

  const clean = () => {
    const current = drag;
    drag = null;
    if (!current) return;
    clearTimeout(current.holdTimer);
    cancelAnimationFrame(current.scrollFrame);
    current.ghost?.remove();
    (current.bubbles || []).forEach(bubble => bubble.classList.remove('is-dragging'));
    $$('.category-row.drop-target').forEach(row => row.classList.remove('drop-target'));
    $('#transaction-tray').classList.remove('dragging');
    document.body.classList.remove('dragging');
    state.dragInProgress = false;
    state.cancelBubbleDrag = null;
    if (current.pointerId !== null && current.handle?.hasPointerCapture?.(current.pointerId)) {
      try { current.handle.releasePointerCapture(current.pointerId); } catch { /* capture may already be gone */ }
    }
    if (current.active) setTimeout(() => { delete current.bubble.dataset.dragged; }, 0);
  };

  const moveGhost = (x, y) => {
    if (!drag?.ghost) return;
    drag.ghost.style.transform = `translate3d(${x - drag.offsetX}px, ${y - drag.offsetY}px, 0)`;
  };

  const categoryAtPoint = (x, y) => {
    for (const element of document.elementsFromPoint(x, y)) {
      const category = element.closest?.('.category-row[data-category-id]');
      if (category) return category;
    }
    return null;
  };

  const updateDropTarget = (x, y) => {
    if (!drag?.active) return;
    drag.target?.classList.remove('drop-target');
    drag.target = categoryAtPoint(x, y);
    drag.target?.classList.add('drop-target');
  };

  const runAutoScroll = () => {
    if (!drag?.active || !drag.scrollDirection) {
      if (drag) drag.scrollFrame = null;
      return;
    }
    window.scrollBy({ top: drag.scrollDirection, behavior: 'auto' });
    updateDropTarget(drag.lastX, drag.lastY);
    drag.scrollFrame = requestAnimationFrame(runAutoScroll);
  };

  const updateAutoScroll = (x, y) => {
    if (!drag?.active) return;
    drag.lastX = x;
    drag.lastY = y;
    const edge = 72;
    drag.scrollDirection = y < edge ? -14 : y > window.innerHeight - edge ? 14 : 0;
    if (drag.scrollDirection && drag.scrollFrame === null) drag.scrollFrame = requestAnimationFrame(runAutoScroll);
  };

  const activateDrag = (x, y) => {
    if (!drag || drag.active || state.assignmentInFlight) return;
    const sourceId = drag.bubble.dataset.transactionId;
    const transactionIds = state.selectedTransactionIds.has(sourceId) ? selectedTrayTransactionIds() : [sourceId];
    const transactions = transactionIds.map(transactionById).filter(Boolean);
    if (!transactions.length || transactions.length !== transactionIds.length) { clean(); return; }
    drag.active = true;
    drag.transactionIds = transactionIds;
    drag.bubble.dataset.dragged = 'true';
    if (drag.pointerId !== null) {
      try {
        document.body.setPointerCapture(drag.pointerId);
        drag.handle = document.body;
      } catch { /* window listeners still track the active pointer */ }
    }
    drag.bubbles = $$('.tx-bubble', container).filter(bubble => transactionIds.includes(bubble.dataset.transactionId));
    drag.bubbles.forEach(bubble => bubble.classList.add('is-dragging'));
    const total = transactions.reduce((sum, transaction) => sum + toUnits(transaction.amount), 0n);
    const first = transactions[0];
    drag.ghost = document.createElement('div');
    drag.ghost.className = 'drag-ghost';
    drag.ghost.setAttribute('aria-hidden', 'true');
    drag.ghost.style.width = `${Math.min(210, Math.max(160, drag.rect.width))}px`;
    drag.ghost.innerHTML = `<strong>${escapeHtml(transactionLabel(first))}</strong>
      <span class="amount ${total > 0n ? 'inflow' : ''}">${money(unitsToString(total), { plus: true })}</span>
      <small>${transactions.length === 1 ? `${escapeHtml(first.account_name)} · ${escapeHtml(formatDate(first.effective_date))}` : `${transactions.length} transactions moving together`}</small>
      ${transactions.length > 1 ? `<span class="drag-count">${transactions.length}</span>` : ''}`;
    document.body.append(drag.ghost);
    state.dragInProgress = true;
    state.cancelBubbleDrag = clean;
    document.body.classList.add('dragging');
    $('#transaction-tray').classList.add('dragging');
    moveGhost(x, y);
    updateDropTarget(x, y);
    if (navigator.vibrate && drag.touchId !== null) navigator.vibrate(18);
  };

  const startDrag = ({ bubble, handle, x, y, pointerId = null, touchId = null }) => {
    state.cancelReorderDrag?.();
    clean();
    state.transactionEditorLoadSequence += 1;
    const rect = bubble.getBoundingClientRect();
    drag = {
      bubble,
      handle,
      pointerId,
      touchId,
      startX: x,
      startY: y,
      offsetX: Math.min(rect.width - 12, Math.max(12, x - rect.left)),
      offsetY: Math.min(rect.height - 12, Math.max(12, y - rect.top)),
      rect,
      active: false,
      target: null,
      ghost: null,
      bubbles: [],
      holdTimer: null,
      scrollFrame: null,
      scrollDirection: 0,
      lastX: x,
      lastY: y,
      transactionIds: [],
    };
    state.cancelBubbleDrag = clean;
  };

  const finish = async (x, y) => {
    if (!drag) return;
    if (drag.active) updateDropTarget(x, y);
    const wasActive = drag.active;
    const transactionIds = [...drag.transactionIds];
    const categoryId = drag.target?.dataset.categoryId || null;
    const firstDraggedIndex = Math.max(0, trayTransactions().findIndex(transaction => transactionIds.includes(transaction.id)));
    const trayReturned = wasActive ? waitForTrayReturn() : Promise.resolve();
    clean();
    if (wasActive && categoryId) {
      await assignTransactions(transactionIds, categoryId, { keepTrayOpen: true });
      await trayReturned;
      focusTrayTransactionAt(firstDraggedIndex);
    }
  };

  container.addEventListener('click', event => {
    const bubble = event.target.closest('.tx-bubble');
    if (bubble?.dataset.dragged === 'true') {
      event.preventDefault();
      event.stopPropagation();
      delete bubble.dataset.dragged;
      return;
    }
    const selectionControl = event.target.closest('.tx-select-control');
    if (selectionControl) {
      event.preventDefault();
      event.stopPropagation();
      const transactionId = selectionControl.closest('.tx-bubble').dataset.transactionId;
      if (event.shiftKey) selectBubbleRange(transactionId, event.ctrlKey || event.metaKey);
      else toggleBubbleSelection(transactionId);
      return;
    }
    const content = event.target.closest('.tx-bubble-content');
    if (!content) return;
    const transactionId = content.closest('.tx-bubble').dataset.transactionId;
    if (event.shiftKey) {
      event.preventDefault();
      selectBubbleRange(transactionId, event.ctrlKey || event.metaKey);
    } else if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      toggleBubbleSelection(transactionId);
    } else {
      openTransactionEditor(transactionId, {
        keepTrayOpen: true,
        shouldOpen: () => (
          state.trayOpen
          && !state.modalOpen
          && !state.dragInProgress
          && !state.assignmentInFlight
          && trayTransactions().some(transaction => transaction.id === transactionId)
        ),
        returnFocus: () => {
          if (!state.trayOpen) return null;
          const currentBubble = $$('.tx-bubble', container).find(item => item.dataset.transactionId === transactionId);
          return $('.tx-bubble-content', currentBubble || container) || $('#tray-close');
        },
      });
    }
  });

  container.addEventListener('pointerdown', event => {
    const bubble = event.target.closest('.tx-bubble');
    if (!bubble || event.target.closest('.tx-select-control') || event.button !== 0 || event.isPrimary === false || event.pointerType === 'touch' || state.assignmentInFlight) return;
    startDrag({ bubble, handle: bubble, x: event.clientX, y: event.clientY, pointerId: event.pointerId });
  });

  window.addEventListener('pointermove', event => {
    if (!drag || drag.pointerId !== event.pointerId || event.pointerType === 'touch') return;
    if (event.buttons === 0) { clean(); return; }
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (!drag.active && distance < 9) return;
    event.preventDefault();
    activateDrag(event.clientX, event.clientY);
    moveGhost(event.clientX, event.clientY);
    updateDropTarget(event.clientX, event.clientY);
    updateAutoScroll(event.clientX, event.clientY);
  }, { passive: false });

  window.addEventListener('pointerup', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    finish(event.clientX, event.clientY);
  });
  window.addEventListener('pointercancel', event => {
    if (drag?.pointerId === event.pointerId) clean();
  });
  container.addEventListener('touchstart', event => {
    if (event.touches.length !== 1) { clean(); return; }
    if (state.assignmentInFlight) return;
    const bubble = event.target.closest('.tx-bubble');
    if (!bubble || event.target.closest('.tx-select-control')) return;
    const touch = event.changedTouches[0];
    startDrag({
      bubble,
      handle: bubble,
      x: touch.clientX,
      y: touch.clientY,
      touchId: touch.identifier,
    });
    drag.holdTimer = setTimeout(() => activateDrag(touch.clientX, touch.clientY), 340);
  }, { passive: true });

  container.addEventListener('touchmove', event => {
    if (!drag || drag.touchId === null) return;
    const touch = Array.from(event.touches).find(item => item.identifier === drag.touchId);
    if (!touch) return;
    const distance = Math.hypot(touch.clientX - drag.startX, touch.clientY - drag.startY);
    if (!drag.active && distance > 8) { clean(); return; }
    if (!drag.active) return;
    event.preventDefault();
    moveGhost(touch.clientX, touch.clientY);
    updateDropTarget(touch.clientX, touch.clientY);
    updateAutoScroll(touch.clientX, touch.clientY);
  }, { passive: false });

  container.addEventListener('touchend', event => {
    if (!drag || drag.touchId === null) return;
    const touch = Array.from(event.changedTouches).find(item => item.identifier === drag.touchId);
    if (!touch) return;
    if (drag.active) event.preventDefault();
    finish(touch.clientX, touch.clientY);
  }, { passive: false });
  container.addEventListener('touchcancel', clean);
  container.addEventListener('contextmenu', event => {
    if (drag?.active && event.target.closest('.tx-bubble')) event.preventDefault();
  });
  window.addEventListener('blur', clean);
  document.addEventListener('visibilitychange', () => { if (document.hidden) clean(); });
}

function transactionCategoryText(transaction) {
  if (transaction.deleted_at) return 'Trash';
  if (!transaction.allocations?.length) return 'Unassigned';
  if (transaction.allocations.length === 1) {
    const part = transaction.allocations[0];
    return `${part.section_name} › ${part.category_name}`;
  }
  return `Split across ${transaction.allocations.length} categories`;
}

function selectedListTransactions() {
  return state.transactions.filter(transaction => state.selectedListTransactionIds.has(transaction.id));
}

function reconcileTransactionListSelection() {
  const visibleTransactions = new Map(state.transactions.filter(transaction => !transaction.deleted_at).map(transaction => [transaction.id, transaction]));
  let changedCount = 0;
  for (const id of state.selectedListTransactionIds) {
    const transaction = visibleTransactions.get(id);
    if (!transaction || state.listSelectionVersions.get(id) !== transaction.version) {
      state.selectedListTransactionIds.delete(id);
      state.listSelectionVersions.delete(id);
      if (transaction) changedCount += 1;
    }
  }
  if (state.listSelectionAnchorId && !state.selectedListTransactionIds.has(state.listSelectionAnchorId)) state.listSelectionAnchorId = null;
  if (changedCount) toast(`${changedCount} selected transaction${changedCount === 1 ? '' : 's'} changed elsewhere and ${changedCount === 1 ? 'was' : 'were'} deselected.`);
}

function syncTransactionListSelection() {
  const container = $('.transaction-list', $('#app-view'));
  $$('.transaction-card', container || document).forEach(card => {
    const selected = state.selectedListTransactionIds.has(card.dataset.transactionId);
    card.classList.toggle('is-selected', selected);
    const checkbox = $('.transaction-list-select', card);
    if (checkbox) checkbox.checked = selected;
  });
  const count = selectedListTransactions().length;
  container?.classList.toggle('selection-mode', count > 0);
  $('.transaction-selection-bar', $('#app-view'))?.classList.toggle('hidden', count === 0);
  if ($('#transaction-selection-count', $('#app-view'))) $('#transaction-selection-count', $('#app-view')).textContent = `${count} selected`;
  if ($('.edit-selected-transactions', $('#app-view'))) $('.edit-selected-transactions', $('#app-view')).disabled = count === 0 || state.bulkTransactionInFlight;
}

function clearTransactionListSelection() {
  state.selectedListTransactionIds.clear();
  state.listSelectionVersions.clear();
  state.listSelectionAnchorId = null;
  syncTransactionListSelection();
}

function toggleTransactionListSelection(transactionId, selected = null) {
  const transaction = state.transactions.find(item => item.id === transactionId);
  if (!transaction || transaction.deleted_at) return;
  const shouldSelect = selected ?? !state.selectedListTransactionIds.has(transactionId);
  if (shouldSelect) {
    if (state.selectedListTransactionIds.size >= MAX_BULK_TRANSACTIONS) { toast(`You can edit up to ${MAX_BULK_TRANSACTIONS} transactions at once.`, 'error'); return; }
    state.selectedListTransactionIds.add(transactionId);
    state.listSelectionVersions.set(transactionId, transaction.version);
  } else {
    state.selectedListTransactionIds.delete(transactionId);
    state.listSelectionVersions.delete(transactionId);
  }
  state.listSelectionAnchorId = transactionId;
  syncTransactionListSelection();
}

function selectTransactionListRange(transactionId, additive = false) {
  const ids = state.transactions.filter(transaction => !transaction.deleted_at).map(transaction => transaction.id);
  const targetIndex = ids.indexOf(transactionId);
  const anchorIndex = ids.indexOf(state.listSelectionAnchorId);
  if (targetIndex < 0) return;
  if (anchorIndex < 0) {
    if (!additive) { state.selectedListTransactionIds.clear(); state.listSelectionVersions.clear(); }
    state.selectedListTransactionIds.add(transactionId);
    state.listSelectionVersions.set(transactionId, state.transactions.find(transaction => transaction.id === transactionId).version);
    state.listSelectionAnchorId = transactionId;
    syncTransactionListSelection();
    return;
  }
  if (!additive) { state.selectedListTransactionIds.clear(); state.listSelectionVersions.clear(); }
  const range = ids.slice(Math.min(anchorIndex, targetIndex), Math.max(anchorIndex, targetIndex) + 1);
  let limitReached = false;
  range.forEach(id => {
    if (!state.selectedListTransactionIds.has(id) && state.selectedListTransactionIds.size >= MAX_BULK_TRANSACTIONS) { limitReached = true; return; }
    const transaction = state.transactions.find(item => item.id === id);
    state.selectedListTransactionIds.add(id); state.listSelectionVersions.set(id, transaction.version);
  });
  if (limitReached) toast(`Only the first ${MAX_BULK_TRANSACTIONS} transactions were selected.`, 'error');
  syncTransactionListSelection();
}

function selectAllVisibleTransactions() {
  const visible = state.transactions.filter(transaction => !transaction.deleted_at);
  state.selectedListTransactionIds.clear();
  state.listSelectionVersions.clear();
  visible.slice(0, MAX_BULK_TRANSACTIONS).forEach(transaction => {
    state.selectedListTransactionIds.add(transaction.id);
    state.listSelectionVersions.set(transaction.id, transaction.version);
  });
  if (visible.length > MAX_BULK_TRANSACTIONS) toast(`Only the first ${MAX_BULK_TRANSACTIONS} visible transactions were selected.`, 'error');
  state.listSelectionAnchorId = state.transactions.find(transaction => !transaction.deleted_at)?.id || null;
  syncTransactionListSelection();
}

function transactionCard(transaction) {
  const inflow = toUnits(transaction.amount) > 0n;
  const label = transactionLabel(transaction);
  const symbol = label.trim().slice(0, 1).toUpperCase() || '?';
  const description = `${label}, ${money(transaction.amount)}, ${formatDate(transaction.effective_date)}`;
  const badges = [
    transaction.pending ? '<span class="pending-badge">Pending</span>' : '',
    transaction.needs_review ? '<span class="review-badge">Review</span>' : '',
    transaction.excluded ? '<span class="excluded-badge">Excluded</span>' : '',
  ].join('');
  return `<article class="transaction-card ${transaction.deleted_at ? 'is-deleted' : ''}" data-transaction-id="${transaction.id}">
    ${transaction.deleted_at ? '' : `<label class="transaction-list-select-control" title="Select ${escapeHtml(label)}"><input class="transaction-list-select" type="checkbox" aria-label="Select ${escapeHtml(description)}"><span class="transaction-list-select-mark" aria-hidden="true"></span></label>`}
    <button class="transaction-card-content" type="button" aria-label="Open ${escapeHtml(description)}">
      <div class="transaction-symbol ${inflow ? 'inflow' : ''}">${escapeHtml(symbol)}</div>
      <div class="transaction-copy"><strong>${escapeHtml(label)} ${badges}</strong><small>${escapeHtml(formatDate(transaction.effective_date))} · ${escapeHtml(transaction.account_name)} · ${escapeHtml(transactionCategoryText(transaction))}</small></div>
      <div class="transaction-amount ${inflow ? 'inflow' : ''}">${money(transaction.amount, { plus: true })}<small>${transaction.source_kind === 'manual' ? 'Manual' : 'Synced'}</small></div>
    </button>
  </article>`;
}

async function renderTransactions() {
  const params = new URLSearchParams({ month: state.month, status: state.transactionStatus, limit: '300' });
  if (state.transactionSearch) params.set('search', state.transactionSearch);
  if (state.transactionCategory) params.set('category_id', state.transactionCategory);
  const result = await api(`/api/transactions?${params}`);
  state.transactions = result.transactions;
  reconcileTransactionListSelection();
  const category = state.transactionCategory ? categoryById(state.transactionCategory) : null;
  const title = category ? category.name : 'Transactions';
  const filters = [
    ['active', 'All'], ['unassigned', 'Unassigned'], ['assigned', 'Assigned'], ['review', 'Needs review'], ['pending', 'Pending'], ['excluded', 'Excluded'], ['trash', 'Trash'],
  ];
  $('#app-view').innerHTML = `
    <header class="view-header"><div><h1>${escapeHtml(title)}</h1><p>${category ? `${escapeHtml(category.section.name)} · ${monthLabel(state.month)} · Select from the left edge to edit a group.` : 'Search, review, or recategorize entries. Select from the left edge to edit a group.'}</p></div><div class="view-actions"><button class="button button--primary add-manual" type="button">+ Add transaction</button></div></header>
    <div class="toolbar">
      <label class="search-field"><span data-icon="search"></span><input id="transaction-search" type="search" placeholder="Search payee, source text, or note" value="${escapeHtml(state.transactionSearch)}"></label>
      <div class="filter-row">${filters.map(([value, label]) => `<button class="filter-chip ${state.transactionStatus === value ? 'active' : ''}" type="button" data-filter="${value}">${label}</button>`).join('')}${category ? '<button class="filter-chip clear-category" type="button">Clear category filter ×</button>' : ''}</div>
    </div>
    <div class="transaction-selection-bar hidden" role="region" aria-label="Selected transaction actions">
      <strong id="transaction-selection-count" role="status" aria-live="polite" aria-atomic="true">0 selected</strong>
      <div class="button-row"><button class="button button--ghost select-all-transactions" type="button">Select all</button><button class="button button--ghost clear-transaction-selection" type="button">Clear</button><button class="button button--primary edit-selected-transactions" type="button">Edit selected…</button></div>
    </div>
    <div class="transaction-list">${state.transactions.map(transactionCard).join('') || '<div class="empty-state"><strong>No matching transactions</strong>Try another filter or add a manual cash transaction.</div>'}</div>`;
  hydrateIcons($('#app-view'));
  $('.add-manual', $('#app-view')).addEventListener('click', openManualTransaction);
  $$('.filter-chip[data-filter]', $('#app-view')).forEach(button => button.addEventListener('click', async () => {
    clearTransactionListSelection();
    state.transactionStatus = button.dataset.filter;
    await renderTransactions();
  }));
  $('.clear-category', $('#app-view'))?.addEventListener('click', async () => { clearTransactionListSelection(); state.transactionCategory = null; await renderTransactions(); });
  $('.select-all-transactions', $('#app-view')).addEventListener('click', selectAllVisibleTransactions);
  $('.clear-transaction-selection', $('#app-view')).addEventListener('click', clearTransactionListSelection);
  $('.edit-selected-transactions', $('#app-view')).addEventListener('click', openBulkTransactionEditor);
  let searchTimer;
  $('#transaction-search', $('#app-view')).addEventListener('input', event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => { clearTransactionListSelection(); state.transactionSearch = event.target.value.trim(); await renderTransactions(); }, 260);
  });
  $$('.transaction-list-select-control', $('#app-view')).forEach(control => control.addEventListener('click', event => {
    event.preventDefault(); event.stopPropagation();
    const transactionId = control.closest('.transaction-card').dataset.transactionId;
    if (event.shiftKey) selectTransactionListRange(transactionId, event.ctrlKey || event.metaKey);
    else toggleTransactionListSelection(transactionId);
  }));
  $$('.transaction-card-content', $('#app-view')).forEach(content => content.addEventListener('click', event => {
    const transactionId = content.closest('.transaction-card').dataset.transactionId;
    if (event.shiftKey) { event.preventDefault(); selectTransactionListRange(transactionId, event.ctrlKey || event.metaKey); }
    else if (event.ctrlKey || event.metaKey) { event.preventDefault(); toggleTransactionListSelection(transactionId); }
    else openTransactionEditor(transactionId);
  }));
  syncTransactionListSelection();
}

function openBulkTransactionEditor() {
  const transactions = selectedListTransactions();
  if (!transactions.length) return;
  openModal({
    title: `Edit ${transactions.length} transaction${transactions.length === 1 ? '' : 's'}`,
    body: `<form id="bulk-transaction-form" class="form-grid">
      <label class="full">Category<select id="bulk-transaction-category"><option value="__keep">Keep each current category</option><option value="__unassigned">Make unassigned</option>${categoryOptions()}</select></label>
      <label>Review status<select id="bulk-transaction-review"><option value="keep">No change</option><option value="true">Needs review</option><option value="false">Reviewed</option></select></label>
      <label>Budget status<select id="bulk-transaction-excluded"><option value="keep">No change</option><option value="false">Include in budget</option><option value="true">Exclude from budget</option></select></label>
      <p class="muted full">Choosing a category replaces an existing single category on every selected transaction. Split transactions must be recategorized individually. Fields set to “No change” keep their individual values.</p>
    </form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary apply-bulk-transactions" type="button">Apply changes</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('select', root).forEach(select => select.addEventListener('change', () => { state.formDirty = true; }));
      const save = async () => {
        const body = { transactions: transactions.map(transaction => ({ id: transaction.id, version: transaction.version })) };
        const category = $('#bulk-transaction-category', root).value;
        const review = $('#bulk-transaction-review', root).value;
        const excluded = $('#bulk-transaction-excluded', root).value;
        if (category !== '__keep') body.category_id = category === '__unassigned' ? null : category;
        if (review !== 'keep') body.needs_review = review === 'true';
        if (excluded !== 'keep') body.excluded = excluded === 'true';
        if (Object.keys(body).length === 1) { toast('Choose at least one change.', 'error'); return; }
        const button = $('.apply-bulk-transactions', root); setButtonBusy(button, true, 'Applying…');
        state.bulkTransactionInFlight = true; syncTransactionListSelection();
        try {
          const result = await api('/api/transactions/batch', { method: 'PATCH', body });
          state.formDirty = false; closeModal(); clearTransactionListSelection();
          toast(`${result.transactions.length} transaction${result.transactions.length === 1 ? '' : 's'} updated`);
          await refreshCurrentView();
        } catch (error) {
          if (error instanceof ConflictError) {
            state.formDirty = false; closeModal(); clearTransactionListSelection();
            await refreshCurrentView();
            toast('Some selected transactions changed elsewhere. Review them and try again.', 'error');
          } else toast(error.message, 'error');
        } finally {
          state.bulkTransactionInFlight = false; setButtonBusy(button, false); syncTransactionListSelection();
        }
      };
      $('.apply-bulk-transactions', root).addEventListener('click', save);
      $('#bulk-transaction-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function signedInputForTransaction(transaction, raw) {
  const absolute = raw.trim();
  if (!absolute) return '0';
  const units = toUnits(absolute);
  const transactionUnits = toUnits(transaction.amount);
  return unitsToString(transactionUnits < 0n ? -(units < 0n ? -units : units) : (units < 0n ? -units : units));
}

function absoluteAllocationInput(value) {
  let units = toUnits(value);
  if (units < 0n) units = -units;
  return unitsToString(units);
}

function allocationCategoryOptions(selected = '', split = false) {
  return `<option value="" ${selected ? '' : 'selected'}>${split ? 'Choose category' : 'Unassigned'}</option>${categoryOptions(selected)}`;
}

function allocationEditorRow(transaction, allocation, split, index = 0) {
  const categoryId = String(allocation?.category_id || '');
  const rawAmount = String(allocation?.amount ?? '');
  const amount = rawAmount.trim() ? absoluteAllocationInput(rawAmount) : '';
  const splitNumber = index + 1;
  return `<div class="split-row ${split ? '' : 'single-allocation-row'}">
    <select class="allocation-category" aria-label="${split ? `Category for split ${splitNumber}` : 'Category'}">${allocationCategoryOptions(categoryId, split)}</select>
    ${split ? `<input class="allocation-amount" inputmode="decimal" aria-label="Amount for split ${splitNumber}" placeholder="Amount" value="${escapeHtml(amount)}">
    <button class="icon-button remove-allocation" type="button" aria-label="Remove split ${splitNumber}">×</button>` : ''}
  </div>`;
}

function allocationEditorRows(transaction, allocations = transaction.allocations || []) {
  const drafts = allocations.length
    ? allocations
    : [{ category_id: '', amount: transaction.amount }];
  const split = drafts.length > 1;
  return drafts.map((allocation, index) => allocationEditorRow(transaction, allocation, split, index)).join('');
}

function allocationDrafts(root, transaction) {
  return $$('.split-row', $('.split-table', root)).map(row => ({
    category_id: $('.allocation-category', row).value,
    amount: $('.allocation-amount', row)?.value ?? absoluteAllocationInput(transaction.amount),
  }));
}

function allocationTotals(root, transaction) {
  const rows = $$('.split-row', root);
  let total = 0n;
  let invalid = false;
  rows.forEach(row => {
    const input = $('.allocation-amount', row);
    if (!input?.value.trim()) { invalid = true; return; }
    try { total += toUnits(signedInputForTransaction(transaction, input.value)); }
    catch { invalid = true; }
  });
  const target = toUnits(transaction.amount);
  const remainder = target - total;
  const node = $('.split-summary', root);
  if (node) node.innerHTML = invalid
    ? '<span>Check an amount</span><span class="warning">Incomplete</span>'
    : `<span>Allocated ${money(unitsToString(total))}</span><span class="${remainder === 0n ? 'positive' : 'warning'}">${remainder === 0n ? 'Balanced' : `${money(unitsToString(remainder))} remaining`}</span>`;
  return { total, target, remainder, invalid };
}

function renderAllocationRows(root, transaction, drafts, { focusIndex = null, revealFocus = false } = {}) {
  const normalized = drafts.length
    ? drafts
    : [{ category_id: '', amount: transaction.amount }];
  const split = normalized.length > 1;
  const editor = $('.allocation-editor', root);
  const table = $('.split-table', root);
  editor.dataset.allocationMode = split ? 'split' : 'single';
  $('.allocation-title', editor).textContent = split ? 'Split categories' : 'Category';
  table.innerHTML = normalized.map((allocation, index) => allocationEditorRow(transaction, allocation, split, index)).join('');
  $('.split-summary', editor).classList.toggle('hidden', !split);
  $('.assign-remainder', editor).classList.toggle('hidden', !split);
  $$('input,select', table).forEach(control => {
    const markChanged = () => {
      control.removeAttribute('aria-invalid');
      state.formDirty = true;
      if (split) allocationTotals(root, transaction);
    };
    control.addEventListener('input', markChanged);
    control.addEventListener('change', markChanged);
  });
  $$('.remove-allocation', table).forEach((button, index) => button.addEventListener('click', () => {
    const next = allocationDrafts(root, transaction);
    next.splice(index, 1);
    state.formDirty = true;
    renderAllocationRows(root, transaction, next, { focusIndex: Math.min(index, next.length - 1) });
  }));
  if (split) allocationTotals(root, transaction);
  if (focusIndex !== null) {
    const row = $$('.split-row', table)[Math.max(0, focusIndex)];
    const control = $('.allocation-category', row || table);
    control?.focus({ preventScroll: !revealFocus });
    if (revealFocus) control?.scrollIntoView({ block: 'nearest' });
  }
}

function rejectAllocation(control, message) {
  control?.setAttribute('aria-invalid', 'true');
  control?.focus({ preventScroll: true });
  control?.scrollIntoView({ block: 'nearest' });
  throw new Error(message);
}

function allocationPayload(root, transaction) {
  const editor = $('.allocation-editor', root);
  const rows = $$('.split-row', editor);
  $$('[aria-invalid="true"]', editor).forEach(control => control.removeAttribute('aria-invalid'));
  if (editor.dataset.allocationMode !== 'split') {
    const categoryId = $('.allocation-category', rows[0])?.value || '';
    return categoryId ? [{ category_id: categoryId, amount: String(transaction.amount), memo: '' }] : [];
  }
  const categoryControls = rows.map(row => $('.allocation-category', row));
  const missingCategory = categoryControls.find(control => !control.value);
  if (missingCategory) rejectAllocation(missingCategory, 'Choose a category for every split.');
  const seenCategories = new Set();
  const duplicateCategory = categoryControls.find(control => {
    if (seenCategories.has(control.value)) return true;
    seenCategories.add(control.value);
    return false;
  });
  if (duplicateCategory) rejectAllocation(duplicateCategory, 'Choose each category only once.');
  const invalidAmount = rows.map(row => $('.allocation-amount', row)).find(control => {
    if (!control.value.trim()) return true;
    try { signedInputForTransaction(transaction, control.value); return false; }
    catch { return true; }
  });
  if (invalidAmount) rejectAllocation(invalidAmount, 'Enter a valid amount for every split.');
  const totals = allocationTotals(root, transaction);
  if (totals.remainder !== 0n) rejectAllocation($('.allocation-amount', rows.at(-1)), 'Split amounts must add up exactly.');
  return rows.map(row => ({
    category_id: $('.allocation-category', row).value,
    amount: signedInputForTransaction(transaction, $('.allocation-amount', row).value),
    memo: '',
  }));
}

function bindAllocationRows(root, transaction) {
  const initial = transaction.allocations?.length
    ? transaction.allocations.map(allocation => ({ category_id: allocation.category_id, amount: allocation.amount }))
    : [{ category_id: '', amount: transaction.amount }];
  renderAllocationRows(root, transaction, initial);
  $('.add-allocation', root).addEventListener('click', () => {
    const drafts = allocationDrafts(root, transaction);
    if (drafts.length >= 100) { toast('A transaction can have at most 100 splits.', 'error'); return; }
    if (drafts.length === 1) drafts[0].amount = absoluteAllocationInput(transaction.amount);
    drafts.push({ category_id: '', amount: '' });
    state.formDirty = true;
    renderAllocationRows(root, transaction, drafts, { focusIndex: drafts.length - 1, revealFocus: true });
  });
  $('.assign-remainder', root).addEventListener('click', () => {
    const rows = $$('.split-row', root);
    const targetInput = $('.allocation-amount', rows.at(-1));
    let earlierTotal = 0n;
    for (const row of rows.slice(0, -1)) {
      const input = $('.allocation-amount', row);
      try {
        if (!input.value.trim()) throw new Error();
        earlierTotal += toUnits(signedInputForTransaction(transaction, input.value));
      } catch {
        input.setAttribute('aria-invalid', 'true');
        input.focus({ preventScroll: true });
        input.scrollIntoView({ block: 'nearest' });
        toast('Enter a valid amount before filling the remainder.', 'error');
        return;
      }
    }
    const target = toUnits(transaction.amount);
    const remainder = target - earlierTotal;
    if (remainder !== 0n && (target === 0n || (remainder < 0n) !== (target < 0n))) {
      targetInput.setAttribute('aria-invalid', 'true');
      targetInput.focus({ preventScroll: true });
      targetInput.scrollIntoView({ block: 'nearest' });
      toast('Earlier splits already exceed the transaction total.', 'error');
      return;
    }
    targetInput.removeAttribute('aria-invalid');
    targetInput.value = unitsToString(remainder < 0n ? -remainder : remainder);
    allocationTotals(root, transaction); state.formDirty = true;
  });
}

async function openTransactionEditor(transactionId, {
  keepTrayOpen = false,
  returnFocus = null,
  shouldOpen = null,
} = {}) {
  const loadSequence = ++state.transactionEditorLoadSequence;
  let transaction;
  try {
    transaction = (await api(`/api/transactions/${transactionId}`)).transaction;
  } catch (error) {
    if (loadSequence === state.transactionEditorLoadSequence && (!shouldOpen || shouldOpen())) toast(error.message, 'error');
    return;
  }
  if (loadSequence !== state.transactionEditorLoadSequence || (shouldOpen && !shouldOpen())) return;
  if (!keepTrayOpen) closeTray();
  const inflow = toUnits(transaction.amount) > 0n;
  const deleted = !!transaction.deleted_at;
  openModal({
    title: deleted ? 'Transaction in Trash' : 'Transaction details',
    className: 'modal--wide',
    returnFocus,
    body: `<div class="transaction-hero">
      <div><h3>${escapeHtml(transactionLabel(transaction))}</h3><p>${escapeHtml(transaction.account_name)} · ${escapeHtml(formatDate(transaction.effective_date))}${transaction.pending ? ' · Pending' : ''}</p></div>
      <div class="hero-amount ${inflow ? 'positive' : ''}">${money(transaction.amount, { plus: true })}</div>
    </div>
    ${deleted ? `<div class="delete-warning">Deleted ${escapeHtml(relativeTime(transaction.deleted_at))}. It is excluded from budgets and will not be recreated by synchronization.</div>` : `<form id="transaction-form" class="form-grid" data-transaction-id="${escapeHtml(transaction.id)}">
      <label>Payee<input id="transaction-payee" value="${escapeHtml(transaction.payee)}" required maxlength="500"></label>
      <label>Budget date<input id="transaction-date" type="date" value="${escapeHtml(transaction.effective_date)}" required></label>
      <label class="full">Note<textarea id="transaction-note" maxlength="10000">${escapeHtml(transaction.note || '')}</textarea></label>
      <label class="full"><span><input id="transaction-review" type="checkbox" style="width:auto;min-height:auto" ${transaction.needs_review ? 'checked' : ''}> Keep in Needs Review</span></label>
      <label class="full"><span><input id="transaction-excluded" type="checkbox" style="width:auto;min-height:auto" ${transaction.excluded ? 'checked' : ''}> Exclude from budget totals</span></label>
    </form>
    <div class="form-section allocation-editor" data-allocation-mode="${transaction.allocations?.length > 1 ? 'split' : 'single'}">
      <div class="allocation-header"><strong class="allocation-title">${transaction.allocations?.length > 1 ? 'Split categories' : 'Category'}</strong><button class="button button--soft add-allocation" type="button">+ Add split</button></div>
      <div class="split-table">${allocationEditorRows(transaction)}</div>
      <div class="split-summary ${transaction.allocations?.length > 1 ? '' : 'hidden'}" role="status" aria-live="polite"></div>
      <button class="button button--ghost assign-remainder ${transaction.allocations?.length > 1 ? '' : 'hidden'}" type="button">Fill remainder</button>
    </div>`}
    <div class="form-section"><details><summary>Imported source details</summary><p class="muted">${escapeHtml(transaction.imported_description || 'Manual transaction')}</p><p class="muted">Source: ${escapeHtml(transaction.source_kind)} · Revision ${transaction.version}</p></details></div>
    ${!deleted ? '<div class="form-section button-row"><button class="button button--soft create-rule-from-transaction" type="button">Create rule from this transaction</button><button class="button button--danger delete-transaction" type="button">Delete transaction</button></div>' : ''}`,
    footer: deleted
      ? '<button class="button modal-cancel" type="button">Close</button><button class="button button--primary restore-transaction" type="button">Restore transaction</button>'
      : '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary save-transaction" type="button">Save changes</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      if (deleted) {
        $('.restore-transaction', root).addEventListener('click', async event => {
          setButtonBusy(event.currentTarget, true);
          try {
            await withConflict(body => api(`/api/transactions/${transaction.id}/restore`, { method: 'POST', body }), { version: transaction.version }, 'restore');
            closeModal(); toast('Transaction restored'); await refreshCurrentView();
          } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(event.currentTarget, false); }
        });
        return;
      }
      bindAllocationRows(root, transaction);
      $$('#transaction-form input, #transaction-form textarea, #transaction-form select', root).forEach(control => control.addEventListener('input', () => { state.formDirty = true; }));
      $('.create-rule-from-transaction', root).addEventListener('click', () => { closeModal(); openRuleEditor(null, transaction); });
      $('.delete-transaction', root).addEventListener('click', async () => {
        const expected = unitsToString(toUnits(transaction.amount) < 0n ? -toUnits(transaction.amount) : toUnits(transaction.amount));
        const accepted = await confirmDialog({
          title: 'Delete this transaction?',
          message: 'It will leave all budget totals and move to Trash. A synced transaction keeps a minimal tombstone so the next import cannot bring it back.',
          confirmText: 'Delete transaction', danger: true,
          inputLabel: `Type the amount ${expected} to confirm`, expected,
        });
        if (!accepted) return;
        try {
          await withConflict(body => api(`/api/transactions/${transaction.id}`, { method: 'DELETE', body }), {
            version: transaction.version, confirm: true, confirm_amount: transaction.amount,
          }, 'deletion');
          closeModal(); toast('Transaction moved to Trash'); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); }
      });
      const save = async () => {
        let allocations;
        try { allocations = allocationPayload(root, transaction); }
        catch (error) { toast(error.message, 'error'); return; }
        const button = $('.save-transaction', root); setButtonBusy(button, true, 'Saving…');
        try {
          const body = {
            version: transaction.version,
            effective_date: $('#transaction-date', root).value,
            allocations,
            note: $('#transaction-note', root).value,
            needs_review: $('#transaction-review', root).checked,
            excluded: $('#transaction-excluded', root).checked,
          };
          const editedPayee = $('#transaction-payee', root).value.trim();
          if (editedPayee !== transaction.payee) body.payee = editedPayee;
          const updated = await withConflict(
            conflictBody => api(`/api/transactions/${transaction.id}`, { method: 'PATCH', body: conflictBody }),
            body,
            'transaction',
          );
          if (!updated) return;
          state.formDirty = false; closeModal(); toast('Transaction saved'); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.save-transaction', root).addEventListener('click', save);
      $('#transaction-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function openManualTransaction() {
  const defaultAccount = state.budget?.accounts?.find(account => account.source_type === 'manual') || state.budget?.accounts?.[0];
  if (!defaultAccount) { toast('Create or sync an account before adding a transaction.', 'error'); return; }
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  const defaultDate = localDate.slice(0, 7) === state.month ? localDate : `${state.month}-01`;
  openModal({
    title: 'Add a cash or manual transaction',
    body: `<form id="manual-form" class="form-grid">
      <label>Type<select id="manual-direction"><option value="outflow">Expense</option><option value="inflow">Income</option></select></label>
      <label>Amount<input id="manual-amount" inputmode="decimal" placeholder="0.00" required></label>
      <label>Payee or source<input id="manual-payee" maxlength="500" required></label>
      <label>Date<input id="manual-date" type="date" value="${defaultDate}" required></label>
      <label>Account<select id="manual-account">${state.budget.accounts.map(account => `<option value="${account.id}" ${account.id === defaultAccount.id ? 'selected' : ''}>${escapeHtml(account.name)}</option>`).join('')}</select></label>
      <label>Category<select id="manual-category"><option value="">Leave unassigned</option>${categoryOptions()}</select></label>
      <label class="full">Note<textarea id="manual-note" maxlength="10000"></textarea></label>
    </form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary create-manual" type="submit" form="manual-form">Add transaction</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      const save = async () => {
        const button = $('.create-manual', root); setButtonBusy(button, true, 'Adding…');
        try {
          let amount = toUnits($('#manual-amount', root).value);
          if (amount < 0n) amount = -amount;
          if (amount === 0n) throw new Error('Enter a non-zero amount.');
          if ($('#manual-direction', root).value === 'outflow') amount = -amount;
          const categoryId = $('#manual-category', root).value;
          const body = {
            account_id: $('#manual-account', root).value,
            effective_date: $('#manual-date', root).value,
            amount: unitsToString(amount),
            payee: $('#manual-payee', root).value.trim(),
            note: $('#manual-note', root).value,
            allocations: categoryId ? [{ category_id: categoryId, amount: unitsToString(amount), memo: '' }] : [],
          };
          await api('/api/transactions', { method: 'POST', body });
          closeModal(); toast('Manual transaction added'); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('#manual-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

const RULE_FIELDS = {
  original_description: 'Imported description', payee: 'Payee', account_id: 'Account', amount: 'Signed amount',
  outflow: 'Outflow amount', inflow: 'Income amount', date: 'Date', day_of_week: 'Day of week',
  day_of_month: 'Day of month', month: 'Month number', pending: 'Pending', cleared: 'Cleared',
  source: 'Source', unassigned: 'Unassigned', note: 'Note', tags: 'Tags', currency: 'Currency', needs_review: 'Needs review',
};
const RULE_PHASES = [
  { value: 'cleanup', label: '1. Clean up', description: 'Normalize names and details first.' },
  { value: 'categorize', label: '2. Categorize', description: 'Assign categories and splits.' },
  { value: 'finish', label: '3. Finish and flag', description: 'Add notes, tags, and review flags.' },
];
const RULE_OPERATORS = {
  is: 'is', is_not: 'is not', contains: 'contains', not_contains: 'does not contain', starts_with: 'starts with',
  ends_with: 'ends with', regex: 'matches pattern', one_of: 'is one of', not_one_of: 'is not one of', between: 'is between',
  gt: 'is above', gte: 'is at least', lt: 'is below', lte: 'is at most', before: 'is before', after: 'is after',
  has_tag: 'has tag', lacks_tag: 'lacks tag', is_true: 'is true', is_false: 'is false',
};
const FIELD_OPERATORS = {
  original_description: ['contains','not_contains','is','is_not','starts_with','ends_with','regex'],
  payee: ['contains','not_contains','is','is_not','starts_with','ends_with','one_of'],
  account_id: ['is','is_not','one_of','not_one_of'],
  amount: ['is','is_not','gt','gte','lt','lte','between'],
  outflow: ['is','gt','gte','lt','lte','between'], inflow: ['is','gt','gte','lt','lte','between'],
  date: ['is','before','after','between'], day_of_week: ['is','is_not','one_of'], day_of_month: ['is','gt','gte','lt','lte','between'],
  month: ['is','one_of','between'], pending: ['is_true','is_false'], cleared: ['is_true','is_false'],
  source: ['is','is_not','one_of'], unassigned: ['is_true','is_false'], note: ['contains','not_contains','is'],
  tags: ['has_tag','lacks_tag'], currency: ['is','is_not'], needs_review: ['is_true','is_false'],
};
const ACTION_LABELS = {
  assign_category: 'Assign category', set_payee: 'Rename payee', split_fixed: 'Split fixed amounts', split_percent: 'Split by percentages',
  add_note: 'Add note', add_tag: 'Add tag', mark_review: 'Mark for review', exclude: 'Exclude from budget',
  suggest_transfer: 'Suggest a transfer', alert: 'Send an alert',
};

function ruleConditionSummary(condition) {
  if (condition.children) {
    const joiner = condition.combinator === 'any' ? ' OR ' : condition.combinator === 'none' ? ' NOR ' : ' AND ';
    return condition.children.map(ruleConditionSummary).join(joiner);
  }
  const rawValues = Array.isArray(condition.value) ? condition.value : [condition.value];
  const displayValues = condition.field === 'account_id'
    ? rawValues.map(value => accountById(String(value ?? ''))?.name || 'Unavailable account')
    : rawValues;
  const value = Array.isArray(condition.value) ? displayValues.join(' and ') : displayValues[0];
  return `${RULE_FIELDS[condition.field] || condition.field} ${RULE_OPERATORS[condition.operator] || condition.operator}${['is_true','is_false'].includes(condition.operator) ? '' : ` “${value ?? ''}”`}`;
}

function ruleActionSummary(action) {
  if (action.type === 'assign_category') return `assign ${categoryById(action.category_id)?.name || 'a category'}`;
  if (action.type === 'set_payee') return `rename to “${action.value || ''}”`;
  if (action.type === 'split_fixed') return `split across ${(action.splits || []).length + (action.remainder_category_id ? 1 : 0)} categories`;
  if (action.type === 'split_percent') return `percentage split across ${(action.splits || []).length + (action.remainder_category_id ? 1 : 0)} categories`;
  if (action.type === 'add_note') return 'add a note';
  if (action.type === 'add_tag') return `add tag “${action.value || ''}”`;
  if (action.type === 'mark_review') return 'mark for review';
  if (action.type === 'exclude') return 'exclude from budget';
  if (action.type === 'suggest_transfer') return 'suggest a transfer';
  if (action.type === 'alert') return 'send an alert';
  return action.type;
}

function ruleCard(rule, position) {
  return `<article class="rule-card" data-rule-id="${rule.id}" data-rule-phase="${escapeHtml(rule.phase)}" data-priority="${rule.priority}" data-version="${rule.version}">
    <div class="rule-card-header"><div><h3>${escapeHtml(rule.name)}</h3><div class="rule-meta"><span class="pill">Order ${position + 1}</span>${rule.enabled ? '<span class="pill positive">On</span>' : '<span class="pill">Off</span>'}</div></div><div class="rule-card-actions"><button class="reorder-handle rule-reorder-handle" type="button" aria-label="Reorder ${escapeHtml(rule.name)} within ${escapeHtml(rule.phase)}" aria-describedby="rule-reorder-help" title="Drag to reorder within this phase"><span aria-hidden="true">⠿</span></button><button class="icon-button edit-rule" type="button" aria-label="Edit ${escapeHtml(rule.name)}"><span data-icon="pencil"></span></button></div></div>
    <div class="rule-sentence"><b>When:</b> ${escapeHtml(ruleConditionSummary(rule.conditions))}</div>
    <div class="rule-sentence"><b>Then:</b> ${escapeHtml(rule.actions.map(ruleActionSummary).join(', '))}</div>
  </article>`;
}

function rulePhaseLane(phase) {
  const rules = state.rules.filter(rule => rule.phase === phase.value);
  return `<section class="rule-phase" data-rule-phase="${phase.value}">
    <header class="rule-phase-header"><div><h2>${escapeHtml(phase.label)}</h2><p>${escapeHtml(phase.description)}</p></div><span class="pill">${rules.length} rule${rules.length === 1 ? '' : 's'}</span></header>
    <div class="rule-list" data-rule-phase="${phase.value}">${rules.map(ruleCard).join('') || '<div class="rule-lane-empty">No rules in this phase.</div>'}</div>
  </section>`;
}

async function renderRules() {
  const result = await api('/api/rules');
  state.rules = result.rules;
  const reorderFocus = currentReorderFocus();
  $('#app-view').innerHTML = `<header class="view-header"><div><h1>Rules</h1><p>Automatic cleanup for new imports; manual runs only process unsorted transactions in the selected month.</p></div><div class="view-actions"><button class="button button--soft run-rules" type="button">Run rules</button><button class="button button--primary add-rule" type="button">+ New rule</button></div></header>
    <p id="rule-reorder-help" class="sr-only">Drag this handle to change the order within its phase. With a keyboard, use the Up and Down arrow keys or the rule editor's Order within phase field.</p>
    <div id="reorder-status" class="sr-only" aria-live="polite" aria-atomic="true"></div>
    ${state.rules.length ? `<div class="rule-phase-list">${RULE_PHASES.map(rulePhaseLane).join('')}</div>` : '<div class="empty-state"><strong>No rules yet</strong>Create a rule from a transaction or build one here. Rules run automatically during every import.</div>'}`;
  hydrateIcons($('#app-view'));
  $('.run-rules', $('#app-view')).addEventListener('click', async event => {
    const button = event.currentTarget;
    const runMonth = state.month;
    setButtonBusy(button, true, 'Running…');
    try {
      const run = await api('/api/rules/run', { method: 'POST', body: { month: runMonth } });
      const scanned = run.transactions_scanned || 0;
      const changed = run.transactions_changed || 0;
      const sorted = run.transactions_sorted || 0;
      const stillUnsorted = run.transactions_still_unsorted || 0;
      if (sorted && stillUnsorted) toast(`Sorted ${sorted} transaction${sorted === 1 ? '' : 's'}; ${stillUnsorted} matching transaction${stillUnsorted === 1 ? '' : 's'} remain${stillUnsorted === 1 ? 's' : ''} in To sort`, 'error');
      else if (sorted) toast(`Sorted ${sorted} of ${scanned} unsorted transaction${scanned === 1 ? '' : 's'} in ${monthLabel(runMonth)}`);
      else if (stillUnsorted) toast(`${stillUnsorted} matching transaction${stillUnsorted === 1 ? '' : 's'} could not be sorted and remain${stillUnsorted === 1 ? 's' : ''} in To sort`, 'error');
      else if (changed) toast(`Updated ${changed} unsorted transaction${changed === 1 ? '' : 's'} in ${monthLabel(runMonth)}`);
      else toast(`No matching rule changes in ${monthLabel(runMonth)}`);
      await refreshCurrentView();
    } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
  });
  $('.add-rule', $('#app-view')).addEventListener('click', () => openRuleEditor());
  $$('.edit-rule', $('#app-view')).forEach(button => button.addEventListener('click', () => openRuleEditor(state.rules.find(rule => rule.id === button.closest('.rule-card').dataset.ruleId))));
  restoreReorderFocus(reorderFocus);
}

function simpleConditionsFromRule(rule, transaction) {
  if (rule?.conditions?.children) return rule.conditions.children.map(item => ({ ...item }));
  if (rule?.conditions?.field) return [{ ...rule.conditions }];
  if (transaction) {
    const sourceText = transaction.imported_description || transaction.payee;
    return [
      { field: 'original_description', operator: 'contains', value: sourceText },
      { field: 'account_id', operator: 'is', value: transaction.account_id },
    ];
  }
  return [{ field: 'original_description', operator: 'contains', value: '' }];
}

function defaultRuleActions(rule, transaction) {
  if (rule?.actions?.length) return structuredClone(rule.actions);
  if (transaction?.allocations?.length === 1) return [{ type: 'assign_category', category_id: transaction.allocations[0].category_id }];
  return [{ type: 'assign_category', category_id: state.budget.sections.flatMap(section => section.categories)[0]?.id || '' }];
}

function conditionValueMarkup(condition) {
  const field = condition.field;
  const operator = condition.operator;
  if (['is_true','is_false'].includes(operator)) return '<span class="condition-value muted">No additional value</span>';
  if (field === 'account_id') {
    const accounts = accountCatalog();
    const optionMarkup = selected => accounts.map(account => {
      const qualifier = account.is_duplicate ? ' — duplicate' : account.is_active ? '' : ' — inactive';
      return `<option value="${account.id}" ${selected.includes(account.id) ? 'selected' : ''}>${escapeHtml(account.name + qualifier)}</option>`;
    }).join('');
    if (['one_of','not_one_of'].includes(operator)) {
      const selected = Array.isArray(condition.value) ? condition.value : [condition.value];
      return `<label class="condition-value">Accounts<select class="condition-value-input" multiple size="${Math.max(1, Math.min(4, accounts.length))}">${optionMarkup(selected)}</select></label>`;
    }
    return `<label class="condition-value">Account<select class="condition-value-input">${optionMarkup([condition.value])}</select></label>`;
  }
  const isDate = field === 'date';
  const inputType = isDate ? 'date' : 'text';
  if (operator === 'between') {
    const values = Array.isArray(condition.value) ? condition.value : ['', ''];
    return `<div class="condition-value form-grid"><label>From<input class="condition-low" type="${inputType}" inputmode="${['amount','outflow','inflow','day_of_month','month'].includes(field) ? 'decimal' : 'text'}" value="${escapeHtml(values[0] ?? '')}"></label><label>Through<input class="condition-high" type="${inputType}" inputmode="${['amount','outflow','inflow','day_of_month','month'].includes(field) ? 'decimal' : 'text'}" value="${escapeHtml(values[1] ?? '')}"></label></div>`;
  }
  if (field === 'source') return `<label class="condition-value">Value<select class="condition-value-input"><option value="simplefin" ${condition.value === 'simplefin' ? 'selected' : ''}>SimpleFIN</option><option value="manual" ${condition.value === 'manual' ? 'selected' : ''}>Manual or cash</option></select></label>`;
  if (field === 'day_of_week' && !['one_of','not_one_of'].includes(operator)) return `<label class="condition-value">Day<select class="condition-value-input">${['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(day => `<option value="${day}" ${condition.value === day ? 'selected' : ''}>${day[0].toUpperCase()+day.slice(1)}</option>`).join('')}</select></label>`;
  const listHint = ['one_of','not_one_of'].includes(operator) ? 'Comma-separated values' : 'Value';
  return `<label class="condition-value">${listHint}<input class="condition-value-input" type="${inputType}" value="${escapeHtml(Array.isArray(condition.value) ? condition.value.join(', ') : condition.value ?? '')}"></label>`;
}

function conditionRowMarkup(condition) {
  const operators = FIELD_OPERATORS[condition.field] || ['is','is_not'];
  if (!operators.includes(condition.operator)) condition.operator = operators[0];
  return `<div class="condition-row" data-condition='${escapeHtml(JSON.stringify(condition))}'>
    <label class="condition-field-control">Field<select class="condition-field">${Object.entries(RULE_FIELDS).map(([value,label]) => `<option value="${value}" ${condition.field === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label>
    <label class="condition-operator-control">Comparison<select class="condition-operator">${operators.map(value => `<option value="${value}" ${condition.operator === value ? 'selected' : ''}>${escapeHtml(RULE_OPERATORS[value])}</option>`).join('')}</select></label>
    ${conditionValueMarkup(condition)}
    <button class="row-remove remove-condition" type="button" aria-label="Remove condition">×</button>
  </div>`;
}

function splitPartsMarkup(action) {
  const metric = action.type === 'split_percent' ? 'percent' : 'amount';
  const parts = action.splits?.length ? action.splits : [{ category_id: '', [metric]: '' }];
  return `<div class="split-parts">${parts.map(part => `<div class="split-part"><select class="split-category">${categoryOptions(part.category_id, true)}</select><input class="split-value" inputmode="decimal" placeholder="${metric === 'percent' ? '%' : 'Amount'}" value="${escapeHtml(part[metric] ?? '')}"><button class="icon-button remove-split-part" type="button">×</button></div>`).join('')}<button class="button button--ghost add-split-part" type="button">+ Add part</button><label>Remainder category<select class="remainder-category"><option value="">None</option>${categoryOptions(action.remainder_category_id || '', true)}</select></label></div>`;
}

function actionValueMarkup(action) {
  switch (action.type) {
    case 'assign_category': return `<label class="action-value">Category<select class="action-category">${categoryOptions(action.category_id, true)}</select></label>`;
    case 'set_payee': return `<label class="action-value">New payee<input class="action-text" value="${escapeHtml(action.value || '')}"></label>`;
    case 'add_note': return `<label class="action-value">Note<input class="action-text" value="${escapeHtml(action.value || '')}"></label>`;
    case 'add_tag': return `<label class="action-value">Tag<input class="action-text" value="${escapeHtml(action.value || '')}"></label>`;
    case 'alert': return `<div class="action-value form-grid"><label>Alert title<input class="alert-title" value="${escapeHtml(action.title || 'Budget rule matched')}"></label><label>Severity<select class="alert-severity"><option value="info" ${action.severity === 'info' ? 'selected' : ''}>Info</option><option value="warning" ${action.severity !== 'info' && action.severity !== 'critical' ? 'selected' : ''}>Warning</option><option value="critical" ${action.severity === 'critical' ? 'selected' : ''}>Critical</option></select></label></div>`;
    case 'split_fixed': case 'split_percent': return splitPartsMarkup(action);
    default: return '<span class="action-value muted">No additional setting</span>';
  }
}

function actionRowMarkup(action) {
  return `<div class="action-row" data-action-type="${escapeHtml(action.type)}">
    <label class="action-type-control">Action<select class="action-type">${Object.entries(ACTION_LABELS).map(([value,label]) => `<option value="${value}" ${action.type === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label>
    ${actionValueMarkup(action)}
    <button class="row-remove remove-action" type="button" aria-label="Remove action">×</button>
  </div>`;
}

function readConditionRow(row) {
  const field = $('.condition-field', row).value;
  const operator = $('.condition-operator', row).value;
  let value = null;
  if (!['is_true','is_false'].includes(operator)) {
    if (operator === 'between') value = [$('.condition-low', row).value.trim(), $('.condition-high', row).value.trim()];
    else if (field === 'account_id' && ['one_of','not_one_of'].includes(operator)) value = [...$('.condition-value-input', row).selectedOptions].map(option => option.value);
    else {
      value = $('.condition-value-input', row).value.trim();
      if (['one_of','not_one_of'].includes(operator)) value = value.split(',').map(item => item.trim()).filter(Boolean);
    }
  }
  return { field, operator, value };
}

function readActionRow(row) {
  const type = $('.action-type', row).value;
  if (type === 'assign_category') return { type, category_id: $('.action-category', row).value };
  if (['set_payee','add_note','add_tag'].includes(type)) return { type, value: $('.action-text', row).value.trim() };
  if (type === 'alert') return { type, title: $('.alert-title', row).value.trim(), severity: $('.alert-severity', row).value };
  if (['split_fixed','split_percent'].includes(type)) {
    const metric = type === 'split_percent' ? 'percent' : 'amount';
    return {
      type,
      splits: $$('.split-part', row).map(part => ({ category_id: $('.split-category', part).value, [metric]: $('.split-value', part).value.trim(), memo: '' })),
      remainder_category_id: $('.remainder-category', row).value || null,
    };
  }
  return { type };
}

function bindConditionRow(row) {
  const rebuild = () => {
    const condition = readConditionRow(row);
    const replacement = document.createElement('div');
    replacement.innerHTML = conditionRowMarkup(condition);
    const next = replacement.firstElementChild;
    row.replaceWith(next); bindConditionRow(next); state.formDirty = true;
  };
  $('.condition-field', row).addEventListener('change', event => {
    const field = event.target.value;
    const operators = FIELD_OPERATORS[field] || ['is'];
    row.dataset.condition = JSON.stringify({ field, operator: operators[0], value: '' });
    const replacement = document.createElement('div'); replacement.innerHTML = conditionRowMarkup({ field, operator: operators[0], value: '' });
    const next = replacement.firstElementChild; row.replaceWith(next); bindConditionRow(next); state.formDirty = true;
  });
  $('.condition-operator', row).addEventListener('change', rebuild);
  $('.remove-condition', row).addEventListener('click', () => { row.remove(); state.formDirty = true; });
  $$('input,select', row).forEach(input => input.addEventListener('input', () => { state.formDirty = true; }));
}

function bindActionRow(row) {
  const typeSelect = $('.action-type', row);
  typeSelect.addEventListener('change', () => {
    const replacement = document.createElement('div'); replacement.innerHTML = actionRowMarkup({ type: typeSelect.value });
    const next = replacement.firstElementChild; row.replaceWith(next); bindActionRow(next); state.formDirty = true;
  });
  $('.remove-action', row).addEventListener('click', () => { row.remove(); state.formDirty = true; });
  const bindPart = part => $('.remove-split-part', part)?.addEventListener('click', () => { part.remove(); state.formDirty = true; });
  $$('.split-part', row).forEach(bindPart);
  $('.add-split-part', row)?.addEventListener('click', () => {
    const actionType = $('.action-type', row).value;
    const metric = actionType === 'split_percent' ? '%' : 'Amount';
    const part = document.createElement('div'); part.className = 'split-part';
    part.innerHTML = `<select class="split-category">${categoryOptions('', true)}</select><input class="split-value" inputmode="decimal" placeholder="${metric}"><button class="icon-button remove-split-part" type="button">×</button>`;
    $('.add-split-part', row).before(part); bindPart(part); state.formDirty = true;
  });
  $$('input,select', row).forEach(input => input.addEventListener('input', () => { state.formDirty = true; }));
}

function readRuleEditor(root, existingRule = null) {
  const conditions = $$('.condition-row', root).map(readConditionRow);
  const actions = $$('.action-row', root).map(readActionRow);
  if (!conditions.length) throw new Error('Add at least one condition.');
  if (!actions.length) throw new Error('Add at least one action.');
  return {
    ...(existingRule ? { version: existingRule.version } : {}),
    name: $('#rule-name', root).value.trim(), enabled: $('#rule-enabled', root).checked,
    phase: $('#rule-phase', root).value, priority: Number($('#rule-priority', root).value || 100),
    conditions: { combinator: $('#rule-combinator', root).value, children: conditions },
    actions,
    apply_to_manual_overrides: $('#rule-manual-overrides', root).checked,
    stop_processing: $('#rule-stop', root).checked,
    apply_now: $('#rule-apply-now', root).value,
  };
}

function openRuleEditor(rule = null, transaction = null) {
  const conditions = simpleConditionsFromRule(rule, transaction);
  const actions = defaultRuleActions(rule, transaction);
  openModal({
    title: rule ? `Edit ${rule.name}` : transaction ? `Rule for ${transactionLabel(transaction)}` : 'Create a rule',
    className: 'modal--wide',
    body: `<form id="rule-form" class="rule-builder">
      <div class="form-grid"><label>Rule name<input id="rule-name" maxlength="180" required value="${escapeHtml(rule?.name || (transaction ? `${transactionLabel(transaction)} → category` : ''))}"></label><label>Phase<select id="rule-phase"><option value="cleanup" ${rule?.phase === 'cleanup' ? 'selected' : ''}>1. Clean up</option><option value="categorize" ${!rule || rule.phase === 'categorize' ? 'selected' : ''}>2. Categorize</option><option value="finish" ${rule?.phase === 'finish' ? 'selected' : ''}>3. Finish and flag</option></select></label><label>Order within phase<input id="rule-priority" type="number" min="0" max="100000" value="${rule?.priority ?? 100}"></label><label><span><input id="rule-enabled" type="checkbox" style="width:auto;min-height:auto" ${rule?.enabled !== false ? 'checked' : ''}> Rule is enabled</span></label></div>
      <section class="builder-panel"><header><div><h3>When</h3><small>Match <select id="rule-combinator" class="inline-select"><option value="all" ${rule?.conditions?.combinator !== 'any' && rule?.conditions?.combinator !== 'none' ? 'selected' : ''}>all conditions</option><option value="any" ${rule?.conditions?.combinator === 'any' ? 'selected' : ''}>any condition</option><option value="none" ${rule?.conditions?.combinator === 'none' ? 'selected' : ''}>none of these</option></select></small></div><button class="button button--soft add-condition" type="button">+ Condition</button></header><div class="builder-body condition-list">${conditions.map(conditionRowMarkup).join('')}</div></section>
      <section class="builder-panel"><header><div><h3>Then</h3><small>Actions run from top to bottom.</small></div><button class="button button--soft add-action" type="button">+ Action</button></header><div class="builder-body action-list">${actions.map(actionRowMarkup).join('')}</div></section>
      <section class="builder-panel"><div class="builder-body"><label><span><input id="rule-stop" type="checkbox" style="width:auto;min-height:auto" ${rule?.stop_processing !== false ? 'checked' : ''}> Stop other rules in this phase after a match</span></label><label><span><input id="rule-manual-overrides" type="checkbox" style="width:auto;min-height:auto" ${rule?.apply_to_manual_overrides ? 'checked' : ''}> Allow this rule to overwrite a person's manual category or payee</span></label><label>When saving<select id="rule-apply-now"><option value="none">Future transactions only</option><option value="unassigned">Also apply to existing unassigned transactions</option><option value="eligible">Apply to every eligible historical transaction</option></select></label><div class="preview-box rule-preview">Preview has not been run.</div><button class="button button--soft preview-rule" type="button">Preview matching transactions</button></div></section>
    </form>
    ${rule ? '<div class="form-section"><button class="button button--danger archive-rule" type="button">Archive rule</button></div>' : ''}`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary save-rule" type="button">Save rule</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('.condition-row', root).forEach(bindConditionRow); $$('.action-row', root).forEach(bindActionRow);
      $('.add-condition', root).addEventListener('click', () => {
        const wrapper = document.createElement('div'); wrapper.innerHTML = conditionRowMarkup({ field: 'original_description', operator: 'contains', value: '' });
        const row = wrapper.firstElementChild; $('.condition-list', root).append(row); bindConditionRow(row); state.formDirty = true;
      });
      $('.add-action', root).addEventListener('click', () => {
        const wrapper = document.createElement('div'); wrapper.innerHTML = actionRowMarkup({ type: 'assign_category' });
        const row = wrapper.firstElementChild; $('.action-list', root).append(row); bindActionRow(row); state.formDirty = true;
      });
      $$('input,select,textarea', root).forEach(input => input.addEventListener('input', () => { state.formDirty = true; }));
      $('.preview-rule', root).addEventListener('click', async event => {
        let body; try { body = readRuleEditor(root, null); delete body.version; } catch (error) { toast(error.message, 'error'); return; }
        body.apply_now = 'none'; setButtonBusy(event.currentTarget, true, 'Checking…');
        try {
          const result = await api('/api/rules/preview', { method: 'POST', body });
          $('.rule-preview', root).innerHTML = `<strong>${result.match_count_in_sample} matches</strong> in the newest ${result.sample_size} transactions.${result.transactions.length ? `<div style="margin-top:8px">${result.transactions.slice(0,5).map(item => `${escapeHtml(transactionLabel(item))} · ${money(item.amount)}`).join('<br>')}</div>` : ''}`;
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(event.currentTarget, false); }
      });
      $('.archive-rule', root)?.addEventListener('click', async () => {
        const yes = await confirmDialog({ title: 'Archive this rule?', message: 'It will stop running, but its revision history and prior audit events remain.', confirmText: 'Archive rule', danger: true });
        if (!yes) return;
        try { await withConflict(body => api(`/api/rules/${rule.id}`, { method: 'DELETE', body }), { version: rule.version }, 'rule'); closeModal(); toast('Rule archived'); await renderRules(); } catch (error) { toast(error.message, 'error'); }
      });
      const save = async () => {
        let body; try { body = readRuleEditor(root, rule); } catch (error) { toast(error.message, 'error'); return; }
        const button = $('.save-rule', root); setButtonBusy(button, true, 'Saving…');
        try {
          const result = rule
            ? await withConflict(current => api(`/api/rules/${rule.id}`, { method: 'PATCH', body: current }), body, 'rule')
            : await api('/api/rules', { method: 'POST', body });
          if (!result) return;
          state.formDirty = false; closeModal();
          const changed = result.historical_transactions_changed || 0;
          const sorted = result.historical_transactions_sorted || 0;
          const stillUnsorted = result.historical_transactions_still_unsorted || 0;
          if (sorted && stillUnsorted) toast(`Rule saved: ${sorted} transaction${sorted === 1 ? '' : 's'} sorted; ${stillUnsorted} remain${stillUnsorted === 1 ? 's' : ''} in To sort`, 'error');
          else if (sorted) toast(`Rule saved and sorted ${sorted} transaction${sorted === 1 ? '' : 's'}`);
          else if (stillUnsorted) toast(`Rule saved, but ${stillUnsorted} matching transaction${stillUnsorted === 1 ? '' : 's'} remain${stillUnsorted === 1 ? 's' : ''} in To sort`, 'error');
          else toast(changed ? `Rule saved and updated ${changed} transaction${changed === 1 ? '' : 's'}` : 'Rule saved');
          await refreshCurrentView(); if (state.view === 'rules') await renderRules();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.save-rule', root).addEventListener('click', save);
      $('#rule-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

const THEME_META = {
  citrus: { label: 'Citrus', colors: ['#ffbf2f','#ff6b35','#276ef1'] },
  ocean: { label: 'Ocean', colors: ['#17c3e2','#276ef1','#0b3954'] },
  berry: { label: 'Berry', colors: ['#ef4f9a','#8b5cf6','#4c1d95'] },
  meadow: { label: 'Meadow', colors: ['#84cc16','#14b8a6','#14532d'] },
  sunrise: { label: 'Sunrise', colors: ['#fbbf24','#fb7185','#4f46e5'] },
  'high-contrast': { label: 'High contrast', colors: ['#000000','#ffffff','#ffd400'] },
  system: { label: 'Follow device', colors: ['#64748b','#e2e8f0','#0f172a'] },
};

function connectionHealthMarkup(connection) {
  if (!connection.connected) return '<span class="danger">Disconnected</span>';
  if (!connection.enabled) return '<span class="warning">Paused</span>';
  if (connection.consecutive_failures || connection.last_error_code) return `<span class="danger">${connection.consecutive_failures} failed cycle${connection.consecutive_failures === 1 ? '' : 's'}</span>`;
  if (!connection.last_success_at) return '<span class="warning">Initial import queued</span>';
  return `<span class="positive">Healthy · ${escapeHtml(relativeTime(connection.last_success_at))}</span>`;
}

async function renderMore() {
  const admin = state.me.user.is_admin;
  const requests = [api('/api/connections'), api('/api/system/status')];
  if (admin) requests.push(
    api('/api/admin/users'),
    api('/api/admin/incidents'),
    api('/api/admin/operations'),
    api('/api/alerts/balances'),
  );
  const results = await Promise.all(requests);
  const connections = results[0].connections;
  const system = results[1];
  if (admin) {
    state.users = results[2].users;
    state.incidents = results[3].incidents.filter(incident => !incident.incident_key.startsWith('balance-alert:'));
    state.operations = results[4];
    state.balanceAlerts = results[5].alerts;
  }
  const themes = state.me.themes || Object.keys(THEME_META);
  const channelLabels = [state.me.notification_channels.smtp ? 'SMTP' : '', state.me.notification_channels.ntfy ? 'ntfy' : '', state.me.notification_channels.external_heartbeat ? 'external heartbeat' : ''].filter(Boolean);
  const balanceChannels = admin ? results[5].available_channels : [];
  const balanceAlertCards = state.balanceAlerts.map(alert => {
    const condition = alert.comparison === 'below' ? 'Below' : 'Above';
    const delivery = alert.channels.map(channel => channel === 'smtp' ? 'SMTP2GO' : 'ntfy').join(' + ');
    const unavailableLabels = {
      duplicate_account: 'Duplicate account',
      inactive_account: 'Inactive account',
      balance_unavailable: 'Balance unavailable',
      connection_unavailable: 'Connection unavailable',
    };
    const status = !alert.available ? 'Unavailable' : !alert.enabled ? 'Paused' : alert.triggered ? 'Triggered' : 'Watching';
    const balance = alert.current_balance === null ? 'Current balance unavailable' : `Current ${money(alert.current_balance)}`;
    const availability = alert.available ? '' : ` · ${unavailableLabels[alert.unavailable_reason] || 'Account unavailable'}`;
    const deliveryAvailability = alert.channels.some(channel => !balanceChannels.includes(channel)) ? ' · Delivery channel not configured' : '';
    const statusClass = alert.triggered ? 'warning' : alert.available && alert.enabled ? 'positive' : '';
    return `<div class="connection-card balance-alert-card ${alert.triggered ? 'balance-alert-card--triggered' : ''} ${!alert.available ? 'balance-alert-card--unavailable' : ''}" data-alert-id="${alert.id}"><div class="connection-top"><div><strong>${escapeHtml(alert.name)}</strong><small>${escapeHtml(alert.account_name)} · ${condition} ${money(alert.threshold)} · ${escapeHtml(balance)} · ${escapeHtml(delivery)}${escapeHtml(availability)}${escapeHtml(deliveryAvailability)}</small></div><div class="account-card-actions"><span class="pill ${statusClass}">${status}</span><button class="icon-button edit-balance-alert" type="button" aria-label="Edit ${escapeHtml(alert.name)}"><span data-icon="pencil"></span></button></div></div></div>`;
  }).join('');
  const allAccounts = accountCatalog();
  const duplicateAccountCount = allAccounts.filter(account => account.is_duplicate).length;
  const inactiveAccountCount = allAccounts.filter(account => !account.is_duplicate && !account.is_active).length;
  const hiddenAccountCount = duplicateAccountCount + inactiveAccountCount;
  const accountCards = allAccounts.filter(account => account.is_active && !account.is_duplicate).map(account => {
    const status = account.is_budget ? 'On budget' : 'Off budget';
    return `<div class="connection-card" data-account-id="${account.id}"><div class="connection-top"><div><strong>${escapeHtml(account.name)}</strong><small>${escapeHtml(account.source_type === 'manual' ? 'Manual account' : 'SimpleFIN account')} · ${escapeHtml(status)}</small></div><div class="account-card-actions"><b>${money(account.balance)}</b>${admin ? `<button class="icon-button edit-account-name" type="button" aria-label="Rename ${escapeHtml(account.name)}"><span data-icon="pencil"></span></button>` : ''}</div></div></div>`;
  }).join('');
  const hiddenAccountNote = [
    duplicateAccountCount ? `${duplicateAccountCount} duplicate account${duplicateAccountCount === 1 ? ' is' : 's are'} hidden here.` : '',
    inactiveAccountCount ? `${inactiveAccountCount} inactive account${inactiveAccountCount === 1 ? ' is' : 's are'} hidden here.` : '',
  ].filter(Boolean).join(' ');
  const emptyAccounts = hiddenAccountCount
    ? `<div class="empty-state"><strong>No accounts to show</strong>${hiddenAccountCount} account${hiddenAccountCount === 1 ? ' is' : 's are'} inactive or duplicate and hidden from this list.</div>`
    : '<div class="empty-state"><strong>No accounts yet</strong>Connect a bank or add a manual transaction after an account is available.</div>';
  $('#app-view').innerHTML = `<header class="view-header"><div><h1>More</h1><p>Appearance, bank connections, people, and system reliability.</p></div></header>
    <div class="settings-grid">
      <section class="settings-card"><header><div><h2>${escapeHtml(state.me.user.display_name)}</h2><p>${escapeHtml(state.me.user.email)}${admin ? ' · Owner' : ''}</p></div><span class="avatar-button profile-avatar" aria-hidden="true">${escapeHtml(initials(state.me.user.display_name))}</span></header><div class="button-row"><button class="button button--soft sessions-button" type="button">Signed-in devices</button><button class="button logout-button" type="button">Sign out</button></div></section>
      <section class="settings-card"><header><div><h2>Your theme</h2><p>Appearance is saved independently for each user.</p></div></header><div class="theme-grid">${themes.map(theme => { const meta = THEME_META[theme] || { label: theme, colors: [] }; return `<button class="theme-choice ${state.me.user.theme === theme ? 'active' : ''}" data-theme-choice="${theme}" type="button"><span class="theme-swatches">${meta.colors.map(color => `<i style="--swatch:${color}"></i>`).join('')}</span><strong>${escapeHtml(meta.label)}</strong></button>`; }).join('')}</div>
        <div class="form-grid" style="margin-top:13px"><label>Layout density<select id="preference-density"><option value="comfortable" ${state.me.user.preferences?.density !== 'compact' ? 'selected' : ''}>Comfortable</option><option value="compact" ${state.me.user.preferences?.density === 'compact' ? 'selected' : ''}>Compact</option></select></label><label>Motion<select id="preference-motion"><option value="full" ${state.me.user.preferences?.motion !== 'reduced' ? 'selected' : ''}>Full</option><option value="reduced" ${state.me.user.preferences?.motion === 'reduced' ? 'selected' : ''}>Reduced</option></select></label></div>
      </section>
      <section class="settings-card"><header><div><h2>Bank connections</h2><p>SimpleFIN imports continue in the background; opening this page does not trigger a bank request.</p></div>${admin ? '<button class="button button--primary add-connection" type="button">+ Connect</button>' : ''}</header>
        <div class="connection-list">${connections.map(connection => `<div class="connection-card" data-connection-id="${connection.id}"><div class="connection-top"><div><strong>${escapeHtml(connection.name)}</strong><small>Every ${connection.sync_interval_minutes / 60} hours · Next ${escapeHtml(relativeTime(connection.next_sync_at))}</small></div><button class="icon-button connection-details" type="button">›</button></div><div class="health-line"><span class="status-dot"></span>${connectionHealthMarkup(connection)}</div>${connection.last_error_message ? `<p class="danger">${escapeHtml(connection.last_error_message)}</p>` : ''}</div>`).join('') || '<div class="empty-state"><strong>No bank connected</strong>Manual and cash budgeting still work. The owner can add SimpleFIN here.</div>'}</div>
      </section>
      <section class="settings-card"><header><div><h2>Accounts</h2><p>Balances shown are the latest values retained by Mosaic.${admin ? ' Use edit to give any account a familiar name.' : ''}${hiddenAccountNote ? ` ${escapeHtml(hiddenAccountNote)} Imported accounts remain available inside their bank connection.` : ''}</p></div></header>${accountCards || emptyAccounts}</section>
      ${admin ? `<section class="settings-card"><header><div><h2>People</h2><p>Multiple devices can be active at once. Conflicting edits require an explicit choice.</p></div><button class="button button--soft add-user" type="button">+ User</button></header><div class="user-list">${state.users.map(user => `<div class="user-row" data-user-id="${user.id}"><div><strong>${escapeHtml(user.display_name)} ${user.is_admin ? '<span class="pill">Owner</span>' : ''}</strong><small>${escapeHtml(user.email)} · ${user.is_active ? 'Active' : 'Disabled'}</small></div><button class="icon-button edit-user" type="button">›</button></div>`).join('')}</div></section>
      <section class="settings-card"><header><div><h2>Balance alerts</h2><p>${balanceChannels.length ? `Notify through ${escapeHtml(balanceChannels.map(channel => channel === 'smtp' ? 'SMTP2GO' : 'ntfy').join(' and '))} when an account crosses a threshold.` : 'Configure SMTP2GO or ntfy in the deployment environment to enable balance alerts.'}</p></div><button class="button button--soft add-balance-alert" type="button" ${balanceChannels.length ? '' : 'disabled'}>+ Add alert</button></header><div class="balance-alert-list">${balanceAlertCards || '<div class="empty-state"><strong>No balance alerts</strong>Add a threshold for any active account and choose where it should be delivered.</div>'}</div></section>
      <section class="settings-card"><header><div><h2>Operational alerts</h2><p>${channelLabels.length ? `Delivery configured through ${escapeHtml(channelLabels.join(' and '))}.` : 'No external alert channel is currently enabled.'}</p></div><button class="button button--soft test-notifications" type="button">Send test</button></header><div class="incident-list">${state.incidents.map(incident => `<div class="incident-row"><div class="incident-top"><div><strong class="${incident.severity === 'critical' ? 'danger' : incident.severity === 'warning' ? 'warning' : ''}">${escapeHtml(incident.title)}</strong><small>${escapeHtml(relativeTime(incident.last_seen_at))} · Seen ${incident.occurrence_count} time${incident.occurrence_count === 1 ? '' : 's'}</small></div>${incident.acknowledged_at ? '<span class="pill">Acknowledged</span>' : `<button class="button button--ghost acknowledge-incident" data-incident-id="${incident.id}" type="button">Acknowledge</button>`}</div><p>${escapeHtml(incident.message)}</p></div>`).join('') || '<div class="empty-state"><strong>No open incidents</strong>Synchronization and background checks have not reported an unresolved problem.</div>'}</div></section>
      <section class="settings-card"><header><div><h2>Reliability</h2><p>Worker, synchronization, and verified backup status.</p></div></header><div class="health-line"><span class="status-dot"></span><strong>${system.healthy ? 'All monitored systems healthy' : 'Attention required'}</strong></div><div class="health-line">Worker: ${state.operations.worker.healthy ? 'healthy' : 'stale'} · heartbeat ${escapeHtml(relativeTime(state.operations.worker.heartbeat_at))}</div><div class="health-line">Backup: ${state.operations.backup.verified_at ? `verified ${escapeHtml(relativeTime(state.operations.backup.verified_at))}` : 'not yet verified'}</div><div class="health-line">Sync: ${escapeHtml(system.synchronization)} · Backup: ${escapeHtml(system.backup)}</div></section>` : ''}
    </div>`;
  hydrateIcons($('#app-view'));
  $$('.theme-choice', $('#app-view')).forEach(button => button.addEventListener('click', () => savePreferences(button.dataset.themeChoice)));
  $('#preference-density', $('#app-view')).addEventListener('change', () => savePreferences());
  $('#preference-motion', $('#app-view')).addEventListener('change', () => savePreferences());
  $('.sessions-button', $('#app-view')).addEventListener('click', openSessions);
  $('.logout-button', $('#app-view')).addEventListener('click', logout);
  $('.add-connection', $('#app-view'))?.addEventListener('click', openConnectionSetup);
  $$('.connection-details', $('#app-view')).forEach(button => button.addEventListener('click', () => openConnectionDetails(connections.find(item => item.id === button.closest('.connection-card').dataset.connectionId))));
  $$('.edit-account-name', $('#app-view')).forEach(button => button.addEventListener('click', () => openAccountNameEditor(accountById(button.closest('.connection-card').dataset.accountId))));
  $('.add-user', $('#app-view'))?.addEventListener('click', () => openUserEditor());
  $$('.edit-user', $('#app-view')).forEach(button => button.addEventListener('click', () => openUserEditor(state.users.find(user => user.id === button.closest('.user-row').dataset.userId))));
  $('.add-balance-alert', $('#app-view'))?.addEventListener('click', () => openBalanceAlertEditor(null, balanceChannels));
  $$('.edit-balance-alert', $('#app-view')).forEach(button => button.addEventListener('click', () => openBalanceAlertEditor(state.balanceAlerts.find(alert => alert.id === button.closest('.balance-alert-card').dataset.alertId), balanceChannels)));
  $$('.acknowledge-incident', $('#app-view')).forEach(button => button.addEventListener('click', async () => {
    try { await api(`/api/admin/incidents/${button.dataset.incidentId}/acknowledge`, { method: 'POST', body: { acknowledged: true } }); toast('Incident acknowledged'); await renderMore(); } catch (error) { toast(error.message, 'error'); }
  }));
  $('.test-notifications', $('#app-view'))?.addEventListener('click', async event => {
    setButtonBusy(event.currentTarget, true, 'Queueing…');
    try { await api('/api/admin/notifications/test', { method: 'POST' }); toast('Test alert queued for the background delivery worker'); } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(event.currentTarget, false); }
  });
}

function openBalanceAlertEditor(alert = null, availableChannels = []) {
  const accounts = accountCatalog().filter(account => account.balance_alert_available !== false && account.is_active && !account.is_duplicate && account.balance !== null);
  if (!accounts.length && !alert) { toast('No active account with a current balance and available connection can be monitored yet.', 'error'); return; }
  const selectedChannels = new Set(alert?.channels || availableChannels);
  const channelOptions = [...new Set([...availableChannels, ...(alert?.channels || [])])];
  const accountOptions = accounts.map(account => `<option value="${account.id}" ${account.id === alert?.account_id ? 'selected' : ''}>${escapeHtml(account.name)}${account.is_active ? '' : ' — inactive'}</option>`).join('');
  const missingAccount = alert && !accounts.some(account => account.id === alert.account_id)
    ? `<option value="${alert.account_id}" selected disabled>${escapeHtml(alert.account_name)} — unavailable</option>`
    : '';
  const channelMarkup = channelOptions.map(channel => {
    const configured = availableChannels.includes(channel);
    const label = channel === 'smtp' ? 'SMTP2GO email' : 'ntfy push notification';
    return `<label class="account-toggle"><input class="balance-alert-channel" type="checkbox" value="${channel}" ${selectedChannels.has(channel) ? 'checked' : ''} data-configured="${configured}"><span>${label}${configured ? '' : ' (not configured)'}</span></label>`;
  }).join('');
  openModal({
    title: alert ? 'Edit balance alert' : 'Add balance alert',
    body: `<form id="balance-alert-form" class="form-grid">
      <label class="full">Alert name<input id="balance-alert-name" value="${escapeHtml(alert?.name || '')}" maxlength="160" placeholder="Checking balance is low" required></label>
      <label>Account<select id="balance-alert-account" required>${missingAccount}${accountOptions}</select></label>
      <label>Condition<select id="balance-alert-comparison"><option value="below" ${alert?.comparison !== 'above' ? 'selected' : ''}>Balance falls below</option><option value="above" ${alert?.comparison === 'above' ? 'selected' : ''}>Balance rises above</option></select></label>
      <label>Amount<input id="balance-alert-threshold" inputmode="decimal" value="${escapeHtml(alert?.threshold || '')}" placeholder="100.00" required></label>
      <label><span><input id="balance-alert-enabled" type="checkbox" style="width:auto;min-height:auto" ${alert?.enabled !== false ? 'checked' : ''}> Alert is active</span></label>
      <fieldset class="account-toggle-group full"><legend>Send through</legend><div class="account-toggle-row">${channelMarkup}</div></fieldset>
      <p class="muted full">Mosaic sends once when the threshold is crossed and sends a recovery message when the balance returns to the other side.</p>
    </form>`,
    footer: `${alert ? '<button class="button button--danger delete-balance-alert" type="button">Delete alert</button>' : ''}<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary save-balance-alert" type="button" ${availableChannels.length || alert ? '' : 'disabled'}>${alert ? 'Save alert' : 'Add alert'}</button>`,
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('input,select', root).forEach(control => control.addEventListener('input', () => { state.formDirty = true; }));
      const save = async () => {
        const name = $('#balance-alert-name', root).value.trim();
        if (!name) { toast('Enter a name for this alert.', 'error'); return; }
        let threshold;
        try { threshold = unitsToString(toUnits($('#balance-alert-threshold', root).value)); }
        catch { toast('Enter a valid balance amount.', 'error'); return; }
        const channels = $$('.balance-alert-channel:checked', root).map(input => input.value);
        if (!channels.length) { toast('Choose at least one configured notification channel.', 'error'); return; }
        const enabled = $('#balance-alert-enabled', root).checked;
        if (enabled && $$('.balance-alert-channel:checked[data-configured="false"]', root).length) {
          toast('Configure the selected channel again, or pause the alert before saving.', 'error'); return;
        }
        const accountId = $('#balance-alert-account', root).value;
        if (enabled && !accounts.some(account => account.id === accountId)) {
          toast('Choose an available account with a current balance, or pause this alert.', 'error'); return;
        }
        const body = {
          account_id: accountId,
          name,
          comparison: $('#balance-alert-comparison', root).value,
          threshold,
          channels,
          enabled,
          ...(alert ? { version: alert.version } : {}),
        };
        const button = $('.save-balance-alert', root); setButtonBusy(button, true, 'Saving…');
        try {
          const result = alert
            ? await withConflict(current => api(`/api/alerts/balances/${alert.id}`, { method: 'PATCH', body: current }), body, 'balance alert')
            : await api('/api/alerts/balances', { method: 'POST', body });
          if (!result) return;
          state.formDirty = false; closeModal();
          toast(result.alert.triggered ? 'Balance alert saved and currently triggered' : 'Balance alert saved');
          await renderMore();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.save-balance-alert', root).addEventListener('click', save);
      $('#balance-alert-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
      $('.delete-balance-alert', root)?.addEventListener('click', async () => {
        const accepted = await confirmDialog({
          title: 'Delete this balance alert?',
          message: 'It will stop watching this account. Existing notification delivery records remain in the audit trail.',
          confirmText: 'Delete alert',
          danger: true,
        });
        if (!accepted) return;
        try {
          const result = await withConflict(current => api(`/api/alerts/balances/${alert.id}`, { method: 'DELETE', body: current }), { version: alert.version }, 'balance alert deletion');
          if (!result) return;
          state.formDirty = false; closeModal(); toast('Balance alert deleted'); await renderMore();
        } catch (error) { toast(error.message, 'error'); }
      });
    },
  });
}

function openAccountNameEditor(account) {
  if (!account) { toast('That account is no longer available.', 'error'); return; }
  openModal({
    title: 'Name account',
    body: `<form id="account-name-form" class="form-grid"><label>Account name<input id="account-display-name" value="${escapeHtml(account.name)}" required maxlength="255" autocomplete="off"></label><p class="muted">This name is used in transactions, rules, and account lists. Bank synchronization will not overwrite it.</p></form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary save-account-name" type="button">Save name</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $('#account-display-name', root).addEventListener('input', () => { state.formDirty = true; });
      const save = async () => {
        const name = $('#account-display-name', root).value.trim();
        if (!name) { toast('Enter an account name.', 'error'); return; }
        const button = $('.save-account-name', root); setButtonBusy(button, true, 'Saving…');
        try {
          const result = await withConflict(
            body => api(`/api/connections/accounts/${account.id}`, { method: 'PATCH', body }),
            { version: account.version, name },
            'account name',
          );
          if (!result) return;
          Object.assign(account, result.account);
          state.formDirty = false; closeModal(); toast('Account name saved');
          await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.save-account-name', root).addEventListener('click', save);
      $('#account-name-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

async function savePreferences(theme = null) {
  const preferences = {
    ...(state.me.user.preferences || {}),
    density: $('#preference-density')?.value || state.me.user.preferences?.density || 'comfortable',
    motion: $('#preference-motion')?.value || state.me.user.preferences?.motion || 'full',
  };
  const body = { version: state.me.user.version, theme: theme || state.me.user.theme, preferences };
  try {
    const result = await withConflict(current => api('/api/auth/preferences', { method: 'PATCH', body: current }), body, 'preferences');
    if (!result) return;
    state.me.user = result.user;
    document.body.dataset.theme = result.user.theme;
    document.body.dataset.density = result.user.preferences?.density || 'comfortable';
    document.body.dataset.motion = result.user.preferences?.motion || 'full';
    toast('Preferences saved');
    if (state.view === 'more') await renderMore();
  } catch (error) { toast(error.message, 'error'); }
}

function openConnectionSetup() {
  openModal({
    title: 'Connect SimpleFIN',
    body: `<form id="connection-form" class="form-grid"><label>Connection name<input id="connection-name" value="Household banks" maxlength="160" required></label><label class="full">One-time setup token<textarea id="simplefin-token" rows="6" autocomplete="off" spellcheck="false" required></textarea></label></form><div class="preview-box">The token is claimed once over HTTPS. The resulting Access URL is encrypted before it is stored and is never returned to the browser.</div>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary connect-simplefin" type="button">Connect and queue import</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      const save = async () => {
        const button = $('.connect-simplefin', root); setButtonBusy(button, true, 'Claiming token…');
        try {
          const result = await api('/api/connections/simplefin', { method: 'POST', body: { name: $('#connection-name', root).value.trim(), setup_token: $('#simplefin-token', root).value.trim() } });
          $('#simplefin-token', root).value = ''; closeModal(); toast(result.message); await refreshCurrentView(); if (state.view === 'more') await renderMore();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.connect-simplefin', root).addEventListener('click', save); $('#connection-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

async function openConnectionDetails(connection) {
  let accounts = [], runs = [];
  try {
    [accounts, runs] = await Promise.all([
      api(`/api/connections/${connection.id}/accounts`).then(result => result.accounts),
      api(`/api/connections/${connection.id}/runs`).then(result => result.runs),
    ]);
  } catch (error) { toast(error.message, 'error'); return; }
  const admin = state.me.user.is_admin;
  openModal({
    title: connection.name,
    className: 'modal--wide',
    body: `<div class="connection-card"><div class="connection-top"><div><strong>${connectionHealthMarkup(connection)}</strong><small>Next scheduled ${escapeHtml(relativeTime(connection.next_sync_at))}</small></div></div><div class="health-line">Last attempt: ${escapeHtml(relativeTime(connection.last_attempt_at))}</div><div class="health-line">Last success: ${escapeHtml(relativeTime(connection.last_success_at))}</div>${connection.last_error_message ? `<p class="danger">${escapeHtml(connection.last_error_message)}</p>` : ''}</div>
      <div class="form-section"><div class="button-row">${admin && connection.connected ? `<button class="button button--soft retry-connection" type="button">Queue retry</button><button class="button toggle-connection" type="button">${connection.enabled ? 'Pause automatic sync' : 'Resume automatic sync'}</button>` : ''}${admin && accounts.length ? '<button class="button button--soft manage-accounts" type="button">Manage accounts</button>' : ''}</div></div>
      <div class="form-section"><strong>Accounts</strong>${accounts.map(account => `<div class="connection-card account-source-card ${account.is_duplicate ? 'is-duplicate-account' : !account.is_active ? 'is-inactive-account' : ''}"><div class="connection-top"><div><strong>${escapeHtml(account.name)} ${account.is_duplicate ? '<span class="pill duplicate-account-badge">Duplicate</span>' : !account.is_active ? '<span class="pill inactive-account-badge">Inactive</span>' : ''}</strong><small>${account.is_duplicate ? 'Transactions hidden' : !account.is_active ? 'Inactive' : (account.is_budget ? 'Included in budget' : 'Off budget')} · ${escapeHtml(account.currency)}</small></div><b>${money(account.balance)}</b></div></div>`).join('') || '<p class="muted">No accounts have been imported yet.</p>'}</div>
      <div class="form-section"><strong>Recent synchronization runs</strong>${runs.slice(0,10).map(run => `<div class="health-line"><span class="status-dot"></span>${escapeHtml(formatDate(run.started_at))} · ${escapeHtml(run.status)} · ${run.transactions_new} new / ${run.transactions_changed} changed${run.error_message ? ` · ${escapeHtml(run.error_message)}` : ''}</div>`).join('') || '<p class="muted">The first run has not started yet.</p>'}</div>
      ${admin && connection.connected ? '<div class="form-section"><button class="button button--danger disconnect-connection" type="button">Disconnect and destroy credential</button></div>' : ''}`,
    footer: '<button class="button modal-cancel" type="button">Close</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $('.retry-connection', root)?.addEventListener('click', async event => {
        setButtonBusy(event.currentTarget, true, 'Queueing…'); try { const result = await withConflict(body => api(`/api/connections/${connection.id}/retry`, { method: 'POST', body }), { version: connection.version }, 'connection'); if (result) { closeModal(); toast('Synchronization retry queued'); await refreshCurrentView(); } } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(event.currentTarget, false); }
      });
      $('.toggle-connection', root)?.addEventListener('click', async () => {
        try { await withConflict(body => api(`/api/connections/${connection.id}`, { method: 'PATCH', body }), { version: connection.version, enabled: !connection.enabled }, 'connection'); closeModal(); toast(connection.enabled ? 'Automatic synchronization paused' : 'Automatic synchronization resumed'); await refreshCurrentView(); if (state.view === 'more') await renderMore(); } catch (error) { toast(error.message, 'error'); }
      });
      $('.manage-accounts', root)?.addEventListener('click', () => { closeModal(); openAccountManager(connection, accounts); });
      $('.disconnect-connection', root)?.addEventListener('click', async () => {
        const yes = await confirmDialog({ title: 'Disconnect SimpleFIN?', message: 'The encrypted credential will be destroyed. Imported accounts, transactions, tombstones, and audit history remain.', confirmText: 'Disconnect permanently', danger: true, inputLabel: `Type ${connection.name} exactly`, expected: connection.name });
        if (!yes) return;
        try { await withConflict(body => api(`/api/connections/${connection.id}`, { method: 'DELETE', body }), { version: connection.version, confirm_name: connection.name }, 'connection'); toast('SimpleFIN credential destroyed; imported data retained'); await refreshCurrentView(); if (state.view === 'more') await renderMore(); } catch (error) { toast(error.message, 'error'); }
      });
    },
  });
}

function openAccountManager(connection, accounts) {
  openModal({
    title: `Accounts in ${connection.name}`,
    className: 'modal--wide',
    body: `<form id="account-manager-form"><div class="account-editor-list">${accounts.map(account => `<div class="connection-card account-editor-card ${account.is_duplicate ? 'is-duplicate-account' : ''}" data-account-id="${account.id}"><label><span class="account-name-label">Name <span class="pill duplicate-account-badge ${account.is_duplicate ? '' : 'hidden'}">Duplicate</span></span><input class="account-name" value="${escapeHtml(account.name)}" required maxlength="255"></label><fieldset class="account-toggle-group"><legend class="sr-only">Account settings</legend><label class="account-toggle account-toggle--duplicate"><input class="account-duplicate" type="checkbox" ${account.is_duplicate ? 'checked' : ''}><span>This is a duplicate account</span></label><div class="account-toggle-row"><label class="account-toggle"><input class="account-budget" type="checkbox" ${account.is_budget ? 'checked' : ''} ${account.is_duplicate ? 'disabled' : ''}><span>Include in budget</span></label><label class="account-toggle"><input class="account-active" type="checkbox" ${account.is_active ? 'checked' : ''} ${account.is_duplicate ? 'disabled' : ''}><span>Active</span></label></div></fieldset></div>`).join('')}</div></form>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary save-all-accounts" type="submit" form="account-manager-form" disabled>Save all accounts</button>',
    onMount(root) {
      const form = $('#account-manager-form', root);
      const saveButton = $('.save-all-accounts', root);
      const initialAccounts = new Map(accounts.map(account => [account.id, {
        name: account.name.trim(),
        is_budget: account.is_budget,
        is_active: account.is_active,
        is_duplicate: account.is_duplicate,
      }]));
      const draftForCard = card => ({
        id: card.dataset.accountId,
        name: $('.account-name', card).value.trim(),
        is_budget: $('.account-budget', card).checked,
        is_active: $('.account-active', card).checked,
        is_duplicate: $('.account-duplicate', card).checked,
      });
      const hasChanged = draft => {
        const initial = initialAccounts.get(draft.id);
        return !initial || draft.name !== initial.name || draft.is_budget !== initial.is_budget
          || draft.is_active !== initial.is_active || draft.is_duplicate !== initial.is_duplicate;
      };
      const updateDirtyState = () => {
        state.formDirty = $$('.account-editor-card', root).some(card => hasChanged(draftForCard(card)));
        saveButton.disabled = !state.formDirty;
      };
      const updateDuplicateState = card => {
        const duplicate = $('.account-duplicate', card).checked;
        card.classList.toggle('is-duplicate-account', duplicate);
        $('.duplicate-account-badge', card).classList.toggle('hidden', !duplicate);
        $('.account-budget', card).disabled = duplicate;
        $('.account-active', card).disabled = duplicate;
      };
      const setSaving = saving => {
        form.setAttribute('aria-busy', String(saving));
        $$('input', form).forEach(input => { input.disabled = saving; });
        $('.modal-cancel', root).disabled = saving;
        $('.modal-close', root).disabled = saving;
        if (!saving) $$('.account-editor-card', root).forEach(updateDuplicateState);
        setButtonBusy(saveButton, saving, 'Saving accounts…');
      };
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('.account-duplicate', root).forEach(input => input.addEventListener('change', () => {
        const card = input.closest('.connection-card');
        updateDuplicateState(card);
        updateDirtyState();
      }));
      $$('.account-name, .account-budget, .account-active', root).forEach(input => input.addEventListener('input', updateDirtyState));
      const save = async () => {
        const updates = [];
        for (const card of $$('.account-editor-card', root)) {
          const account = accounts.find(item => item.id === card.dataset.accountId);
          const draft = draftForCard(card);
          if (!draft.name) { toast('Enter a name for every account.', 'error'); $('.account-name', card).focus(); return; }
          if (!hasChanged(draft)) continue;
          updates.push({
            id: account.id,
            version: account.version,
            name: draft.name,
            is_budget: draft.is_budget,
            is_active: draft.is_active,
            is_duplicate: draft.is_duplicate,
          });
        }
        if (!updates.length) { updateDirtyState(); return; }
        $$('.account-editor-card', root).forEach(card => card.classList.remove('has-conflict'));
        setSaving(true);
        try {
          const result = await api(`/api/connections/${connection.id}/accounts`, { method: 'PATCH', body: { accounts: updates } });
          (result.accounts || []).forEach(updated => Object.assign(accounts.find(account => account.id === updated.id), updated));
          state.formDirty = false;
          closeModal();
          toast(result.updated_count ? `${result.updated_count} account${result.updated_count === 1 ? '' : 's'} updated` : 'Accounts are already up to date');
          await refreshCurrentView();
        } catch (error) {
          if (error instanceof ConflictError) {
            const conflictIds = new Set((error.detail?.conflicts || []).map(conflict => conflict.id || conflict.account_id));
            $$('.account-editor-card', root).forEach(card => card.classList.toggle('has-conflict', conflictIds.has(card.dataset.accountId)));
            toast('Some accounts changed elsewhere. Your edits are still here; reload the account list before saving again.', 'error');
          } else toast(error.message, 'error');
        } finally { if (state.modalOpen && root.contains(form)) { setSaving(false); updateDirtyState(); } }
      };
      form.addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function openUserEditor(user = null) {
  const isSelf = user?.id === state.me.user.id;
  openModal({
    title: user ? `Manage ${user.display_name}` : 'Add a user',
    body: `<form id="user-form" class="form-grid"><label>Display name<input id="user-name" value="${escapeHtml(user?.display_name || '')}" required maxlength="120"></label><label>Email<input id="user-email" type="email" value="${escapeHtml(user?.email || '')}" ${user ? 'disabled' : ''} required></label><label class="full">${user ? 'New password (leave blank to keep current)' : 'Temporary password (14 characters minimum)'}<input id="user-password" type="password" minlength="14" ${user ? '' : 'required'} autocomplete="new-password"></label>${user ? `<label class="full"><span><input id="user-active" type="checkbox" style="width:auto;min-height:auto" ${user.is_active ? 'checked' : ''} ${user.is_admin ? 'disabled' : ''}> User can sign in</span></label>` : ''}</form>
      ${user && !user.is_admin ? `<div class="form-section button-row"><button class="button button--danger remove-user" type="button">Disable and sign out</button><button class="button transfer-owner" type="button">Transfer ownership</button></div>` : ''}${isSelf ? '<p class="muted">Changes to your password revoke all active sessions, including this one.</p>' : ''}`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary save-user" type="button">Save user</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $('.remove-user', root)?.addEventListener('click', async () => {
        const yes = await confirmDialog({ title: `Disable ${user.display_name}?`, message: 'All sessions for this person will be revoked immediately. Historical audit attribution remains.', confirmText: 'Disable user', danger: true });
        if (!yes) return;
        try { await withConflict(body => api(`/api/admin/users/${user.id}`, { method: 'DELETE', body }), { version: user.version }, 'user'); toast('User disabled'); await renderMore(); } catch (error) { toast(error.message, 'error'); }
      });
      $('.transfer-owner', root)?.addEventListener('click', async () => {
        const yes = await confirmDialog({ title: `Make ${user.display_name} the owner?`, message: 'They will become the sole administrator. Your account will remain active as an ordinary user.', confirmText: 'Transfer ownership', danger: true, inputLabel: `Type ${user.display_name} exactly`, expected: user.display_name });
        if (!yes) return;
        try { await api(`/api/admin/transfer-ownership/${user.id}`, { method: 'POST', body: { target_version: user.version, owner_version: state.me.user.version } }); closeModal(); toast('Ownership transferred. Reloading permissions.'); state.me = await api('/api/auth/me'); await refreshCurrentView(); } catch (error) { toast(error.message, 'error'); }
      });
      const save = async () => {
        const button = $('.save-user', root); setButtonBusy(button, true, 'Saving…');
        try {
          let result;
          if (user) {
            const body = { version: user.version, display_name: $('#user-name', root).value.trim(), is_active: $('#user-active', root)?.checked ?? user.is_active };
            if ($('#user-password', root).value) body.password = $('#user-password', root).value;
            result = await withConflict(current => api(`/api/admin/users/${user.id}`, { method: 'PATCH', body: current }), body, 'user');
          } else result = await api('/api/admin/users', { method: 'POST', body: { display_name: $('#user-name', root).value.trim(), email: $('#user-email', root).value.trim(), password: $('#user-password', root).value, is_admin: false } });
          if (!result) return;
          if (isSelf && result.user) state.me.user = result.user;
          closeModal(); toast(user ? 'User updated' : 'User created'); if (isSelf && $('#user-password', root)?.value) { showLogin(); return; } await renderMore();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.save-user', root).addEventListener('click', save); $('#user-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

async function openSessions() {
  let sessions;
  try { sessions = (await api('/api/auth/sessions')).sessions; } catch (error) { toast(error.message, 'error'); return; }
  openModal({
    title: 'Signed-in devices',
    body: `<p class="muted">Revoke any device you no longer recognize. The current browser is labeled below.</p>${sessions.map(session => `<div class="connection-card" data-session-id="${session.id}"><div class="connection-top"><div><strong>${session.current ? 'This device' : escapeHtml(session.user_agent || 'Unknown browser')}</strong><small>${escapeHtml(session.ip_address || 'Unknown address')} · Active ${escapeHtml(relativeTime(session.last_seen_at))}</small></div>${session.current ? '<span class="pill">Current</span>' : '<button class="button button--danger revoke-session" type="button">Sign out</button>'}</div></div>`).join('')}`,
    footer: '<button class="button modal-cancel" type="button">Close</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('.revoke-session', root).forEach(button => button.addEventListener('click', async () => {
        try { await api(`/api/auth/sessions/${button.closest('.connection-card').dataset.sessionId}`, { method: 'DELETE' }); button.closest('.connection-card').remove(); toast('Device signed out'); } catch (error) { toast(error.message, 'error'); }
      }));
    },
  });
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (error) { if (error.status !== 401) toast(error.message, 'error'); }
  state.me = null; state.budget = null; closeModal(); showLogin();
}

function openMonthPicker() {
  openModal({
    title: 'Choose budget month',
    body: `<label>Month<input id="month-picker" type="month" value="${escapeHtml(state.month)}"></label>`,
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary choose-month" type="button">Open month</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      const choose = async () => {
        const value = $('#month-picker', root).value;
        if (!/^\d{4}-\d{2}$/.test(value)) return;
        closeTray({ restoreFocus: false });
        clearTransactionListSelection();
        state.month = value; closeModal(); if (await loadBudget()) await renderCurrentView({ skipBudgetLoad: true });
      };
      $('.choose-month', root).addEventListener('click', choose);
      $('#month-picker', root).addEventListener('change', () => { state.formDirty = true; });
    },
  });
}

function handleLayeredBack({ returnToBudget = false } = {}) {
  try {
    if (state.cancelReorderDrag) {
      state.cancelReorderDrag();
      return 'handled';
    }
    if (state.cancelBubbleDrag) {
      state.cancelBubbleDrag();
      return 'handled';
    }
    if (state.modalOpen) {
      if (state.formDirty) return 'dirty';
      closeModal();
      return 'handled';
    }
    if (selectedTrayTransactionIds().length) {
      clearBubbleSelection();
      return 'handled';
    }
    if (selectedListTransactions().length) {
      clearTransactionListSelection();
      return 'handled';
    }
    if (state.trayOpen) {
      closeTray();
      return 'handled';
    }
    if (returnToBudget && state.me && state.view !== 'budget') {
      void setView('budget').catch(error => {
        if (error.status !== 401) toast(error.message || 'Could not open the budget.', 'error');
      });
      return 'handled';
    }
  } catch (error) {
    console.error('Could not handle back navigation.', error);
  }
  return 'unhandled';
}

// The Android host calls these synchronously and decides whether to consume the
// system Back event or show its own discard-changes confirmation.
window.mosaicAndroidBack = () => handleLayeredBack({ returnToBudget: true });
window.mosaicAndroidDiscardChanges = () => {
  if (!state.modalOpen) return 'unhandled';
  closeModal();
  return 'handled';
};

function connectEvents() {
  state.eventSource?.close();
  const source = new EventSource('/api/events', { withCredentials: true });
  state.eventSource = source;
  const scheduleRefresh = () => {
    clearTimeout(state.eventReloadTimer);
    const reload = async () => {
      if (state.formDirty || state.dragInProgress || state.assignmentInFlight || state.bulkTransactionInFlight) {
        state.eventReloadTimer = setTimeout(reload, 650);
        return;
      }
      try { await refreshCurrentView(); } catch { /* ordinary API handler reports meaningful failures */ }
    };
    state.eventReloadTimer = setTimeout(reload, 650);
  };
  source.addEventListener('ready', scheduleRefresh);
  source.addEventListener('change', scheduleRefresh);
  source.addEventListener('tick', () => { syncPill(); if (state.trayOpen) scheduleRefresh(); });
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED && state.me) setTimeout(connectEvents, 5000);
  };
}

async function enterApplication() {
  state.me = await api('/api/auth/me');
  const defaultMonth = state.me.user.preferences?.default_month;
  if (/^\d{4}-\d{2}$/.test(defaultMonth || '')) state.month = defaultMonth;
  document.body.dataset.theme = state.me.user.theme || 'citrus';
  document.body.dataset.density = state.me.user.preferences?.density || 'comfortable';
  document.body.dataset.motion = state.me.user.preferences?.motion || 'full';
  showApp();
  await loadBudget();
  await renderCurrentView({ skipBudgetLoad: true });
  connectEvents();
}

async function initialize() {
  hydrateIcons();
  installReorderDrag();
  $$('.nav-item').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  $('#brand-button').addEventListener('click', () => setView('budget'));
  $('#avatar-button').addEventListener('click', () => setView('more'));
  $('#sync-status').addEventListener('click', () => setView('more'));
  $('#month-prev').addEventListener('click', async () => { closeTray({ restoreFocus: false }); clearTransactionListSelection(); state.month = addMonths(state.month, -1); if (await loadBudget()) await renderCurrentView({ skipBudgetLoad: true }); });
  $('#month-next').addEventListener('click', async () => { closeTray({ restoreFocus: false }); clearTransactionListSelection(); state.month = addMonths(state.month, 1); if (await loadBudget()) await renderCurrentView({ skipBudgetLoad: true }); });
  $('#month-label').addEventListener('click', openMonthPicker);
  $('#inbox-button').addEventListener('click', openTray);
  $('#tray-close').addEventListener('click', () => closeTray());
  $('#scrim').addEventListener('click', () => closeTray());
  $('#tray-clear-selection').addEventListener('click', clearBubbleSelection);
  $('#tray-assign-selection').addEventListener('click', openSelectedAssignment);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || state.modalOpen) return;
    if (handleLayeredBack() === 'handled') event.preventDefault();
  });

  $('#login-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('#login-form button[type="submit"]');
    const errorNode = $('#login-error'); errorNode.textContent = ''; setButtonBusy(button, true, 'Signing in…');
    try {
      await api('/api/auth/login', { method: 'POST', body: { email: $('#login-email').value.trim(), password: $('#login-password').value } });
      $('#login-password').value = '';
      await enterApplication();
    } catch (error) { errorNode.textContent = error.message; } finally { setButtonBusy(button, false); }
  });

  try { await enterApplication(); }
  catch (error) {
    if (error.status !== 401) {
      $('#boot-screen').innerHTML = `<div class="empty-state"><strong>Mosaic could not start</strong>${escapeHtml(error.message)}</div>`;
    }
  }

  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}

initialize();

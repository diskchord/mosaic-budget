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
  rules: [],
  users: [],
  incidents: [],
  operations: null,
  trayOpen: false,
  modalOpen: false,
  formDirty: false,
  eventSource: null,
  eventReloadTimer: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ICONS = {
  budget: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 19V9M10 19V4M16 19v-7M22 19H2"/></svg>',
  transactions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M7 7h11l-3-3M17 17H6l3 3M18 7l-3 3M6 17l3-3"/></svg>',
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
  if (response.status === 401) {
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
  if (action) $('button', node).addEventListener('click', () => { action.run(); node.remove(); });
  $('#toast-root').append(node);
  setTimeout(() => node.remove(), action ? 7000 : 4200);
}

function setButtonBusy(button, busy, label = 'Working…') {
  if (!button) return;
  if (busy) { button.dataset.original = button.textContent; button.disabled = true; button.textContent = label; }
  else { button.disabled = false; button.textContent = button.dataset.original || button.textContent; }
}

function openModal({ title, body, footer = '', className = '', onMount = null }) {
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
  document.addEventListener('keydown', modalEscape, { once: true });
  hydrateIcons(root);
  if (onMount) onMount(root);
  setTimeout(() => $('input, select, textarea, button', $('.modal-body', root))?.focus(), 20);
  return root;
}

function modalEscape(event) {
  if (event.key === 'Escape' && state.modalOpen && !state.formDirty) closeModal();
  else if (state.modalOpen) document.addEventListener('keydown', modalEscape, { once: true });
}

function closeModal() {
  $('#modal-root').innerHTML = '';
  state.modalOpen = false;
  state.formDirty = false;
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
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === state.view));
  $('#month-control').classList.toggle('hidden', !['budget', 'transactions', 'rules'].includes(state.view));
  $('#inbox-button').classList.toggle('hidden', !state.budget?.unassigned?.length || state.view !== 'budget');
  $('#inbox-count').textContent = state.budget?.unassigned?.length || 0;
}

async function setView(view) {
  state.view = view;
  if (view !== 'transactions') state.transactionCategory = null;
  updateNavigation();
  await renderCurrentView();
  $('#app-view').focus({ preventScroll: true });
}

function loadingView() {
  $('#app-view').innerHTML = '<div class="skeleton"></div><div class="skeleton" style="margin-top:14px"></div><div class="skeleton" style="margin-top:14px"></div>';
}

async function loadBudget({ silent = false } = {}) {
  if (!silent) loadingView();
  state.budget = await api(`/api/budget?month=${encodeURIComponent(state.month)}`);
  $('#month-label').textContent = monthLabel(state.month);
  syncPill();
  updateNavigation();
  renderTray();
}

async function refreshCurrentView() {
  try {
    await loadBudget({ silent: true });
    await renderCurrentView({ skipBudgetLoad: true });
  } catch (error) { if (error.status !== 401) toast(error.message, 'error'); }
}

async function renderCurrentView({ skipBudgetLoad = false } = {}) {
  try {
    if (!state.budget && !skipBudgetLoad) await loadBudget();
    if (state.view === 'budget') renderBudget();
    else if (state.view === 'transactions') await renderTransactions();
    else if (state.view === 'rules') await renderRules();
    else await renderMore();
    updateNavigation();
    hydrateIcons($('#app-view'));
  } catch (error) {
    if (error.status !== 401) {
      $('#app-view').innerHTML = `<div class="empty-state"><strong>Unable to load this screen</strong>${escapeHtml(error.message)}</div>`;
      toast(error.message, 'error');
    }
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

function accountById(id) { return state.budget?.accounts?.find(account => account.id === id) || null; }
function transactionById(id) {
  return state.budget?.unassigned?.find(item => item.id === id) || state.transactions.find(item => item.id === id) || null;
}

function renderBudget() {
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
      const ratio = planned > 0n ? Math.max(0, Math.min(1.25, Number(used * 10000n / planned) / 10000)) : (used > 0n ? 1.25 : 0);
      const over = !section.is_income && remaining < 0n;
      return `<article class="category-row" data-category-id="${category.id}" data-section-id="${section.id}">
        <div class="category-main" role="button" tabindex="0" aria-label="View ${escapeHtml(category.name)} transactions">
          <div class="category-name"><span>${escapeHtml(category.name)}</span>${category.rollover ? '<span class="fund-badge">Fund</span>' : ''}</div>
          <div class="category-sub">${section.is_income ? `${money(category.activity)} received` : `${money(unitsToString(used))} used`}</div>
        </div>
        <button class="category-money budget-edit ${over ? 'over' : ''}" type="button" data-category-id="${category.id}" aria-label="Edit ${escapeHtml(category.name)} planned amount">
          <b>${money(category.remaining)}</b><span>of ${money(category.planned)}</span>
        </button>
        <button class="icon-button edit-category" data-category-id="${category.id}" type="button" aria-label="Edit ${escapeHtml(category.name)} category"><span data-icon="pencil"></span></button>
        <div class="progress-track" aria-hidden="true"><div class="progress-bar ${over ? 'over' : ''}" style="width:${Math.min(100, ratio * 100)}%"></div></div>
      </article>`;
    }).join('');
    return `<section class="section-card ${section.is_income ? 'income' : ''} ${collapsed ? 'collapsed' : ''}" data-section-id="${section.id}">
      <header class="section-header">
        <span class="section-icon" data-icon="${escapeHtml(section.icon || 'wallet')}"></span>
        <button class="section-title collapse-section" data-section-id="${section.id}" type="button" aria-expanded="${collapsed ? 'false' : 'true'}" aria-label="${collapsed ? 'Expand' : 'Collapse'} ${escapeHtml(section.name)}"><h2>${escapeHtml(section.name)}</h2><small>${section.categories.length} categor${section.categories.length === 1 ? 'y' : 'ies'}</small></button>
        <div class="section-actions"><button class="icon-button collapse-section collapse-chevron" data-section-id="${section.id}" type="button" aria-expanded="${collapsed ? 'false' : 'true'}" aria-label="${collapsed ? 'Expand' : 'Collapse'} ${escapeHtml(section.name)}">⌄</button><button class="icon-button edit-section" data-section-id="${section.id}" type="button" aria-label="Edit ${escapeHtml(section.name)}"><span data-icon="pencil"></span></button></div>
      </header>
      <div class="category-list">${categories || '<div class="empty-state" style="border:0;border-radius:0">No categories yet.</div>'}</div>
      <button class="add-category" data-section-id="${section.id}" type="button">+ Add category</button>
    </section>`;
  }).join('');

  $('#app-view').innerHTML = `
    <header class="view-header"><div><h1>${monthLabel(state.month)}</h1><p>Give every planned dollar a job.</p></div><div class="view-actions"><button class="button button--soft add-manual" type="button">+ Cash transaction</button></div></header>
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
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary modal-save" type="button">Save</button>',
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
            await withConflict(current => api(`/api/categories/${found.id}`, { method: 'PATCH', body: current }), body, 'category');
          } else {
            body.starts_month = readStartMonth(root, 'category');
            await api('/api/categories', { method: 'POST', body });
          }
          closeModal(); await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      };
      $('.modal-save', root).addEventListener('click', save);
      $('#category-form', root).addEventListener('submit', event => { event.preventDefault(); save(); });
    },
  });
}

function renderTray() {
  const container = $('#transaction-bubbles');
  if (!container || !state.budget) return;
  const rows = state.budget.unassigned || [];
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><strong>Everything is sorted</strong>New imported transactions will appear here automatically.</div>';
    return;
  }
  container.innerHTML = rows.map(transaction => {
    const inflow = toUnits(transaction.amount) > 0n;
    return `<button class="tx-bubble" type="button" data-transaction-id="${transaction.id}" aria-label="Assign ${escapeHtml(transaction.payee)}, ${escapeHtml(money(transaction.amount))}">
      <strong>${escapeHtml(transaction.payee || transaction.imported_description || 'Transaction')}</strong>
      <span class="amount ${inflow ? 'inflow' : ''}">${money(transaction.amount, { plus: true })}</span>
      <small>${escapeHtml(transaction.account_name)} · ${escapeHtml(formatDate(transaction.effective_date))}</small>
      ${transaction.pending ? '<span class="pending-badge">Pending</span>' : ''}
    </button>`;
  }).join('');
  $$('.tx-bubble', container).forEach(bubble => {
    bubble.addEventListener('click', event => {
      if (bubble.dataset.dragged === 'true') { bubble.dataset.dragged = 'false'; return; }
      openTransactionEditor(bubble.dataset.transactionId);
    });
  });
}

function openTray() {
  if (!state.budget?.unassigned?.length) return;
  state.trayOpen = true;
  renderTray();
  $('#transaction-tray').classList.add('open');
  $('#transaction-tray').setAttribute('aria-hidden', 'false');
  $('#scrim').classList.remove('hidden');
  document.body.classList.add('sheet-open');
}

function closeTray() {
  state.trayOpen = false;
  $('#transaction-tray').classList.remove('open', 'dragging');
  $('#transaction-tray').setAttribute('aria-hidden', 'true');
  $('#scrim').classList.add('hidden');
  document.body.classList.remove('sheet-open');
}

async function assignTransaction(transactionId, categoryId) {
  const transaction = transactionById(transactionId);
  const category = categoryById(categoryId);
  if (!transaction || !category) return;
  const localBody = {
    version: transaction.version,
    allocations: [{ category_id: category.id, amount: transaction.amount, memo: '' }],
  };
  try {
    const result = await withConflict(
      body => api(`/api/transactions/${transaction.id}/allocations`, { method: 'PUT', body }),
      localBody,
      'category assignment',
    );
    if (!result) return;
    closeTray();
    toast(`${transaction.payee} assigned to ${category.name}`, 'default', {
      label: 'Undo',
      run: async () => {
        try {
          await api(`/api/transactions/${transaction.id}/allocations`, {
            method: 'PUT',
            body: { version: result.transaction.version, allocations: [] },
          });
          await refreshCurrentView();
        } catch (error) { toast(error.message, 'error'); }
      },
    });
    await refreshCurrentView();
  } catch (error) {
    if (error.status !== 401) toast(error.message, 'error');
  }
}

function installBubbleDrag() {
  const container = $('#transaction-bubbles');
  if (!container || container.dataset.dragInstalled === 'true') return;
  container.dataset.dragInstalled = 'true';
  let drag = null;

  const clean = () => {
    if (!drag) return;
    drag.ghost?.remove();
    drag.bubble?.releasePointerCapture?.(drag.pointerId);
    drag.bubble?.classList.remove('is-dragging');
    $$('.category-row.drop-target').forEach(row => row.classList.remove('drop-target'));
    $('#transaction-tray').classList.remove('dragging');
    drag = null;
  };

  const moveGhost = (x, y) => {
    if (!drag?.ghost) return;
    drag.ghost.style.transform = `translate3d(${x - drag.offsetX}px, ${y - drag.offsetY}px, 0)`;
  };

  container.addEventListener('pointerdown', event => {
    const bubble = event.target.closest('.tx-bubble');
    if (!bubble || event.button !== 0) return;
    const rect = bubble.getBoundingClientRect();
    drag = {
      bubble,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: Math.min(rect.width - 12, Math.max(12, event.clientX - rect.left)),
      offsetY: Math.min(rect.height - 12, Math.max(12, event.clientY - rect.top)),
      active: false,
      target: null,
      ghost: null,
    };
    bubble.setPointerCapture?.(event.pointerId);
  });

  container.addEventListener('pointermove', event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (!drag.active && distance < 9) return;
    event.preventDefault();
    if (!drag.active) {
      drag.active = true;
      drag.bubble.dataset.dragged = 'true';
      drag.bubble.classList.add('is-dragging');
      drag.ghost = drag.bubble.cloneNode(true);
      drag.ghost.className = 'drag-ghost';
      drag.ghost.style.width = `${drag.bubble.getBoundingClientRect().width}px`;
      document.body.append(drag.ghost);
      $('#transaction-tray').classList.add('dragging');
    }
    moveGhost(event.clientX, event.clientY);
    $$('.category-row.drop-target').forEach(row => row.classList.remove('drop-target'));
    const hit = document.elementFromPoint(event.clientX, event.clientY)?.closest('.category-row');
    drag.target = hit || null;
    hit?.classList.add('drop-target');

    const edge = 72;
    if (event.clientY < edge) window.scrollBy({ top: -14, behavior: 'auto' });
    else if (event.clientY > window.innerHeight - edge) window.scrollBy({ top: 14, behavior: 'auto' });
  }, { passive: false });

  const finish = async event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const transactionId = drag.bubble.dataset.transactionId;
    const categoryId = drag.target?.dataset.categoryId;
    const wasActive = drag.active;
    clean();
    if (wasActive && categoryId) await assignTransaction(transactionId, categoryId);
  };
  container.addEventListener('pointerup', finish);
  container.addEventListener('pointercancel', clean);
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

function transactionCard(transaction) {
  const inflow = toUnits(transaction.amount) > 0n;
  const symbol = (transaction.payee || '?').trim().slice(0, 1).toUpperCase();
  const badges = [
    transaction.pending ? '<span class="pending-badge">Pending</span>' : '',
    transaction.needs_review ? '<span class="review-badge">Review</span>' : '',
  ].join('');
  return `<article class="transaction-card" tabindex="0" role="button" data-transaction-id="${transaction.id}">
    <div class="transaction-symbol ${inflow ? 'inflow' : ''}">${escapeHtml(symbol)}</div>
    <div class="transaction-copy"><strong>${escapeHtml(transaction.payee || transaction.imported_description || 'Transaction')} ${badges}</strong><small>${escapeHtml(formatDate(transaction.effective_date))} · ${escapeHtml(transaction.account_name)} · ${escapeHtml(transactionCategoryText(transaction))}</small></div>
    <div class="transaction-amount ${inflow ? 'inflow' : ''}">${money(transaction.amount, { plus: true })}<small>${transaction.source_kind === 'manual' ? 'Manual' : 'Synced'}</small></div>
  </article>`;
}

async function renderTransactions() {
  const params = new URLSearchParams({ month: state.month, status: state.transactionStatus, limit: '300' });
  if (state.transactionSearch) params.set('search', state.transactionSearch);
  if (state.transactionCategory) params.set('category_id', state.transactionCategory);
  const result = await api(`/api/transactions?${params}`);
  state.transactions = result.transactions;
  const category = state.transactionCategory ? categoryById(state.transactionCategory) : null;
  const title = category ? category.name : 'Transactions';
  const filters = [
    ['active', 'All'], ['unassigned', 'Unassigned'], ['assigned', 'Assigned'], ['review', 'Needs review'], ['pending', 'Pending'], ['excluded', 'Excluded'], ['trash', 'Trash'],
  ];
  $('#app-view').innerHTML = `
    <header class="view-header"><div><h1>${escapeHtml(title)}</h1><p>${category ? `${escapeHtml(category.section.name)} · ${monthLabel(state.month)}` : 'Search, review, split, or recategorize every entry.'}</p></div><div class="view-actions"><button class="button button--primary add-manual" type="button">+ Add transaction</button></div></header>
    <div class="toolbar">
      <label class="search-field"><span data-icon="search"></span><input id="transaction-search" type="search" placeholder="Search payee, source text, or note" value="${escapeHtml(state.transactionSearch)}"></label>
      <div class="filter-row">${filters.map(([value, label]) => `<button class="filter-chip ${state.transactionStatus === value ? 'active' : ''}" type="button" data-filter="${value}">${label}</button>`).join('')}${category ? '<button class="filter-chip clear-category" type="button">Clear category filter ×</button>' : ''}</div>
    </div>
    <div class="transaction-list">${state.transactions.map(transactionCard).join('') || '<div class="empty-state"><strong>No matching transactions</strong>Try another filter or add a manual cash transaction.</div>'}</div>`;
  hydrateIcons($('#app-view'));
  $('.add-manual', $('#app-view')).addEventListener('click', openManualTransaction);
  $$('.filter-chip[data-filter]', $('#app-view')).forEach(button => button.addEventListener('click', async () => {
    state.transactionStatus = button.dataset.filter;
    await renderTransactions();
  }));
  $('.clear-category', $('#app-view'))?.addEventListener('click', async () => { state.transactionCategory = null; await renderTransactions(); });
  let searchTimer;
  $('#transaction-search', $('#app-view')).addEventListener('input', event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => { state.transactionSearch = event.target.value.trim(); await renderTransactions(); }, 260);
  });
  $$('.transaction-card', $('#app-view')).forEach(card => {
    const open = () => openTransactionEditor(card.dataset.transactionId);
    card.addEventListener('click', open);
    card.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } });
  });
}

function signedInputForTransaction(transaction, raw) {
  const absolute = raw.trim();
  if (!absolute) return '0';
  const units = toUnits(absolute);
  const transactionUnits = toUnits(transaction.amount);
  return unitsToString(transactionUnits < 0n ? -(units < 0n ? -units : units) : (units < 0n ? -units : units));
}

function allocationEditorRows(transaction, allocations = transaction.allocations || []) {
  return allocations.map(allocation => `<div class="split-row">
    <select class="allocation-category" aria-label="Category">${categoryOptions(allocation.category_id)}</select>
    <input class="allocation-amount" inputmode="decimal" aria-label="Amount" value="${escapeHtml(unitsToString(toUnits(allocation.amount) < 0n ? -toUnits(allocation.amount) : toUnits(allocation.amount)))}">
    <button class="icon-button remove-allocation" type="button" aria-label="Remove split">×</button>
  </div>`).join('');
}

function allocationTotals(root, transaction) {
  const rows = $$('.split-row', root);
  let total = 0n;
  let invalid = false;
  rows.forEach(row => {
    try { total += toUnits(signedInputForTransaction(transaction, $('.allocation-amount', row).value)); }
    catch { invalid = true; }
  });
  const target = toUnits(transaction.amount);
  const remainder = target - total;
  const node = $('.split-summary', root);
  if (node) node.innerHTML = `<span>${invalid ? 'Check an amount' : `Allocated ${money(unitsToString(total))}`}</span><span class="${remainder === 0n ? 'positive' : 'warning'}">${remainder === 0n ? 'Balanced' : `${money(unitsToString(remainder))} remaining`}</span>`;
  return { total, target, remainder, invalid };
}

function bindAllocationRows(root, transaction) {
  const table = $('.split-table', root);
  const bindRow = row => {
    $('.remove-allocation', row).addEventListener('click', () => { row.remove(); allocationTotals(root, transaction); state.formDirty = true; });
    $$('input,select', row).forEach(control => control.addEventListener('input', () => { allocationTotals(root, transaction); state.formDirty = true; }));
  };
  $$('.split-row', table).forEach(bindRow);
  $('.add-allocation', root).addEventListener('click', () => {
    const row = document.createElement('div');
    row.className = 'split-row';
    row.innerHTML = `<select class="allocation-category" aria-label="Category">${categoryOptions()}</select><input class="allocation-amount" inputmode="decimal" aria-label="Amount" value=""><button class="icon-button remove-allocation" type="button" aria-label="Remove split">×</button>`;
    table.append(row); bindRow(row); $('.allocation-amount', row).focus(); state.formDirty = true; allocationTotals(root, transaction);
  });
  $('.assign-remainder', root).addEventListener('click', () => {
    const totals = allocationTotals(root, transaction);
    const rows = $$('.split-row', root);
    if (!rows.length) $('.add-allocation', root).click();
    const targetRow = $$('.split-row', root).at(-1);
    const current = (() => { try { return toUnits(signedInputForTransaction(transaction, $('.allocation-amount', targetRow).value || '0')); } catch { return 0n; } })();
    const next = current + totals.remainder;
    $('.allocation-amount', targetRow).value = unitsToString(next < 0n ? -next : next);
    allocationTotals(root, transaction); state.formDirty = true;
  });
  allocationTotals(root, transaction);
}

async function openTransactionEditor(transactionId) {
  let transaction;
  try {
    transaction = (await api(`/api/transactions/${transactionId}`)).transaction;
  } catch (error) { toast(error.message, 'error'); return; }
  closeTray();
  const inflow = toUnits(transaction.amount) > 0n;
  const deleted = !!transaction.deleted_at;
  openModal({
    title: deleted ? 'Transaction in Trash' : 'Transaction details',
    className: 'modal--wide',
    body: `<div class="transaction-hero">
      <div><h3>${escapeHtml(transaction.payee)}</h3><p>${escapeHtml(transaction.account_name)} · ${escapeHtml(formatDate(transaction.effective_date))}${transaction.pending ? ' · Pending' : ''}</p></div>
      <div class="hero-amount ${inflow ? 'positive' : ''}">${money(transaction.amount, { plus: true })}</div>
    </div>
    ${deleted ? `<div class="delete-warning">Deleted ${escapeHtml(relativeTime(transaction.deleted_at))}. It is excluded from budgets and will not be recreated by synchronization.</div>` : `<form id="transaction-form" class="form-grid">
      <label>Payee<input id="transaction-payee" value="${escapeHtml(transaction.payee)}" required maxlength="500"></label>
      <label>Budget date<input id="transaction-date" type="date" value="${escapeHtml(transaction.effective_date)}" required></label>
      <label class="full">Note<textarea id="transaction-note" maxlength="10000">${escapeHtml(transaction.note || '')}</textarea></label>
      <label class="full"><span><input id="transaction-review" type="checkbox" style="width:auto;min-height:auto" ${transaction.needs_review ? 'checked' : ''}> Keep in Needs Review</span></label>
      <label class="full"><span><input id="transaction-excluded" type="checkbox" style="width:auto;min-height:auto" ${transaction.excluded ? 'checked' : ''}> Exclude from budget totals</span></label>
    </form>
    <div class="form-section">
      <div class="button-row" style="justify-content:space-between"><div><strong>Category allocation</strong><p class="muted" style="margin:3px 0">Use one row for a normal assignment or several rows to split it.</p></div><button class="button button--soft add-allocation" type="button">+ Split row</button></div>
      <div class="split-table">${allocationEditorRows(transaction)}</div>
      <div class="split-summary"></div>
      <button class="button button--ghost assign-remainder" type="button">Put remainder in last row</button>
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
      $$('input,textarea,select', root).forEach(control => control.addEventListener('input', () => { state.formDirty = true; }));
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
        const totals = allocationTotals(root, transaction);
        if (totals.invalid || ($$('.split-row', root).length && totals.remainder !== 0n)) {
          toast('Split rows must add up exactly to the transaction amount.', 'error'); return;
        }
        const button = $('.save-transaction', root); setButtonBusy(button, true, 'Saving…');
        try {
          const allocations = $$('.split-row', root).map(row => ({
            category_id: $('.allocation-category', row).value,
            amount: signedInputForTransaction(transaction, $('.allocation-amount', row).value),
            memo: '',
          }));
          const updated = await withConflict(body => api(`/api/transactions/${transaction.id}`, { method: 'PATCH', body }), {
            version: transaction.version,
            payee: $('#transaction-payee', root).value.trim(),
            effective_date: $('#transaction-date', root).value,
            allocations,
            note: $('#transaction-note', root).value,
            needs_review: $('#transaction-review', root).checked,
            excluded: $('#transaction-excluded', root).checked,
          }, 'transaction');
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
    footer: '<button class="button modal-cancel" type="button">Cancel</button><button class="button button--primary create-manual" type="button">Add transaction</button>',
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
      $('.create-manual', root).addEventListener('click', save);
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
  const value = Array.isArray(condition.value) ? condition.value.join(' and ') : condition.value;
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

function ruleCard(rule) {
  return `<article class="rule-card" data-rule-id="${rule.id}">
    <div class="rule-card-header"><div><h3>${escapeHtml(rule.name)}</h3><div class="rule-meta"><span class="pill">${escapeHtml(rule.phase)}</span><span class="pill">Priority ${rule.priority}</span>${rule.enabled ? '<span class="pill positive">On</span>' : '<span class="pill">Off</span>'}</div></div><button class="icon-button edit-rule" type="button" aria-label="Edit ${escapeHtml(rule.name)}"><span data-icon="pencil"></span></button></div>
    <div class="rule-sentence"><b>When:</b> ${escapeHtml(ruleConditionSummary(rule.conditions))}</div>
    <div class="rule-sentence"><b>Then:</b> ${escapeHtml(rule.actions.map(ruleActionSummary).join(', '))}</div>
  </article>`;
}

async function renderRules() {
  const result = await api('/api/rules');
  state.rules = result.rules;
  $('#app-view').innerHTML = `<header class="view-header"><div><h1>Rules</h1><p>Automatic cleanup for new imports; manual runs only process unsorted transactions in the selected month.</p></div><div class="view-actions"><button class="button button--soft run-rules" type="button">Run rules</button><button class="button button--primary add-rule" type="button">+ New rule</button></div></header>
    <div class="rule-list">${state.rules.map(ruleCard).join('') || '<div class="empty-state"><strong>No rules yet</strong>Create a rule from a transaction or build one here. Rules run automatically during every import.</div>'}</div>`;
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
      if (sorted) toast(`Sorted ${sorted} of ${scanned} unsorted transaction${scanned === 1 ? '' : 's'} in ${monthLabel(runMonth)}`);
      else if (changed) toast(`Updated ${changed} unsorted transaction${changed === 1 ? '' : 's'} in ${monthLabel(runMonth)}`);
      else toast(`No matching rule changes in ${monthLabel(runMonth)}`);
      await refreshCurrentView();
    } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
  });
  $('.add-rule', $('#app-view')).addEventListener('click', () => openRuleEditor());
  $$('.edit-rule', $('#app-view')).forEach(button => button.addEventListener('click', () => openRuleEditor(state.rules.find(rule => rule.id === button.closest('.rule-card').dataset.ruleId))));
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
    if (['one_of','not_one_of'].includes(operator)) {
      const selected = Array.isArray(condition.value) ? condition.value : [condition.value];
      return `<label class="condition-value">Accounts<select class="condition-value-input" multiple size="${Math.min(4, state.budget.accounts.length)}">${state.budget.accounts.map(account => `<option value="${account.id}" ${selected.includes(account.id) ? 'selected' : ''}>${escapeHtml(account.name)}</option>`).join('')}</select></label>`;
    }
    return `<label class="condition-value">Account<select class="condition-value-input">${state.budget.accounts.map(account => `<option value="${account.id}" ${condition.value === account.id ? 'selected' : ''}>${escapeHtml(account.name)}</option>`).join('')}</select></label>`;
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
    <label>Field<select class="condition-field">${Object.entries(RULE_FIELDS).map(([value,label]) => `<option value="${value}" ${condition.field === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label>
    <label>Comparison<select class="condition-operator">${operators.map(value => `<option value="${value}" ${condition.operator === value ? 'selected' : ''}>${escapeHtml(RULE_OPERATORS[value])}</option>`).join('')}</select></label>
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
    <label>Action<select class="action-type">${Object.entries(ACTION_LABELS).map(([value,label]) => `<option value="${value}" ${action.type === value ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label>
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
    title: rule ? `Edit ${rule.name}` : transaction ? `Rule for ${transaction.payee}` : 'Create a rule',
    className: 'modal--wide',
    body: `<form id="rule-form" class="rule-builder">
      <div class="form-grid"><label>Rule name<input id="rule-name" maxlength="180" required value="${escapeHtml(rule?.name || (transaction ? `${transaction.payee} → category` : ''))}"></label><label>Phase<select id="rule-phase"><option value="cleanup" ${rule?.phase === 'cleanup' ? 'selected' : ''}>1. Clean up</option><option value="categorize" ${!rule || rule.phase === 'categorize' ? 'selected' : ''}>2. Categorize</option><option value="finish" ${rule?.phase === 'finish' ? 'selected' : ''}>3. Finish and flag</option></select></label><label>Order within phase<input id="rule-priority" type="number" min="0" max="100000" value="${rule?.priority ?? 100}"></label><label><span><input id="rule-enabled" type="checkbox" style="width:auto;min-height:auto" ${rule?.enabled !== false ? 'checked' : ''}> Rule is enabled</span></label></div>
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
          $('.rule-preview', root).innerHTML = `<strong>${result.match_count_in_sample} matches</strong> in the newest ${result.sample_size} transactions.${result.transactions.length ? `<div style="margin-top:8px">${result.transactions.slice(0,5).map(item => `${escapeHtml(item.payee)} · ${money(item.amount)}`).join('<br>')}</div>` : ''}`;
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
          toast(changed ? `Rule saved and applied to ${changed} transactions` : 'Rule saved');
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
  if (admin) requests.push(api('/api/admin/users'), api('/api/admin/incidents'), api('/api/admin/operations'));
  const results = await Promise.all(requests);
  const connections = results[0].connections;
  const system = results[1];
  if (admin) {
    state.users = results[2].users; state.incidents = results[3].incidents; state.operations = results[4];
  }
  const themes = state.me.themes || Object.keys(THEME_META);
  const channelLabels = [state.me.notification_channels.smtp ? 'SMTP' : '', state.me.notification_channels.ntfy ? 'ntfy' : '', state.me.notification_channels.external_heartbeat ? 'external heartbeat' : ''].filter(Boolean);
  $('#app-view').innerHTML = `<header class="view-header"><div><h1>More</h1><p>Appearance, bank connections, people, and system reliability.</p></div></header>
    <div class="settings-grid">
      <section class="settings-card"><header><div><h2>${escapeHtml(state.me.user.display_name)}</h2><p>${escapeHtml(state.me.user.email)}${admin ? ' · Owner' : ''}</p></div><span class="avatar-button profile-avatar" aria-hidden="true">${escapeHtml(initials(state.me.user.display_name))}</span></header><div class="button-row"><button class="button button--soft sessions-button" type="button">Signed-in devices</button><button class="button logout-button" type="button">Sign out</button></div></section>
      <section class="settings-card"><header><div><h2>Your theme</h2><p>Appearance is saved independently for each user.</p></div></header><div class="theme-grid">${themes.map(theme => { const meta = THEME_META[theme] || { label: theme, colors: [] }; return `<button class="theme-choice ${state.me.user.theme === theme ? 'active' : ''}" data-theme-choice="${theme}" type="button"><span class="theme-swatches">${meta.colors.map(color => `<i style="--swatch:${color}"></i>`).join('')}</span><strong>${escapeHtml(meta.label)}</strong></button>`; }).join('')}</div>
        <div class="form-grid" style="margin-top:13px"><label>Layout density<select id="preference-density"><option value="comfortable" ${state.me.user.preferences?.density !== 'compact' ? 'selected' : ''}>Comfortable</option><option value="compact" ${state.me.user.preferences?.density === 'compact' ? 'selected' : ''}>Compact</option></select></label><label>Motion<select id="preference-motion"><option value="full" ${state.me.user.preferences?.motion !== 'reduced' ? 'selected' : ''}>Full</option><option value="reduced" ${state.me.user.preferences?.motion === 'reduced' ? 'selected' : ''}>Reduced</option></select></label></div>
      </section>
      <section class="settings-card"><header><div><h2>Bank connections</h2><p>SimpleFIN imports continue in the background; opening this page does not trigger a bank request.</p></div>${admin ? '<button class="button button--primary add-connection" type="button">+ Connect</button>' : ''}</header>
        <div class="connection-list">${connections.map(connection => `<div class="connection-card" data-connection-id="${connection.id}"><div class="connection-top"><div><strong>${escapeHtml(connection.name)}</strong><small>Every ${connection.sync_interval_minutes / 60} hours · Next ${escapeHtml(relativeTime(connection.next_sync_at))}</small></div><button class="icon-button connection-details" type="button">›</button></div><div class="health-line"><span class="status-dot"></span>${connectionHealthMarkup(connection)}</div>${connection.last_error_message ? `<p class="danger">${escapeHtml(connection.last_error_message)}</p>` : ''}</div>`).join('') || '<div class="empty-state"><strong>No bank connected</strong>Manual and cash budgeting still work. The owner can add SimpleFIN here.</div>'}</div>
      </section>
      <section class="settings-card"><header><div><h2>Accounts</h2><p>Balances shown are the latest values retained by Mosaic.</p></div></header>${state.budget.accounts.map(account => `<div class="connection-card"><div class="connection-top"><div><strong>${escapeHtml(account.name)}</strong><small>${escapeHtml(account.source_type === 'manual' ? 'Manual account' : 'SimpleFIN account')} · ${account.is_budget ? 'On budget' : 'Off budget'}</small></div><b>${money(account.balance)}</b></div></div>`).join('')}</section>
      ${admin ? `<section class="settings-card"><header><div><h2>People</h2><p>Multiple devices can be active at once. Conflicting edits require an explicit choice.</p></div><button class="button button--soft add-user" type="button">+ User</button></header><div class="user-list">${state.users.map(user => `<div class="user-row" data-user-id="${user.id}"><div><strong>${escapeHtml(user.display_name)} ${user.is_admin ? '<span class="pill">Owner</span>' : ''}</strong><small>${escapeHtml(user.email)} · ${user.is_active ? 'Active' : 'Disabled'}</small></div><button class="icon-button edit-user" type="button">›</button></div>`).join('')}</div></section>
      <section class="settings-card"><header><div><h2>Alerts</h2><p>${channelLabels.length ? `Delivery configured through ${escapeHtml(channelLabels.join(' and '))}.` : 'No external alert channel is currently enabled.'}</p></div><button class="button button--soft test-notifications" type="button">Send test</button></header><div class="incident-list">${state.incidents.map(incident => `<div class="incident-row"><div class="incident-top"><div><strong class="${incident.severity === 'critical' ? 'danger' : incident.severity === 'warning' ? 'warning' : ''}">${escapeHtml(incident.title)}</strong><small>${escapeHtml(relativeTime(incident.last_seen_at))} · Seen ${incident.occurrence_count} time${incident.occurrence_count === 1 ? '' : 's'}</small></div>${incident.acknowledged_at ? '<span class="pill">Acknowledged</span>' : `<button class="button button--ghost acknowledge-incident" data-incident-id="${incident.id}" type="button">Acknowledge</button>`}</div><p>${escapeHtml(incident.message)}</p></div>`).join('') || '<div class="empty-state"><strong>No open incidents</strong>Synchronization and background checks have not reported an unresolved problem.</div>'}</div></section>
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
  $('.add-user', $('#app-view'))?.addEventListener('click', () => openUserEditor());
  $$('.edit-user', $('#app-view')).forEach(button => button.addEventListener('click', () => openUserEditor(state.users.find(user => user.id === button.closest('.user-row').dataset.userId))));
  $$('.acknowledge-incident', $('#app-view')).forEach(button => button.addEventListener('click', async () => {
    try { await api(`/api/admin/incidents/${button.dataset.incidentId}/acknowledge`, { method: 'POST', body: { acknowledged: true } }); toast('Incident acknowledged'); await renderMore(); } catch (error) { toast(error.message, 'error'); }
  }));
  $('.test-notifications', $('#app-view'))?.addEventListener('click', async event => {
    setButtonBusy(event.currentTarget, true, 'Queueing…');
    try { await api('/api/admin/notifications/test', { method: 'POST' }); toast('Test alert queued for the background delivery worker'); } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(event.currentTarget, false); }
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
      <div class="form-section"><strong>Accounts</strong>${accounts.map(account => `<div class="connection-card"><div class="connection-top"><div><strong>${escapeHtml(account.name)} ${account.is_duplicate ? '<span class="pill">Duplicate</span>' : ''}</strong><small>${account.is_duplicate ? 'Transactions hidden' : (account.is_budget ? 'Included in budget' : 'Off budget')} · ${escapeHtml(account.currency)}</small></div><b>${money(account.balance)}</b></div></div>`).join('') || '<p class="muted">No accounts have been imported yet.</p>'}</div>
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
    body: `<div class="account-editor-list">${accounts.map(account => `<div class="connection-card" data-account-id="${account.id}"><label>Name<input class="account-name" value="${escapeHtml(account.name)}"></label><label><span><input class="account-duplicate" type="checkbox" style="width:auto;min-height:auto" ${account.is_duplicate ? 'checked' : ''}> This is a duplicate account</span><small class="duplicate-account-help">${account.is_duplicate ? 'Imported source history is retained, but its transactions are hidden and excluded from the budget.' : 'Mark this only when the same bank account is already imported through another connection.'}</small></label><div class="button-row"><label><span><input class="account-budget" type="checkbox" style="width:auto;min-height:auto" ${account.is_budget ? 'checked' : ''} ${account.is_duplicate ? 'disabled' : ''}> Include in budget</span></label><label><span><input class="account-active" type="checkbox" style="width:auto;min-height:auto" ${account.is_active ? 'checked' : ''} ${account.is_duplicate ? 'disabled' : ''}> Active</span></label></div><button class="button button--soft save-account" type="button">Save account</button></div>`).join('')}</div>`,
    footer: '<button class="button modal-cancel" type="button">Close</button>',
    onMount(root) {
      $('.modal-cancel', root).addEventListener('click', closeModal);
      $$('.account-duplicate', root).forEach(input => input.addEventListener('change', () => {
        const card = input.closest('.connection-card');
        $('.account-budget', card).disabled = input.checked;
        $('.account-active', card).disabled = input.checked;
        $('.duplicate-account-help', card).textContent = input.checked
          ? 'Imported source history is retained, but its transactions are hidden and excluded from the budget.'
          : 'Mark this only when the same bank account is already imported through another connection.';
      }));
      $$('.save-account', root).forEach(button => button.addEventListener('click', async () => {
        const card = button.closest('.connection-card'); const account = accounts.find(item => item.id === card.dataset.accountId);
        setButtonBusy(button, true, 'Saving…');
        try {
          const result = await withConflict(body => api(`/api/connections/accounts/${account.id}`, { method: 'PATCH', body }), { version: account.version, name: $('.account-name', card).value.trim(), is_budget: $('.account-budget', card).checked, is_active: $('.account-active', card).checked, is_duplicate: $('.account-duplicate', card).checked }, 'account');
          if (result) { Object.assign(account, result.account); toast(account.is_duplicate ? 'Duplicate account transactions hidden' : 'Account saved'); await refreshCurrentView(); }
        } catch (error) { toast(error.message, 'error'); } finally { setButtonBusy(button, false); }
      }));
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
        state.month = value; closeModal(); await loadBudget(); await renderCurrentView({ skipBudgetLoad: true });
      };
      $('.choose-month', root).addEventListener('click', choose);
      $('#month-picker', root).addEventListener('change', () => { state.formDirty = true; });
    },
  });
}

function connectEvents() {
  state.eventSource?.close();
  const source = new EventSource('/api/events', { withCredentials: true });
  state.eventSource = source;
  source.addEventListener('change', () => {
    clearTimeout(state.eventReloadTimer);
    state.eventReloadTimer = setTimeout(async () => {
      if (state.formDirty) return;
      try { await refreshCurrentView(); } catch { /* ordinary API handler reports meaningful failures */ }
    }, 650);
  });
  source.addEventListener('tick', () => syncPill());
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
  $$('.nav-item').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  $('#brand-button').addEventListener('click', () => setView('budget'));
  $('#avatar-button').addEventListener('click', () => setView('more'));
  $('#sync-status').addEventListener('click', () => setView('more'));
  $('#month-prev').addEventListener('click', async () => { state.month = addMonths(state.month, -1); await loadBudget(); await renderCurrentView({ skipBudgetLoad: true }); });
  $('#month-next').addEventListener('click', async () => { state.month = addMonths(state.month, 1); await loadBudget(); await renderCurrentView({ skipBudgetLoad: true }); });
  $('#month-label').addEventListener('click', openMonthPicker);
  $('#inbox-button').addEventListener('click', openTray);
  $('#tray-close').addEventListener('click', closeTray);
  $('#scrim').addEventListener('click', closeTray);

  $('#login-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('#login-form button[type="submit"]');
    const errorNode = $('#login-error'); errorNode.textContent = ''; setButtonBusy(button, true, 'Signing in…');
    try {
      await api('/api/auth/login', { method: 'POST', body: { email: $('#login-email').value.trim(), password: $('#login-password').value } });
      $('#login-password').value = '';
      await enterApplication();
    } catch (error) { if (error.status !== 401 || !state.me) errorNode.textContent = error.message; } finally { setButtonBusy(button, false); }
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

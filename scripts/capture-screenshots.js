#!/usr/bin/env node
'use strict';

/**
 * Capture Mosaic's desktop and mobile screenshot pack from a running,
 * disposable instance. Chromium must already be running with remote debugging:
 *
 *   chromium --headless=new --remote-debugging-port=9222 \
 *     --remote-allow-origins=* --user-data-dir="$(mktemp -d)" about:blank
 *
 * This script intentionally has no npm dependencies. Debian's Node 20 build
 * exposes undici.WebSocket, which is used to speak the Chrome DevTools Protocol.
 */

const fs = require('node:fs/promises');
const path = require('node:path');
const process = require('node:process');
const { WebSocket, fetch } = require('undici');

const DEFAULT_BANNED_TOKENS = Object.freeze([
  'acadia',
  'alex',
  'alexander',
  'blueberry',
  'camden',
  'central maine power',
  'diamond canine',
  'everyday checking',
  'fake example',
  'friday movie night',
  'hannaford',
  'harbor coffee',
  'maine',
  'mosaic-screenshot-fake',
  'penobscot',
  'peppe',
  'pine state',
  'rewards card',
]);

const READY_SELECTORS = Object.freeze({
  budget: '.summary-card',
  transactions: '.transaction-list',
  analytics: '.analytics-kpis',
  rules: '.rule-list',
  more: '.settings-grid',
});

const SCREENSHOTS = Object.freeze({
  budgetDesktop: '01-budget-desktop-citrus.png',
  trayDesktop: '02-sort-tray-desktop-meadow.png',
  dragDesktop: '03-group-drag-desktop-meadow.png',
  transactionsDesktop: '04-transactions-desktop-ocean.png',
  transactionDesktop: '05-transaction-detail-desktop-ocean.png',
  analyticsDesktop: '06-analytics-desktop-berry.png',
  rulesDesktop: '07-rules-desktop-sunrise.png',
  ruleDesktop: '08-rule-builder-desktop-sunrise.png',
  settingsDesktop: '09-settings-themes-desktop.png',
  budgetMobile: '10-budget-mobile-meadow.png',
  trayMobile: '11-sort-tray-mobile-meadow.png',
  manualMobile: '12-add-transaction-mobile.png',
  transactionsMobile: '13-transactions-mobile-ocean.png',
  analyticsMobile: '14-analytics-mobile-berry.png',
});

function usage() {
  return `Usage:
  node scripts/capture-screenshots.js [options]

Required credentials (CLI or environment):
  --email VALUE               MOSAIC_SCREENSHOT_EMAIL
  --password VALUE            MOSAIC_SCREENSHOT_PASSWORD

Connection and output options:
  --app-url URL               MOSAIC_SCREENSHOT_APP_URL
                              Default: http://127.0.0.1:8080
  --cdp-url URL               MOSAIC_SCREENSHOT_CDP_URL
                              Default: http://127.0.0.1:9222
  --output-dir PATH           MOSAIC_SCREENSHOT_OUTPUT_DIR
                              Default: artifacts/mosaic-screenshots
  --timeout-ms NUMBER         MOSAIC_SCREENSHOT_TIMEOUT_MS
                              Default: 20000

Privacy options:
  --banned-tokens CSV         MOSAIC_SCREENSHOT_BANNED_TOKENS
                              Replace the built-in case-insensitive list.
  --ban TOKEN                 Append one token; may be repeated.

Other:
  -h, --help                  Show this help.

Use only a disposable Mosaic instance populated with synthetic data. Passing a
fresh Chromium --user-data-dir avoids stale sessions and service-worker caches.
The password environment variable is preferred so it is not stored in shell
history.`;
}

function parseArgs(argv) {
  const options = { ban: [] };
  const valueOptions = new Set([
    'app-url', 'cdp-url', 'email', 'password', 'output-dir', 'timeout-ms',
    'banned-tokens', 'ban',
  ]);

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help' || argument === '-h') {
      options.help = true;
      continue;
    }
    if (!argument.startsWith('--')) throw new Error(`Unknown argument: ${argument}`);

    const equals = argument.indexOf('=');
    const key = argument.slice(2, equals === -1 ? undefined : equals);
    if (!valueOptions.has(key)) throw new Error(`Unknown option: --${key}`);
    const value = equals === -1 ? argv[++index] : argument.slice(equals + 1);
    if (value === undefined || value.startsWith('--')) throw new Error(`--${key} requires a value`);
    if (key === 'ban') options.ban.push(value);
    else options[key] = value;
  }
  return options;
}

function csvTokens(value) {
  return String(value ?? '')
    .split(',')
    .map(token => token.trim())
    .filter(Boolean);
}

function configuration(argv, env) {
  const options = parseArgs(argv);
  if (options.help) return { help: true };

  const customBanned = options['banned-tokens'] ?? env.MOSAIC_SCREENSHOT_BANNED_TOKENS;
  const bannedTokens = customBanned === undefined
    ? [...DEFAULT_BANNED_TOKENS]
    : csvTokens(customBanned);
  bannedTokens.push(...options.ban);

  const timeoutRaw = options['timeout-ms'] ?? env.MOSAIC_SCREENSHOT_TIMEOUT_MS ?? '20000';
  const timeoutMs = Number(timeoutRaw);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 300000) {
    throw new Error('--timeout-ms must be an integer from 1000 through 300000');
  }

  const config = {
    appUrl: options['app-url'] ?? env.MOSAIC_SCREENSHOT_APP_URL ?? 'http://127.0.0.1:8080',
    cdpUrl: options['cdp-url'] ?? env.MOSAIC_SCREENSHOT_CDP_URL ?? 'http://127.0.0.1:9222',
    email: options.email ?? env.MOSAIC_SCREENSHOT_EMAIL ?? '',
    password: options.password ?? env.MOSAIC_SCREENSHOT_PASSWORD ?? '',
    outputDir: path.resolve(options['output-dir'] ?? env.MOSAIC_SCREENSHOT_OUTPUT_DIR ?? 'artifacts/mosaic-screenshots'),
    bannedTokens: [...new Set(bannedTokens.map(token => token.trim()).filter(Boolean))],
    timeoutMs,
  };

  for (const [name, value] of [['--app-url', config.appUrl], ['--cdp-url', config.cdpUrl]]) {
    let parsed;
    try { parsed = new URL(value); }
    catch { throw new Error(`${name} must be a valid URL`); }
    const allowed = name === '--cdp-url' ? ['http:', 'https:', 'ws:', 'wss:'] : ['http:', 'https:'];
    if (!allowed.includes(parsed.protocol)) throw new Error(`${name} must use ${allowed.join(' or ')}`);
  }
  if (!config.email) throw new Error('Provide --email or MOSAIC_SCREENSHOT_EMAIL');
  if (!config.password) throw new Error('Provide --password or MOSAIC_SCREENSHOT_PASSWORD');
  return config;
}

function delay(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

class CdpClient {
  constructor(socket, timeoutMs) {
    this.socket = socket;
    this.timeoutMs = timeoutMs;
    this.nextId = 1;
    this.pending = new Map();
    this.runtimeExceptions = [];

    socket.addEventListener('message', event => this.onMessage(event));
    socket.addEventListener('close', () => this.rejectPending(new Error('Chromium closed the CDP connection')));
    socket.addEventListener('error', () => this.rejectPending(new Error('Chromium CDP WebSocket failed')));
  }

  onMessage(event) {
    let message;
    try {
      const raw = typeof event.data === 'string'
        ? event.data
        : Buffer.from(event.data).toString('utf8');
      message = JSON.parse(raw);
    } catch (error) {
      this.rejectPending(new Error(`Could not decode a CDP message: ${error.message}`));
      return;
    }

    if (message.method === 'Runtime.exceptionThrown') {
      const details = message.params?.exceptionDetails;
      this.runtimeExceptions.push(details?.exception?.description || details?.text || 'Unknown page exception');
      return;
    }
    if (!message.id) return;
    const pending = this.pending.get(message.id);
    if (!pending) return;
    this.pending.delete(message.id);
    clearTimeout(pending.timer);
    if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message}`));
    else pending.resolve(message.result || {});
  }

  rejectPending(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timed out after ${this.timeoutMs} ms`));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer, method });
      try { this.socket.send(JSON.stringify({ id, method, params })); }
      catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  close() {
    try { this.socket.close(); } catch { /* The browser may already be gone. */ }
  }
}

async function discoverWebSocket(cdpUrl, appUrl) {
  const supplied = new URL(cdpUrl);
  if (supplied.protocol === 'ws:' || supplied.protocol === 'wss:') return supplied.href;

  const root = new URL('/', supplied);
  const listUrl = new URL('json/list', root);
  let response;
  try { response = await fetch(listUrl); }
  catch (error) { throw new Error(`Could not reach Chromium at ${listUrl.href}: ${error.message}`); }
  if (!response.ok) throw new Error(`Chromium target discovery failed (${response.status}) at ${listUrl.href}`);
  let targets = await response.json();
  const appOrigin = new URL(appUrl).origin;
  let target = targets.find(item => item.type === 'page' && String(item.url).startsWith(appOrigin))
    || targets.find(item => item.type === 'page' && item.url === 'about:blank')
    || targets.find(item => item.type === 'page');

  if (!target) {
    const createUrl = new URL(`json/new?${encodeURIComponent('about:blank')}`, root);
    response = await fetch(createUrl, { method: 'PUT' });
    if (!response.ok) throw new Error(`Chromium could not create a page target (${response.status})`);
    target = await response.json();
    targets = [...targets, target];
  }
  if (!target.webSocketDebuggerUrl) throw new Error('Chromium returned a page without a WebSocket debugger URL');
  return target.webSocketDebuggerUrl;
}

async function connectCdp(webSocketUrl, timeoutMs) {
  const socket = new WebSocket(webSocketUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`CDP WebSocket connection timed out after ${timeoutMs} ms`)), timeoutMs);
    socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
    socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Could not open the CDP WebSocket')); }, { once: true });
  });
  return new CdpClient(socket, timeoutMs);
}

class MosaicCapture {
  constructor(client, config) {
    this.client = client;
    this.config = config;
    this.mobile = false;
    this.captures = new Map();
  }

  async evaluate(expression, { awaitPromise = true } = {}) {
    const response = await this.client.send('Runtime.evaluate', {
      expression,
      awaitPromise,
      returnByValue: true,
      userGesture: true,
    });
    if (response.exceptionDetails) {
      const details = response.exceptionDetails;
      throw new Error(details.exception?.description || details.text || 'Browser evaluation failed');
    }
    return response.result?.value;
  }

  async waitUntil(expression, description, timeoutMs = this.config.timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    let lastError = null;
    while (Date.now() < deadline) {
      try {
        if (await this.evaluate(`Boolean(${expression})`)) return;
        lastError = null;
      } catch (error) { lastError = error; }
      await delay(80);
    }
    const suffix = lastError ? ` Last browser error: ${lastError.message}` : '';
    throw new Error(`Timed out waiting for ${description}.${suffix}`);
  }

  async waitFor(selector, description = selector) {
    await this.waitUntil(`document.querySelector(${JSON.stringify(selector)})`, description);
  }

  async click(selector) {
    const clicked = await this.evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return false;
      element.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      element.click();
      return true;
    })()`);
    if (!clicked) throw new Error(`Could not find element to click: ${selector}`);
  }

  async clickFirst(selector, count) {
    const clicked = await this.evaluate(`(() => {
      const elements = [...document.querySelectorAll(${JSON.stringify(selector)})].slice(0, ${count});
      elements.forEach(element => element.click());
      return elements.length;
    })()`);
    if (clicked !== count) throw new Error(`Expected ${count} elements for ${selector}, found ${clicked}`);
  }

  async setValue(selector, value, { change = true } = {}) {
    const updated = await this.evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return false;
      element.value = ${JSON.stringify(value)};
      element.dispatchEvent(new Event('input', { bubbles: true }));
      ${change ? "element.dispatchEvent(new Event('change', { bubbles: true }));" : ''}
      return true;
    })()`);
    if (!updated) throw new Error(`Could not find field: ${selector}`);
  }

  async selectByText(selector, label) {
    const selected = await this.evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return { ok: false, reason: 'missing select' };
      const option = [...element.options].find(item => item.textContent.trim() === ${JSON.stringify(label)});
      if (!option) return { ok: false, reason: 'missing option' };
      element.value = option.value;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true };
    })()`);
    if (!selected?.ok) throw new Error(`Could not select “${label}” in ${selector}: ${selected?.reason || 'unknown error'}`);
  }

  async setViewport({ width, height, mobile }) {
    this.mobile = mobile;
    await this.client.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 1,
      mobile,
      screenWidth: width,
      screenHeight: height,
      screenOrientation: { type: mobile ? 'portraitPrimary' : 'landscapePrimary', angle: 0 },
    });
    await this.client.send('Emulation.setTouchEmulationEnabled', {
      enabled: mobile,
      maxTouchPoints: mobile ? 5 : 1,
    });
    await this.client.send('Emulation.setEmulatedMedia', {
      media: 'screen',
      features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
    });
  }

  async initialize() {
    await this.client.send('Page.enable');
    await this.client.send('Runtime.enable');
    await this.client.send('Network.enable');
    await this.setViewport({ width: 1440, height: 900, mobile: false });
    await this.client.send('Page.navigate', { url: this.config.appUrl });
    await this.waitUntil(`document.readyState === 'complete'`, 'the Mosaic document to load');
    await this.waitUntil(
      `document.querySelector('#login-view:not(.hidden)') || document.querySelector('#app-shell:not(.hidden)')`,
      'the login or application screen',
    );

    const signedIn = await this.evaluate(`Boolean(document.querySelector('#app-shell:not(.hidden)'))`);
    if (!signedIn) {
      await this.setValue('#login-email', this.config.email);
      await this.setValue('#login-password', this.config.password, { change: false });
      await this.evaluate(`document.querySelector('#login-form').requestSubmit()`);
      await this.waitFor('#app-shell:not(.hidden)', 'successful Mosaic sign-in');
    }
    await this.waitFor(READY_SELECTORS.budget, 'the initial budget');
  }

  navSelector(view) {
    const navigation = this.mobile ? '.bottom-nav' : '.side-nav';
    return `${navigation} .nav-item[data-view=${JSON.stringify(view)}]`;
  }

  async goTo(view) {
    await this.click(this.navSelector(view));
    await this.waitFor(READY_SELECTORS[view], `${view} view`);
    await this.waitUntil(
      `document.querySelector(${JSON.stringify(this.navSelector(view))})?.getAttribute('aria-current') === 'page'`,
      `${view} navigation state`,
    );
  }

  async verifyReorderAffordances(view) {
    const result = await this.evaluate(`(() => {
      const handlesAreUsable = handles => handles.length > 0 && handles.every(handle => {
        const rect = handle.getBoundingClientRect();
        return rect.width >= 44 && rect.height >= 44;
      });
      if (${JSON.stringify(view)} === 'budget') {
        const expenseSections = [...document.querySelectorAll('.section-card:not(.income)')];
        const categories = [...document.querySelectorAll('.category-row')];
        const sectionHandles = [...document.querySelectorAll('.section-reorder-handle')];
        const categoryHandles = [...document.querySelectorAll('.category-reorder-handle')];
        return {
          ok: expenseSections.length === sectionHandles.length
            && categories.length === categoryHandles.length
            && !document.querySelector('.section-card.income .section-reorder-handle')
            && handlesAreUsable(sectionHandles)
            && handlesAreUsable(categoryHandles)
            && document.documentElement.scrollWidth <= window.innerWidth,
          expenseSections: expenseSections.length,
          sectionHandles: sectionHandles.length,
          categories: categories.length,
          categoryHandles: categoryHandles.length,
        };
      }
      const phases = [...document.querySelectorAll('.rule-phase')].map(phase => phase.dataset.rulePhase);
      const cards = [...document.querySelectorAll('.rule-card')];
      const handles = [...document.querySelectorAll('.rule-reorder-handle')];
      return {
        ok: phases.join(',') === 'cleanup,categorize,finish'
          && cards.length === handles.length
          && handlesAreUsable(handles)
          && document.documentElement.scrollWidth <= window.innerWidth,
        phases,
        cards: cards.length,
        handles: handles.length,
      };
    })()`);
    if (!result?.ok) throw new Error(`${view} reorder affordances are incomplete: ${JSON.stringify(result)}`);
  }

  async setTheme(theme) {
    await this.goTo('more');
    const selector = `.theme-choice[data-theme-choice=${JSON.stringify(theme)}]`;
    const active = await this.evaluate(
      `document.body.dataset.theme === ${JSON.stringify(theme)} && document.querySelector(${JSON.stringify(selector)})?.classList.contains('active')`,
    );
    if (!active) {
      await this.click(selector);
      await this.waitUntil(
        `document.body.dataset.theme === ${JSON.stringify(theme)} && document.querySelector(${JSON.stringify(selector)})?.classList.contains('active')`,
        `${theme} theme to save`,
      );
    }
  }

  async scrollTop() {
    await this.evaluate(`window.scrollTo({ top: 0, behavior: 'auto' })`);
  }

  async settle() {
    await this.evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
    await delay(40);
  }

  async clearToastsAndFocus() {
    await this.evaluate(`(() => {
      document.querySelector('#toast-root')?.replaceChildren();
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      window.getSelection()?.removeAllRanges();
    })()`);
  }

  async privacyScan(filename) {
    if (!this.config.bannedTokens.length) return;
    const matches = await this.evaluate(`(() => {
      const tokens = ${JSON.stringify(this.config.bannedTokens)}
        .map(token => token.normalize('NFKC').toLocaleLowerCase());
      const sources = [{ label: 'visible text', text: document.body?.innerText || '' }];
      document.querySelectorAll('input, textarea, select, [aria-label], [title], [alt]').forEach((element, index) => {
        const pieces = [];
        if ('value' in element && element.value) pieces.push(element.value);
        if (element instanceof HTMLSelectElement && element.selectedOptions.length) {
          pieces.push(...[...element.selectedOptions].map(option => option.textContent || ''));
        }
        for (const attribute of ['aria-label', 'title', 'alt']) {
          const value = element.getAttribute(attribute);
          if (value) pieces.push(value);
        }
        if (pieces.length) sources.push({ label: element.id || element.className || element.tagName + ':' + index, text: pieces.join(' ') });
      });
      const found = [];
      for (const source of sources) {
        const original = String(source.text).replace(/\\s+/g, ' ').trim();
        const normalized = original.normalize('NFKC').toLocaleLowerCase();
        for (let tokenIndex = 0; tokenIndex < tokens.length; tokenIndex += 1) {
          const offset = normalized.indexOf(tokens[tokenIndex]);
          if (offset === -1) continue;
          found.push({
            token: ${JSON.stringify(this.config.bannedTokens)}[tokenIndex],
            source: String(source.label),
            snippet: original.slice(Math.max(0, offset - 45), Math.min(original.length, offset + tokens[tokenIndex].length + 45)),
          });
          if (found.length >= 30) return found;
        }
      }
      return found;
    })()`);
    if (matches.length) {
      const details = matches.map(match => `  - “${match.token}” in ${match.source}: …${match.snippet}…`).join('\n');
      throw new Error(`Privacy scan blocked ${filename}:\n${details}`);
    }
  }

  async capture(filename) {
    await this.settle();
    await this.clearToastsAndFocus();
    await this.privacyScan(filename);
    await this.settle();
    await this.evaluate(`document.querySelector('#toast-root')?.replaceChildren()`);
    const result = await this.client.send('Page.captureScreenshot', {
      format: 'png',
      fromSurface: true,
      captureBeyondViewport: false,
    });
    const buffer = Buffer.from(result.data || '', 'base64');
    const signature = buffer.subarray(0, 8).toString('hex');
    if (signature !== '89504e470d0a1a0a') throw new Error(`Chromium did not return a valid PNG for ${filename}`);
    this.captures.set(filename, buffer);
    console.log(`Captured ${filename}`);
  }

  async openTray(selectionCount) {
    await this.click('#inbox-button');
    await this.waitFor('#transaction-tray.open .tx-bubble', 'the transaction sorting tray');
    await this.clickFirst('#transaction-tray.open .tx-select-control', selectionCount);
    await this.waitUntil(
      `document.querySelector('#tray-selection-count')?.textContent.trim().startsWith(${JSON.stringify(String(selectionCount))})`,
      `${selectionCount} selected tray transactions`,
    );
  }

  async dragSelectedToCategory(categoryName, filename) {
    const lookup = await this.evaluate(`(() => {
      const normalize = value => String(value || '').replace(/\\s+/g, ' ').trim().toLocaleLowerCase();
      const wanted = normalize(${JSON.stringify(categoryName)});
      const bubbles = [...document.querySelectorAll('#transaction-tray.open .tx-bubble')];
      const selectedBubbles = bubbles.filter(bubble => bubble.classList.contains('is-selected'));
      const sourceBubble = selectedBubbles[0] || bubbles[0] || null;
      const source = sourceBubble?.querySelector('.tx-bubble-content') || null;
      const categoryRows = [...document.querySelectorAll('.category-row[data-category-id]')];
      const categoryNameFor = row => normalize(
        row.querySelector('.category-name span:first-child')?.textContent
        || row.querySelector('.category-name')?.textContent
        || row.querySelector('.category-main')?.getAttribute('aria-label')?.replace(/^View\\s+/i, '').replace(/\\s+transactions$/i, '')
      );
      let stateCategoryId = null;
      try {
        const categories = state.budget?.sections?.flatMap(section => section.categories || []) || [];
        const stateCategory = categories.find(category => normalize(category.name) === wanted)
          || categories.find(category => normalize(category.name).includes(wanted));
        stateCategoryId = stateCategory?.id || null;
      } catch { /* DOM lookup below remains authoritative. */ }
      const target = (stateCategoryId
        ? categoryRows.find(row => row.dataset.categoryId === String(stateCategoryId))
        : null)
        || categoryRows.find(row => categoryNameFor(row) === wanted)
        || categoryRows.find(row => categoryNameFor(row).includes(wanted));
      if (!source || !target) {
        return {
          ok: false,
          bubbleCount: bubbles.length,
          selectedBubbleCount: selectedBubbles.length,
          categoryCount: categoryRows.length,
          categoryNames: categoryRows.map(categoryNameFor).filter(Boolean).slice(0, 40),
          sourceFound: Boolean(source),
          targetFound: Boolean(target),
          stateCategoryId,
        };
      }
      // A seed may retain a collapsed-section display preference. Revealing the
      // already-rendered rows locally keeps this capture non-mutating.
      target.closest('.section-card.collapsed')?.classList.remove('collapsed');
      target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'auto' });
      // The fixed tray narrows the apparent content area. Some Chromium builds
      // respond by nudging the document horizontally while centering the row,
      // which clips the navigation in the resulting frame.
      window.scrollTo({ left: 0, top: window.scrollY, behavior: 'auto' });
      const sourceRect = source.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      return {
        ok: true,
        source: { x: sourceRect.left + sourceRect.width / 2, y: sourceRect.top + sourceRect.height / 2 },
        target: { x: targetRect.left + targetRect.width / 2, y: targetRect.top + targetRect.height / 2 },
        targetName: categoryNameFor(target),
      };
    })()`);
    if (!lookup?.ok) {
      const names = lookup?.categoryNames?.length ? lookup.categoryNames.join(', ') : '(none)';
      throw new Error(
        `Could not prepare the ${categoryName} drag target: source=${lookup?.sourceFound}, target=${lookup?.targetFound}, `
        + `bubbles=${lookup?.bubbleCount ?? 0}, selected=${lookup?.selectedBubbleCount ?? 0}, `
        + `categories=${lookup?.categoryCount ?? 0}, names=[${names}]`,
      );
    }
    const points = lookup;

    let pressed = false;
    try {
      await this.client.send('Input.dispatchMouseEvent', {
        type: 'mousePressed', x: points.source.x, y: points.source.y,
        button: 'left', buttons: 1, clickCount: 1,
      });
      pressed = true;
      await this.client.send('Input.dispatchMouseEvent', {
        type: 'mouseMoved', x: points.source.x - 14, y: points.source.y,
        button: 'left', buttons: 1,
      });
      await this.waitFor('.drag-ghost', 'the transaction drag ghost');
      await this.client.send('Input.dispatchMouseEvent', {
        type: 'mouseMoved', x: points.target.x, y: points.target.y,
        button: 'left', buttons: 1,
      });
      await this.waitFor('.category-row.drop-target', 'the highlighted category drop target');
      await this.capture(filename);
    } finally {
      // Cancelling the application drag before mouseReleased guarantees this
      // visual capture can never assign or otherwise mutate a transaction.
      await this.evaluate(`state.cancelBubbleDrag?.()`).catch(() => {});
      if (pressed) {
        await this.client.send('Input.dispatchMouseEvent', {
          type: 'mouseReleased', x: points.target.x, y: points.target.y,
          button: 'left', buttons: 0, clickCount: 1,
        }).catch(() => {});
      }
    }
    await this.waitUntil(`!document.querySelector('.drag-ghost')`, 'drag cleanup');
  }

  async desktopSequence() {
    // Theme is persisted per user, so make the first frame deterministic even
    // when this is a retry against the same disposable workspace.
    await this.setTheme('citrus');
    await this.goTo('budget');
    await this.scrollTop();
    await this.verifyReorderAffordances('budget');
    await this.capture(SCREENSHOTS.budgetDesktop);

    await this.setTheme('meadow');
    await this.goTo('budget');
    await this.scrollTop();
    await this.openTray(3);
    await this.capture(SCREENSHOTS.trayDesktop);
    await this.dragSelectedToCategory('Groceries', SCREENSHOTS.dragDesktop);
    const desktopInspection = await this.evaluate(`(() => ({
      transactionId: document.querySelector('#transaction-tray.open .tx-bubble:first-child')?.dataset.transactionId,
      selectedIds: [...document.querySelectorAll('#transaction-tray.open .tx-bubble.is-selected')]
        .map(bubble => bubble.dataset.transactionId).sort(),
    }))()`);
    if (desktopInspection.selectedIds.length !== 3 || !desktopInspection.selectedIds.includes(desktopInspection.transactionId)) {
      throw new Error('Desktop tray inspection requires the first transaction to remain in the three-item selection');
    }
    await this.click('#transaction-tray.open .tx-bubble:first-child .tx-bubble-content');
    await this.waitUntil(
      `document.querySelector('#transaction-form')?.dataset.transactionId === ${JSON.stringify(desktopInspection.transactionId)}
        && document.querySelector('#transaction-tray.open')?.getAttribute('aria-hidden') === 'false'
        && document.querySelector('#transaction-tray.open')?.hasAttribute('inert')`,
      'the selected transaction details to open above the inactive sorting tray',
    );
    await this.click('.modal-cancel');
    await this.waitUntil(
      `!document.querySelector('#modal-root .modal')
        && document.querySelector('#transaction-tray.open')?.getAttribute('aria-hidden') === 'false'
        && JSON.stringify([...document.querySelectorAll('#transaction-tray.open .tx-bubble.is-selected')]
          .map(bubble => bubble.dataset.transactionId).sort()) === ${JSON.stringify(JSON.stringify(desktopInspection.selectedIds))}
        && document.activeElement?.matches('.tx-bubble-content')
        && document.activeElement?.closest('.tx-bubble')?.dataset.transactionId === ${JSON.stringify(desktopInspection.transactionId)}`,
      'transaction inspection to return focus to the sorting tray',
    );
    await this.click('#tray-close');
    await this.waitUntil(`!document.querySelector('#transaction-tray.open')`, 'the tray to close');

    await this.setTheme('ocean');
    await this.goTo('transactions');
    await this.scrollTop();
    await this.clickFirst('.transaction-list .transaction-list-select-control', 2);
    await this.waitUntil(
      `document.querySelector('#transaction-selection-count')?.textContent.trim().startsWith('2')`,
      'two selected transactions',
    );
    await this.capture(SCREENSHOTS.transactionsDesktop);
    await this.click('.transaction-list .transaction-card:first-child .transaction-card-content');
    await this.waitFor('#transaction-form', 'the transaction details editor');
    await this.capture(SCREENSHOTS.transactionDesktop);
    await this.click('.modal-close');
    await this.waitUntil(`!document.querySelector('#modal-root .modal')`, 'the transaction modal to close');

    await this.setTheme('berry');
    await this.goTo('analytics');
    await this.scrollTop();
    await this.waitFor('.analytics-chart .analytics-chart-month', 'the analytics chart');
    await this.capture(SCREENSHOTS.analyticsDesktop);

    await this.setTheme('sunrise');
    await this.goTo('rules');
    await this.scrollTop();
    await this.waitFor('.rule-list .rule-card', 'at least one automation rule');
    await this.verifyReorderAffordances('rules');
    await this.capture(SCREENSHOTS.rulesDesktop);
    await this.click('.rule-list .rule-card:first-child .edit-rule');
    await this.waitFor('#rule-form', 'the rule builder');
    await this.capture(SCREENSHOTS.ruleDesktop);
    await this.click('.modal-close');
    await this.waitUntil(`!document.querySelector('#modal-root .modal')`, 'the rule modal to close');

    await this.setTheme('citrus');
    await this.scrollTop();
    await this.capture(SCREENSHOTS.settingsDesktop);
  }

  async switchToMobile() {
    await this.setViewport({ width: 390, height: 844, mobile: true });
    await this.client.send('Page.reload', { ignoreCache: false });
    await this.waitUntil(`document.readyState === 'complete'`, 'the mobile document reload');
    await this.waitFor('#app-shell:not(.hidden)', 'the signed-in mobile application');
    await this.waitFor(READY_SELECTORS.budget, 'the reloaded mobile budget');
  }

  async mobileSequence() {
    await this.switchToMobile();
    await this.setTheme('meadow');
    await this.goTo('budget');
    await this.scrollTop();
    await this.verifyReorderAffordances('budget');
    await this.capture(SCREENSHOTS.budgetMobile);

    await this.openTray(2);
    await this.capture(SCREENSHOTS.trayMobile);
    const mobileInspection = await this.evaluate(`(() => ({
      transactionId: document.querySelector('#transaction-tray.open .tx-bubble:first-child')?.dataset.transactionId,
      selectedIds: [...document.querySelectorAll('#transaction-tray.open .tx-bubble.is-selected')]
        .map(bubble => bubble.dataset.transactionId).sort(),
    }))()`);
    if (mobileInspection.selectedIds.length !== 2 || !mobileInspection.selectedIds.includes(mobileInspection.transactionId)) {
      throw new Error('Mobile tray inspection requires the first transaction to remain in the two-item selection');
    }
    await this.click('#transaction-tray.open .tx-bubble:first-child .tx-bubble-content');
    await this.waitUntil(
      `document.querySelector('#transaction-form')?.dataset.transactionId === ${JSON.stringify(mobileInspection.transactionId)}
        && document.querySelector('#transaction-tray.open')?.getAttribute('aria-hidden') === 'false'
        && document.querySelector('#transaction-tray.open')?.hasAttribute('inert')`,
      'the selected mobile transaction details to open above the inactive sorting tray',
    );
    await this.click('.modal-cancel');
    await this.waitUntil(
      `!document.querySelector('#modal-root .modal')
        && document.querySelector('#transaction-tray.open')?.getAttribute('aria-hidden') === 'false'
        && JSON.stringify([...document.querySelectorAll('#transaction-tray.open .tx-bubble.is-selected')]
          .map(bubble => bubble.dataset.transactionId).sort()) === ${JSON.stringify(JSON.stringify(mobileInspection.selectedIds))}
        && document.activeElement?.matches('.tx-bubble-content')
        && document.activeElement?.closest('.tx-bubble')?.dataset.transactionId === ${JSON.stringify(mobileInspection.transactionId)}`,
      'mobile transaction inspection to return focus to the sorting tray',
    );
    await this.click('#tray-close');
    await this.waitUntil(`!document.querySelector('#transaction-tray.open')`, 'the mobile tray to close');

    await this.click('#app-view .add-manual');
    await this.waitFor('#manual-form', 'the manual transaction form');
    await this.setValue('#manual-amount', '18.40');
    await this.setValue('#manual-payee', 'Daybreak Bakery');
    await this.selectByText('#manual-account', 'Everyday Account');
    await this.selectByText('#manual-category', 'Dining Out');
    await this.setValue('#manual-note', 'Saturday breakfast');
    await this.capture(SCREENSHOTS.manualMobile);
    await this.click('.modal-close');
    await this.waitUntil(`!document.querySelector('#modal-root .modal')`, 'the manual transaction modal to close');

    await this.setTheme('ocean');
    await this.goTo('transactions');
    await this.scrollTop();
    await this.waitFor('.transaction-list .transaction-card', 'mobile transactions');
    await this.capture(SCREENSHOTS.transactionsMobile);

    await this.setTheme('berry');
    await this.goTo('analytics');
    await this.waitFor('.analytics-chart .analytics-chart-month', 'mobile analytics');
    await this.evaluate(`document.querySelector('.analytics-kpis').scrollIntoView({ block: 'start', behavior: 'auto' })`);
    await this.capture(SCREENSHOTS.analyticsMobile);
  }

  async commit() {
    const expected = Object.values(SCREENSHOTS);
    const missing = expected.filter(filename => !this.captures.has(filename));
    if (missing.length) throw new Error(`Capture run is incomplete: ${missing.join(', ')}`);

    await fs.mkdir(this.config.outputDir, { recursive: true });
    const temporary = [];
    try {
      for (const filename of expected) {
        const target = path.join(this.config.outputDir, filename);
        const temp = path.join(this.config.outputDir, `.${filename}.${process.pid}.tmp`);
        await fs.writeFile(temp, this.captures.get(filename), { mode: 0o644 });
        temporary.push({ temp, target });
      }
      for (const entry of temporary) await fs.rename(entry.temp, entry.target);
    } catch (error) {
      await Promise.all(temporary.map(entry => fs.unlink(entry.temp).catch(() => {})));
      throw error;
    }
    console.log(`Wrote ${expected.length} screenshots to ${this.config.outputDir}`);
  }

  async run() {
    await this.initialize();
    await this.desktopSequence();
    await this.mobileSequence();
    if (this.client.runtimeExceptions.length) {
      throw new Error(`The page reported ${this.client.runtimeExceptions.length} uncaught exception(s):\n${this.client.runtimeExceptions.join('\n')}`);
    }
    await this.commit();
  }
}

async function main() {
  const config = configuration(process.argv.slice(2), process.env);
  if (config.help) {
    console.log(usage());
    return;
  }

  const webSocketUrl = await discoverWebSocket(config.cdpUrl, config.appUrl);
  const client = await connectCdp(webSocketUrl, config.timeoutMs);
  try {
    const capture = new MosaicCapture(client, config);
    await capture.run();
  } finally {
    client.close();
  }
}

main().catch(error => {
  console.error(`Screenshot capture failed: ${error.message}`);
  process.exitCode = 1;
});

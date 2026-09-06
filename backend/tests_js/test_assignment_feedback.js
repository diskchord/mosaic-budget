'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const appPath = path.join(__dirname, '../app/static/app.js');
const stylesPath = path.join(__dirname, '../app/static/styles.css');
const templatePath = path.join(__dirname, '../app/templates/index.html');
const appSource = fs.readFileSync(appPath, 'utf8');
const stylesSource = fs.readFileSync(stylesPath, 'utf8');
const templateSource = fs.readFileSync(templatePath, 'utf8');

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

const feedbackSource = sourceBetween(
  'function getAssignmentAudioContext()',
  'function setButtonBusy(',
);
const assignmentSource = sourceBetween(
  'async function assignTransactions(',
  'function openSelectedAssignment()',
);
const bubbleDragSource = sourceBetween(
  'function installBubbleDrag()',
  'function transactionCategoryText(',
);

function loadFeedback(overrides = {}) {
  const context = vm.createContext({
    window: {},
    document: { hidden: false },
    $: () => null,
    requestAnimationFrame: callback => callback(),
    setTimeout: () => 0,
    ...overrides,
  });
  vm.runInContext(`
    'use strict';
    let assignmentAudioContext = null;
    ${feedbackSource}
    globalThis.feedback = {
      getAssignmentAudioContext,
      primeAssignmentAudio,
      playAssignmentPop,
      announceInteraction,
      animateCategoryAssignment,
    };
  `, context, { filename: appPath });
  return context.feedback;
}

function approximate(actual, expected, epsilon = 1e-12) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} is not approximately ${expected}`);
}

test('assignment pop requests interactive audio and schedules two short higher voices immediately', () => {
  const frequencyEvents = [[], []];
  const gainEvents = [[], []];
  const oscillators = frequencyEvents.map(events => ({
    type: '',
    frequency: {
      setValueAtTime(value, time) { events.push({ method: 'set', value, time }); },
      exponentialRampToValueAtTime(value, time) { events.push({ method: 'ramp', value, time }); },
    },
    connectedTo: null,
    startedAt: null,
    stoppedAt: null,
    disconnected: false,
    ended: null,
    connect(target) { this.connectedTo = target; },
    disconnect() { this.disconnected = true; },
    addEventListener(type, listener, options) { this.ended = { type, listener, options }; },
    start(time) { this.startedAt = time; },
    stop(time) { this.stoppedAt = time; },
  }));
  const gainNodes = gainEvents.map(events => ({
    gain: {
      setValueAtTime(value, time) { events.push({ method: 'set', value, time }); },
      exponentialRampToValueAtTime(value, time) { events.push({ method: 'ramp', value, time }); },
    },
    connectedTo: null,
    disconnected: false,
    connect(target) { this.connectedTo = target; },
    disconnect() { this.disconnected = true; },
  }));
  const destination = {};
  let oscillatorIndex = 0;
  let gainIndex = 0;
  const audioContext = {
    state: 'running',
    currentTime: 4,
    destination,
    createOscillator: () => oscillators[oscillatorIndex++],
    createGain: () => gainNodes[gainIndex++],
  };
  let contextOptions = null;
  class FakeAudioContext {
    constructor(options) { contextOptions = options; return audioContext; }
  }

  const feedback = loadFeedback({ window: { AudioContext: FakeAudioContext }, document: { hidden: false } });
  feedback.playAssignmentPop();

  assert.equal(contextOptions.latencyHint, 'interactive');
  assert.deepEqual(oscillators.map(oscillator => oscillator.type), ['sine', 'triangle']);
  assert.deepEqual(
    frequencyEvents.map(events => events.map(event => [event.method, event.value])),
    [[['set', 480], ['ramp', 240]], [['set', 960], ['ramp', 640]]],
  );
  assert.deepEqual(
    gainEvents.map(events => events.map(event => [event.method, event.value])),
    [
      [['set', 0.0001], ['ramp', 0.085], ['ramp', 0.0001]],
      [['set', 0.0001], ['ramp', 0.022], ['ramp', 0.0001]],
    ],
  );
  oscillators.forEach((oscillator, index) => {
    assert.equal(oscillator.connectedTo, gainNodes[index]);
    assert.equal(gainNodes[index].connectedTo, destination);
    approximate(oscillator.startedAt, 4);
    assert.equal(oscillator.ended.type, 'ended');
    assert.equal(oscillator.ended.options.once, true);
  });
  approximate(oscillators[0].stoppedAt, 4.115);
  approximate(oscillators[1].stoppedAt, 4.05);
  approximate(frequencyEvents[0][1].time, 4.0902);
  approximate(frequencyEvents[1][1].time, 4.0369);
  approximate(gainEvents[0][1].time, 4.003);
  approximate(gainEvents[0][2].time, 4.11);
  approximate(gainEvents[1][1].time, 4.002);
  approximate(gainEvents[1][2].time, 4.045);

  oscillators.forEach((oscillator, index) => {
    oscillator.ended.listener();
    assert.equal(oscillator.disconnected, true);
    assert.equal(gainNodes[index].disconnected, true);
  });
});

test('assignment audio is optional and every browser failure is contained', async () => {
  const constructorCalls = [];
  const legacyContext = { state: 'running' };
  class LegacyAudioContext {
    constructor(options) {
      constructorCalls.push(options);
      if (options) throw new Error('constructor options are unsupported');
      return legacyContext;
    }
  }
  const legacy = loadFeedback({ window: { AudioContext: LegacyAudioContext } });
  assert.equal(legacy.getAssignmentAudioContext(), legacyContext);
  assert.equal(constructorCalls[0].latencyHint, 'interactive');
  assert.equal(constructorCalls[1], undefined);

  class ThrowingAudioContext {
    constructor() { throw new Error('audio is blocked'); }
  }
  const unavailable = loadFeedback({ window: { AudioContext: ThrowingAudioContext } });
  assert.doesNotThrow(() => unavailable.primeAssignmentAudio());
  assert.doesNotThrow(() => unavailable.playAssignmentPop());

  const resumeFailure = {
    state: 'suspended',
    resume() { return Promise.reject(new Error('resume rejected')); },
  };
  class SuspendedAudioContext {
    constructor() { return resumeFailure; }
  }
  const suspended = loadFeedback({ window: { webkitAudioContext: SuspendedAudioContext } });
  assert.doesNotThrow(() => suspended.primeAssignmentAudio());
  assert.doesNotThrow(() => suspended.playAssignmentPop());
  await new Promise(resolve => setImmediate(resolve));

  const nodeFailure = {
    state: 'running',
    currentTime: 0,
    createOscillator() { throw new Error('node creation failed'); },
  };
  class BrokenNodeAudioContext {
    constructor() { return nodeFailure; }
  }
  const brokenNode = loadFeedback({ window: { AudioContext: BrokenNodeAudioContext } });
  assert.doesNotThrow(() => brokenNode.playAssignmentPop());
});

test('starting a transaction drag warms audio during the pointer gesture', () => {
  assert.match(
    bubbleDragSource,
    /const startDrag = \([^)]*\) => \{\s*primeAssignmentAudio\(\);/,
  );
});

test('assignment feedback restarts category motion and updates the hidden live region', () => {
  const classEvents = [];
  const classes = new Set(['assignment-confirmed']);
  const listeners = new Map();
  const row = {
    offsetWidth: 320,
    classList: {
      add(name) { classEvents.push(['add', name]); classes.add(name); },
      remove(name) { classEvents.push(['remove', name]); classes.delete(name); },
    },
    addEventListener(type, listener, options) { listeners.set(type, { listener, options }); },
  };
  const status = { textContent: 'previous message', isConnected: true };
  const appView = {};
  const animationFrames = [];
  const timers = [];
  const feedback = loadFeedback({
    $: selector => {
      if (selector === '#interaction-status') return status;
      if (selector === '#app-view') return appView;
      if (selector === '.category-row[data-category-id="groceries"]') return row;
      return null;
    },
    requestAnimationFrame: callback => { animationFrames.push(callback); return animationFrames.length; },
    setTimeout: (callback, delay) => { timers.push({ callback, delay }); return timers.length; },
  });

  feedback.animateCategoryAssignment('groceries');
  assert.deepEqual(classEvents, [
    ['remove', 'assignment-confirmed'],
    ['add', 'assignment-confirmed'],
  ]);
  assert.equal(classes.has('assignment-confirmed'), true);
  assert.equal(listeners.get('animationend').options.once, true);
  assert.equal(timers[0].delay, 850);

  listeners.get('animationend').listener();
  assert.equal(classes.has('assignment-confirmed'), false);

  feedback.announceInteraction('Coffee moved to Groceries in September 2026');
  assert.equal(status.textContent, '');
  assert.equal(animationFrames.length, 1);
  animationFrames[0]();
  assert.equal(status.textContent, 'Coffee moved to Groceries in September 2026');
});

test('successful assignment uses sound, motion, and announcement without a toast or Undo action', async () => {
  const calls = [];
  const toastCalls = [];
  const tray = {
    attributes: new Map(),
    setAttribute(name, value) { this.attributes.set(name, value); },
    removeAttribute(name) { this.attributes.delete(name); },
  };
  const appView = { focus() { calls.push(['focus']); } };
  const transaction = { id: 'tx-1', version: 8, display_payee: 'Coffee' };
  const category = { id: 'cat-1', name: 'Groceries' };
  class ConflictError extends Error {}
  let request = null;
  const context = vm.createContext({
    state: { assignmentInFlight: false, month: '2026-09', budget: {} },
    transactionById: id => id === transaction.id ? transaction : null,
    categoryById: id => id === category.id ? category : null,
    toast: (...args) => toastCalls.push(args),
    primeAssignmentAudio: () => calls.push(['prime']),
    api: async (pathName, options) => {
      request = { pathName, options };
      return { transactions: [{ id: transaction.id, version: 9 }], undo_token: 'unused-token' };
    },
    closeTray: () => calls.push(['close-tray']),
    transactionLabel: item => item.display_payee,
    monthLabel: () => 'September 2026',
    refreshCurrentView: async () => { calls.push(['refresh']); return true; },
    reconcileBubbleSelection: () => calls.push(['reconcile']),
    renderTray: () => calls.push(['render-tray']),
    updateNavigation: () => calls.push(['update-navigation']),
    animateCategoryAssignment: id => calls.push(['animate', id]),
    playAssignmentPop: () => calls.push(['pop']),
    announceInteraction: message => calls.push(['announce', message]),
    syncBubbleSelection: () => calls.push(['sync-selection']),
    $: selector => selector === '#transaction-tray' ? tray : selector === '#app-view' ? appView : null,
    ConflictError,
  });
  vm.runInContext(`${assignmentSource}\nglobalThis.assignTransactionsForTest = assignTransactions;`, context, {
    filename: appPath,
  });

  const assigned = await context.assignTransactionsForTest([transaction.id], category.id);

  assert.equal(assigned, true);
  assert.equal(request.pathName, '/api/transactions/batch');
  assert.equal(request.options.method, 'PUT');
  assert.equal(request.options.body.category_id, category.id);
  assert.equal(request.options.body.target_month, '2026-09');
  assert.equal(toastCalls.length, 0);
  assert.deepEqual(calls.filter(call => ['prime', 'pop'].includes(call[0])), [['prime'], ['pop']]);
  assert.ok(
    calls.findIndex(call => call[0] === 'pop') < calls.findIndex(call => call[0] === 'refresh'),
    'audio feedback should start as soon as the assignment succeeds, before refreshing the view',
  );
  assert.deepEqual(calls.find(call => call[0] === 'animate'), ['animate', category.id]);
  assert.deepEqual(calls.find(call => call[0] === 'announce'), [
    'announce',
    'Coffee moved to Groceries in September 2026',
  ]);
  assert.doesNotMatch(assignmentSource, /undoTransactionAssignment|undoAction|label:\s*['"]Undo['"]|result\.undo_token/);
  assert.match(assignmentSource, /if \(error\.status !== 401\) toast\(error\.message, 'error'\)/);
});

function cssRule(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = stylesSource.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  assert.ok(match, `Missing CSS rule for ${selector}`);
  return match[1];
}

test('category styling visibly swells, contracts, and honors reduced motion', () => {
  assert.match(cssRule('.category-row.assignment-confirmed'), /animation\s*:\s*category-assignment-confirmed\s+\.68s/);
  const keyframes = stylesSource.slice(
    stylesSource.indexOf('@keyframes category-assignment-confirmed'),
    stylesSource.indexOf('.category-main', stylesSource.indexOf('@keyframes category-assignment-confirmed')),
  );
  assert.match(keyframes, /34%\s*\{[^}]*transform\s*:\s*scale\(1\.025\)/s);
  assert.match(keyframes, /68%\s*\{[^}]*transform\s*:\s*scale\(\.993\)/s);
  assert.match(keyframes, /100%\s*\{[^}]*transform\s*:\s*scale\(1\)/s);
  assert.match(stylesSource, /@media \(prefers-reduced-motion:\s*reduce\)[\s\S]*?animation-duration\s*:\s*\.01ms\s*!important/);
  assert.match(stylesSource, /body\[data-motion="reduced"\][\s\S]*?animation-duration\s*:\s*\.01ms\s*!important/);
});

test('tray instructions remain accessible but are no longer visible explanatory copy', () => {
  const trayTag = templateSource.match(/<aside id="transaction-tray"[^>]*>/)?.[0];
  const help = templateSource.match(/<p id="tray-help" class="([^"]*)">([^<]*)<\/p>/);
  assert.ok(trayTag, 'Missing transaction tray');
  assert.ok(help, 'Missing accessible tray help');
  assert.ok(help[1].split(/\s+/).includes('sr-only'));
  assert.match(help[2], /press and hold/i);
  assert.match(help[2], /select multiple transactions/i);
  assert.match(trayTag, /aria-describedby="[^"]*\btray-help\b[^"]*"/);
  assert.doesNotMatch(appSource, /\$\('#tray-help'\)\.textContent/);
  assert.doesNotMatch(stylesSource, /\.tray-help\s*\{/);
  assert.match(cssRule('.sr-only'), /clip\s*:\s*rect\(0,0,0,0\)/);
});

function listenerCallback(eventName) {
  const escaped = eventName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = bubbleDragSource.match(new RegExp(
    `container\\.addEventListener\\('${escaped}',\\s*(event\\s*=>\\s*\\{[\\s\\S]*?\\n\\s*\\})\\);`,
  ));
  assert.ok(match, `Missing ${eventName} listener`);
  return match[1];
}

function selectionEvent(overBubble = true) {
  return {
    defaultPrevented: false,
    target: { closest: () => overBubble ? {} : null },
    preventDefault() { this.defaultPrevented = true; },
  };
}

test('touch drag surfaces and JavaScript prevent transaction text selection and callouts', () => {
  for (const selector of ['.transaction-tray', '.tx-bubble', '.tx-bubble *']) {
    const rule = cssRule(selector);
    assert.match(rule, /-webkit-user-select\s*:\s*none/);
    assert.match(rule, /user-select\s*:\s*none/);
    assert.match(rule, /-webkit-touch-callout\s*:\s*none/);
  }
  assert.match(cssRule('.tx-bubble'), /touch-action\s*:\s*pan-y/);
  assert.match(stylesSource, /@media \(hover:none\), \(pointer:coarse\)\s*\{\s*\.tx-select-mark\s*\{[^}]*opacity\s*:\s*\.7/s);
  assert.match(bubbleDragSource, /document\.getSelection\?\.\(\)\?\.removeAllRanges\(\)/);

  const preventSelection = vm.runInNewContext(`(${listenerCallback('selectstart')})`);
  const bubbleSelection = selectionEvent(true);
  preventSelection(bubbleSelection);
  assert.equal(bubbleSelection.defaultPrevented, true);
  const outsideSelection = selectionEvent(false);
  preventSelection(outsideSelection);
  assert.equal(outsideSelection.defaultPrevented, false);

  const touchContextMenu = vm.runInNewContext(`(${listenerCallback('contextmenu')})`, {
    drag: { touchId: 4 },
  });
  const touchCallout = selectionEvent(true);
  touchContextMenu(touchCallout);
  assert.equal(touchCallout.defaultPrevented, true);

  const idleContextMenu = vm.runInNewContext(`(${listenerCallback('contextmenu')})`, { drag: null });
  const idleCallout = selectionEvent(true);
  idleContextMenu(idleCallout);
  assert.equal(idleCallout.defaultPrevented, false);
});

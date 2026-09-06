'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const appPath = path.join(__dirname, '../app/static/app.js');
const appSource = fs.readFileSync(appPath, 'utf8');

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

const openModalSource = sourceBetween(
  'function openModal(',
  'function modalEscape(',
);

function renderModal(options) {
  class FakeElement {}

  const appShell = new FakeElement();
  const tray = new FakeElement();
  const root = new FakeElement();
  const backdrop = new FakeElement();
  const closeButton = new FakeElement();
  const modalBody = new FakeElement();
  const firstInput = new FakeElement();
  const activeElement = new FakeElement();
  const timers = [];

  for (const element of [appShell, tray]) {
    const attributes = new Set();
    element.hasAttribute = name => attributes.has(name);
    element.setAttribute = name => attributes.add(name);
  }
  root.addEventListener = () => {};
  backdrop.addEventListener = () => {};
  closeButton.addEventListener = () => {};
  closeButton.focusCount = 0;
  closeButton.focus = () => { closeButton.focusCount += 1; };
  firstInput.focusCount = 0;
  firstInput.focus = () => { firstInput.focusCount += 1; };
  modalBody.isConnected = true;

  const context = vm.createContext({
    state: {
      transactionEditorLoadSequence: 0,
      modalOpen: false,
      modalReturnFocus: null,
      modalInertBackgrounds: [],
      formDirty: false,
    },
    document: { activeElement, addEventListener() {} },
    HTMLElement: FakeElement,
    escapeHtml: value => value,
    hydrateIcons() {},
    moneyInput: { formatAll() {} },
    modalEscape() {},
    closeModal() {},
    setTimeout(callback) { timers.push(callback); return timers.length; },
    $: (selector, queryRoot) => {
      if (selector === '#app-shell') return appShell;
      if (selector === '#transaction-tray') return tray;
      if (selector === '#modal-root') return root;
      if (selector === '.modal-backdrop' && queryRoot === root) return backdrop;
      if (selector === '.modal-close' && queryRoot === root) return closeButton;
      if (selector === '.modal-body' && queryRoot === root) return modalBody;
      if (selector === 'input, select, textarea, button' && queryRoot === modalBody) return firstInput;
      return null;
    },
  });
  vm.runInContext(`${openModalSource}\nglobalThis.openModalForTest = openModal;`, context, { filename: appPath });
  context.openModalForTest({ title: 'Details', body: '<input>', ...options });
  timers.forEach(callback => callback());

  return { closeButton, firstInput };
}

test('modal initialFocus overrides the default form-control focus', () => {
  const focused = renderModal({ initialFocus: '.modal-close' });

  assert.equal(focused.closeButton.focusCount, 1);
  assert.equal(focused.firstInput.focusCount, 0);
});

test('transaction details opt out of focusing their first text field', () => {
  const transactionEditorSource = sourceBetween(
    'async function openTransactionEditor(',
    'function openTransferEditor(',
  );

  assert.match(transactionEditorSource, /initialFocus:\s*['"]\.modal-close['"]/);
});

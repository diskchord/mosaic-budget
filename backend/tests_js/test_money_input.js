'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const helperPath = path.join(__dirname, '../app/static/money-input.js');
const MoneyInput = require(helperPath);

class FakeInput {
  constructor(value, marked = true) {
    this.value = value;
    this.marked = marked;
    this.validationMessage = '';
    this.reportCount = 0;
    this.selectCount = 0;
    this.selectionStart = 0;
    this.selectionEnd = 0;
  }

  matches(selector) {
    return this.marked && selector === MoneyInput.DEFAULT_SELECTOR;
  }

  reportValidity() {
    this.reportCount += 1;
    return !this.validationMessage;
  }

  select() {
    this.selectCount += 1;
    this.selectionStart = 0;
    this.selectionEnd = this.value.length;
  }

  setCustomValidity(message) {
    this.validationMessage = message;
  }
}

class FakeRoot {
  constructor(controls = []) {
    this.controls = controls;
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? [];
    this.listeners.set(type, listeners.filter(candidate => candidate !== listener));
  }

  querySelectorAll(selector) {
    return this.controls.filter(control => control.matches(selector));
  }

  dispatch(type, target, properties = {}) {
    const event = {
      defaultPrevented: false,
      key: undefined,
      target,
      preventDefault() { this.defaultPrevented = true; },
      ...properties,
    };
    for (const listener of this.listeners.get(type) ?? []) listener(event);
    return event;
  }
}

test('format keeps a minimum of two decimal places without using floating point', () => {
  assert.equal(MoneyInput.format('0'), '0.00');
  assert.equal(MoneyInput.format('12.5'), '12.50');
  assert.equal(MoneyInput.format('0012.'), '12.00');
  assert.equal(MoneyInput.format('.75'), '0.75');
  assert.equal(MoneyInput.format('999999999999999999999.1'), '999999999999999999999.10');
});

test('format accepts grouped input, signs, and blank values', () => {
  assert.equal(MoneyInput.format(' 1,234,567.8 '), '1234567.80');
  assert.equal(MoneyInput.format('-1,234.56'), '-1234.56');
  assert.equal(MoneyInput.format('+4'), '4.00');
  assert.equal(MoneyInput.format('-0.0000'), '0.00');
  assert.equal(MoneyInput.format(''), '');
  assert.equal(MoneyInput.format(null), '');
});

test('format preserves meaningful precision through four decimal places', () => {
  assert.equal(MoneyInput.format('12.3456'), '12.3456');
  assert.equal(MoneyInput.format('12.3450'), '12.345');
  assert.equal(MoneyInput.format('12.3400'), '12.34');
  assert.equal(MoneyInput.format('12.0000'), '12.00');
  assert.equal(MoneyInput.format('12.3456000'), '12.3456');
});

test('format rejects malformed input and nonzero precision beyond four places', () => {
  for (const value of ['money', '1,23.45', '12,50', '1 000.00', '.', '--1', '12.34561']) {
    assert.throws(() => MoneyInput.format(value), MoneyInput.MoneyInputError, value);
  }
  assert.throws(
    () => MoneyInput.format('12.34561'),
    error => error.code === 'precision' && /four decimal places/.test(error.message),
  );
});

test('browser script exposes the formatter without CommonJS globals', () => {
  const context = {};
  vm.runInNewContext(fs.readFileSync(helperPath, 'utf8'), context);
  assert.equal(context.MoneyInput.format('7.5'), '7.50');
});

test('read normalizes a control, allows blank, and can opt into blank-as-zero', () => {
  const input = new FakeInput('1,234.5');
  assert.equal(MoneyInput.read(input), '1234.50');
  assert.equal(input.value, '1234.50');
  assert.equal(input.validationMessage, '');

  input.value = '';
  assert.equal(MoneyInput.read(input), '');
  assert.equal(input.value, '');
  assert.equal(MoneyInput.read(input, { blankAsZero: true }), '0.00');
  assert.equal(input.value, '0.00');
});

test('read preserves invalid text and supplies a native validation error', () => {
  const input = new FakeInput('12.34561');
  assert.throws(() => MoneyInput.read(input), MoneyInput.MoneyInputError);
  assert.equal(input.value, '12.34561');
  assert.match(input.validationMessage, /four decimal places/);
});

test('bind formats existing controls and selects zero when focused', () => {
  const zero = new FakeInput('0');
  const amount = new FakeInput('2.5');
  const unrelated = new FakeInput('7', false);
  const root = new FakeRoot([zero, amount, unrelated]);

  const unbind = MoneyInput.bind(root);
  assert.equal(zero.value, '0.00');
  assert.equal(amount.value, '2.50');
  assert.equal(unrelated.value, '7');

  root.dispatch('focusin', zero);
  root.dispatch('focusin', amount);
  assert.equal(zero.selectCount, 1);
  assert.equal(amount.selectCount, 0);
  unbind();
});

test('bind delegates blur and input behavior to dynamically added controls', () => {
  const root = new FakeRoot();
  const unbind = MoneyInput.bind(root);
  const dynamic = new FakeInput('3.5');
  root.controls.push(dynamic);

  root.dispatch('focusout', dynamic);
  assert.equal(dynamic.value, '3.50');

  dynamic.value = '3.14159';
  root.dispatch('focusout', dynamic);
  assert.equal(dynamic.value, '3.14159');
  assert.match(dynamic.validationMessage, /four decimal places/);

  root.dispatch('input', dynamic);
  assert.equal(dynamic.validationMessage, '');
  unbind();
});

test('bind reselects a zero immediately before mobile or pointer insertion', () => {
  const root = new FakeRoot();
  const unbind = MoneyInput.bind(root);
  const input = new FakeInput('0.00');

  input.selectionStart = input.value.length;
  input.selectionEnd = input.value.length;
  root.dispatch('beforeinput', input, { inputType: 'insertText', data: '2' });
  assert.equal(input.selectCount, 1);
  assert.equal(input.selectionStart, 0);
  assert.equal(input.selectionEnd, input.value.length);

  input.value = '25'; // Simulate the browser replacing the selected zero value.
  root.dispatch('input', input, { inputType: 'insertText', data: '25' });
  root.dispatch('focusout', input);
  assert.equal(input.value, '25.00');

  input.value = '0.00';
  input.selectionStart = 0;
  input.selectionEnd = input.value.length;
  root.dispatch('beforeinput', input, { inputType: 'insertText', data: '2' });
  assert.equal(input.selectCount, 1);

  input.selectionStart = input.value.length;
  input.selectionEnd = input.value.length;
  root.dispatch('beforeinput', input, { inputType: 'deleteContentBackward' });
  assert.equal(input.selectCount, 1);
  unbind();
});

test('bind normalizes Enter input and prevents invalid keyboard submission', () => {
  const root = new FakeRoot();
  const unbind = MoneyInput.bind(root);
  const input = new FakeInput('42');

  const validEvent = root.dispatch('keydown', input, { key: 'Enter' });
  assert.equal(input.value, '42.00');
  assert.equal(validEvent.defaultPrevented, false);

  input.value = '42.00001';
  const invalidEvent = root.dispatch('keydown', input, { key: 'Enter' });
  assert.equal(input.value, '42.00001');
  assert.equal(invalidEvent.defaultPrevented, true);
  assert.equal(input.reportCount, 1);
  assert.notEqual(input.validationMessage, '');
  unbind();
});

test('bind is idempotent per root and its cleanup removes delegated listeners', () => {
  const root = new FakeRoot();
  const firstUnbind = MoneyInput.bind(root);
  assert.equal(MoneyInput.bind(root), firstUnbind);
  firstUnbind();

  const input = new FakeInput('5');
  root.dispatch('focusout', input);
  assert.equal(input.value, '5');
});

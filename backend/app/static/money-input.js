(function (root, factory) {
  const moneyInput = factory();

  if (typeof module === 'object' && module && module.exports) {
    module.exports = moneyInput;
  } else {
    root.MoneyInput = moneyInput;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const DEFAULT_SELECTOR = 'input[data-money-input]';
  const INVALID_AMOUNT_MESSAGE = 'Enter a valid monetary amount.';
  const EXCESS_PRECISION_MESSAGE = 'Amounts can have at most four decimal places.';
  const bindings = new WeakMap();

  class MoneyInputError extends Error {
    constructor(message, code) {
      super(message);
      this.name = 'MoneyInputError';
      this.code = code;
    }
  }

  function fail(message, code) {
    throw new MoneyInputError(message, code);
  }

  function format(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return '';

    const match = /^([+-]?)(?:(\d[\d,]*)(?:\.(\d*))?|\.(\d+))$/.exec(raw);
    if (!match) fail(INVALID_AMOUNT_MESSAGE, 'invalid');

    const sign = match[1];
    const integerPart = match[2] ?? '0';
    let fractionPart = match[2] === undefined ? match[4] : (match[3] ?? '');

    if (integerPart.includes(',') && !/^\d{1,3}(?:,\d{3})+$/.test(integerPart)) {
      fail(INVALID_AMOUNT_MESSAGE, 'invalid');
    }

    if (fractionPart.length > 4 && /[1-9]/.test(fractionPart.slice(4))) {
      fail(EXCESS_PRECISION_MESSAGE, 'precision');
    }

    const whole = integerPart.replaceAll(',', '').replace(/^0+(?=\d)/, '');
    fractionPart = fractionPart.slice(0, 4);
    while (fractionPart.length > 2 && fractionPart.endsWith('0')) {
      fractionPart = fractionPart.slice(0, -1);
    }
    fractionPart = fractionPart.padEnd(2, '0');

    const isZero = /^0+$/.test(whole) && /^0+$/.test(fractionPart);
    return `${sign === '-' && !isZero ? '-' : ''}${whole}.${fractionPart}`;
  }

  function setValidity(input, message) {
    if (typeof input.setCustomValidity === 'function') input.setCustomValidity(message);
  }

  function read(input, { blankAsZero = false } = {}) {
    if (!input || !('value' in Object(input))) {
      throw new TypeError('MoneyInput.read requires an input-like object.');
    }

    try {
      let value = format(input.value);
      if (!value && blankAsZero) value = '0.00';
      input.value = value;
      setValidity(input, '');
      return value;
    } catch (error) {
      setValidity(input, error instanceof MoneyInputError ? error.message : INVALID_AMOUNT_MESSAGE);
      throw error;
    }
  }

  function resolveRoot(root) {
    if (root) return root;
    if (typeof document !== 'undefined') return document;
    throw new TypeError('MoneyInput requires a root outside the browser.');
  }

  function matchingInput(target, selector) {
    return target && typeof target.matches === 'function' && target.matches(selector)
      ? target
      : null;
  }

  function controlsWithin(root, selector) {
    const controls = [];
    if (matchingInput(root, selector)) controls.push(root);
    if (typeof root.querySelectorAll === 'function') {
      for (const control of root.querySelectorAll(selector)) {
        if (!controls.includes(control)) controls.push(control);
      }
    }
    return controls;
  }

  function normalizeControl(control, options, reportInvalid = false) {
    try {
      read(control, options);
      return true;
    } catch {
      if (reportInvalid && typeof control.reportValidity === 'function') {
        control.reportValidity();
      }
      return false;
    }
  }

  function formatAll(root, { selector = DEFAULT_SELECTOR, blankAsZero = false } = {}) {
    const resolvedRoot = resolveRoot(root);
    const results = [];
    for (const control of controlsWithin(resolvedRoot, selector)) {
      results.push(normalizeControl(control, { blankAsZero }));
    }
    return results;
  }

  function bind(root, { selector = DEFAULT_SELECTOR, blankAsZero = false } = {}) {
    const resolvedRoot = resolveRoot(root);
    const existing = bindings.get(resolvedRoot);
    if (existing) return existing;
    if (typeof resolvedRoot.addEventListener !== 'function') {
      throw new TypeError('MoneyInput.bind requires an event target.');
    }

    formatAll(resolvedRoot, { selector, blankAsZero });

    const onFocusIn = event => {
      const control = matchingInput(event.target, selector);
      if (!control) return;
      try {
        if (format(control.value) === '0.00' && typeof control.select === 'function') {
          control.select();
        }
      } catch {
        // Invalid text should remain available for correction.
      }
    };

    const onFocusOut = event => {
      const control = matchingInput(event.target, selector);
      if (control) normalizeControl(control, { blankAsZero });
    };

    const onBeforeInput = event => {
      if (!String(event.inputType || '').startsWith('insert')) return;
      const control = matchingInput(event.target, selector);
      if (!control || control.selectionStart !== control.selectionEnd) return;
      try {
        if (format(control.value) === '0.00' && typeof control.select === 'function') {
          control.select();
        }
      } catch {
        // Invalid text should remain available for correction.
      }
    };

    const onInput = event => {
      const control = matchingInput(event.target, selector);
      if (control) setValidity(control, '');
    };

    const onKeyDown = event => {
      if (event.key !== 'Enter') return;
      const control = matchingInput(event.target, selector);
      if (!control) return;
      if (!normalizeControl(control, { blankAsZero }, true)) event.preventDefault();
    };

    resolvedRoot.addEventListener('focusin', onFocusIn);
    resolvedRoot.addEventListener('focusout', onFocusOut);
    resolvedRoot.addEventListener('beforeinput', onBeforeInput);
    resolvedRoot.addEventListener('input', onInput);
    resolvedRoot.addEventListener('keydown', onKeyDown);

    const unbind = () => {
      resolvedRoot.removeEventListener('focusin', onFocusIn);
      resolvedRoot.removeEventListener('focusout', onFocusOut);
      resolvedRoot.removeEventListener('beforeinput', onBeforeInput);
      resolvedRoot.removeEventListener('input', onInput);
      resolvedRoot.removeEventListener('keydown', onKeyDown);
      if (bindings.get(resolvedRoot) === unbind) bindings.delete(resolvedRoot);
    };
    bindings.set(resolvedRoot, unbind);
    return unbind;
  }

  return Object.freeze({
    DEFAULT_SELECTOR,
    MoneyInputError,
    bind,
    format,
    formatAll,
    read,
  });
});

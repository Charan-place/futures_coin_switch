;(function () {
  var safe = {
    getItem: function () { return null; },
    setItem: function () {},
    removeItem: function () {},
    clear: function () {},
    key: function () { return null; },
    length: 0,
  };
  try {
    // Replace the whole localStorage if it exists but is broken
    Object.defineProperty(globalThis, 'localStorage', {
      value: safe, writable: true, configurable: true,
    });
  } catch (e) {
    // Non-configurable — patch individual methods instead
    try {
      var ls = globalThis.localStorage;
      ['getItem', 'setItem', 'removeItem', 'clear', 'key'].forEach(function (m) {
        try {
          Object.defineProperty(ls, m, { value: safe[m], writable: true, configurable: true });
        } catch (_) {}
      });
    } catch (_) {}
  }
})();

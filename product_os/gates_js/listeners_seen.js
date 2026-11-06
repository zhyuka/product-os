(() => {
  const add = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, listener, options) {
    if (this instanceof Element) (this.__d2bOn = this.__d2bOn || new Set()).add(type);
    return add.call(this, type, listener, options);
  };
})()
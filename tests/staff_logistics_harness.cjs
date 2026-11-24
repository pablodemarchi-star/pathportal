const fs = require('node:fs');
const vm = require('node:vm');

function harness(fetcher) {
  const events = new Map(), windowEvents = new Map(), timers = new Map();
  let timerId = 0;
  const selectorMatch = (node, selector) => {
    if (selector.includes(',')) return selector.split(',').some(part => selectorMatch(node, part.trim()));
    if (selector === 'form') return node.tag === 'form';
    if (selector === 'a') return node.tag === 'a';
    if (selector.startsWith('.')) return node.className.split(' ').includes(selector.slice(1));
    const match = selector.match(/^\[([^=\]]+)(?:=["']?([^\]"']+)["']?)?\](:checked)?$/);
    if (!match) return false;
    const value = node.getAttribute(match[1]);
    return value !== null && (match[2] === undefined || value === match[2]) && (!match[3] || node.checked);
  };
  class Element {
    constructor(tag = 'div', attrs = {}) {
      this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.handlers = {};
      this.value = ''; this.className = ''; this.disabled = false; this.hidden = false;
      this.checked = false; this.innerHTML = ''; this.textContent = ''; this.type = ''; this.parentElement = null;
      for (const [name, value] of Object.entries(attrs)) this.setAttribute(name, value);
      this.classList = {
        add: cls => { this.className += ' ' + cls; },
        remove: cls => { this.className = this.className.split(' ').filter(x => x !== cls).join(' '); }
      };
    }
    setAttribute(name, value = '') {
      this.attributes[name] = String(value);
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
      else if (name === 'class') this.className = String(value);
      else this[name] = String(value);
    }
    getAttribute(name) {
      if (name.startsWith('data-')) return this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] ?? null;
      if (name === 'class') return this.className;
      return this.attributes[name] ?? (name === 'name' && this.name ? this.name : null);
    }
    hasAttribute(name) { return this.getAttribute(name) !== null; }
    removeAttribute(name) { delete this.attributes[name]; delete this[name]; }
    matches(selector) { return selectorMatch(this, selector); }
    closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
    append(...nodes) { for (const node of nodes) { node.remove(); this.children.push(node); node.parentElement = this; } }
    replaceChildren(...nodes) { for (const node of [...this.children]) node.remove(); this.append(...nodes); }
    insertBefore(node, target) { node.remove(); const at = target ? this.children.indexOf(target) : this.children.length; this.children.splice(at, 0, node); node.parentElement = this; }
    remove() { if (this.parentElement) this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1); this.parentElement = null; }
    get previousElementSibling() { return this.parentElement?.children[this.parentElement.children.indexOf(this) - 1] || null; }
    get nextElementSibling() { return this.parentElement?.children[this.parentElement.children.indexOf(this) + 1] || null; }
    get nextSibling() { return this.nextElementSibling; }
    get isConnected() { return this === document.body || Boolean(this.parentElement?.isConnected); }
    querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    addEventListener(name, fn) { this.handlers[name] = fn; }
    focus() { document.activeElement = this; }
    setPointerCapture() {}
    getBoundingClientRect() { return {top: 100, height: 40}; }
    showModal() { this.open = true; }
    close() { this.open = false; this.handlers.close?.(); }
    checkValidity() { return true; }
    dispatchEvent(event) { emit(event.type, this); }
  }
  const register = (map, name, fn) => map.set(name, [...(map.get(name) || []), fn]);
  const document = {
    addEventListener: (name, fn) => register(events, name, fn),
    createElement: tag => new Element(tag),
    querySelectorAll: selector => document.body.querySelectorAll(selector),
    querySelector: selector => document.body.querySelector(selector),
    elementFromPoint: () => document.pointTarget,
    execCommand: cmd => document.commands.push(cmd), commands: []
  };
  document.body = new Element('body');
  const range = {collapsed: false, cloneRange() { return this; }, commonAncestorContainer: null};
  const window = {
    location: {href: 'https://portal.test/modal', assign() { throw new Error('Autosave must not reload the modal'); }},
    addEventListener: (name, fn) => register(windowEvents, name, fn),
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id),
    getSelection: () => ({rangeCount: 1, getRangeAt: () => range, removeAllRanges() {}, addRange() {}})
  };
  class FormData {
    constructor(form) { this.values = {}; for (const input of form.querySelectorAll('[name]')) this.values[input.name] = input.value; }
    set(name, value) { this.values[name] = value; }
  }
  function form(id) {
    const article = new Element('article', {class: 'staff-logistics-card'});
    const chip = new Element('span', {class: 'staff-logistics-state'}); article.append(chip);
    const form = new Element('form', {'data-logistics-card-form': '', 'data-card-id': id, 'data-session-id': '10'});
    form.action = `https://portal.test/pre-session-control-tower/logistics/cards/${id}`;
    const fieldset = new Element('fieldset', {class: 'staff-logistics-editor'});
    const session = new Element('input', {name: 'session_ids'}); session.value = '10'; session.checked = true;
    const status = new Element('select', {name: 'status'}); status.value = 'Pending';
    const wrapper = new Element('div', {'data-logistics-rich-text': ''});
    const editor = new Element('div', {'data-logistics-instructions-editor': '', contenteditable: 'true'});
    const hidden = new Element('input', {name: 'instructions_html'});
    const panel = new Element('div', {'data-logistics-rich-link-panel': ''}); panel.hidden = true;
    const error = new Element('span', {'data-logistics-rich-link-error': ''});
    const url = new Element('input', {'data-logistics-rich-link-url': ''}); panel.append(url, error);
    wrapper.append(editor, hidden, panel);
    const links = new Element('div', {'data-logistics-links': ''});
    const add = new Element('button', {'data-add-logistics-link': ''});
    const retry = new Element('button', {'data-logistics-retry': ''}); retry.hidden = true;
    const output = new Element('span', {'data-logistics-save-status': ''});
    fieldset.append(session, status, wrapper, links, add, retry, output); form.append(fieldset);
    article.append(form); document.body.append(article);
    return {form, article, chip, editor, hidden, links, add, retry, output, status, session, fieldset, wrapper, panel, error, url};
  }
  const first = form('1'), second = form('2');
  const requests = [];
  const fetch = async (url, options) => {
    requests.push({url, options});
    return fetcher ? fetcher(url, options, requests.length) : {ok: true, status: 200, json: async () => ({ok: true, status: options.body.values.status})};
  };
  const context = {document, window, URL, FormData, Event: class {constructor(type) {this.type = type;}}, fetch};
  vm.runInNewContext(fs.readFileSync('app/static/js/staff_logistics.js', 'utf8'), context);
  function emit(type, target, extra = {}) {
    const event = {type, target, preventDefault() {this.prevented = true;}, ...extra};
    return Promise.all((events.get(type) || []).map(fn => fn(event)));
  }
  const settle = () => new Promise(resolve => setImmediate(resolve));
  async function flush() { for (const [id, fn] of [...timers]) { timers.delete(id); fn(); } await settle(); }
  const beforeUnload = () => { const event = {preventDefault() {this.prevented = true;}}; for (const fn of windowEvents.get('beforeunload') || []) fn(event); return event; };
  return {window, document, first, second, Element, emit, flush, settle, requests, range, beforeUnload};
}
module.exports = {harness};

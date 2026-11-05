const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/tower_live.js', 'utf8');

function childContext() {
  const events = new Map();
  const timers = [];
  const messages = [];
  const posts = [];
  const fields = new Map();
  const timeoutJobs = [];
  const input = {type: 'text', value: 'Draft', isConnected: true, closest: () => form};
  const form = {
    method: 'post', action: 'https://portal.test/save', isConnected: true, elements: [input],
    querySelector: selector => fields.get(selector.match(/name="([^"]+)"/)?.[1]) || null,
    append: input => fields.set(input.name, input)
  };
  const message = {textContent: ''};
  const reloadButton = {hidden: false, addEventListener() {}};
  const notice = {hidden: true, querySelector: selector => selector.includes('message') ? message : reloadButton};
  const body = {
    dataset: {sessionId: '7', revision: 'r1', revisionUrl: '/revision'},
    matches: () => true, hasAttribute: () => false
  };
  const document = {
    body, forms: [form], hidden: false, activeElement: null,
    currentScript: {src: 'https://portal.test/static/js/tower_live.js'},
    querySelector: selector => selector === '[data-tower-update-notice]' ? notice : null,
    querySelectorAll: selector => selector === 'form' ? [form] : [],
    createElement: () => ({}),
    addEventListener: (type, listener) => {
      if (!events.has(type)) events.set(type, []);
      events.get(type).push(listener);
    }
  };
  let remote = 'r1';
  let reloads = 0;
  const window = {
    location: {href: 'https://portal.test/modal', origin: 'https://portal.test', reload: () => reloads++},
    parent: {postMessage: data => messages.push(data)},
    frameElement: {closest: () => ({classList: {contains: () => true}})},
    fetch: async (input, options = {}) => {
      if ((options.method || 'GET') === 'POST') {
        posts.push(options.headers.get('X-Tower-Revision'));
        remote = `r${posts.length + 1}`;
        return new Response('{"ok":true}', {headers: {'Content-Type': 'application/json', 'X-Tower-Revision': remote}});
      }
      return new Response(JSON.stringify({revision: remote}), {headers: {'Content-Type': 'application/json'}});
    },
    addEventListener() {}, setInterval: fn => timers.push(fn), confirm: () => true
  };
  const context = vm.createContext({window, document, URL, Request, Response, Headers,
    MutationObserver: class {observe() {}}, Element: class {},
    sessionStorage: {setItem() {},getItem: () => null,removeItem() {}}, setTimeout: fn => timeoutJobs.push(fn), console});
  vm.runInContext(source, context);
  return {window, form, input, fields, notice, message, timers, posts, messages,
    flushTimeouts: () => timeoutJobs.splice(0).forEach(fn => fn()),
    setRemote: value => {remote = value;}, reloads: () => reloads,
    edit: () => events.get('input').forEach(listener => listener({target: input, isTrusted: true}))};
}

(async () => {
  const concurrent = childContext();
  concurrent.edit();
  await Promise.all([
    concurrent.window.fetch('https://portal.test/save', {method:'POST'}),
    concurrent.window.fetch('https://portal.test/save', {method:'POST'})
  ]);
  assert.deepEqual(concurrent.posts, ['r1', 'r2'], 'Our own simultaneous autosaves must use sequential snapshots');
  assert.equal(concurrent.fields.get('tower_revision').value, 'r3');
  assert.equal(concurrent.notice.hidden, true);

  const finance = childContext();
  finance.edit();
  await finance.window.fetch('https://portal.test/save', {method:'POST', headers:{'X-Finance-Autosave':'1'}});
  finance.flushTimeouts();
  assert.equal(finance.fields.get('tower_revision').value, 'r2');
  assert.ok(finance.messages.some(message => message.type === 'tower-session-saved'));
  assert.equal(finance.messages.some(message => message.type === 'tower-session-refresh-request'), false,
    'Finance autosave must update the revision without refreshing the modal');

  const draft = childContext();
  draft.edit(); draft.setRemote('someone-elses-change');
  await draft.timers[0]();
  assert.equal(draft.message.textContent, 'This session was updated by another user.');
  assert.equal(draft.notice.hidden, false);
  assert.equal(draft.reloads(), 0, 'Never reload while the user has unsaved edits');
  const refused = await draft.window.fetch('https://portal.test/save', {method:'POST'});
  assert.equal(refused.status, 409);
  await refused.json();
  draft.input.value = 'Old value restored by a legacy error handler';
  draft.flushTimeouts();
  assert.equal(draft.input.value, 'Draft', 'A stale autosave must retain the typed draft');
  assert.equal(draft.posts.length, 0, 'Known stale drafts must not be submitted');

  const reader = childContext();
  reader.setRemote('fresh-information');
  await reader.timers[0]();
  assert.equal(reader.reloads(), 0, 'Automatic refresh must keep the current document until its replacement is ready');
  assert.ok(reader.messages.some(message => message.type === 'tower-session-refresh-request'), 'Read-only modals ask the parent for a staged refresh');
  assert.equal(reader.messages[0].type, 'tower-session-refresh-request');
  console.log('Tower live: autosave serialization, stale draft preservation, and reader refresh passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});

// Lazy opens keep the active table filters and request the selected block only.
{
  const frame = {};
  const loading = {};
  const header = {};
  const retry = {};
  const nodes = {'[data-tower-frame]':frame, '[data-tower-loading]':loading,
    '[data-tower-loading-header]':header, '[data-tower-retry]':retry};
  const modal = {dataset:{towerSession:'7'}, querySelector:key=>nodes[key],
    classList:{contains:key=>key==='is-staffing-only'}};
  const window = {
    location:{href:'https://portal.test/pre-session-control-tower?session_year=2026&view=bundle&bundle_id=3&bundle_q=Patagonian&schedule_only=1&open_schedule_action=mark_ready',origin:'https://portal.test'},
    fetch:async()=>new Response(''), addEventListener() {}
  };
  const document = {body:{matches:()=>false},currentScript:{src:'https://portal.test/static/js/tower_live.js'}};
  vm.runInNewContext(source,{window,document,URL});
  window.loadTowerModal(modal,{dataset:{modalScrollTarget:'staffing-7'}});
  const url = new URL(frame.src);
  assert.equal(url.searchParams.get('session_modal'),'7');
  assert.equal(url.searchParams.get('open_modal_target'),'staffing');
  assert.equal(url.searchParams.get('staffing_only'),'1');
  assert.equal(url.searchParams.get('bundle_q'),'Patagonian');
  assert.equal(url.searchParams.get('bundle_id'),'3');
  assert.equal(url.searchParams.has('schedule_only'),false);
  assert.equal(url.searchParams.has('open_schedule_action'),false);
  frame.onload();
  assert.equal(retry.hidden,false,'A failed modal load must offer a retry');
  assert.match(loading.textContent,/could not be loaded/);
  console.log('Tower lazy load: session, block, filter context, and load failure retry passed.');
}

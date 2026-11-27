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
  let reloadClick;
  const reloadButton = {hidden: false, addEventListener(type, callback) {reloadClick=callback;}};
  const notice = {hidden: true, dataset:{}, querySelector: selector => selector.includes('message') ? message : reloadButton};
  const body = {
    dataset: {sessionId: '7', revision: 'r1', revisionUrl: '/revision'},
    matches: () => true, hasAttribute: () => false
  };
  const document = {
    body, forms: [form], hidden: false, activeElement: null,
    currentScript: {src: 'https://portal.test/static/js/tower_live.js'},
    querySelector: selector => selector === '[data-tower-update-notice]' ? notice : selector === '.modal.is-open' ? {id:'schedule-workflow-7',classList:{contains:name=>name==='is-finance-only'}} : null,
    querySelectorAll: selector => selector === 'form' ? [form] : [],
    createElement: () => ({}),
    addEventListener: (type, listener) => {
      if (!events.has(type)) events.set(type, []);
      events.get(type).push(listener);
    }
  };
  let remote = 'r1';
  let pauseReads=false;
  const reads=[];
  let reloads = 0;
  const navigations = [];
  const windowEvents = new Map();
  let failPosts=false,failReads=false;
  let holdPosts=false;const heldPosts=[];
  const window = {
    location: {href: 'https://portal.test/modal', origin: 'https://portal.test', reload: () => reloads++, assign:url=>navigations.push(url)},
    parent: {postMessage: data => messages.push(data)},
    frameElement: {closest: () => ({classList: {contains: () => true}})},
    fetch: async (input, options = {}) => {
      if ((options.method || 'GET') === 'POST') {
        if(failPosts)throw new Error('Offline');
        if(holdPosts)await new Promise(resolve=>heldPosts.push(resolve));
        posts.push(options.headers.get('X-Tower-Revision'));
        remote = `r${posts.length + 1}`;
        return new Response('{"ok":true}', {headers: {'Content-Type': 'application/json', 'X-Tower-Revision': remote}});
      }
      if(failReads)throw new Error('Check unavailable');
      const snapshot = remote;
      if(pauseReads)await new Promise(resolve=>reads.push(resolve));
      return new Response(JSON.stringify({revision: snapshot}), {headers: {'Content-Type': 'application/json'}});
    },
    addEventListener(type, fn) {if(!windowEvents.has(type))windowEvents.set(type,[]);windowEvents.get(type).push(fn);}, setInterval: fn => timers.push(fn), confirm: () => true
  };
  const context = vm.createContext({window, document, URL, Request, Response, Headers,
    MutationObserver: class {observe() {}}, Element: class {},
    sessionStorage: {setItem() {},getItem: () => null,removeItem() {}}, setTimeout: fn => timeoutJobs.push(fn), console});
  vm.runInContext(source, context);
  return {window, form, input, fields, notice, message, timers, posts, messages, navigations, failPosts:value=>failPosts=value, failReads:value=>failReads=value, holdPosts:()=>holdPosts=true, releasePosts:()=>{holdPosts=false;heldPosts.splice(0).forEach(resolve=>resolve());}, parentMessage:type=>(windowEvents.get('message')||[]).forEach(fn=>fn({origin:window.location.origin,source:window.parent,data:{type}})), reloadClick:()=>reloadClick(),
    flushTimeouts: () => timeoutJobs.splice(0).forEach(fn => fn()),
    pauseReads:()=>{pauseReads=true;}, releaseReads:()=>{pauseReads=false;reads.splice(0).forEach(resolve=>resolve());}, setRemote: value => {remote = value;}, reloads: () => reloads,
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
  assert.equal(concurrent.message.textContent, 'Saved');

  const finance = childContext();
  finance.edit();
  await finance.window.fetch('https://portal.test/save', {method:'POST', headers:{'X-Finance-Autosave':'1'}});
  finance.flushTimeouts();
  assert.equal(finance.fields.get('tower_revision').value, 'r2');
  assert.ok(finance.messages.some(message => message.type === 'tower-session-saved'));
  assert.equal(finance.messages.some(message => message.type === 'tower-session-refresh-request'), false,
    'Finance autosave must update the revision without refreshing the modal');

  const logistics = childContext();
  logistics.form.hasAttribute = name => name === 'data-logistics-card-form';
  let pendingLogistics = true;
  logistics.window.logisticsHasUnsavedChanges = () => pendingLogistics;
  logistics.edit();
  assert.equal(logistics.window.towerHasUnsavedChanges(), true);
  await logistics.window.fetch('https://portal.test/save', {method: 'POST', headers: {'X-Logistics-Autosave': '1'}});
  logistics.flushTimeouts();
  assert.equal(logistics.window.towerHasUnsavedChanges(), true, 'An older response must not clear newer Logistics drafts');
  pendingLogistics = false;
  assert.equal(logistics.window.towerHasUnsavedChanges(), false);
  assert.equal(logistics.messages.some(message => message.type === 'tower-session-refresh-request'), false,
    'Logistics autosave must preserve the current modal and its other cards');

  const draft = childContext();
  draft.edit(); draft.setRemote('someone-elses-change');
  await draft.timers[0]();
  assert.equal(draft.message.textContent, 'Not saved');
  assert.match(draft.notice.title,/New session information/);
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
  const raced=childContext();raced.pauseReads();
  const oldPoll=raced.timers[0]();
  await raced.window.fetch('https://portal.test/save',{method:'POST',headers:{'X-Finance-Autosave':'1'}});
  raced.releaseReads();await oldPoll;
  assert.equal(raced.message.textContent,'Saved','An earlier poll must not mistake our own save for another user');
  assert(!raced.messages.some(item=>item.type==='tower-session-refresh-request'));
  const status=childContext();assert.equal(status.message.textContent,'Saved');
  status.edit();assert.equal(status.message.textContent,'Unsaved changes');
  status.holdPosts();const saving=status.window.fetch('https://portal.test/save',{method:'POST',headers:{'X-Finance-Autosave':'1'}});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(status.message.textContent,'Saving…');
  status.releasePosts();await saving;status.flushTimeouts();assert.equal(status.message.textContent,'Saved');
  status.parentMessage('tower-refresh-failed');assert.equal(status.message.textContent,'Saved');
  status.failReads(true);await status.timers[0]();assert.equal(status.message.textContent,'Saved');status.failReads(false);
  status.edit();status.parentMessage('tower-refresh-deferred');assert.equal(status.message.textContent,'Unsaved changes');
  status.failPosts(true);await assert.rejects(status.window.fetch('https://portal.test/save',{method:'POST'}));
  status.flushTimeouts();assert.equal(status.message.textContent,'Not saved');assert.equal(status.input.value,'Draft');
  status.failPosts(false);await status.window.fetch('https://portal.test/save',{method:'POST',headers:{'X-Finance-Autosave':'1'}});
  status.flushTimeouts();assert.equal(status.message.textContent,'Saved');
  const newerEdit=childContext();newerEdit.edit();newerEdit.holdPosts();
  const olderSave=newerEdit.window.fetch('https://portal.test/save',{method:'POST',headers:{'X-Finance-Autosave':'1'}});
  await new Promise(resolve=>setImmediate(resolve));newerEdit.edit();newerEdit.input.value='Newer answer';newerEdit.releasePosts();await olderSave;
  newerEdit.flushTimeouts();assert.equal(newerEdit.message.textContent,'Unsaved changes');assert.equal(newerEdit.input.value,'Newer answer');
  const queued=childContext();queued.edit();queued.holdPosts();
  const firstQueued=queued.window.fetch('https://portal.test/save',{method:'POST',headers:{'X-Finance-Autosave':'1'}});
  const secondQueued=queued.window.fetch('https://portal.test/save',{method:'POST',headers:{'X-Finance-Autosave':'1'}});
  await new Promise(resolve=>setImmediate(resolve));queued.edit();queued.input.value='Typed after both requests were queued';
  queued.releasePosts();await Promise.all([firstQueued,secondQueued]);queued.flushTimeouts();
  assert.equal(queued.message.textContent,'Unsaved changes','Queued requests must not acknowledge answers typed after their bodies were captured');
  const manual=childContext();manual.reloadClick();
  const manualURL=new URL(manual.navigations[0]);
  assert.equal(manualURL.searchParams.get('session_modal'),'7');
  assert.equal(manualURL.searchParams.get('open_schedule_modal'),'7');
  assert.equal(manualURL.searchParams.get('finance_only'),'1');
  console.log('Tower live: autosave serialization, stale draft preservation, and reader refresh passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});

// Lazy opens keep the active table filters and request the selected block only.
{
  const frame = {};
  const loading = {};
  const header = {};
  const retry = {};
  const title = {textContent:'Test session'};
  const nodes = {'[data-tower-frame]':frame, '[data-tower-loading]':loading,
    '[data-tower-loading-header]':header, '[data-tower-retry]':retry, '[data-tower-loading-title]':title};
  let mode = 'staffing';
  const modal = {dataset:{towerSession:'7',towerSessionName:'Test session',towerBundleNumber:'27-26'}, querySelector:key=>nodes[key],
    classList:{contains:key=>key===`is-${mode}-only`}};
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
  mode='shipments';
  window.loadTowerModal(modal,{dataset:{modalScrollTarget:'shipments-7',modalBundleNumber:'28-26'}});
  assert.equal(title.textContent,'Bundle 28-26','Use the current bundle opener instead of a session name');
  assert.equal(loading.textContent,'Loading bundle details…');
  assert.equal(frame.title,'Bundle 28-26 — bundle details');
  frame.onload();
  assert.match(loading.textContent,/Bundle details could not be loaded/);
  retry.onclick();
  assert.equal(title.textContent,'Bundle 28-26');
  assert.equal(loading.textContent,'Loading bundle details…');
  mode='staffing';
  window.loadTowerModal(modal,{dataset:{modalScrollTarget:'staffing-7'}});
  assert.equal(title.textContent,'Test session');
  assert.equal(loading.textContent,'Loading session details…');
  assert.equal(frame.title,'Test session — session details');
  console.log('Tower lazy load: bundle/session loading titles, retries, mode changes and filter context passed.');
}

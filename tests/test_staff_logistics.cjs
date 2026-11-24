const assert = require('node:assert/strict');
const {harness} = require('./staff_logistics_harness.cjs');

(async () => {
  const h = harness();
  const {first: a, second: b} = h;
  a.editor.innerHTML = '<p><strong>Flight details</strong></p>';
  b.editor.innerHTML = '<p>Hotel instructions</p>';
  await h.emit('input', a.editor); await h.emit('input', b.editor);
  assert.equal(h.window.logisticsHasUnsavedChanges(), true);
  assert.equal(h.beforeUnload().prevented, true);
  await h.flush();
  assert.equal(h.requests.length, 2, 'Both edited cards save without a reload');
  assert.equal(h.requests[0].options.body.values.instructions_html, a.editor.innerHTML);
  assert.equal(h.requests[1].options.body.values.instructions_html, b.editor.innerHTML);
  assert.equal(h.requests[0].options.headers['X-Logistics-Autosave'], '1');
  assert.equal(a.output.textContent, 'Saved'); assert.equal(b.output.textContent, 'Saved');
  assert.equal(h.window.logisticsHasUnsavedChanges(), false);
  assert.equal(h.beforeUnload().prevented, undefined);

  await h.emit('click', a.add); await h.flush();
  assert.equal(h.requests.length, 2, 'Incomplete new links stay local and never overwrite the server');
  assert.match(a.output.textContent, /Complete each link/);
  assert.equal(h.window.logisticsHasUnsavedChanges(), true);
  const row = a.links.children[0];
  row.querySelector('[data-link-name]').value = 'Hotel';
  row.querySelector('[data-link-url]').value = 'https://example.com/hotel';
  await h.emit('input', row.querySelector('[data-link-url]')); await h.flush();
  assert.equal(row.querySelector('a').href, 'https://example.com/hotel');
  assert.deepEqual(JSON.parse(h.requests.at(-1).options.body.values.links), [{name: 'Hotel', url: 'https://example.com/hotel'}]);

  // A late response cannot mark a newer draft Saved or overwrite it.
  let release;
  const delayed = harness(async (_, options, n) => {
    if (n === 1) await new Promise(resolve => {release = resolve;});
    return {ok: true, status: 200, json: async () => ({ok: true, status: options.body.values.status})};
  });
  delayed.first.editor.innerHTML = 'Original'; await delayed.emit('input', delayed.first.editor); await delayed.flush();
  assert.equal(delayed.first.output.textContent, 'Saving…');
  delayed.first.editor.innerHTML = 'Latest draft'; await delayed.emit('input', delayed.first.editor);
  delayed.second.editor.innerHTML = 'Other card draft'; await delayed.emit('input', delayed.second.editor); await delayed.flush();
  assert.equal(delayed.requests.length, 1, 'Writes are serialized');
  assert.equal(delayed.window.logisticsHasUnsavedChanges(), true);
  release(); await delayed.settle(); await delayed.settle();
  assert.equal(delayed.requests.length, 3);
  assert.equal(delayed.requests.at(-1).options.body.values.instructions_html, 'Latest draft');
  assert.equal(delayed.first.editor.innerHTML, 'Latest draft');
  assert.equal(delayed.window.logisticsHasUnsavedChanges(), false);

  // Failed requests keep the draft and a warning until an explicit retry succeeds.
  let fail = true;
  const failed = harness(async () => {if (fail) throw new Error('Network unavailable'); return {ok: true, json: async () => ({ok: true})};});
  failed.first.editor.innerHTML = 'Keep this draft'; await failed.emit('input', failed.first.editor); await failed.flush();
  assert.equal(failed.first.retry.hidden, false); assert.match(failed.first.output.textContent, /Network/);
  assert.equal(failed.beforeUnload().prevented, true); assert.equal(failed.first.editor.innerHTML, 'Keep this draft');
  fail = false; await failed.emit('click', failed.first.retry); await failed.settle();
  assert.equal(failed.first.output.textContent, 'Saved'); assert.equal(failed.first.retry.hidden, true);
  assert.equal(failed.window.logisticsHasUnsavedChanges(), false);

  // Keyboard and pointer reordering serialize the DOM order used by the portal.
  await h.emit('click', a.add);
  const other = a.links.children[1];
  other.querySelector('[data-link-name]').value = 'Tickets'; other.querySelector('[data-link-url]').value = 'https://example.com/tickets';
  await h.emit('input', other.querySelector('[data-link-name]')); await h.flush();
  await h.emit('keydown', other.querySelector('[data-logistics-drag-handle]'), {key: 'ArrowUp'}); await h.flush();
  assert.deepEqual(JSON.parse(h.requests.at(-1).options.body.values.links).map(x => x.name), ['Tickets', 'Hotel']);
  h.document.pointTarget = row;
  await h.emit('pointerdown', other.querySelector('[data-logistics-drag-handle]'), {button: 0, pointerId: 1, clientY: 90});
  await h.emit('pointermove', other.querySelector('[data-logistics-drag-handle]'), {clientX: 1, clientY: 135});
  await h.emit('pointerup', other.querySelector('[data-logistics-drag-handle]')); await h.flush();
  assert.deepEqual(JSON.parse(h.requests.at(-1).options.body.values.links).map(x => x.name), ['Hotel', 'Tickets']);
  await h.emit('click', row.querySelector('[data-remove-logistics-link]')); await h.flush();
  assert.equal(JSON.parse(h.requests.at(-1).options.body.values.links).length, 1);

  // Rich text commands still sync the hidden HTML and schedule an autosave.
  h.range.commonAncestorContainer = a.editor; a.editor.nodeType = 1; await h.emit('selectionchange', a.editor);
  const action = new h.Element('button', {'data-logistics-text-command': 'bold'}); a.wrapper.append(action);
  await h.emit('click', action); await h.flush();
  assert.equal(h.document.commands.at(-1), 'bold'); assert.equal(a.hidden.value, a.editor.innerHTML);
  const linkAction = new h.Element('button', {'data-logistics-text-link': ''}); a.wrapper.append(linkAction);
  const applyLink = new h.Element('button', {'data-logistics-rich-link-apply': ''}); a.wrapper.append(applyLink);
  await h.emit('click', linkAction); assert.equal(a.panel.hidden, false);
  a.url.value = 'javascript:alert(1)'; await h.emit('click', applyLink);
  assert.match(a.error.textContent, /http/); assert.equal(h.document.commands.at(-1), 'bold');
  a.url.value = 'https://example.com/booking'; await h.emit('click', applyLink);
  assert.equal(h.document.commands.at(-1), 'createLink'); assert.equal(a.panel.hidden, true);
  a.fieldset.disabled = true;
  const count = h.requests.length; await h.emit('click', a.add);
  assert.equal(h.requests.length, count);
  console.log('Logistics: multiple-card autosaves, in-flight drafts, errors/retry, close warnings, pointer/keyboard link order, rich text and read-only controls passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});

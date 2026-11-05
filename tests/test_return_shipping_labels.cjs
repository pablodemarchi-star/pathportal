const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const handlers = () => ({events: {}, addEventListener(event, fn) {this.events[event] = fn;}});
const input = {...handlers(), disabled: false, files: [], value: '', matches: () => input.disabled};
const remove = {...handlers(), disabled: false};
const drop = {...handlers(), hidden: false, classList: {add() {}, remove() {}}};
const documentRow = {hidden: true};
const link = {};
const feedback = {hidden: true, classList: {add() {}, remove() {}}};
const form = {dataset: {returnEnabled: 'true'}, querySelector: () => ({value: 'csrf-token'})};
const elements = {'[data-return-label-file]': input, '[data-return-label-delete]': remove,
  '[data-return-label-dropzone]': drop, '[data-return-label-document]': documentRow,
  '[data-return-label-view]': link, '[data-return-label-feedback]': feedback};
const widget = {dataset: {url: '/label', fileId: '', filePresent: 'false'},
  closest: () => form, querySelector: selector => elements[selector]};
const posts = [];
let saved = null, failDelete = false, syncs = 0;
const context = {document: {querySelectorAll: () => [widget], querySelector: () => null}, window: {},
  FormData, setTimeout, WeakMap, returnMaterialsSaveQueues: new WeakMap(),
  syncReturnMaterialsOptions: () => syncs++,
  fetch: async (url, options = {}) => {
    if (options.method === 'POST') {
      posts.push(options.body);
      if (options.body.get('action') === 'delete') {
        if (failDelete) return {ok: false, json: async () => ({ok: false, error: 'Drive trash failed'})};
        saved = null;
      } else saved = {file_id: 'uploaded-label', filename: options.body.get('document').name, url: '/private-label'};
    }
    return {ok: true, json: async () => ({ok: true, document: saved})};
  }};
vm.runInNewContext(fs.readFileSync('app/static/js/return_shipping_labels.js', 'utf8'), context);
const tick = () => new Promise(resolve => setTimeout(resolve, 10));
(async () => {
  const file = new File(['pdf bytes'], 'label.pdf', {type: 'application/pdf'});
  drop.events.drop({preventDefault() {}, dataTransfer: {files: [file]}});
  await tick();
  assert.equal(posts.length, 1);
  assert.equal(posts[0].get('document').name, 'label.pdf');
  assert.equal(widget.dataset.filePresent, 'true');
  assert.equal(link.textContent, 'label.pdf');
  assert.equal(drop.hidden, true);
  drop.events.drop({preventDefault() {}, dataTransfer: {files: [file, file]}});
  await tick();
  assert.equal(posts.length, 1);
  assert.match(feedback.textContent, /exactly one/);
  failDelete = true;
  await remove.events.click();
  assert.equal(widget.dataset.fileId, 'uploaded-label');
  assert.equal(documentRow.hidden, false);
  assert.equal(feedback.textContent, 'Drive trash failed');
  failDelete = false;
  await remove.events.click();
  assert.equal(posts.at(-1).get('previous_file_id'), 'uploaded-label');
  assert.equal(widget.dataset.filePresent, 'false');
  assert.equal(drop.hidden, false);
  assert.equal(documentRow.hidden, true);
  assert.ok(syncs > 0);
  form.dataset.returnEnabled = 'false';
  const previous = posts.length;
  drop.events.drop({preventDefault() {}, dataTransfer: {files: [file]}});
  await tick();
  assert.equal(posts.length, previous);
  console.log('Return label widget: single-file drop, private view, delete, error preservation and blocked editing passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});

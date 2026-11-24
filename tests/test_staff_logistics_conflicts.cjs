const assert = require('node:assert/strict');
const {harness} = require('./staff_logistics_harness.cjs');

async function scenario(cancel) {
  const conflict = {ok: false, code: 'logistics_card_conflict', conflict_token: 'snapshot-token',
    sessions: ['Session A', 'Session B'], cards: [
      {id: 1, name: 'Staff', sessions: ['Session A'], status: 'Pending', link_count: 0, description: 'Source'},
      {id: 2, name: 'Staff', sessions: ['Session B'], status: 'Completed', link_count: 1, description: 'Other instructions'}]};
  const h = harness(async (_, options, n) => {
    if (n === 1) return {status: 409, ok: false, json: async () => conflict};
    assert.equal(options.body.values.keep_card_id, '2');
    assert.equal(options.body.values.conflict_token, 'snapshot-token');
    return {status: 200, ok: true, json: async () => ({ok: true, card_id: 2, status: 'Pending', scope_changed: true,
      retired_card_ids: [1], card: {session_ids: [10], instructions_html: '<p>Retained instructions</p>', links: [{name: 'Booking', url: 'https://example.com/booking'}]}})};
  });
  h.first.editor.innerHTML = 'Source draft'; await h.emit('input', h.first.editor); await h.flush();
  const modal = h.document.body.children.find(node => node.tag === 'dialog');
  assert.ok(modal); assert.equal(modal.open, true); assert.equal(h.requests.length, 1);
  const options = modal.children[4], footer = modal.children[5];
  assert.equal(footer.children[1].disabled, true); assert.match(modal.children[2].textContent, /cancelled/);
  assert.equal(options.children[1].children[1].children[3].textContent, 'Other instructions');
  if (cancel) footer.children[0].handlers.click();
  else {options.children[1].children[0].handlers.change(); footer.children[1].handlers.click();}
  await h.settle(); await h.settle();
  assert.equal(h.requests.length, cancel ? 1 : 2); assert.equal(modal.isConnected, false);
  if (cancel) {
    assert.match(h.first.output.textContent, /not saved/);
    assert.equal(h.window.logisticsHasUnsavedChanges(), true);
    assert.equal(h.first.editor.innerHTML, 'Source draft');
  } else {
    assert.equal(h.first.form.dataset.cardId, '2'); assert.match(h.first.form.action, /cards\/2$/);
    assert.equal(h.first.editor.innerHTML, '<p>Retained instructions</p>');
    assert.equal(h.second.article.isConnected, false);
    assert.equal(h.first.links.children[0].querySelector('[data-link-name]').value, 'Booking');
    assert.equal(h.window.logisticsHasUnsavedChanges(), false);
  }
}
(async () => {
  await scenario(true); await scenario(false);
  console.log('Logistics sharing: cancellation preserves drafts, explicit retained-card choice, confirmation token and canonical card update without reloading passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});

const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('app/static/js/staff_exam_sessions.js', 'utf8');
const shared = fs.readFileSync('app/static/js/app.js', 'utf8');
const makeNode = tag => ({tag, children: [], style: {}, append(...items) { this.children.push(...items); }, setAttribute() {}});
for (const format of ['Onsite', 'Online']) {
  const materials = {children: [], insertBefore(node) { this.children.push(node); }};
  const context = {URL, document: {createElement: makeNode}, materials, role: 'Examiner', zoomAccess: null,
    data: {format, material_for_examiners_url: 'https://example.com/configured-material'},
    cleanEmailValue: value => String(value || '').trim(), SINAPSIS_LOGIN_URL: 'https://sinapsis.pathexaminations.com/login',
    OFFICIAL_CONFIRMATION_MATERIAL_URL: 'https://example.com/fallback'};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  const make ='), source.indexOf('  const hydrate =')) +
    shared.slice(shared.indexOf('const officialMaterialRows ='), shared.indexOf('const officialMaterialDescriptionHtml =')) +
    'const rows = officialMaterialRows(role, data);' +
    source.slice(source.indexOf('      rows.forEach('), source.indexOf('      if (!rows.length')), context);
  assert.equal(materials.children[0].children[0].textContent, '🗓️ Exam session schedule');
  const block = materials.children[1];
  assert.equal(block.children[0].textContent, format === 'Online' ? '🗣️ Material for examiners' : '🎧🗣️ Material for examiners');
  assert.equal(block.children[2].textContent, 'Open resource ↗');
  assert.equal(block.children[2].href, 'https://example.com/configured-material');
  const paragraph = block.children[1];
  if (format === 'Online') {
    assert.equal(paragraph.children[1].tag, 'strong');
    assert.equal(paragraph.children[1].textContent, 'you must not conduct the Listening component online.');
  } else {
    const link = paragraph.children[1];
    assert.equal(link.href, context.SINAPSIS_LOGIN_URL);
    assert.equal(link.style.fontWeight, '700');
    assert.equal(link.style.color, '#00506b');
    assert.equal(link.style.textDecoration, 'underline');
  }
}
console.log('Examiner portal materials: order, format-specific copy, configured resource and Sinapsis styling verified.');

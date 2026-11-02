const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/app.js','utf8');
const start = source.indexOf('  form.addEventListener("formdata", (event) => {');
const end = source.indexOf('  form.addEventListener("submit", async (event) => {',start);
const control = (name,value,kind,disabled=false) => ({name,value,disabled,matches:selector=>selector===kind});
let listener;
const form = {elements:[
  control('examiner_participation_status_existing-1','Confirmed','[data-participation-select]'),
  control('intern_participation_status_existing-2','Official confirmation sent','[data-participation-select]'),
  control('supervisor_participation_status_existing-3','Cancelled','[data-participation-select]',true),
  control('emergency_contact_participation_status','Confirmed','[data-emergency-contact-status-select]'),
  control('emergency_contact_participation_status','Pre-confirmed','[data-emergency-contact-status-select]')
],addEventListener:(event,fn)=>{assert.equal(event,'formdata');listener=fn;}};
vm.runInNewContext(source.slice(start,end),{form,Array});
const formData = new FormData();
// Only the second emergency contact is included by ordinary form submission.
formData.append('emergency_contact_participation_status','Pre-confirmed');
listener({formData});
assert.equal(formData.get('examiner_participation_status_existing-1'),'Confirmed');
assert.equal(formData.get('intern_participation_status_existing-2'),'Official confirmation sent');
assert.equal(formData.has('supervisor_participation_status_existing-3'),false);
assert.deepEqual(formData.getAll('emergency_contact_participation_status'),['Confirmed','Pre-confirmed']);
console.log('Participation serialization preserves locked statuses and emergency contact row alignment.');

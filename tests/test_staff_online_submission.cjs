const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
const functionSource = (name, next) => source.slice(source.indexOf(`const ${name} =`), source.indexOf(`const ${next} =`, source.indexOf(`const ${name} =`)));
let lastError;
const context = {
  cleanEmailValue: value => String(value ?? '').trim(),
  emailLinkIsUsable: value => /^https:\/\//.test(String(value || '')),
  parseStaffOfficialConfirmationPayload: form => form.payload,
  showStaffOfficialConfirmationEmailFeedback: (_button,error) => { lastError = error; },
};
vm.createContext(context);
vm.runInContext(functionSource('validateStaffOfficialConfirmationEmailPayload', 'officialConfirmationStatusStyle') +
  functionSource('validateStaffSessionSubmit', 'appendStaffInvitationIcons') +
  '\nthis.validate = validateStaffSessionSubmit; this.validateEmail = validateStaffOfficialConfirmationEmailPayload;',context);
for (const format of ['Online','Online at exam centre']) {
  for (const role of ['Supervisor','Examiner']) {
    const payload = {full_name:'Test staff',role,format,session_name:'Online session',session_date:'3 November 2026',time_ranges:['09:00 - 12:00'],logistics_status:'Does not apply'};
    const form={payload,querySelector:()=>({})};
    if (format === 'Online at exam centre' && role === 'Examiner') {
      assert.equal(context.validate(form), false);
      assert.match(lastError, /Examiners cannot be assigned/);
      continue;
    }
    assert.equal(context.validate(form),true,`${format} ${role} should pass Add without onsite email resources`);
    assert.match(context.validateEmail(payload),/only available for onsite/);
    assert.equal(context.validate({...form,payload:{...payload,time_ranges:[]}}),false);
    assert.match(lastError,/time range/);
    assert.equal(context.validate({...form,payload:{...payload,logistics_status:''}}),format === "Online");
    if (format !== "Online") assert.match(lastError,/Select Logistics/);
    assert.equal(context.validate({...form,payload:{...payload,full_name:''}}),false);
    assert.match(lastError,/full name/);
  }
}
const onsite={full_name:'Staff',role:'Supervisor',format:'Onsite',session_name:'Onsite',session_date:'3 November',time_ranges:['09:00'],logistics_status:'Does not apply'};
assert.equal(context.validate({payload:onsite,querySelector:()=>({})}),false);
assert.match(lastError,/address/);
console.log('Online portal Add accepts both formats and roles while retaining required assignment checks and onsite validation.');

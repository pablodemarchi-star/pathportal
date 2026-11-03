const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const events=()=>({listeners:{},addEventListener(type,fn){this.listeners[type]=fn;}});
const input={...events(),files:[]};Object.defineProperty(input,'value',{set(value){if(value==='')this.files=[];}});
const zone={...events(),classList:{add(){},remove(){}},contains:()=>false};
const selected={},filename={},error={},button={textContent:'Upload invoice',dataset:{}},remove=events();
const nodes={'[data-staff-invoice-input]':input,'[data-staff-invoice-dropzone]':zone,'[data-staff-invoice-selected]':selected,
 '[data-staff-invoice-filename]':filename,'[data-staff-invoice-error]':error,'[data-staff-invoice-submit]':button,'[data-staff-invoice-remove]':remove};
const form={...events(),querySelector:selector=>nodes[selector]};const window=events();
class DataTransfer{constructor(){this.files=[];this.items={add:file=>this.files.push(file)};}}
vm.runInNewContext(fs.readFileSync('app/static/js/staff_invoice_upload.js','utf8'),{document:{querySelectorAll:()=>[form]},window,DataTransfer});
const drop=files=>zone.listeners.drop({preventDefault(){},dataTransfer:{files}});
drop([{name:'one.pdf'},{name:'two.pdf'}]);assert.equal(error.hidden,false);assert.equal(input.files.length,0);
drop([{name:'invoice.pdf'}]);assert.equal(input.files.length,1);assert.equal(filename.textContent,'invoice.pdf');assert.equal(selected.hidden,false);
drop([{name:'one.pdf'},{name:'two.pdf'}]);assert.equal(input.files[0].name,'invoice.pdf');assert.equal(error.hidden,false);
remove.listeners.click();assert.equal(input.files.length,0);assert.equal(selected.hidden,true);
let blocked=false;form.listeners.submit({preventDefault(){blocked=true;}});assert.equal(blocked,true);
drop([{name:'final.pdf'}]);form.listeners.submit({preventDefault(){throw Error('Valid upload was blocked');}});assert.equal(button.disabled,true);assert.equal(button.textContent,'Uploading…');
window.listeners.pageshow();assert.equal(button.disabled,false);assert.equal(button.textContent,'Upload invoice');
console.log('Staff invoice dropzone: exactly one file, multiple-file rejection, removal and submission state verified.');

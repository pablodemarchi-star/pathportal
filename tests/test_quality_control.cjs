const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(text='') {this.textContent=text;this.children=[];this.listeners={};this.dataset={};this.value='';this.hidden=false;this.checked=false;}
  addEventListener(name,handler) {this.listeners[name]=handler;}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren(...nodes) {this.children=nodes;}
}
const selectors={};
for(const id of ['qc-query','qc-format','qc-attention','qc-sort','qc-dialog','qc-dialog-content','qc-open-block','qc-total','qc-ready','qc-overdue','qc-issues','qc-near','qc-empty','qc-year','qc-filters','qc-dialog-title','qc-dialog-subtitle','qc-times']) selectors['#'+id]=new Element();
selectors['#qc-sort'].value='date';
selectors['.qc-header-actions a']=new Element();
const dialog=selectors['#qc-dialog'], close=new Element();
dialog.querySelector=()=>close;dialog.showModal=()=>{dialog.open=true;};dialog.close=()=>{dialog.open=false;};
const timing={enabled_at:'2026-11-01T12:00:00Z',first_action_at:'2026-11-02T12:00:00Z',completed_at:'2026-11-03T12:00:00Z',elapsed:2,wait:1,duration:1,reopenings:0,history:[]};
const buttons=[];
const makeRow=(name,format,attention,ready,days)=>{
 const row=new Element();row.dataset={name,format,attention,ready,days:String(days),overdue:attention,issues:'0'};
 row.parentElement={append(){}};
 const button=new Element();button.dataset={key:'staffing',session:name,label:'Staffing',status:'Confirmed',detail:'All confirmed',timing:JSON.stringify(timing),url:'/pre-session-control-tower?view=sessions',applicable:'1',deadline:'04/11/2026',deadlineIso:'2026-11-04'};
 buttons.push(button);row.querySelectorAll=()=>[button];return row;
};
const rows=[makeRow('north school','Onsite','1','0',10),makeRow('universidad del sur','Online','0','1',20)];
const root={querySelector:s=>selectors[s],querySelectorAll:s=>s==='[data-qc-row]'?rows:s==='.qc-tabs a'?[]:buttons,dispatchEvent(){}};
let lastUrl;
const context=vm.createContext({document:{querySelector:()=>root,createElement:()=>new Element()},URL,location:{href:'http://localhost/quality-control?session_year=2026'},CustomEvent:class{constructor(name){this.type=name;}},history:{replaceState:(_,__,url)=>{lastUrl=String(url);}},Intl});
vm.runInContext(fs.readFileSync('app/static/js/quality_control.js','utf8'),context);
assert.equal(selectors['#qc-total'].textContent,2);
assert.equal(selectors['#qc-ready'].textContent,1);
selectors['#qc-query'].value='SUR';selectors['#qc-query'].listeners.input();
assert.equal(rows[0].hidden,true);assert.equal(rows[1].hidden,false);
assert.match(lastUrl,/q=SUR/);assert.match(lastUrl,/session_year=2026/);
selectors['#qc-query'].value='';selectors['#qc-format'].value='Onsite';selectors['#qc-format'].listeners.input();
assert.equal(rows[0].hidden,false);assert.equal(rows[1].hidden,true);
selectors['#qc-attention'].checked=true;selectors['#qc-attention'].listeners.input();
assert.equal(selectors['#qc-total'].textContent,1);
buttons[0].listeners.click();assert.equal(dialog.open,true);assert.equal(selectors['#qc-dialog-title'].textContent,'Staffing');assert.equal(selectors['#qc-open-block'].hidden,false);
close.listeners.click();assert.equal(dialog.open,false);
selectors['#qc-query'].value='no match';selectors['#qc-query'].listeners.input();assert.equal(selectors['#qc-empty'].hidden,false);
console.log('Quality control: live search, format and attention filters, counters, URL persistence, readiness detail and tab-safe filters passed.');

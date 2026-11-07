const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(text='') {this.textContent=text;this.children=[];this.listeners={};this.dataset={};this.value='';this.hidden=false;this.checked=false;}
  addEventListener(name,handler) {this.listeners[name]=handler;}
  setAttribute(name,value){this[name]=value;}
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
const indicator=new Element(),header=new Element(),sortButton=new Element();
header.dataset.qcSortHeader='block_package';header.querySelector=()=>indicator;sortButton.dataset.qcSort='block_package';
const root={addEventListener(){},querySelector:s=>selectors[s],querySelectorAll:s=>s==='[data-qc-row]'?rows:s==='.qc-tabs a'?[]:s==='[data-qc-sort]'?[sortButton]:s==='[data-qc-sort-header]'?[header]:buttons,dispatchEvent(){}};
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
// Exercise actual rendered order in both directions, including missing receivers.
const inserted=[];
rows.forEach(row=>{row.parentElement={append:item=>inserted.push(item)};});
selectors['#qc-query'].value='';selectors['#qc-format'].value='';selectors['#qc-attention'].checked=false;
rows[0].dataset.recipient='Zoë';rows[1].dataset.recipient='Álvaro';
function order(mode){inserted.length=0;selectors['#qc-sort'].value=mode;selectors['#qc-sort'].listeners.input();return inserted;}
assert.deepEqual(order('recipient'),[rows[1],rows[0]]);
assert.match(lastUrl,/sort=recipient/);
assert.deepEqual(order('recipient_desc'),[rows[0],rows[1]]);
rows[0].dataset.recipient='';
assert.deepEqual(order('recipient'),[rows[1],rows[0]]);
assert.deepEqual(order('recipient_desc'),[rows[1],rows[0]]);
rows[0].dataset.recipient='Same recipient';rows[1].dataset.recipient='Same recipient';
assert.deepEqual(order('recipient'),[rows[0],rows[1]]);
assert.deepEqual(order('date_desc'),[rows[1],rows[0]]);
assert.deepEqual(order('date'),[rows[0],rows[1]]);
console.log('Session sorting: dates in both directions, recipient A–Z/Z–A, accents, missing recipients last and chronological ties passed.');

// All process columns sort by readiness state or displayed timing, not by date.
const cells=rows.map(()=>({dataset:{applicable:'1',state:'pending',sortLabel:''}}));
rows.forEach((row,index)=>{row.querySelector=()=>cells[index];});
root.dataset={tab:'readiness'};
cells[0].dataset.state='complete';cells[1].dataset.state='pending';
assert.deepEqual(order('block_package'),[rows[1],rows[0]]);
assert.deepEqual(order('block_package_desc'),[rows[0],rows[1]]);
cells[0].dataset.applicable='0';
assert.deepEqual(order('block_package'),[rows[1],rows[0]]);
assert.deepEqual(order('block_package_desc'),[rows[1],rows[0]]);
cells[0].dataset.applicable='1';
cells.forEach(cell=>cell.dataset.state='progress');
cells[0].dataset.sortLabel='2/3 confirmed';cells[1].dataset.sortLabel='1/3 confirmed';
assert.deepEqual(order('block_package'),[rows[1],rows[0]]);
assert.equal(header['aria-sort'],'ascending');assert.equal(indicator.textContent,'↑');
sortButton.listeners.click();
assert.equal(selectors['#qc-sort'].value,'block_package_desc');
assert.equal(header['aria-sort'],'descending');assert.equal(indicator.textContent,'↓');
assert.match(lastUrl,/sort=block_package_desc/);
assert.deepEqual(order('name'),[rows[0],rows[1]]);
assert.deepEqual(order('name_desc'),[rows[1],rows[0]]);
const timingSource=fs.readFileSync('app/static/js/process_timing.js','utf8');
vm.runInContext(timingSource.slice(0,timingSource.indexOf('(() => {')),context);
root.dataset.tab='timing';
const timingButtons=rows.map(()=>({dataset:{}}));
cells.forEach((cell,index)=>{cell.querySelector=()=>timingButtons[index];});
const fullClock={category:'Completed',coverage_complete:true,as_of:new Date().toISOString(),totals:{total:200,path:200,external:0,incident:0}};
const partialClock={...fullClock,coverage_complete:false,totals:{total:50,path:50,external:0,incident:0}};
timingButtons[0].dataset.clock=JSON.stringify(fullClock);timingButtons[1].dataset.clock=JSON.stringify(partialClock);
assert.deepEqual(order('block_package'),[rows[1],rows[0]]);
assert.deepEqual(order('block_package_desc'),[rows[0],rows[1]]);
partialClock.category='Path time';partialClock.as_of=new Date(Date.now()-7200000).toISOString();
timingButtons[1].dataset.clock=JSON.stringify(partialClock);
assert.deepEqual(order('block_package_desc'),[rows[1],rows[0]],'Include the current open interval');
timingButtons[1].dataset.stale='1';
assert.deepEqual(order('block_package'),[rows[0],rows[1]]);
assert.deepEqual(order('block_package_desc'),[rows[0],rows[1]]);
console.log('All-column sorting: readiness states, numeric totals including partial data/open intervals, missing values, header toggles and URL persistence passed.');

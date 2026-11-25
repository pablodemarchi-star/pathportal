const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
let instant = '2026-11-16T02:59:59.000Z', scheduled, delay;
class Clock extends Date { constructor(...args) { super(...(args.length ? args : [instant])); } }
const parent = () => ({children:[], appendChild(row) { this.children=this.children.filter(item=>item!==row); this.children.push(row); }});
const row = (container, date) => {
  const item = {dataset:{staffSessionDate:date}, parentElement:container, past:false, classList:{toggle(name, value){item.past=value;}}, handler:()=>42};
  container.children.push(item); return item;
};
const regular=parent(), remote=parent(), emergency=parent(), fees=parent(), awaiting=parent();
const containers=[regular,remote,emergency,fees,awaiting];
containers.forEach(container => ['2026-11-10','2026-11-15','2026-11-20'].forEach(date=>row(container,date)));
const document={hidden:false,querySelectorAll:()=>containers.flatMap(container=>container.children),addEventListener(name,fn){this[name]=fn;}};
const window={addEventListener(name,fn){this[name]=fn;}};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_session_dates.js','utf8'),{Date:Clock,Intl,document,window,setTimeout(fn,ms){scheduled=fn;delay=ms;return 1;},clearTimeout(){}});
const dates=container=>container.children.map(item=>item.dataset.staffSessionDate.slice(-2));
for(const container of containers){assert.deepEqual(dates(container),['15','20','10']);assert.deepEqual(container.children.map(r=>r.past),[false,false,true]);}
assert.equal(delay,1000,'refresh exactly at Argentina midnight');
const original=regular.children[0];instant='2026-11-16T03:00:00.000Z';scheduled();
for(const container of containers){assert.deepEqual(dates(container),['20','10','15']);assert.deepEqual(container.children.map(r=>r.past),[false,true,true]);}
assert(regular.children.includes(original));assert.equal(original.handler(),42,'moving rows preserves their handlers');
assert.equal(delay,86400000);
instant='2026-11-21T03:00:00.000Z';window.focus();
for(const container of containers){assert.deepEqual(dates(container),['10','15','20']);assert(container.children.every(r=>r.past));}
instant='2026-11-10T03:00:00.000Z';document.visibilitychange();
for(const container of containers){assert.deepEqual(dates(container),['10','15','20']);assert(container.children.every(r=>!r.past));}
console.log('Staff session dates: all groups, Argentina midnight, ascending past dates, focus/visibility refresh and preserved handlers passed.');

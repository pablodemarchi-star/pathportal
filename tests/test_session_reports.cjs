const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const control=(value='')=>({value,checked:false,addEventListener(event,fn){this[event]=fn;}});
const query=control(),format=control(),sort=control('date'),status=control(),attention=control(),year=control('2026');
const fields={'[data-reports-query]':query,'[data-reports-format]':format,'[data-reports-sort]':sort,'[data-reports-status]':status,'[data-reports-attention]':attention,'[data-reports-year]':year};
const form={querySelector:key=>fields[key],addEventListener(){},submit(){this.submitted=true;}};
const rows=[
 {dataset:{name:'Zulu onsite',format:'Onsite',date:'2026-12-10',score:'',report:'0',reportApplicable:'1',feedback:'0',complete:'0',attention:'0'}},
 {dataset:{name:'Alpha online',format:'Online',date:'2026-12-01',score:'6.5',report:'0',reportApplicable:'0',feedback:'1',complete:'1',attention:'2'}},
 {dataset:{name:'Beta onsite',format:'Onsite',date:'2026-11-20',score:'9',report:'1',reportApplicable:'1',feedback:'1',complete:'1',attention:'0'}}];
const order=[];const body={querySelectorAll:()=>rows,appendChild:row=>order.push(row.dataset.name)};
const stats={};for(const key of ['total','supervisor','feedback','complete','alerts'])stats[`[data-reports-${key}]`]={};
const empty={};const dialog={querySelector:()=>({addEventListener(){}}),addEventListener(){}};
let lastURL;
const document={querySelector:key=>key==='[data-reports-filters]'?form:key==='[data-reports-body]'?body:key==='[data-reports-dialog]'?dialog:key==='[data-reports-empty]'?empty:stats[key],querySelectorAll:()=>[]};
vm.runInNewContext(fs.readFileSync('app/static/js/session_reports.js','utf8'),{document,window:{location:{href:'https://portal.test/quality-control?tab=reports'},history:{replaceState(a,b,url){lastURL=String(url);}}},URL});
assert.deepEqual(order.slice(-3),['Beta onsite','Alpha online','Zulu onsite']);
assert.equal(stats['[data-reports-total]'].textContent,3);
assert.equal(stats['[data-reports-supervisor]'].textContent,1);
query.value='beta';query.input();assert.equal(rows.filter(row=>!row.hidden).length,1);assert.match(lastURL,/q=beta/);
query.value='';format.value='Online';format.change();assert.equal(stats['[data-reports-total]'].textContent,1);
format.value='';status.value='supervisor_pending';status.change();assert.equal(rows.find(row=>!row.hidden).dataset.name,'Zulu onsite');
status.value='';attention.checked=true;attention.change();assert.equal(rows.find(row=>!row.hidden).dataset.name,'Alpha online');
attention.checked=false;sort.value='score';sort.change();assert.deepEqual(order.slice(-3),['Alpha online','Beta onsite','Zulu onsite']);
status.value='both';status.change();assert.equal(stats['[data-reports-total]'].textContent,2);
year.change();assert.equal(form.submitted,true);
console.log('Session reports: live search, format/status/attention filters, score sorting, counters and year navigation passed.');

const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context=vm.createContext({document:{querySelector:()=>null}});
vm.runInContext(fs.readFileSync('app/static/js/process_timing.js','utf8'),context);
for(const [seconds,text] of [[0,'0h'],[60,'<1h'],[3600,'1h'],[12*3600,'12h'],[24*3600,'1d'],[30*3600,'1d 6h'],[16*86400+2*3600,'16d 2h']]){
  assert.equal(context.processDuration(seconds),text);
}
assert.equal(context.processDuration(null),'Insufficient timing data');
assert.equal(context.processMedian([]),null);assert.equal(context.processMedian([10,1,3]),3);assert.equal(context.processMedian([4,10]),7);
const values=[5,1,9];context.processMedian(values);assert.deepEqual(values,[5,1,9]);
const clock={category:'Path time',as_of:'2026-11-07T12:00:00Z',totals:{total:3600,path:1000,external:2000,incident:600}};
let totals=context.processTotals(clock,Date.parse('2026-11-07T13:00:00Z'));
assert.equal(totals.total,7200);assert.equal(totals.path,4600);
assert.equal(totals.external,2000);assert.equal(clock.totals.path,1000);
clock.category='Completed';totals=context.processTotals(clock,Date.parse('2026-11-07T18:00:00Z'));assert.equal(totals.total,3600);
clock.category='Blocked';totals=context.processTotals(clock,Date.parse('2026-11-07T18:00:00Z'));assert.equal(totals.total,3600);
clock.category='Incident time';totals=context.processTotals(clock,Date.parse('2026-11-07T13:00:00Z'));assert.equal(totals.incident,4200);
assert.equal(totals.total,totals.path+totals.external+totals.incident);
console.log('Process timing: day/hour formatting, medians, immutable snapshots and exclusive live category counters passed.');
// Exercise the actual cell updater: partial intervals are visible without
// changing coverage, and full/partial/N/A snapshots keep their meanings.
const source=fs.readFileSync('app/static/js/process_timing.js','utf8');
const start=source.indexOf('  function updateCells() {'),end=source.indexOf('  function renderSummary()',start);
const fields={};
for(const key of ['total','total-label','partial','breakdown','path','external','incident'])fields[`[data-time-${key}]`]={hidden:false,textContent:''};
const snapshot={category:'Completed',coverage_complete:false,tracked_from:'2026-11-07T12:00:00Z',as_of:'2026-11-07T13:00:00Z',totals:{total:30*3600,path:24*3600,external:5*3600,incident:3600}};
const button={dataset:{applicable:'1'},querySelector:selector=>fields[selector]};
context.buttons=[button];context.read=()=>snapshot;context.stamp=value=>value;context.renderSummary=()=>{};
vm.runInContext(source.slice(start,end)+'\nthis.updateCellsForTest=updateCells;',context);
context.updateCellsForTest();
assert.equal(fields['[data-time-total]'].textContent,'1d 6h');
assert.equal(fields['[data-time-total-label]'].textContent,'Recorded time');
assert.equal(fields['[data-time-path]'].textContent,'1d');
assert.equal(fields['[data-time-external]'].textContent,'5h');
assert.equal(fields['[data-time-incident]'].textContent,'1h');
assert.equal(fields['[data-time-partial]'].hidden,false);
assert.equal(snapshot.coverage_complete,false);
snapshot.coverage_complete=true;context.updateCellsForTest();
assert.equal(fields['[data-time-total-label]'].textContent,'Total time');
assert.equal(fields['[data-time-partial]'].hidden,true);
button.dataset.applicable='0';context.updateCellsForTest();
assert.equal(fields['[data-time-total]'].textContent,'N/A');
assert.equal(fields['[data-time-breakdown]'].hidden,true);
button.dataset.stale='1';context.updateCellsForTest();
assert.equal(fields['[data-time-total]'].textContent,'Refresh required');
console.log('Inline cells: recorded/full totals, three components, Partial data, N/A and reassignment safeguards passed.');

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

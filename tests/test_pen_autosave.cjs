const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const timers = new Map(); let timerID = 0;
const window = {};
vm.runInNewContext(fs.readFileSync('app/static/js/pen_autosave.js','utf8'), {window,
  setTimeout(fn){const id=++timerID;timers.set(id,fn);return id;}, clearTimeout(id){timers.delete(id);}});
const tick = async () => { const pending=[...timers.values()];timers.clear();for(const fn of pending)fn();for(let i=0;i<12;i++)await Promise.resolve(); };
function card(revision=0){
  let current={name:'Candidate',number:'001',refs:['staff:1'],file:null}, missing='', requests=[], results=[], states=[];
  let operation=null;
  const controller=new window.PenCardAutosave({validate:()=>missing,snapshot:()=>({...current}),
    status:(state,message)=>states.push({state,message}),save:(snapshot,version)=>{requests.push({snapshot,version});return operation?operation():Promise.resolve({candidate:{revision:version+1}});},
    saved:(candidate,snapshot)=>results.push({candidate,snapshot})},revision);
  return {controller,requests,results,states,edit(values){Object.assign(current,values);controller.change();},invalid(value){missing=value;},operation(fn){operation=fn;}};
}
(async()=>{
  const incomplete=card();incomplete.invalid('Complete required fields');incomplete.edit({name:''});await tick();
  assert.equal(incomplete.requests.length,0);assert.equal(incomplete.controller.dirty,true);assert.equal(incomplete.states.at(-1).state,'invalid');
  incomplete.invalid('');incomplete.edit({name:'Now complete'});await tick();assert.equal(incomplete.requests.length,1);assert.equal(incomplete.controller.dirty,false);
  const first=card(),second=card();first.edit({name:'First'});second.edit({name:'Second'});await tick();
  assert.equal(first.requests[0].snapshot.name,'First');assert.equal(second.requests[0].snapshot.name,'Second');
  let finish;const during=card(3);during.operation(()=>new Promise(resolve=>finish=resolve));
  during.edit({name:'Before upload',file:{name:'a.pdf'}});await tick();assert.equal(during.requests.length,1);assert.equal(during.controller.dirty,true);
  during.edit({name:'After upload started',file:{name:'b.pdf'}});await tick();assert.equal(during.requests.length,1);
  finish({candidate:{revision:4}});for(let i=0;i<12;i++)await Promise.resolve();
  assert.equal(during.controller.dirty,true);during.operation(null);await tick();
  assert.equal(during.requests.length,2);assert.equal(during.requests[1].snapshot.name,'After upload started');assert.equal(during.requests[1].snapshot.file.name,'b.pdf');assert.equal(during.requests[1].version,4);assert.equal(during.controller.dirty,false);
  const invalidDuring=card(1);let done;invalidDuring.operation(()=>new Promise(resolve=>done=resolve));invalidDuring.edit({name:'Valid snapshot'});await tick();
  invalidDuring.invalid('Complete Candidate name');invalidDuring.edit({name:''});done({candidate:{revision:2}});for(let i=0;i<12;i++)await Promise.resolve();await tick();
  assert.equal(invalidDuring.requests.length,1);assert.equal(invalidDuring.states.at(-1).state,'invalid');assert.equal(invalidDuring.controller.dirty,true);
  const network=card();network.operation(()=>Promise.reject(new Error('Offline')));network.edit({name:'Retain draft'});await tick();
  assert.equal(network.states.at(-1).state,'error');assert.equal(network.controller.dirty,true);assert.equal(network.controller.attempted,true);
  network.operation(null);await network.controller.flush();assert.equal(network.requests[1].snapshot.name,'Retain draft');assert.equal(network.controller.dirty,false);
  const conflict=card(2);conflict.operation(()=>Promise.reject(Object.assign(new Error('Changed by another user'),{status:409})));conflict.edit({name:'Do not overwrite'});await tick();
  conflict.edit({name:'Still do not overwrite'});await tick();assert.equal(conflict.requests.length,1);assert.equal(conflict.states.at(-1).state,'conflict');
  const removing=card();let uploaded;removing.operation(()=>new Promise(resolve=>uploaded=resolve));removing.edit({name:'Uploading'});await tick();
  const paused=removing.controller.pause();removing.edit({name:'Ignored while deleting'});uploaded({candidate:{revision:1}});await paused;await tick();
  assert.equal(removing.requests.length,1);assert.equal(removing.controller.revision,1);removing.controller.remove();assert.equal(removing.controller.dirty,false);
  console.log('PEN autosave: required fields, independent cards, edits/files during uploads, invalid draft retention, retry, conflicts and delete/save ordering passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

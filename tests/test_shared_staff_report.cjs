const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function portal(server, actorRole='examiner') {
  const events={},intervals=[],timers=new Map();let next=0;
  const fields=[{name:'schedule_outcome',type:'select',value:''},{name:'optional_comments',type:'textarea',value:''},{name:'return_instructions_confirmed',type:'checkbox',checked:false,value:'1'},{name:'absent_candidates_checked',type:'checkbox',checked:false,value:'1'}];
  fields.forEach(field=>{field.closest=()=>({dataset:{reportOwner:field.name==='absent_candidates_checked'?'supervisor':'examiner'}});});
  const status={textContent:'',after(node){this.retry=node;}};
  const listeners={},form={children:[],querySelectorAll(selector){return selector.startsWith('input[name]')?fields:[];},querySelector(selector){if(selector==='[data-report-draft-status]')return status;if(selector==='[name="csrf_token"]')return{value:'csrf'};if(selector==='[data-report-return-version]')return{value:'own-return-version'};},append(node){this.children.push(node);},addEventListener(name,fn){(listeners[name]||=[]).push(fn);},dispatchEvent(event){(listeners[event.type]||[]).forEach(fn=>fn(event));},fire(values){this.dispatchEvent({type:'report:shared-change',detail:values});}};
  form.addEventListener('report:shared-restore',event=>{for(const field of fields){const value=event.detail[field.name];if(field.type==='checkbox')field.checked=Array.isArray(value)&&value.includes(field.value);else if(typeof value==='string')field.value=value;}});
  form.addEventListener('report:shared-locked',()=>{form.locked=true;});
  const dialog={open:true},section={dataset:{sharedReportUrl:'/shared/draft',sharedReportRole:actorRole},querySelector(selector){return selector==='[data-session-report-form]'?form:selector==='[data-session-report-dialog]'?dialog:null;},closest(){return null;}};
  const document={hidden:false,querySelectorAll(){return[section];},createElement(){return{addEventListener(name,fn){this[name]=fn;}};}};
  const window={addEventListener(name,fn){events[name]=fn;}};
  class FormData{constructor(){this.fields={};}set(key,value){this.fields[key]=value;}}
  class CustomEvent{constructor(type,options={}){this.type=type;this.detail=options.detail;}}
  const fetch=async(url,options)=>{
    if(server.failure)return{ok:false,json:async()=>({ok:false,error:'Connection failed'})};
    if(server.submitted)return{ok:true,json:async()=>({ok:true,submitted:true,author_name:'Examiner'})};
    if(options.method==='POST'){
      const changes=JSON.parse(options.body.fields.changes),base=JSON.parse(options.body.fields.base);
      if(server.hold)await server.hold;
      for(const [key,value]of Object.entries(changes))if(JSON.stringify(server.values[key])!==JSON.stringify(base[key])&&JSON.stringify(server.values[key])!==JSON.stringify(value))return{ok:false,json:async()=>({ok:false,conflict:true,error:'Someone else changed the same answer'})};
      Object.assign(server.values,changes);server.revision++;
    }
    return{ok:true,json:async()=>({ok:true,submitted:false,values:structuredClone(server.values),revision:server.revision})};
  };
  vm.runInNewContext(fs.readFileSync('app/static/js/shared_staff_report.js','utf8'),{document,window,fetch,FormData,CustomEvent,confirm:()=>true,setInterval:fn=>intervals.push(fn),setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id)});
  const settle=()=>new Promise(r=>setImmediate(r));
  return{form,fields,status,settle,async poll(){for(const fn of intervals)await fn();},change(values){form.fire({...Object.fromEntries(fields.map(f=>[f.name,f.type==='checkbox'?(f.checked?[f.value]:[]):f.value])),...values});},unload(){const e={preventDefault(){this.prevented=true;}};events.beforeunload(e);return e;}};
}
(async()=>{
 const server={values:{},revision:0};const remote=portal(server,'supervisor'),examiner=portal(server);await remote.settle();await examiner.settle();
 examiner.change({schedule_outcome:'There were no delays'});assert(examiner.unload().prevented);assert(await examiner.form.sharedDraftFlush());
 await remote.poll();assert.equal(remote.fields[0].value,'There were no delays');
 remote.change({absent_candidates_checked:['1']});examiner.change({optional_comments:'Examiner note'});
 assert(await remote.form.sharedDraftFlush());assert(await examiner.form.sharedDraftFlush());assert.equal(server.values.optional_comments,'Examiner note');
 await remote.poll();assert.equal(remote.fields[1].value,'Examiner note');assert.deepEqual(server.values.absent_candidates_checked,['1']);
 // Read-only answers cannot be sent by the other role, even if the local DOM is tampered with.
 remote.change({optional_comments:'Forged note'});await remote.form.sharedDraftFlush();assert.equal(server.values.optional_comments,'Examiner note');
 examiner.change({return_instructions_confirmed:['1'],_return_instructions_version:'recipient-version'});assert(await examiner.form.sharedDraftFlush());
 await remote.poll();assert(remote.fields[2].checked);assert.equal(server.values._return_instructions_version,'recipient-version');
 // Editing an owned field while a request is in flight keeps the newest answer.
 let release;server.hold=new Promise(resolve=>release=resolve);examiner.change({optional_comments:'First version'});const saving=examiner.form.sharedDraftFlush();await examiner.settle();examiner.change({optional_comments:'Newest version'});server.hold=null;release();assert(await saving);assert.equal(server.values.optional_comments,'Newest version');
 const otherTab=portal(server);await otherTab.settle();examiner.change({optional_comments:'Examiner first tab'});otherTab.change({optional_comments:'Examiner second tab'});assert(await examiner.form.sharedDraftFlush());assert.equal(await otherTab.form.sharedDraftFlush(),false);assert(otherTab.form.sharedDraftPending());assert.equal(otherTab.status.retry.textContent,'Reload shared draft');
 await otherTab.status.retry.click();assert.equal(otherTab.fields[1].value,'Examiner first tab');
 server.submitted=true;await examiner.poll();assert(examiner.form.locked);assert(!examiner.unload().prevented);
 console.log('Shared report roles: live cross-role sync, ownership filtering, examiner return acknowledgement, in-flight changes, conflicts and final lock passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.listeners={};this.children=[];this.dataset={};this.value='';this.checked=false;this.disabled=false;this.textContent='';this.open=false;this.classList={toggle(){}};}
 addEventListener(type,fn){this.listeners[type]=fn;}
 setAttribute(name,value){this[name]=value;}
 append(...nodes){this.children.push(...nodes);if(this.isSelect&&!this.value&&nodes[0])this.value=nodes[0].value;}
 replaceChildren(...nodes){this.children=[];if(this.isSelect)this.value='';this.append(...nodes);}
 querySelectorAll(selector){const inputs=this.children.flatMap(label=>label.children||[]).filter(input=>input.type==='checkbox');return selector==='input:checked'?inputs.filter(input=>input.checked):inputs;}
 showModal(){this.open=true;}
 close(){this.open=false;}
}
const dialog=new Element(),institution=new Element(),status=new Element(),list=new Element(),all=new Element(),count=new Element(),preview=new Element(),feedback=new Element(),copy=new Element(),close=new Element();institution.isSelect=true;
const language=new Element();language.value='en';
const nodes={'[data-group-language]':language,'[data-group-institution]':institution,'[data-group-status]':status,'[data-group-candidates]':list,'[data-group-all]':all,'[data-group-count]':count,'[data-group-preview]':preview,'[data-group-feedback]':feedback,'[data-group-copy]':copy};
dialog.querySelector=selector=>nodes[selector];dialog.querySelectorAll=()=>[close];
const candidates=[{id:1,number:'A1',name:'One',institution_key:'school',institution_name:'School',review_status:'Confirmed',whatsapp_message:'individual'},
 {id:2,number:'A2',name:'Two',institution_key:'school',institution_name:'  SCHOOL ',review_status:'Confirmed',whatsapp_message:'individual'},
 {id:3,number:'D1',name:'Three',institution_key:'school',institution_name:'School',review_status:'Declined',whatsapp_message:'individual'},
 {id:4,number:'P1',name:'Four',institution_key:'school',institution_name:'School',review_status:'Pending',whatsapp_message:''},
 {id:5,number:'B1',name:'Five',institution_key:'other',institution_name:'Other School',review_status:'Confirmed',whatsapp_message:'individual'}];
class Data{constructor(){this.values={};}set(key,value){this.values[key]=[value];}append(key,value){(this.values[key]||=[]).push(value);}}
let timerId=0,pending=false,version=1;const timers=new Map(),requests=[],copied=[],reports=[];
const context=vm.createContext({window:{},document:{createElement:()=>new Element()},FormData:Data,Map,Number,Boolean,
 setTimeout:fn=>{const id=++timerId;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
 fetch:async(url,options)=>{requests.push(options.body.values);return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({ok:true,message:'Message '+options.body.values.candidate_ids.join(',')+' v'+version})};}});
vm.runInContext(fs.readFileSync('app/static/js/attendance_group_messages.js','utf8'),context);
const controller=context.window.createAttendanceGroupMessages({dialog,getState:()=>({candidates}),getEndpoint:()=>'/absence-message',csrf:'csrf-test',copyText:async text=>copied.push(text),hasPending:()=>pending,report:(...args)=>reports.push(args)});
const flush=async()=>{const jobs=[...timers.values()];timers.clear();for(const job of jobs)await job();};
(async()=>{
 controller.open();assert.equal(dialog.open,true);assert.equal(institution.children.length,2);
 institution.value='school';institution.listeners.change();await flush();
 assert.equal(count.textContent,'2/2 candidates selected');assert.equal(preview.value,'Message 1,2 v1');assert.equal(copy.disabled,false);assert.equal(all.checked,true);
 assert.equal(requests.at(-1).csrf_token[0],'csrf-test');assert.deepEqual(Array.from(requests.at(-1).candidate_ids),['1','2']);
 language.value='es';language.listeners.change();assert.equal(copy.disabled,true);await flush();assert.equal(requests.at(-1).language[0],'es');assert.deepEqual(Array.from(requests.at(-1).candidate_ids),['1','2']);
 language.value='en';language.listeners.change();await flush();assert.equal(requests.at(-1).language[0],'en');
 list.querySelectorAll('input')[1].checked=false;list.listeners.change();await flush();assert.equal(preview.value,'Message 1 v1');assert.equal(all.indeterminate,true);
 all.checked=true;all.listeners.change();await flush();assert.equal(preview.value,'Message 1,2 v1');
 status.value='Declined';status.listeners.change();await flush();assert.equal(count.textContent,'1/1 candidates selected');assert.equal(preview.value,'Message 3 v1');
 await copy.listeners.click();assert.equal(copied.at(-1),'Message 3 v1');
 version=2;await copy.listeners.click();assert.equal(copied.length,1);assert.equal(preview.value,'Message 3 v2');assert.match(feedback.textContent,/details changed/);
 await copy.listeners.click();assert.equal(copied.at(-1),'Message 3 v2');
 all.checked=false;all.listeners.change();await flush();assert.equal(copy.disabled,true);assert.equal(preview.value,'');assert.equal(count.textContent,'0/1 candidates selected');
 close.listeners.click();assert.equal(dialog.open,false);pending=true;controller.open();assert.equal(dialog.open,false);assert.match(reports.at(-1)[0],/finish saving/);
 console.log('Grouped messages: institution/status filters, default selection, deselection, select all, empty-selection guard, CSRF payload, preview, copy and changed-data revalidation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

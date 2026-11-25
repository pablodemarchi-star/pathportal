const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(settings={}) {
  let id=0;const timers=new Map(),requests=[],events={};
  const match=(node,selector)=>{selector=selector.replace(/\[([^=\]]+)=([^"\]]+)\]/g,'[$1="$2"]');const attribute=selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);return attribute ? node.attrs[attribute[1]]!==undefined&&(attribute[2]===undefined||node.attrs[attribute[1]]===attribute[2]) : selector===node.tag;};
  class Node {
    constructor(tag='div',attrs={}){this.tag=tag;this.attrs=attrs;this.children=[];this.handlers={};this.dataset={};this.hidden=false;this.disabled=false;this.checked=false;this.value='';this.files=[];this.textContent='';this.classList={toggle(){},add(){},remove(){}};for(const [key,value] of Object.entries(attrs))if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;}
    querySelectorAll(s){return this.children.flatMap(n=>[...(match(n,s)?[n]:[]),...n.querySelectorAll(s)]);}
    querySelector(s){return this.querySelectorAll(s)[0]||null;}
    append(n){if(n.fragment){n.children.forEach(c=>this.append(c));return;}n.parent=this;this.children.push(n);}
    contains(n){return n===this||this.children.some(c=>c.contains(n));}
    setAttribute(k,v){this.attrs[k]=v;}
    addEventListener(k,f){(this.handlers[k]||=[]).push(f);}
    remove(){this.parent.children=this.parent.children.filter(n=>n!==this);}
    focus(){} pause(){this.paused=true;}
  }
  const node=(tag,key,parent)=>{const n=new Node(tag,key?{[key]:''}:{});if(parent)parent.append(n);return n;};
  const root=new Node(),section=new Node('section',{'data-announcements-section':'1','data-url':'/announcements','data-csrf':'csrf'}),toggle=new Node('button',{'data-announcement-toggle':'1'}),template=new Node('template',{'data-announcement-template':'1'});root.append(section);root.append(toggle);root.append(template);
  for(const [tag,key]of [['div','data-announcements-cards'],['input','data-announcements-ready'],['button','data-announcement-add'],['p','data-announcements-feedback'],['button','data-announcements-retry'],['p','data-announcements-empty'],['span','data-announcements-badge'],['small','data-announcements-help']])node(tag,key,section);
  template.content={cloneNode(){const fragment=new Node();fragment.fragment=true;const form=node('form','data-announcement-form',fragment);form.append(new Node('input',{name:'title'}));form.append(new Node('input',{name:'audio'}));node('audio',null,form);for(const [tag,key]of [['span','data-announcement-filename'],['span','data-announcement-feedback'],['button','data-announcement-retry'],['button','data-announcement-delete'],['label','data-announcement-drop']])node(tag,key,form);return fragment;}};
  const document={querySelector:s=>root.querySelector(s),querySelectorAll:s=>root.querySelectorAll(s)};
  const window={addEventListener(k,f){(events[k]||=[]).push(f);}};
  class FormData{constructor(){this.values={};}set(k,v){this.values[k]=v;}}
  const data={ok:true,can_edit:true,enabled:true,ready:false,revision:1,announcements:[],...settings};let responder;
  const fetch=async(url,options={})=>{
    if(!options.method)return{ok:true,json:async()=>structuredClone(data)};
    const fields=options.body.values;requests.push(fields);
    if(responder)return responder(fields);
    assert.equal(Number(fields.revision),data.revision,'writes must serialize using current revision');
    if(fields.action==='toggle'){data.enabled=fields.enabled==='1';data.ready=false;}
    if(fields.action==='ready')data.ready=true;
    if(fields.action==='pending')data.ready=false;
    if(fields.action==='save'){const old=data.announcements.find(r=>r.id===fields.id);data.announcements=data.announcements.filter(r=>r.id!==fields.id).concat({id:fields.id,title:fields.title,filename:fields.audio?.name||old.filename,audio_url:'/private/'+fields.id});data.ready=false;}
    if(fields.action==='delete'){data.announcements=data.announcements.filter(r=>r.id!==fields.id);data.ready=false;}
    data.revision++;return{ok:true,json:async()=>structuredClone(data)};
  };
  vm.runInNewContext(fs.readFileSync('app/static/js/announcements.js','utf8'),{document,window,fetch,FormData,crypto:{randomUUID:()=>String(++id)},confirm:()=>true,URL:{createObjectURL:()=> 'blob:audio',revokeObjectURL(){}},setTimeout:fn=>{const key=++id;timers.set(key,fn);return key;},clearTimeout:key=>timers.delete(key)});
  const settle=async()=>{for(let i=0;i<4;i++)await new Promise(r=>setImmediate(r));};
  const fire=async(n,k,extra={})=>{for(const fn of n.handlers[k]||[])fn({preventDefault(){},...extra});await settle();};
  const flush=async()=>{const saved=[...timers.values()];timers.clear();saved.forEach(fn=>fn());await settle();};
  return{section,toggle,data,requests,window,settle,fire,flush,find:s=>section.querySelector(s),cards:()=>section.querySelectorAll('form'),respond:fn=>responder=fn,unload(){const e={preventDefault(){this.prevented=true;}};events.beforeunload.forEach(f=>f(e));return e;}};
}
(async()=>{
  const h=harness();await h.settle();assert(h.find('[data-announcements-ready]').disabled);
  await h.fire(h.find('[data-announcement-add]'),'click');const first=h.cards()[0];assert(h.window.announcementsHasUnsavedChanges());assert(h.unload().prevented);
  first.querySelector('[name="title"]').value='First audio';await h.fire(first.querySelector('[name="title"]'),'input');await h.flush();assert.equal(h.data.announcements.length,0);
  await h.fire(h.find('[data-announcement-add]'),'click');const second=h.cards()[1];second.querySelector('[name="title"]').value='Second audio';
  await h.fire(second.querySelector('[name="audio"]'),'change'); // Empty selection cannot save.
  for(const form of [first,second]){form.querySelector('[name="audio"]').files=[{name:'audio.mp3'}];await h.fire(form.querySelector('[name="audio"]'),'change');}
  await h.flush();assert.equal(h.data.announcements.length,2);assert(!h.window.announcementsHasUnsavedChanges());assert(!h.find('[data-announcements-ready]').disabled);
  h.find('[data-announcements-ready]').checked=true;await h.fire(h.find('[data-announcements-ready]'),'change');assert(h.data.ready);
  first.querySelector('[name="title"]').value='Updated';await h.fire(first.querySelector('[name="title"]'),'input');assert(!h.data.ready);assert(h.find('[data-announcements-ready]').disabled);
  await h.flush();assert.equal(h.data.announcements[1].title,'Updated');assert(!h.window.announcementsHasUnsavedChanges());
  await h.fire(first.querySelector('[data-announcement-delete]'),'click');assert.equal(h.data.announcements.length,1);
  await h.fire(h.toggle,'click');assert(h.section.hidden);assert.equal(h.data.announcements.length,1);await h.fire(h.toggle,'click');assert(!h.section.hidden);assert(!h.data.ready);
  const ready=harness({ready:true,announcements:[{id:'saved',title:'Saved',filename:'saved.wav',audio_url:'/audio'}]});await ready.settle();await ready.fire(ready.find('[data-announcement-add]'),'click');assert(!ready.data.ready);assert.equal(ready.requests[0].action,'pending');assert.equal(ready.cards().length,2);
  const readonly=harness({can_edit:false});await readonly.settle();assert(readonly.toggle.disabled);assert(readonly.find('[data-announcement-add]').disabled);
  const conflict=harness();await conflict.settle();await conflict.fire(conflict.find('[data-announcement-add]'),'click');const draft=conflict.cards()[0];draft.querySelector('[name="title"]').value='Conflict';draft.querySelector('[name="audio"]').files=[{name:'audio.mp3'}];conflict.respond(()=>({ok:false,status:409,json:async()=>({error:'Changed by another user'})}));await conflict.fire(draft.querySelector('[name="audio"]'),'change');await conflict.flush();assert(conflict.window.announcementsHasUnsavedChanges());assert(conflict.find('[data-announcement-add]').disabled);
  const failure=harness({enabled:false});await failure.settle();failure.respond(()=>({ok:false,status:503,json:async()=>({error:'Connection failed'})}));await failure.fire(failure.toggle,'click');assert(failure.window.announcementsHasUnsavedChanges());assert(!failure.find('[data-announcements-retry]').hidden);
  console.log('Announcements: independent autosaves, mandatory fields, readiness invalidation, retained toggles, conflicts, read-only and close guards passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

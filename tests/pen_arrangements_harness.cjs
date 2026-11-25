const fs=require('node:fs'),vm=require('node:vm');
function harness(settings={}){
 const timers=new Map(),events={},requests=[];let timerID=0,id=0;
 const match=(node,selector)=>selector.split(',').some(part=>{part=part.trim();if(part==='input:checked')return node.tag==='input'&&node.checked;if(part.startsWith('.'))return node.className.split(' ').includes(part.slice(1));if(part.startsWith('['))return node.hasAttribute(part.slice(1,-1));return node.tag===part;});
 class Node{
  constructor(tag='div',attrs={}){this.tag=tag;this.attrs={};this.children=[];this.handlers={};this.dataset={};this.hidden=false;this.disabled=false;this.checked=false;this.value='';this.className='';this._text='';this.innerHTML='';this.files=[];for(const [key,value]of Object.entries(attrs))this.setAttribute(key,value);this.classList={add:key=>{this.className+=' '+key;},remove:key=>{this.className=this.className.split(' ').filter(item=>item!==key).join(' ');},toggle:(key,value)=>{this.className=this.className.split(' ').filter(item=>item!==key).concat(value?[key]:[]).join(' ');}};}
  setAttribute(key,value=''){this.attrs[key]=String(value);if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(value);else if(key==='class')this.className=String(value);else this[key]=String(value);}
  getAttribute(key){if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]??null;return this.attrs[key]??null;}
  hasAttribute(key){return this.getAttribute(key)!==null;}
  removeAttribute(key){delete this.attrs[key];delete this[key];}
  append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;}
  get firstElementChild(){return this.children[0];}
  get nextElementSibling(){return this.parentElement?.children[this.parentElement.children.indexOf(this)+1];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  set textContent(value){this._text=value;this.children=[];}
  matches(selector){return match(this,selector);}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(match(child,selector)?[child]:[]),...child.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){return this.matches(selector)?this:this.parentElement?.closest(selector)||null;}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  addEventListener(name,fn){(this.handlers[name]||=[]).push(fn);}
  focus(){document.activeElement=this;}
 }
 const element=(tag,key,parent)=>{const node=new Node(tag,key?{[key]:''}:{});if(parent)parent.append(node);return node;};
 const buildCard=()=>{
  const card=element('form','data-pen-form');
  element('strong','data-pen-card-title',card);element('button','data-pen-delete',card);
  for(const name of ['candidate_no','candidate_name'])card.append(new Node('input',{name}));
  const examiners=new Node('div',{class:'pen-examiners'});card.append(examiners);
  element('span','data-pen-examiners-required',examiners);
  const picker=new Node('details',{class:'pen-examiner-picker'});examiners.append(picker);
  const summary=element('summary',null,picker);element('span','data-pen-examiners-label',summary);element('div','data-pen-examiners',picker);element('p','data-pen-examiners-help',examiners);
  const extra=element('details',null,card);element('a','data-pen-document',extra);
  const dropzone=element('label','data-pen-dropzone',extra);element('input','data-pen-file',dropzone);
  element('span','data-pen-filename',extra);element('button','data-pen-file-remove',extra);element('span','data-pen-file-indicator',extra);element('span','data-pen-text-indicator',extra);
  element('button','data-pen-command',card).dataset.penCommand='bold';
  element('div','data-pen-editor',card);element('span','data-pen-status',card);element('button','data-pen-retry',card);
  card.elements={namedItem:name=>card.querySelectorAll('input').find(node=>node.name===name)};
  return card;
 };
 const section=new Node('section',{'data-pen-section':'','data-pen-url':'/sessions/1/pen-candidates','data-pen-csrf':'csrf'});
 for(const [tag,key]of [['span','data-pen-count'],['button','data-pen-add'],['button','data-pen-load-retry'],['span','data-pen-section-status'],['p','data-pen-empty'],['div','data-pen-cards']])element(tag,key,section);
 const completionPanel=new Node('div',{class:'pen-completion'});section.append(completionPanel);element('input','data-pen-confirm',completionPanel);element('small','data-pen-confirm-status',completionPanel);element('span','data-pen-completion-chip',section);
 const template=element('template','data-pen-card-template',section);template.content={firstElementChild:{cloneNode:buildCard}};
 const document={querySelectorAll:selector=>match(section,selector)?[section]:[],createElement:tag=>new Node(tag),commands:[],execCommand(command){this.commands.push(command);}};
 const window={addEventListener:(name,fn)=>{(events[name]||=[]).push(fn);},confirm:()=>true,alerts:[],alert(message){this.alerts.push(message);},getSelection:()=>({rangeCount:0})};
 class FormData{constructor(){this.values={};}set(key,value){this.values[key]=value;}append(key,value){(this.values[key]||=[]).push(value);}}
 const data={ok:true,enabled:true,can_edit:true,examiners_disabled:false,examiners:[{value:'staff:1',label:'Examiner One'},{value:'staff:2',label:'Examiner Two'}],candidates:[],...settings};
 data.completion=data.completion||{count:data.candidates.length,complete:false,snapshot:'snapshot-0'};
 let responder=null;
 const fetch=async(url,options)=>{requests.push({url,options});if(options.method==='POST'){
   if(responder)return responder(url,options);
   const fields=options.body.values,key=url.split('/').at(-1);
   if(key==='confirmation'){
     data.completion={...data.completion,complete:fields.confirmed==='1'};
     return{ok:true,status:200,json:async()=>({ok:true,completion:data.completion})};
   }
   let candidate;
   if(fields.action==='delete')data.candidates=data.candidates.filter(row=>row.id!==key);
   else{
     const old=data.candidates.find(row=>row.id===key);
     candidate={id:key,revision:Number(fields.revision)+1,candidate_no:fields.candidate_no,candidate_name:fields.candidate_name,examiner_refs:fields.examiner_refs||[],document:fields.remove_document?null:fields.document?{filename:fields.document.name,url:'/private-document'}:old?.document||null};
     data.candidates=data.candidates.filter(row=>row.id!==key).concat(candidate);
   }
   data.completion={count:data.candidates.length,complete:false,snapshot:data.completion.snapshot+'-next'};
   return{ok:true,status:200,json:async()=>({ok:true,deleted:fields.action==='delete',candidate,completion:data.completion})};
 }return{ok:true,status:200,json:async()=>data};};
 const context={document,window,FormData,fetch,crypto:{randomUUID:()=>`00000000-0000-0000-0000-${String(++id).padStart(12,'0')}`},setTimeout:fn=>{const key=++timerID;timers.set(key,fn);return key;},clearTimeout:key=>timers.delete(key)};
 vm.createContext(context);for(const name of ['pen_autosave','pen_arrangements'])vm.runInContext(fs.readFileSync(`app/static/js/${name}.js`,'utf8'),context);
 const settle=()=>new Promise(resolve=>setImmediate(resolve));
 const fire=async(node,name,extra={})=>{const event={target:node,currentTarget:null,preventDefault(){},...extra};const pending=[];for(let current=node;current;current=current.parentElement){event.currentTarget=current;for(const fn of current.handlers[name]||[])pending.push(fn(event));}event.currentTarget=null;await Promise.all(pending);await settle();return event;};
 const flush=async()=>{const pending=[...timers];timers.clear();for(const[,fn]of pending)fn();await settle();};
 return{section,window,document,requests,data,settle,fire,flush,respond(fn){responder=fn;},cards:()=>section.querySelectorAll('[data-pen-form]'),posts:()=>requests.filter(item=>item.options.method==='POST'),beforeUnload(){const event={preventDefault(){this.prevented=true;}};(events.beforeunload||[]).forEach(fn=>fn(event));return event;}};
}
module.exports={harness};

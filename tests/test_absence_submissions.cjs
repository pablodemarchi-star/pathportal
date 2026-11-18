const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
class Element {
 constructor(){this.listeners={};this.dataset={};this.hidden=false;this.disabled=false;this.textContent='';this.children=[];this.classes=new Set();this.classList={add:name=>this.classes.add(name),remove:name=>this.classes.delete(name),toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};}
 addEventListener(name,fn){this.listeners[name]=fn;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
}
const root=new Element(),dialog=new Element(),form=new Element(),opener=new Element(),input=new Element(),status=new Element(),duplicate=new Element(),actions=new Element(),filename=new Element(),list=new Element(),zone=new Element(),chip=new Element();
const reviewDialog=new Element(),reviewText=new Element(),reviewClose=new Element();reviewDialog.querySelector=selector=>selector==='[data-absence-review-text]'?reviewText:reviewClose;reviewDialog.showModal=()=>reviewDialog.open=true;reviewDialog.close=()=>reviewDialog.open=false;
const cancel=new Element(),submit=new Element(),replace=new Element(),cancelRequest=new Element();
let resets=0,valid=true;
form.elements={language:{value:'es'}};form.reportValidity=()=>valid;form.reset=()=>{resets++;input.files=[];};input.files=[];
dialog.open=false;dialog.showModal=()=>dialog.open=true;dialog.close=()=>dialog.open=false;
const formSelectors={'[data-absence-file]':input,'[data-absence-status]':status,'[data-absence-duplicate]':duplicate,'[data-absence-actions]':actions,'[data-absence-filename]':filename,'[data-absence-replace]':replace,'[data-absence-cancel-request]':cancelRequest,'[data-absence-drop]':zone};
form.querySelector=selector=>formSelectors[selector];form.querySelectorAll=()=>[cancel,submit,replace,cancelRequest];
dialog.querySelector=()=>form;dialog.querySelectorAll=()=>[cancel];
root.querySelector=selector=>({'dialog':dialog,'[data-absence-review-dialog]':reviewDialog,'[data-absence-open]':opener,'[data-absence-entries]':list}[selector]);root.closest=()=>({querySelector:()=>chip});
const copy={pending:'Pendiente',confirmed:'Confirmado',declined:'Rechazado',review_notes:'Notas',see:'Ver documentación de ausencia',replaced:'Reemplazado',saving:'Cargando…',error:'Error localizado',closed:'Plazo cerrado',single:'Un único archivo',window_open:'Abierto',window_pending:'Pendiente',window_expired:'Vencido'};
root.dataset={copy:JSON.stringify(copy),url:'/institution/absences/12',startsAt:'2026-11-17T00:00:00-03:00',expiresAt:'2026-11-20T00:00:00-03:00',folderConfigured:'true'};
let now=Date.parse('2026-11-18T10:00:00-03:00');class Clock extends Date{static now(){return now;}}
class Payload{constructor(){this.values={language:'es',csrf_token:'test',candidate_number:'1',candidate_name:'Name',document:input.files[0],rescheduled_for:'next_july_online'};}append(key,value){this.values[key]=value;}}
const requests=[],intervals=[];let response;
const context=vm.createContext({document:{querySelectorAll:()=>[root],addEventListener(){},createElement:()=>new Element(),createTextNode:text=>({textContent:text})},window:{addEventListener(){},setInterval:callback=>intervals.push(callback)},Date:Clock,FormData:Payload,DataTransfer:class{constructor(){this.files=[];this.items={add:file=>this.files.push(file)};}},Event:class{constructor(type){this.type=type;}},setTimeout(){},fetch:async(url,options)=>{requests.push({url,payload:options.body?.values});return response;}});
input.dispatchEvent=event=>input.listeners[event.type]();
vm.runInContext(fs.readFileSync('app/static/js/absence_submissions.js','utf8'),context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const post=async()=>{form.listeners.submit({preventDefault(){}});await settle();};
const answer=(status,result)=>({status,ok:status<400,json:async()=>result});
(async()=>{
 assert.equal(opener.disabled,false);assert.equal(chip.textContent,'Abierto');opener.listeners.click();assert.equal(dialog.open,true);
 valid=false;await post();assert.equal(requests.length,0);valid=true;
 input.files=[{},{}];await post();assert.equal(requests.length,0);assert.equal(status.textContent,copy.single);
 input.files=[{name:'evidence.pdf'}];response=answer(409,{ok:false,duplicate:true,previous_file_id:'old-file',error:'Duplicado'});
 await post();assert.equal(duplicate.hidden,false);assert.equal(actions.hidden,true);assert.equal(dialog.open,true);assert.equal(resets,0);
 response=answer(200,{ok:true,message:'Enviado',entries:[{number:'1',name:'Candidate',created_at:'2026-11-18T13:00:00+00:00',current:true,candidate_id:7}]});
 replace.listeners.click();await settle();assert.equal(requests[1].payload.replace,'1');assert.equal(requests[1].payload.confirmed,'1');assert.equal(requests[1].payload.previous_file_id,'old-file');
 assert.equal(dialog.open,false);assert.equal(resets,1);assert.equal(list.children[0].children[1].textContent,copy.see);assert.equal(list.children[0].children[1].href,root.dataset.url+'/7/document');
 opener.listeners.click();input.files=[{name:'retry.pdf'}];response=answer(400,{ok:false,error:'Error de Drive'});await post();assert.equal(dialog.open,true);assert.equal(resets,1);assert.equal(status.textContent,'Error de Drive');assert.equal(input.files[0].name,'retry.pdf');
 response=answer(409,{ok:false,duplicate:true,previous_file_id:'new-file',error:'Duplicado'});await post();const count=requests.length;cancelRequest.listeners.click();assert.equal(requests.length,count);assert.equal(dialog.open,false);assert.equal(resets,2);
 zone.listeners.drop({preventDefault(){},dataTransfer:{files:[{name:'drop.pdf'}]}});assert.equal(input.files[0].name,'drop.pdf');assert.equal(filename.textContent,'drop.pdf');
 zone.listeners.drop({preventDefault(){},dataTransfer:{files:[{},{}]}});assert.equal(status.textContent,copy.single);assert.equal(input.files[0].name,'drop.pdf');
 response=answer(200,{ok:true,entries:[{number:'1',name:'Candidate',created_at:'2026-11-18T13:00:00+00:00',current:true,candidate_id:7,review_status:'Declined',decline_reason:'Illegible <document>'}]});
 const previousResets=resets;await intervals[0]();assert.equal(resets,previousResets);assert.equal(list.children[0].children[3].textContent,'Rechazado');
 const noteButton=list.children[0].children[5];assert.equal(noteButton.textContent,'✎ Notas');root.listeners.click({target:{closest:()=>noteButton}});
 assert.equal(reviewDialog.open,true);assert.equal(reviewText.textContent,'Illegible <document>');reviewClose.listeners.click();assert.equal(reviewDialog.open,false);
 now=Date.parse(root.dataset.expiresAt);opener.listeners.click();assert.equal(opener.disabled,true);assert.equal(dialog.open,false);assert.equal(chip.textContent,'Vencido');assert.equal(chip.classes.has('is-pending'),true);
 console.log('Institutional absences: required fields, single-file drop, duplicate confirmation, replacement payload, cancellation, localized links, failed-upload preservation and exact expiry passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const classes=()=>({values:new Set(),add(value){this.values.add(value);},remove(value){this.values.delete(value);},toggle(value,active){active?this.values.add(value):this.values.delete(value);}});
const feedback={textContent:'',classList:classes()},copyFeedback={textContent:''};
const cell={querySelector:selector=>selector==='[data-marketing-visibility-feedback]'?feedback:copyFeedback};
function button(readOnly=false){return{disabled:readOnly,dataset:{hidden:'0',visibilityUrl:readOnly?'':'/visibility',visibilityCsrf:'csrf'},handlers:{},attrs:{'aria-pressed':'false'},classList:classes(),addEventListener(name,fn){this.handlers[name]=fn;},setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},closest:()=>cell};}
const editable=button(),readonly=button(true),requests=[],copied=[];
let responder=options=>({ok:true,status:200,json:async()=>({ok:true,hidden:options.body.values.hidden==='1'})});
const copy={dataset:{marketingCopy:'info'},handlers:{},addEventListener(name,fn){this.handlers[name]=fn;},closest:()=>cell,parentElement:{querySelector:()=>null}};
const source={innerHTML:'<b>Information</b>',cloneNode:()=>({style:{},innerText:'Information',remove(){}})};
class FormData{constructor(){this.values={};}set(key,value){this.values[key]=value;}}
const document={querySelector:()=>null,querySelectorAll:selector=>selector==='[data-marketing-visibility]'?[editable,readonly]:selector==='[data-marketing-copy]'?[copy]:[],addEventListener(){},getElementById:()=>({querySelector:()=>source}),body:{append(){}}};
vm.runInNewContext(fs.readFileSync('app/static/js/marketing_material.js','utf8'),{document,window:{},FormData,fetch:async(url,options)=>{requests.push({url,options});return responder(options);},navigator:{clipboard:{writeText:async text=>copied.push(text)}}});
(async()=>{
 assert.equal(readonly.handlers.click,undefined);
 await editable.handlers.click();assert.equal(editable.dataset.hidden,'1');assert.equal(editable.attrs['aria-pressed'],'true');assert.equal(editable.classList.values.has('is-hidden'),true);
 assert.deepEqual(requests[0].options.body.values,{csrf_token:'csrf',hidden:'1',previous_hidden:'0'});assert.match(feedback.textContent,/Hidden/);
 await editable.handlers.click();assert.equal(editable.dataset.hidden,'0');assert.equal(editable.attrs['aria-pressed'],'false');assert.equal(editable.classList.values.has('is-hidden'),false);
 responder=()=>({ok:false,status:503,json:async()=>({ok:false,error:'Could not save.'})});await editable.handlers.click();assert.equal(editable.dataset.hidden,'0');assert.equal(editable.disabled,false);assert.match(feedback.textContent,/Could not save/);
 let finish;responder=()=>new Promise(resolve=>finish=resolve);const pending=editable.handlers.click();assert.equal(editable.disabled,true);const before=requests.length;await editable.handlers.click();assert.equal(requests.length,before);
 finish({ok:true,status:200,json:async()=>({ok:true,hidden:true})});await pending;assert.equal(editable.dataset.hidden,'1');
 responder=()=>({ok:false,status:409,json:async()=>({ok:false,error:'Reload this row.'})});await editable.handlers.click();assert.equal(editable.dataset.hidden,'1');assert.equal(editable.disabled,true);assert.match(feedback.textContent,/Reload/);
 await copy.handlers.click();assert.deepEqual(copied,['Information']);assert.equal(copyFeedback.textContent,'Text copied');
 console.log('Marketing visibility: hide/show, CSRF, marked icon, read-only access, failed save retention, duplicate-click guard, stale-state lock and adjacent copy action passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

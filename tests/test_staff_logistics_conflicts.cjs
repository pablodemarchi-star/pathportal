const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node {
 constructor(tag){this.tag=tag;this.children=[];this.handlers={};this.disabled=false;}
 append(...nodes){this.children.push(...nodes);}
 setAttribute(name,value){this[name]=value;}
 addEventListener(name,handler){this.handlers[name]=handler;}
 showModal(){this.open=true;}
 close(){this.open=false;this.handlers.close();}
 remove(){this.removed=true;}
}
async function scenario(cancel=false){
 const events={},body=new Node('body'),output={},submit={};let posts=0,redirected;
 const form={action:'/save',dataset:{sessionId:'1'},querySelector:key=>key==='[data-logistics-save-status]'?output:key==='[name=session_ids]:checked'?{}:key==='[type=submit]'?submit:null,querySelectorAll:()=>[]};
 const conflict={ok:false,code:'logistics_card_conflict',conflict_token:'snapshot-token',sessions:['Session A','Session B'],cards:[{id:1,name:'Staff',sessions:['Session A'],status:'Pending',link_count:0,description:'Source'},{id:2,name:'Staff',sessions:['Session B'],status:'Completed',link_count:1,description:'Other instructions'}]};
 class FormData {constructor(){this.fields={};}set(key,value){this.fields[key]=value;}}
 const document={body,addEventListener(name,fn){events[name]=fn;},createElement:tag=>new Node(tag)};
 const window={location:{href:'https://portal.test/pre-session-control-tower?session_year=2026',assign(value){redirected=String(value);}}};
 vm.runInNewContext(fs.readFileSync('app/static/js/staff_logistics.js','utf8'),{document,window,URL,FormData,WeakMap,fetch:async(url,options)=>{
   posts++;
   if(posts===1)return {status:409,ok:false,json:async()=>conflict};
   assert.equal(options.body.fields.keep_card_id,'2');assert.equal(options.body.fields.conflict_token,'snapshot-token');
   return {status:200,ok:true,json:async()=>({ok:true})};
 }});
 const pending=events.submit({target:{closest:()=>form},preventDefault(){}});
 // Let fetch and JSON promises finish so the modal can be inspected.
 await new Promise(setImmediate);
 const modal=body.children[0];assert.ok(modal,output.textContent);assert.equal(modal.open,true);assert.equal(posts,1);
 const options=modal.children[4],footer=modal.children[5];
 assert.equal(footer.children[1].disabled,true);
 assert.match(modal.children[2].textContent,/cancelled/);
 assert.equal(options.children[1].children[1].children[3].textContent,'Other instructions');
 if(cancel){footer.children[0].handlers.click();}
 else{options.children[1].children[0].handlers.change();assert.equal(footer.children[1].disabled,false);footer.children[1].handlers.click();}
 await pending;
 assert.equal(posts,cancel?1:2);assert.equal(modal.removed,true);
 if(cancel){assert.equal(redirected,undefined);assert.equal(output.textContent,'Changes not saved.');assert.equal(submit.disabled,false);}
 else assert.match(redirected,/open_schedule_modal=1/);
}
(async()=>{await scenario(true);await scenario(false);console.log('Logistics sharing: explicit card choice, cancellation without writes, confirmation token and retaining another card passed.');})().catch(error=>{console.error(error);process.exitCode=1;});

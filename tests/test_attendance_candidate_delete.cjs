const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node{
 constructor(){this.handlers={};this.value='';this.hidden=false;this.disabled=false;this.required=false;this.focused=false;this.textContent='';this.isConnected=true;}
 addEventListener(name,fn){(this.handlers[name]||=[]).push(fn);}
 async fire(name,event={}){const e={preventDefault(){this.prevented=true;},...event};await Promise.all((this.handlers[name]||[]).map(fn=>fn(e)));return e;}
 focus(){this.focused=true;}
}
function setup(){
 const window={};vm.runInNewContext(fs.readFileSync('app/static/js/attendance_candidate_delete.js','utf8'),{window});
 const body=new Node(),dialog=new Node(),form=new Node(),password=new Node(),passwordField=new Node(),feedback=new Node(),cancel=new Node(),submit=new Node(),identity=new Node();
 const nodes={'form':form,'[data-candidate-delete-password]':password,'[data-candidate-delete-password-field]':passwordField,'[data-candidate-delete-status]':feedback,'[data-candidate-delete-cancel]':cancel,'[data-candidate-delete-submit]':submit,'[data-candidate-delete-name]':identity};
 dialog.querySelector=selector=>nodes[selector];dialog.open=false;dialog.showModal=()=>dialog.open=true;dialog.close=()=>{dialog.open=false;(dialog.handlers.close||[]).forEach(fn=>fn());};dialog.getBoundingClientRect=()=>({left:10,right:300,top:10,bottom:300});
 const parentClose=new Node();body.closest=()=>({querySelector:()=>parentClose});
 form.reportValidity=()=>!password.required||Boolean(password.value);
 const candidate={id:1,number:'001',name:'Candidate',review_status:'Pending',delete_allowed:true,delete_version:'version-1'};
 const current={can_edit:true,candidates:[candidate]},calls=[];let pending=false,error='Incorrect authorisation password.',operation=async()=>true;
 const button=new Node();button.dataset={deleteCandidate:'1'};
 window.createAttendanceCandidateDelete({body,dialog,getState:()=>current,hasPending:()=>pending,save:async values=>{calls.push(values);return operation(values);},getError:()=>error});
 const click=()=>body.fire('click',{target:{closest:()=>button}});
 return{body,dialog,form,password,passwordField,feedback,cancel,submit,identity,current,candidate,calls,button,parentClose,click,setPending:value=>pending=value,save:fn=>operation=fn};
}
(async()=>{
 const pending=setup();await pending.click();assert.equal(pending.dialog.open,true);assert.equal(pending.passwordField.hidden,true);assert.equal(pending.password.disabled,true);assert.equal(pending.password.required,false);assert.equal(pending.cancel.focused,true);assert.equal(pending.identity.textContent,'001 · Candidate');
 await pending.cancel.fire('click');assert.equal(pending.calls.length,0);assert.equal(pending.dialog.open,false);
 await pending.click();await pending.form.fire('submit');assert.equal(pending.calls.length,1);assert.deepEqual(JSON.parse(JSON.stringify(pending.calls[0])),{action:'delete_candidate',candidate_id:1,confirmed:'1',delete_version:'version-1',password:''});assert.equal(pending.dialog.open,false);
 for(const status of ['Confirmed','Declined']){
  const reviewed=setup();reviewed.candidate.review_status=status;await reviewed.click();assert.equal(reviewed.passwordField.hidden,false);assert.equal(reviewed.password.required,true);assert.equal(reviewed.password.focused,true);
  await reviewed.form.fire('submit');assert.equal(reviewed.calls.length,0);
  reviewed.password.value='wrong';reviewed.save(async()=>false);await reviewed.form.fire('submit');assert.equal(reviewed.dialog.open,true);assert.equal(reviewed.password.value,'');assert.match(reviewed.feedback.textContent,/Incorrect/);
  reviewed.password.value='EditOK';reviewed.save(async()=>true);await reviewed.form.fire('submit');assert.equal(reviewed.calls.at(-1).password,'EditOK');assert.equal(reviewed.dialog.open,false);assert.equal(reviewed.password.value,'');
 }
 const changed=setup();await changed.click();changed.candidate.delete_version='new-version';await changed.form.fire('submit');assert.equal(changed.calls.length,0);assert.match(changed.feedback.textContent,/changed/);
 const blocked=setup();blocked.setPending(true);await blocked.click();assert.equal(blocked.dialog.open,false);blocked.setPending(false);blocked.current.can_edit=false;await blocked.click();assert.equal(blocked.dialog.open,false);
 const busy=setup();await busy.click();let finish;busy.save(()=>new Promise(resolve=>finish=resolve));const deleting=busy.form.fire('submit');assert.equal(busy.cancel.disabled,true);assert.equal(busy.submit.disabled,true);await busy.cancel.fire('click');assert.equal(busy.dialog.open,true);assert.equal((await busy.dialog.fire('cancel')).prevented,true);await busy.form.fire('submit');assert.equal(busy.calls.length,1);busy.button.isConnected=false;finish(true);await deleting;assert.equal(busy.parentClose.focused,true);
 const outside=setup();await outside.click();await outside.dialog.fire('click',{target:outside.dialog,clientX:1,clientY:1});assert.equal(outside.dialog.open,false);assert.equal(outside.calls.length,0);
 const source=fs.readFileSync('app/static/js/post_attendance.js','utf8');assert.ok(!source.includes('EditOK'),'The operational password must not be exposed in browser code');assert.match(source,/data-delete-candidate/);
 console.log('Attendance deletion: explicit reconfirmation, masked password for reviewed cases, retry/cancel, stale/pending/read-only guards, in-flight locks, backdrop and restored focus passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

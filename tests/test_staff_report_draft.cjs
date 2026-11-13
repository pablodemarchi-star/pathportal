const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const storage=new Map();
const classes=()=>({values:new Set(),toggle(key,value){if(value)this.values.add(key);else this.values.delete(key);},add(key){this.values.add(key);}});
const source=fs.readFileSync('app/static/js/staff_session_report.js','utf8');
function page(){
 const make=(name,type='text',value='')=>({name,type,value,checked:false,disabled:false,dataset:{},handlers:{},classList:classes(),addEventListener(event,fn){(this.handlers[event]||=[]).push(fn);},setAttribute(key,value){this[key]=value;}});
 const outcome=make('schedule_outcome','select');const reasons=make('reasons','textarea');
 const facilities=make('facilities_outcome','select');const comments=make('facilities_comments','textarea');
 const emergency=make('emergency_pack_outcome','select');const emergencyReasons=make('emergency_pack_reasons','textarea');
 const feedbackCheckbox=make('centre_feedback_confirmed','checkbox','1');feedbackCheckbox.dataset.submitted='false';feedbackCheckbox.disabled=true;
 const notes=make('review.examiner:3.notes','textarea');const assessment=make('review.examiner:3.overall','select');
 const steps=Array.from({length:6},(_,i)=>{const step=make('return_verification','checkbox',String(i));const label={classList:classes()};step.closest=()=>label;return step;});
 const fields=[outcome,reasons,facilities,comments,emergency,emergencyReasons,feedbackCheckbox,notes,assessment,...steps];
 const badge={classList:classes()};const feedback={};const submit={};const help={hidden:false};
 const nodes={'[data-report-outcome]':outcome,'[data-report-reasons]':reasons,'[data-report-facilities]':facilities,'[data-report-comments]':comments,
 '[data-report-emergency-pack]':emergency,'[data-report-emergency-reasons]':emergencyReasons,'[data-report-feedback]':feedback,'[type="submit"]':submit,
 '[data-report-feedback-checkbox]':feedbackCheckbox,'[data-report-feedback-status]':badge,'[data-report-feedback-help]':help,
 '[data-report-return-timeline]':{classList:classes(),querySelectorAll:()=>steps},'[data-return-progress]':{},'[data-review-count]':{classList:classes()}};
 for(const name of ['reasons-field','comments-field','emergency-reasons-field'])nodes[`[data-report-${name}]`]={};
 const form={handlers:{},querySelector:key=>nodes[key],querySelectorAll:key=>key==='[data-review-row]'?[]:fields,addEventListener(event,fn){(this.handlers[event]||=[]).push(fn);}};
 const dialog={open:true,querySelector:()=>form,querySelectorAll:()=>[],addEventListener(){},close(){this.open=false;}};
 const opener=make('opener');opener.dataset.folderUrl='/report';
 const section={dataset:{reportDraftKey:'shared-session-draft',feedbackStatusUrl:'/status',opensAt:'2026-11-13T00:00:00-03:00'},querySelector:key=>key==='[data-exam-day-report-link]'?opener:dialog,closest:()=>({open:true})};
 const events={},documentEvents={};let result={ok:true,submitted:false,report_submitted:false};let poll;
 const window={addEventListener(name,fn){events[name]=fn;},setInterval(fn,ms){assert.equal(ms,5000);poll=fn;}};
 const document={hidden:false,querySelectorAll:()=>[section],addEventListener(name,fn){documentEvents[name]=fn;}};
 vm.runInNewContext(source,{window,document,sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},fetch:async()=>({ok:true,json:async()=>result})});
 return {outcome,reasons,notes,assessment,steps,fields,form,feedbackCheckbox,badge,help,submit,feedback,opener,events,documentEvents,setResult(value){result=value;}};
}
(async()=>{
 const first=page();
 first.outcome.value='There were minor delays';first.reasons.value='Bus delay';first.notes.value='Very helpful';first.assessment.value='Remarkable';
 first.steps.slice(0,3).forEach(step=>step.checked=true);
 first.form.handlers.input.forEach(fn=>fn());
 assert.ok(storage.has('shared-session-draft'));
 const restored=page();
 assert.equal(restored.outcome.value,'There were minor delays');assert.equal(restored.reasons.value,'Bus delay');
 assert.equal(restored.notes.value,'Very helpful');assert.equal(restored.assessment.value,'Remarkable');
 assert.ok(restored.steps.slice(0,3).every(step=>step.checked));assert.equal(restored.steps[3].disabled,false);assert.equal(restored.steps[4].disabled,true);
 restored.setResult({ok:true,submitted:true,report_submitted:false});
 await restored.events.focus();
 assert.equal(restored.feedbackCheckbox.disabled,false);assert.equal(restored.badge.textContent,'Feedback form submitted');assert.equal(restored.help.hidden,true);
 assert.equal(restored.notes.value,'Very helpful');assert.equal(restored.reasons.value,'Bus delay');assert.equal(restored.steps[2].checked,true);
 restored.setResult({ok:true,submitted:true,report_submitted:true,author_name:'Other Supervisor'});
 await restored.events.focus();
 assert.equal(restored.opener.disabled,true);assert.ok(restored.fields.every(field=>field.disabled));assert.equal(storage.has('shared-session-draft'),false);
 assert.match(restored.feedback.textContent,/Other Supervisor/);
 console.log('Supervisor report: drafts survive reload, feedback refresh preserves answers, and another Supervisor submission locks the session.');
})().catch(error=>{console.error(error);process.exitCode=1;});

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const classList = () => ({toggle() {}});
const keys=['organisation','candidate_experience','communication','overall'];
const copy={questions:keys.map(key=>({key})),submitted:'Submitted',available:'Available',unavailable:'Exam day only',open:'Open',invalid_score:'Choose a score',missing_comment:'Explain',missing:'Missing required answers',too_long:'Too long',submit:'Submit',submitting:'Sending',thanks:'Thank you',locked:'Locked'};
const fields=[];
const errors={};
const makeInput=(name,type,value='')=>({name,type,value,checked:false,disabled:false,handlers:{},setAttribute(){},focus(){},closest:()=>({scrollIntoView(){}}),addEventListener(event,fn){this.handlers[event]=fn;}});
const questions=keys.map(key=>{
  const radios=Array.from({length:10},(_,i)=>makeInput(key+'_score','radio',String(i+1)));
  const comment=makeInput(key+'_comment','textarea');
  const conditional={querySelector:()=>comment,hidden:true};
  fields.push(...radios,comment);
  for(const name of [key+'_score',key+'_comment'])errors[name]={dataset:{errorFor:name},hidden:true};
  return {radios,comment,conditional,querySelector(selector){
    if(selector==='input:checked')return radios.find(r=>r.checked);
    if(selector==='[data-feedback-conditional]')return conditional;
    if(selector.startsWith('[data-error-for='))return errors[comment.name];
  }};
});
const message={},submit={};
const form={action:'/submit',handlers:{},querySelector(selector){
  if(selector==='[data-feedback-message]')return message;
  if(selector==='[type="submit"]')return submit;
  const name=selector.match(/name="([^"]+)"/)?.[1];
  return fields.find(input=>input.name===name && (!selector.endsWith(':checked') || input.checked));
},querySelectorAll(selector){
  if(selector==='input[type="radio"], textarea')return fields;
  if(selector==='[data-feedback-question]')return questions;
  if(selector==='[data-error-for]')return Object.values(errors);
  if(selector==='textarea')return fields.filter(input=>input.type==='textarea');
},addEventListener(event,fn){this.handlers[event]=fn;}};
const dialog={open:false,querySelector:()=>form,querySelectorAll:()=>[],addEventListener(){},showModal(){this.open=true;},close(){this.open=false;}};
const opener={handlers:{},addEventListener(event,fn){this.handlers[event]=fn;}};
const badge={classList:classList()},thanks={hidden:true};
const opening=Date.parse('2026-11-13T00:00:00-03:00');let now=opening;
const root={dataset:{copy:JSON.stringify(copy),opensAt:'2026-11-13T00:00:00-03:00',submitted:'false',preview:'false',draftKey:'session-1'},querySelector: selector=>({'[data-centre-feedback-open]':opener,'[data-feedback-status]':badge,'[data-feedback-thanks]':thanks,'dialog':dialog}[selector])};
const storage=new Map();let sent=0;
vm.runInNewContext(fs.readFileSync('app/static/js/exam_centre_feedback.js','utf8'),{
  document:{querySelectorAll:()=>[root],addEventListener(){}},window:{addEventListener(){}},
  Date:{parse:Date.parse,now:()=>now},setTimeout(){},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  FormData:class {},fetch:async()=>{sent++;return {ok:true,status:200,json:async()=>({ok:true,message:'Thank you'})};}
});
(async()=>{
  assert.equal(opener.disabled,false);
  assert.ok(fields.filter(input=>input.type==='radio').every(input=>!input.checked));
  await form.handlers.submit({preventDefault(){}});
  assert.equal(sent,0);
  assert.equal(errors.organisation_score.hidden,false);
  const choose=(index,score)=>{
    const question=questions[index];
    question.radios.forEach(r=>{r.checked=r.value===String(score);});
    question.radios[score-1].handlers.change();
  };
  choose(0,7);
  assert.equal(questions[0].conditional.hidden,false);
  assert.equal(questions[0].comment.required,true);
  questions[0].comment.value='Please improve timing';
  questions[0].comment.handlers.input();
  choose(0,8);
  assert.equal(questions[0].conditional.hidden,true);
  assert.equal(questions[0].comment.disabled,true);
  assert.equal(questions[0].comment.value,'Please improve timing');
  choose(0,6);
  assert.equal(questions[0].comment.value,'Please improve timing');
  assert.equal(questions[0].comment.required,true);
  assert.equal(JSON.parse(storage.get('session-1')).organisation_comment,'Please improve timing');
  for(let i=1;i<4;i++)choose(i,8);
  await form.handlers.submit({preventDefault(){}});
  assert.equal(sent,1);
  assert.equal(root.dataset.submitted,'true');
  assert.equal(opener.disabled,true);
  assert.equal(thanks.hidden,false);
  assert.equal(storage.has('session-1'),false);
  console.log('Institution feedback: unselected ratings, inline validation, conditional text retention, draft persistence and submission lock passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

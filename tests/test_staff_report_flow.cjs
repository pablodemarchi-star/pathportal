const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.attrs={};this.hidden=false;this.style={setProperty(){}};this.classList={add(){},toggle(){}};this.textContent='';}
 append(...nodes){this.children.push(...nodes);}
 prepend(...nodes){this.children.unshift(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 insertBefore(node,before){const index=this.children.indexOf(before);this.children.splice(index<0?this.children.length:index,0,node);}
 addEventListener(name,fn,capture){(this.handlers[name]||=[]).push({fn,capture});}
 setAttribute(name,value){this.attrs[name]=value;}
 removeAttribute(name){delete this.attrs[name];}
 focus(){this.focused=true;}
 fire(name,event={}){(this.handlers[name]||[]).forEach(({fn})=>fn(event));}
}
function page(includeModules=true, resume=false, onsite=false){
 const form=new Node('form'),dialog=new Node('dialog'),questions=new Node('ol'),actions=new Node('div'),submit=new Node('button'),close=new Node('button');
 const warning=new Node('p'),feedback=new Node('p'),draft=new Node('small');
 actions.append(close,submit);actions.querySelector=selector=>selector==='[type="submit"]'?submit:close;
 const details={open:false};
 const control=(required=true,valid=false)=>({required,disabled:false,willValidate:true,valid,type:'text',checkValidity(){return this.valid;},reportValidity(){this.reports=(this.reports||0)+1;return this.valid;},closest(selector){return selector==='details'?this.details||null:this.card;}});
 const fields=onsite ? {session:[control()],centre:[control()],materials:[control(),control()],team:[control(),control()],media:[control()],checks:[control()],finish:[control(false,true)]} : {session:[control()],modules:[control()],candidates:[control(false,true)],team:[control(),control()],finish:[control()]};
 if(resume)fields.session[0].valid=true;
 fields.team[1].details=details;fields.team[1].disabled=true;
 const cards=Object.entries(fields).filter(([key])=>includeModules||key!=='modules').map(([key,inputs])=>{const card=new Node('li');card.dataset={reportStage:key};card.querySelectorAll=()=>inputs;inputs.forEach(input=>input.card=card);return card;});
 questions.children=cards;
 const nodes={'.staff-session-report-questions':questions,'.staff-session-report-heading':new Node(),'.staff-session-report-subtitle':new Node(),'[data-report-session-context]':new Node(),'.staff-session-report-warning':warning,'[data-report-feedback]':feedback,'[data-report-draft-status]':draft,'.staff-session-report-actions':actions};
 form.querySelector=selector=>nodes[selector];dialog.querySelector=()=>form;dialog.hasAttribute=name=>onsite&&name==='data-onsite-report-flow';
 vm.runInNewContext(fs.readFileSync('app/static/js/staff_report_flow.js','utf8'),{document:{querySelectorAll:()=>[dialog],createElement:tag=>new Node(tag)}});
 const workspace=form.children[1],sidebar=workspace.children[0],content=workspace.children[1],nav=sidebar.children[2];
 return{form,fields,cards,submit,close,warning,actions,sidebar,nav,content,details,progress:sidebar.children[0],back:actions.children[1],next:actions.children[2]};
}
const p=page();
assert.equal(p.nav.children.length,5);assert.equal(p.submit.hidden,true);assert.equal(p.back.disabled,true);assert.equal(p.warning.hidden,false);
assert.equal(p.progress.textContent,'1 of 5 sections ready');assert.equal(p.cards.filter(card=>!card.hidden).length,1);
p.next.fire('click');assert.equal(p.fields.session[0].reports,1);assert.equal(p.cards[0].hidden,false);
p.fields.session[0].valid=true;p.form.fire('change');p.next.fire('click');assert.equal(p.cards[1].hidden,false);assert.equal(p.warning.hidden,true);
assert.equal(p.fields.session[0].disabled,false); // Hidden stages must still submit their values.
p.nav.children[3].fire('click');assert.equal(p.cards[3].hidden,false);
p.fields.team[0].valid=true;p.fields.team[1].disabled=false;p.next.fire('click');
assert.equal(p.details.open,true);assert.equal(p.fields.team[1].reports,1);
p.fields.team[1].valid=true;p.form.fire('input');p.next.fire('click');assert.equal(p.submit.hidden,false);
p.fields.finish[0].valid=true;p.form.fire('report:before-validate');assert.equal(p.cards[1].hidden,false);assert.equal(p.submit.hidden,true);
p.fields.modules[0].valid=true;p.form.fire('change');p.nav.children[4].fire('click');assert.equal(p.submit.hidden,false);assert.equal(p.progress.textContent,'5 of 5 sections ready');
p.nav.children[3].fire('click');let prevented=false,stopped=false;p.form.fire('submit',{preventDefault(){prevented=true;},stopImmediatePropagation(){stopped=true;}});
assert.equal(prevented,true);assert.equal(stopped,true);assert.equal(p.submit.hidden,false);
p.form.fire('report:locked');assert.equal(p.next.disabled,true);assert.equal(p.nav.children[0].disabled,true);assert.equal(p.progress.textContent,'Report submitted');
const empty=page(false);assert.equal(empty.nav.children.length,4);assert.equal(empty.progress.textContent,'1 of 4 sections ready');
const resumed=page(true,true);assert.equal(resumed.cards[1].hidden,false);assert.equal(resumed.fields.session[0].valid,true);
const finish=page();
finish.fields.finish[0].required=false;finish.fields.finish[0].valid=true;finish.form.fire('change');
assert.equal(finish.nav.children[4].children[2].textContent,'Needs attention');
assert.equal(finish.nav.children[4].children[0].textContent,'05');
assert.equal(finish.progress.textContent,'1 of 5 sections ready');
Object.values(finish.fields).flat().forEach(field=>{field.valid=true;});finish.form.fire('change');
assert.equal(finish.nav.children[4].children[2].textContent,'Ready');
assert.equal(finish.progress.textContent,'5 of 5 sections ready');
finish.fields.modules[0].valid=false;finish.form.fire('change');
assert.equal(finish.nav.children[4].children[2].textContent,'Needs attention');
assert.equal(finish.progress.textContent,'3 of 5 sections ready');
console.log('Online report flow: stage navigation, required fields, no hidden-data loss, invalid-field reveal, notes, Enter key, conditional stages and submitted locks passed.');

const onsite=page(true,false,true);
assert.equal(onsite.nav.children.length,7);
assert.deepEqual(onsite.nav.children.map(button=>button.children[1].textContent),['Session','Exam centre','Exam materials','Staff review','Photos & videos','Final checks','Finish']);
assert.equal(onsite.cards.every(card=>card.dataset.reportStage==='session'||card.hidden),true);
onsite.nav.children[2].fire('click');
onsite.next.fire('click');assert.equal(onsite.fields.materials[0].reports,1);
onsite.fields.materials.forEach(field=>field.valid=true);onsite.form.fire('change');onsite.next.fire('click');
assert.equal(onsite.cards[3].hidden,false);
onsite.nav.children[6].fire('click');onsite.form.fire('report:before-validate');assert.equal(onsite.cards[0].hidden,false);
Object.values(onsite.fields).flat().forEach(field=>field.valid=true);onsite.form.fire('report:draft-restored');
onsite.nav.children[6].fire('click');assert.equal(onsite.submit.hidden,false);
assert.equal(onsite.progress.textContent,'7 of 7 sections ready');
assert.equal(onsite.fields.materials[0].disabled,false);
onsite.form.fire('report:locked');assert.equal(onsite.nav.children[6].disabled,true);
console.log('Onsite report flow: seven stages, materials validation, draft restoration, finish summary and submission lock passed.');

const waiting=page(true,false,true);
Object.values(waiting.fields).flat().forEach(field=>field.valid=true);
waiting.fields.media[0].disabled=true;waiting.fields.media[0].matches=()=>true;
waiting.fields.checks[0].disabled=true;waiting.fields.checks[0].matches=()=>true;
waiting.form.fire('change');assert.equal(waiting.progress.textContent,'4 of 7 sections ready');
waiting.nav.children[4].fire('click');waiting.next.fire('click');assert.equal(waiting.cards[4].hidden,false);
waiting.fields.media[0].disabled=false;waiting.form.fire('change');waiting.next.fire('click');assert.equal(waiting.cards[5].hidden,false);
waiting.next.fire('click');assert.equal(waiting.cards[5].hidden,false);
waiting.fields.checks[0].disabled=false;waiting.form.fire('change');waiting.next.fire('click');assert.equal(waiting.submit.hidden,false);
assert.equal(waiting.progress.textContent,'7 of 7 sections ready');
console.log('Onsite prerequisites: unavailable media/centre-feedback confirmations remain pending and prevent advancing until ready.');

const returnPending=page(true,false,true);
Object.values(returnPending.fields).flat().forEach(field=>field.valid=true);
const acknowledgement={disabled:true,checked:false,required:true,willValidate:false,type:'checkbox',matches:selector=>selector.includes('[data-report-return-confirmed]'),checkValidity:()=>true,reportValidity(){},closest(){return this.card;}};
const returnCard=new Node('li');returnCard.dataset={reportStage:'checks'};returnCard.querySelectorAll=()=>[acknowledgement];acknowledgement.card=returnCard;
// Use the existing checks card's live query result to simulate the extra return acknowledgement.
const checksCard=returnPending.cards.find(card=>card.dataset.reportStage==='checks');
checksCard.querySelectorAll=()=>[...returnPending.fields.checks,acknowledgement];
returnPending.form.fire('change');assert.equal(returnPending.progress.textContent,'5 of 7 sections ready');
returnPending.nav.children[6].fire('click');returnPending.form.fire('report:before-validate');
assert.equal(checksCard.hidden,false);
acknowledgement.disabled=false;acknowledgement.checked=true;returnPending.form.fire('change');assert.equal(returnPending.progress.textContent,'7 of 7 sections ready');
console.log('Final checks: disabled return acknowledgement stays pending and invalid submission reveals its stage.');

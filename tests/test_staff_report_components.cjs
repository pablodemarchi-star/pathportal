const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.dataset={};this.value='';this.disabled=false;this.checked=false;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 setAttribute(name,value){this[name]=value;}
 addEventListener(name,fn){this.handlers[name]=fn;}
 setCustomValidity(value){this.validationMessage=value;}
 showModal(){this.open=true;}
 close(){this.open=false;}
 focus(){this.focused=true;}
 matches(selector){return selector==='[data-it-module]'&&this.isModule;}
 reportValidity(){return !this.disabled&&!this.validationMessage&&(!this.required||Boolean(this.value.trim()))&&this.children.every(node=>node.disabled||node.reportValidity());}
}
function page(isIT=false){
 const host=new Element(),form=new Element('form'),json=new Element('input'),chips=new Element(),add=new Element('button'),panel=new Element(),error=new Element();
 const choices=[new Element('input'),new Element('input')];choices[0].value=isIT?'0':'complete';choices[1].value=isIT?'1':'component_absences';
 let drafts=0;json.value='[]';json.dispatchEvent=()=>drafts++;form.closest=()=>host;
 const fieldset=new Element('fieldset');
 const keys=['number','name','exam',...(isIT?[]:['component']),'reason'];
 const fields=keys.map(key=>{const node=new Element('input');node.dataset.componentField=key;node.required=true;return node;});
 const moduleInputs=isIT?['Speaking','Listening and speaking','Reading and writing'].map(value=>{const node=new Element('input');node.value=value;node.isModule=true;const label={};node.closest=()=>label;return node;}):[];
 const hint={};fieldset.append(...fields,...moduleInputs);
 fieldset.querySelectorAll=selector=>selector==='[data-it-module]'?moduleInputs:fields;
 fieldset.querySelector=()=>hint;
 const nodes={'[data-component-absence-panel]':panel,'[data-component-absence-rows]':chips,'[data-component-absence-json]':json,'template':{content:{firstElementChild:{cloneNode:()=>fieldset}}},'[data-component-absence-error]':error,'[data-add-component-absence]':add};
 const section={dataset:{absenceKind:isIT?'it':'component',moduleOptions:JSON.stringify({'Ready':['Speaking'],'B2 Competency':['Listening and speaking','Reading and writing'],'Mixed':['Speaking','Listening and speaking','Reading and writing']})},closest:()=>form,querySelector:key=>nodes[key],querySelectorAll:()=>choices};
 vm.runInNewContext(fs.readFileSync('app/static/js/staff_report_components.js','utf8'),{document:{querySelectorAll:()=>[section],createElement:tag=>new Element(tag)},Event:class{}});
 const dialog=host.children[0],editor=dialog.children[0];
 const set=entry=>fields.forEach(input=>{input.value=entry[input.dataset.componentField]||'';});
 const save=()=>editor.handlers.submit({preventDefault(){}});
 const change=input=>editor.handlers.change?.({target:input});
 return{host,form,json,chips,add,panel,error,choices,dialog,editor,fields,moduleInputs,set,save,change,drafts:()=>drafts,cancel:editor.children[2].children[0]};
}
const candidate={number:'00120',name:'Josefina Ramirez',exam:'B2 Competency',component:'Listening',reason:'Connection lost'};
const p=page();assert.equal(p.panel.hidden,true);
p.choices[1].checked=true;p.choices[1].handlers.change();assert.match(p.choices[1].validationMessage,/at least one/);
p.add.handlers.click();assert.equal(p.dialog.open,true);assert.equal(p.host.children.length,1);assert.equal(p.form.children.length,0);
p.save();assert.equal(p.chips.children.length,0);
p.set(candidate);p.save();assert.equal(p.dialog.open,false);assert.equal(p.chips.children[0].children[0].textContent,'00120 - Josefina Ramirez');
assert.deepEqual(JSON.parse(p.json.value),[candidate]);assert.equal(p.choices[1].validationMessage,'');
p.chips.children[0].children[0].handlers.click();assert.equal(p.fields[1].value,'Josefina Ramirez');
p.fields[1].value='Not saved';p.cancel.handlers.click();assert.equal(JSON.parse(p.json.value)[0].name,'Josefina Ramirez');
p.chips.children[0].children[0].handlers.click();p.fields[1].value='Updated';p.save();assert.equal(JSON.parse(p.json.value)[0].name,'Updated');assert.equal(p.chips.children.length,1);
p.add.handlers.click();p.set(candidate);p.save();assert.equal(p.chips.children.length,1);assert.match(p.fields[0].validationMessage,/already listed/);
p.set({...candidate,number:'00121'});p.save();assert.equal(p.chips.children.length,2);
p.choices[1].checked=false;p.choices[0].checked=true;p.choices[0].handlers.change();assert.equal(p.panel.hidden,true);assert.equal(JSON.parse(p.json.value).length,2);
p.choices[0].checked=false;p.choices[1].checked=true;p.choices[1].handlers.change();assert.equal(p.panel.hidden,false);
p.chips.children[1].children[1].handlers.click();p.chips.children[0].children[1].handlers.click();assert.equal(p.chips.children.length,0);assert.match(p.choices[1].validationMessage,/at least one/);
p.json.value=JSON.stringify([candidate]);p.form.handlers['report:draft-restored']();assert.equal(p.chips.children.length,1);assert.equal(p.chips.children[0].children[0].textContent,'00120 - Josefina Ramirez');
p.json.value=JSON.stringify([{number:'00120',name:'Unfinished draft'}]);p.form.handlers['report:draft-restored']();assert.match(p.choices[1].validationMessage,/Complete every/);
p.json.value=JSON.stringify([candidate]);p.form.handlers['report:draft-restored']();
p.json.disabled=true;p.form.handlers['report:locked']();assert.equal(p.add.disabled,true);assert.equal(p.chips.children[0].children[0].disabled,true);p.chips.children[0].children[1].handlers.click();assert.equal(p.chips.children.length,1);
console.log('Candidate chips: add, validate, edit, cancel, remove, required cases, restored records and submitted locks passed.');
const it=page(true);it.choices[1].checked=true;it.choices[1].handlers.change();it.add.handlers.click();it.set(candidate);
it.editor.handlers.change({target:it.fields[2]});it.save();assert.equal(it.chips.children.length,0);
it.moduleInputs[1].checked=true;it.editor.handlers.change({target:it.moduleInputs[1]});it.moduleInputs[2].checked=true;it.editor.handlers.change({target:it.moduleInputs[2]});it.save();
assert.equal(it.chips.children.length,1);assert.deepEqual(JSON.parse(it.json.value)[0].modules,['Listening and speaking','Reading and writing']);
it.chips.children[0].children[0].handlers.click();assert.equal(it.moduleInputs[1].checked,true);assert.equal(it.moduleInputs[2].checked,true);
it.fields[2].value='Mixed';it.moduleInputs[1].checked=false;it.moduleInputs[2].checked=false;it.editor.handlers.change({target:it.fields[2]});
it.moduleInputs[0].checked=true;it.editor.handlers.change({target:it.moduleInputs[0]});assert.equal(it.moduleInputs[1].disabled,true);it.save();assert.deepEqual(JSON.parse(it.json.value)[0].modules,['Speaking']);
it.chips.children[0].children[0].handlers.click();it.fields[2].value='B2 Competency';it.editor.handlers.change({target:it.fields[2]});assert.equal(it.moduleInputs[0].checked,false);assert.equal(it.moduleInputs[0].disabled,true);
it.cancel.handlers.click();assert.deepEqual(JSON.parse(it.json.value)[0].modules,['Speaking']);assert.ok(it.drafts()>0);
console.log('IT candidate editor: exam filtering, required modules, combined modules, Speaking exclusivity, restored choices and cancellation passed.');

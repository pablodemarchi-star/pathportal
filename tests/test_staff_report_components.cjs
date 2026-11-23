const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const control = () => ({value:'', checked:false, hidden:false, handlers:{}, addEventListener(key, fn){this.handlers[key]=fn;}, setCustomValidity(text){this.validationMessage=text;}});
const form = control(), panel=control(), json=control(), error=control(), add=control();
let draftEvents=0;
json.dispatchEvent=()=>{draftEvents++;};
const choices=[{...control(),value:'complete'}, {...control(),value:'component_absences'}];
const rows={...control(),children:[],appendChild(row){this.children.push(row);},replaceChildren(){this.children=[];}};
function candidateRow(){
 const inputs=['number','name','institution','exam','component','reason'].map(key=>({...control(),dataset:{componentField:key},focus(){this.focused=true;}}));
 return {inputs,querySelectorAll:()=>inputs,remove(){rows.children=rows.children.filter(row=>row!==this);}};
}
const nodes={'[data-component-absence-panel]':panel,'[data-component-absence-rows]':rows,'[data-component-absence-json]':json,
 'template':{content:{firstElementChild:{cloneNode:candidateRow}}},'[data-component-absence-error]':error,'[data-add-component-absence]':add};
const section={closest:()=>form,querySelector:key=>nodes[key],querySelectorAll:()=>choices};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_report_components.js','utf8'),{
 document:{querySelectorAll:()=>[section]},Event:class{constructor(type,options){this.type=type;this.options=options;}}
});
assert.equal(panel.hidden,true);
choices[1].checked=true;choices[1].handlers.change();
assert.equal(panel.hidden,false);assert.match(choices[1].validationMessage,/at least one/);
add.handlers.click();
assert.equal(rows.children.length,1);assert.equal(choices[1].validationMessage,'');
const row=rows.children[0];assert.equal(row.inputs[0].focused,true);
const values=['00120','Candidate','School','B2 Competency','Listening','Connection lost'];
row.inputs.forEach((input,index)=>input.value=values[index]);rows.handlers.input();
assert.equal(JSON.parse(json.value)[0].number,'00120');assert.ok(draftEvents>0);
choices[1].checked=false;choices[0].checked=true;choices[0].handlers.change();
assert.equal(panel.hidden,true);assert.equal(row.disabled,true);
choices[0].checked=false;choices[1].checked=true;choices[1].handlers.change();
assert.equal(row.disabled,false);assert.equal(row.inputs[0].value,'00120');
rows.handlers.click({target:{closest:()=>({closest:()=>row})}});
assert.equal(rows.children.length,0);assert.match(choices[1].validationMessage,/at least one/);
json.value=JSON.stringify([{number:'0001',name:'One',component:'Listening'},{number:'0002',name:'Two',component:'Speaking'}]);
form.handlers['report:draft-restored']();
assert.equal(rows.children.length,2);assert.equal(rows.children[1].inputs[0].value,'0002');
assert.equal(JSON.parse(json.value)[0].number,'0001');
console.log('Component absences: conditional fields, required candidate, original numbers, add/remove, drafts and switching options passed.');

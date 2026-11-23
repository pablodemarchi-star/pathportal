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

// The IT variant shares row/draft handling, with exam-specific multi-select rules.
const itForm=control(), itPanel=control(), itJson=control(), itError=control(), itAdd=control();
const itChoice={...control(),value:'1'}, noITChoice={...control(),value:'0'};
itJson.dispatchEvent=()=>{};
const itRows={...control(),children:[],appendChild(row){this.children.push(row);},replaceChildren(){this.children=[];}};
function itCandidateRow(){
 const inputs=['number','name','institution','exam','reason'].map(key=>({...control(),dataset:{componentField:key},focus(){},matches:()=>false}));
 const modules=['Speaking','Listening and speaking','Reading and writing'].map(value=>({...control(),value,matches:()=>true,label:{hidden:false}}));
 const row={inputs,modules,hint:{},querySelectorAll:selector=>selector==='[data-it-module]'?modules:inputs,querySelector:()=>row.hint,remove(){itRows.children=itRows.children.filter(item=>item!==row);}};
 modules.forEach(input=>{input.closest=selector=>selector==='label'?input.label:row;});
 return row;
}
const itNodes={'[data-component-absence-panel]':itPanel,'[data-component-absence-rows]':itRows,'[data-component-absence-json]':itJson,
 'template':{content:{firstElementChild:{cloneNode:itCandidateRow}}},'[data-component-absence-error]':itError,'[data-add-component-absence]':itAdd};
const itSection={dataset:{absenceKind:'it',moduleOptions:JSON.stringify({'Ready':['Speaking'],'B2 Competency':['Listening and speaking','Reading and writing'],'Mixed':['Speaking','Listening and speaking','Reading and writing']})},closest:()=>itForm,querySelector:key=>itNodes[key],querySelectorAll:()=>[noITChoice,itChoice]};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_report_components.js','utf8'),{document:{querySelectorAll:()=>[itSection]},Event:class{}});
assert.equal(itPanel.hidden,true);
noITChoice.checked=true;noITChoice.handlers.change();assert.equal(itPanel.hidden,true);
noITChoice.checked=false;
itChoice.checked=true;itChoice.handlers.change();assert.match(itChoice.validationMessage,/at least one/);
itAdd.handlers.click();
const itRow=itRows.children[0],exam=itRow.inputs[3];
assert.ok(itRow.modules.every(input=>input.disabled));
exam.value='B2 Competency';itRows.handlers.change({target:exam});
assert.equal(itRow.modules[0].label.hidden,true);
assert.equal(itRow.modules[1].disabled,false);
assert.match(itRow.modules[1].validationMessage,/at least one/);
itRow.modules[1].checked=true;itRows.handlers.change({target:itRow.modules[1]});
itRow.modules[2].checked=true;itRows.handlers.change({target:itRow.modules[2]});
assert.deepEqual(JSON.parse(itJson.value)[0].modules,['Listening and speaking','Reading and writing']);
exam.value='Mixed';itRow.modules[1].checked=false;itRow.modules[2].checked=false;itRows.handlers.change({target:exam});
itRow.modules[0].checked=true;itRows.handlers.change({target:itRow.modules[0]});
assert.equal(itRow.modules[1].disabled,true);assert.equal(itRow.modules[2].disabled,true);
assert.deepEqual(JSON.parse(itJson.value)[0].modules,['Speaking']);
itRow.modules[0].checked=false;itRows.handlers.change({target:itRow.modules[0]});
itRow.modules[1].checked=true;itRows.handlers.change({target:itRow.modules[1]});assert.equal(itRow.modules[0].disabled,true);
exam.value='Ready';itRows.handlers.change({target:exam});assert.deepEqual(JSON.parse(itJson.value)[0].modules,[]);
itRow.modules[0].checked=true;itRows.handlers.change({target:itRow.modules[0]});
itChoice.checked=false;itChoice.handlers.change();assert.equal(itRow.disabled,true);assert.equal(itChoice.validationMessage,'');
itChoice.checked=true;itChoice.handlers.change();assert.equal(itRow.modules[0].checked,true);
itJson.value=JSON.stringify([{number:'0012',exam:'B2 Competency',modules:['Reading and writing']}]);itForm.handlers['report:draft-restored']();
assert.equal(itRows.children[0].inputs[0].value,'0012');assert.deepEqual(JSON.parse(itJson.value)[0].modules,['Reading and writing']);
console.log('IT issues: optional section, required candidate/modules, exam filtering, Speaking exclusivity, combined modules and draft restoration passed.');

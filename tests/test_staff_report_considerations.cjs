const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.handlers={};this.value='';this.disabled=false;}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(name,value){this[name]=value;}
 addEventListener(name,fn){this.handlers[name]=fn;}
 setCustomValidity(message){this.validationMessage=message;}
 reportValidity(){return !this.validationMessage;}
 showModal(){this.open=true;}
 close(){this.open=false;}
 focus(){this.focused=true;}
}
const host=new Element('section'), form=new Element('form'), json=new Element('input'), chips=new Element('div'), add=new Element('button');
form.closest=()=>host;let drafts=0;json.dispatchEvent=()=>drafts++;
const nodes={'[data-report-considerations-json]':json,'[data-consideration-chips]':chips,'[data-add-consideration]':add};
const section={closest:()=>form,querySelector:key=>nodes[key]};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_report_considerations.js','utf8'),{
 document:{querySelectorAll:()=>[section],createElement:tag=>new Element(tag)},Event:class{}
});
const dialog=host.children[0],editor=dialog.children[0],title=editor.children[1].children[0],text=editor.children[2].children[0],cancel=editor.children[3].children[0];
const save=()=>editor.handlers.submit({preventDefault(){}});
assert.equal(dialog.tag,'dialog');assert.equal(editor.tag,'form');assert.equal(form.children.length,0);
add.handlers.click();assert.equal(dialog.open,true);
text.value='Explanation';save();assert.equal(chips.children.length,0);assert.match(title.validationMessage,/Title/);
title.value='  First title  ';text.value=' First explanation ';save();
assert.equal(chips.children.length,1);assert.equal(dialog.open,false);assert.equal(chips.children[0].children[0].textContent,'First title');
assert.deepEqual(JSON.parse(json.value),[{title:'First title',text:'First explanation'}]);
chips.children[0].children[0].handlers.click();assert.equal(title.value,'First title');assert.equal(text.value,'First explanation');
title.value='Updated title';text.value='Updated explanation';save();assert.equal(chips.children.length,1);
chips.children[0].children[0].handlers.click();title.value='Not saved';cancel.handlers.click();
assert.equal(JSON.parse(json.value)[0].title,'Updated title');
add.handlers.click();title.value='Second';text.value='<script>safe text</script>';save();assert.equal(chips.children.length,2);
json.value=JSON.stringify([{title:'Restored title',text:'Restored text'},{title:'Another title',text:'Another text'}]);
form.handlers['report:draft-restored']();assert.equal(chips.children.length,2);assert.equal(chips.children[0].children[0].textContent,'Restored title');
chips.children[0].children[1].handlers.click();assert.equal(chips.children.length,1);assert.equal(JSON.parse(json.value)[0].title,'Another title');assert.ok(drafts>=4);
json.disabled=true;form.handlers['report:locked']();assert.equal(add.disabled,true);assert.equal(chips.children[0].children[0].disabled,true);assert.equal(chips.children[0].children[1].disabled,true);
chips.children[0].children[0].handlers.click();assert.equal(dialog.open,false);
console.log('Important considerations: separate modal, required fields, chips, edit/cancel/delete, draft restoration and submitted lock passed.');

const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node{
 constructor(){this.events={};this.children=[];this.dataset={};this.open=false;this.parentNode=null;}
 addEventListener(name,fn){this.events[name]=fn;}
 append(...nodes){for(const node of nodes){node.remove();this.children.push(node);node.parentNode=this;}}
 insertBefore(node,before){node.remove();const index=this.children.indexOf(before);this.children.splice(index<0?this.children.length:index,0,node);node.parentNode=this;}
 remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(node=>node!==this);this.parentNode=null;}
 replaceWith(node){const parent=this.parentNode;parent.insertBefore(node,this);this.remove();}
 replaceChildren(...nodes){for(const node of [...this.children])node.remove();this.append(...nodes);}
 showModal(){this.open=true;}
 close(){this.open=false;this.events.close?.({target:this,stopPropagation(){this.stopped=true;}});}
 focus(){this.focused=true;}
 getBoundingClientRect(){return{left:10,right:100,top:10,bottom:100};}
}
const popup=new Node(),content=new Node(),popupClose=new Node(),title={},date={};
popup.querySelector=selector=>({'[data-staff-pen-content]':content,'[data-staff-pen-close]':popupClose,'[data-staff-pen-title]':title,'[data-staff-pen-date]':date}[selector]);
const material=new Node(),before=new Node(),after=new Node(),section=new Node();material.append(before,section,after);
const candidateButtons=[new Node(),new Node()],candidateDialogs=[new Node(),new Node()],closeButtons=[new Node(),new Node()];
candidateButtons.forEach((button,index)=>{button.dataset.staffPenCandidate='candidate-'+index;candidateDialogs[index].querySelectorAll=()=>[closeButtons[index]];});
section.querySelectorAll=selector=>selector==='dialog[open]'?candidateDialogs.filter(dialog=>dialog.open):[];
const shortcut=new Node();shortcut.dataset={staffPenSession:'9',staffPenRole:'examiner',staffPenName:'Exam session',staffPenDate:'25/11/2026'};shortcut.closest=()=>shortcut;
const supervisorSection=new Node(),supervisorMaterial=new Node();supervisorSection.querySelectorAll=()=>[];supervisorMaterial.append(supervisorSection);
const assignments=[{dataset:{staffLogisticsRole:'examiner'},querySelector:()=>section},{dataset:{staffLogisticsRole:'supervisor'},querySelector:()=>supervisorSection}];
const handlers={},classes=new Set();
const document={querySelector:()=>popup,querySelectorAll:()=>candidateButtons,
 getElementById:id=>id.startsWith('candidate-')?candidateDialogs[Number(id.split('-')[1])]:{querySelectorAll:()=>assignments},
 createComment:()=>new Node(),addEventListener:(type,handler)=>handlers[type]=handler,
 body:{classList:{add:value=>classes.add(value),remove:value=>classes.delete(value)}}};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_pen_arrangements.js','utf8'),{document});
candidateButtons[0].events.click();assert.equal(candidateDialogs[0].open,true);assert.equal(popup.open,false);
closeButtons[0].events.click();assert.equal(candidateDialogs[0].open,false);assert.equal(candidateButtons[0].focused,true);
let prevented=false;handlers.click({target:shortcut,preventDefault(){prevented=true;}});
assert.equal(prevented,true);assert.equal(popup.open,true);assert.equal(content.children[0],section);assert.equal(title.textContent,'Exam session');assert.equal(date.textContent,'25/11/2026');assert.equal(classes.has('staff-pen-dialog-open'),true);
assert.equal(material.children.length,3);assert.notEqual(material.children[1],section,'Keep a placeholder for the original section');
candidateButtons[1].events.click();assert.equal(candidateDialogs[1].open,true);
candidateDialogs[1].events.click({target:candidateDialogs[1],clientX:50,clientY:50});assert.equal(candidateDialogs[1].open,true);
candidateDialogs[1].events.click({target:candidateDialogs[1],clientX:0,clientY:0});assert.equal(candidateDialogs[1].open,false);assert.equal(popup.open,true);
candidateButtons[0].events.click();popupClose.events.click();assert.equal(candidateDialogs[0].open,false);assert.equal(popup.open,false);assert.equal(shortcut.focused,true);assert.equal(material.children[1],section);assert.equal(content.children.length,0);assert.equal(classes.has('staff-pen-dialog-open'),false);
handlers.click({target:shortcut,preventDefault(){}});popup.events.click({target:popup,clientX:0,clientY:0});assert.equal(popup.open,false);assert.equal(material.children[1],section);
const supervisorShortcut=new Node();supervisorShortcut.dataset={...shortcut.dataset,staffPenRole:'supervisor'};supervisorShortcut.closest=()=>supervisorShortcut;
handlers.click({target:supervisorShortcut,preventDefault(){}});assert.equal(content.children[0],supervisorSection,'Supervisor action must select the all-candidates section instead of the same person’s Examiner section');popupClose.events.click();assert.equal(supervisorMaterial.children[0],supervisorSection);
// The hydration step must leave PEN after every other information block.
const source=fs.readFileSync('app/static/js/staff_exam_sessions.js','utf8');
const materials={children:[{kind:'pen'},{kind:'resource'}],querySelector(){return this.children.find(node=>node.kind==='pen');},insertBefore(node){this.children=this.children.filter(item=>item!==node).concat(node);}};
vm.runInNewContext(source.slice(source.indexOf('      const penSection ='),source.indexOf('      if (!rows.length')), {materials});
assert.equal(materials.children.at(-1).kind,'pen');
console.log('Staff PEN portal: direct/nested modals, original-section move/restore, unique dialog ownership, X/backdrop, focus and final material ordering passed.');

const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const handlers={};let redirected,posted;
const rows=[];
const status={};const submit={disabled:false};
const hidden={value:'',dispatchEvent(){}};
const editor={innerHTML:'<p><strong>Flight details</strong></p>',editable:true,getAttribute(){return String(this.editable);},focus(){},closest:()=>form};
const commands=[];
const range={collapsed:false,cloneRange(){return this;},commonAncestorContainer:{nodeType:1,closest:()=>editor}};
const selection={rangeCount:1,getRangeAt:()=>range,removeAllRanges(){},addRange(){}};
const panel={hidden:true},linkError={},linkInput={value:'',focus(){}};
const wrapper={querySelector:key=>({'[data-logistics-instructions-editor]':editor,'[data-logistics-rich-link-panel]':panel,'[data-logistics-rich-link-error]':linkError,'[data-logistics-rich-link-url]':linkInput}[key])};

const form={action:'https://portal.test/pre-session-control-tower/logistics/cards/1',dataset:{sessionId:'10'},querySelector(key){return key==='[name="instructions_html"]'?hidden:key==='[data-logistics-instructions-editor]'?editor:key==='[data-logistics-links]'?{append(row){rows.push(row);}}:key==='[data-logistics-save-status]'?status:key==='[name=session_ids]:checked'?{value:'10'}:submit;},querySelectorAll:()=>rows};
class Element{
 constructor(){this.children=[];this.dataset={};this.value='';}
 append(...nodes){this.children.push(...nodes);}
 setAttribute(){} focus(){}
 querySelector(key){return this.children.find(node=>key==='[data-link-name]'?'linkName'in node.dataset:'linkUrl'in node.dataset);}
 remove(){rows.splice(rows.indexOf(this),1);}
}
const window={getSelection:()=>selection,location:{href:'https://portal.test/pre-session-control-tower?session_year=2026&view=sessions',assign(url){redirected=String(url);}}};
const document={addEventListener(name,fn){handlers[name]=fn;},createElement:()=>new Element(),execCommand(command){commands.push(command);}};
class FormData{constructor(){this.values={};}set(key,value){this.values[key]=value;}}
vm.runInNewContext(fs.readFileSync('app/static/js/staff_logistics.js','utf8'),{document,window,URL,FormData,Event:class{},fetch:async(url,options)=>{posted=options;return{ok:true,json:async()=>({ok:true})};}});
(async()=>{
 const add={closest:()=>form};await handlers.click({target:{closest:key=>key==='[data-add-logistics-link]'?add:null}});
 assert.equal(rows.length,1);assert.equal(rows[0].children[0].required,true);assert.equal(rows[0].children[1].type,'url');
 rows[0].children[0].value='Hotel';rows[0].children[1].value='https://example.com/hotel';
 let prevented=false;await handlers.submit({target:{closest:()=>form},preventDefault(){prevented=true;}});
 assert.equal(posted.body.values.instructions_html,'<p><strong>Flight details</strong></p>');
 assert.equal(prevented,true);assert.deepEqual(JSON.parse(posted.body.values.links),[{name:'Hotel',url:'https://example.com/hotel'}]);
 assert.match(redirected,/open_schedule_modal=10/);assert.match(redirected,/open_modal_target=logistics/);
 const remove={closest:()=>rows[0]};await handlers.click({target:{closest:key=>key==='[data-remove-logistics-link]'?remove:null}});assert.equal(rows.length,0);
 const count={};handlers.change({target:{closest:()=>({querySelector:()=>count,querySelectorAll:()=>[{},{}]})}});assert.equal(count.textContent,'2 selected');
 handlers.selectionchange();
 const act=async attribute=>{
   const button={dataset:{logisticsTextCommand:attribute==='bold'?'bold':undefined},closest:()=>wrapper,hasAttribute:key=>key===attribute};
   await handlers.click({target:{closest:key=>key.startsWith('[data-logistics-text-command],')?button:null}});
 };
 await act('bold');assert.equal(commands.at(-1),'bold');assert.equal(hidden.value,editor.innerHTML);
 await act('data-logistics-text-link');assert.equal(panel.hidden,false);
 linkInput.value='javascript:alert(1)';await act('data-logistics-rich-link-apply');assert.equal(commands.length,1);assert.match(linkError.textContent,/http/);
 linkInput.value='https://example.com/booking';await act('data-logistics-rich-link-apply');assert.equal(commands.at(-1),'createLink');assert.equal(panel.hidden,true);
 editor.editable=false;await act('bold');assert.equal(commands.length,2);
 console.log('Rich instructions: formatting commands, HTML synchronisation, link validation and read-only protection passed.');
 console.log('Logistics cards: optional links, add/remove, JSON submission and reopening the current Logistics modal passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

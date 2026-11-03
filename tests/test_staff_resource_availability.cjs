const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/static/js/staff_exam_sessions.js','utf8');
const context={URL,document:{createElement:tag=>({tag,children:[],attributes:{},append(...items){this.children.push(...items);},setAttribute(name,value){this.attributes[name]=value;}})}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('  const make ='),source.indexOf('  const hydrate ='))+'\nthis.appendResource=appendMaterialResource;',context);
for(const title of ['✅ Examiner guidelines for online exams','✅ Examiner guidelines for onsite exams','✅ Supervisor guidelines for onsite sessions','✅ Supervisor guidelines for online sessions','✅ Supervisor guidelines for online sessions at exam centre']){
 const item={children:[],append(...nodes){this.children.push(...nodes);}};
 context.appendResource(item,title,'');
 assert.equal(item.children[0].tag,'span');assert.equal(item.children[0].attributes['aria-disabled'],'true');
 assert.equal(item.children[0].href,undefined);assert.equal(item.children[1].textContent,'Available soon');
 assert.ok(item.children[0].className.includes('staff-detail-resource-disabled'));
 const configured={children:[],append(...nodes){this.children.push(...nodes);}};
 context.appendResource(configured,title,'https://example.com/resource');
 assert.equal(configured.children.length,1);assert.equal(configured.children[0].tag,'a');
 assert.equal(configured.children[0].href,'https://example.com/resource');
}
console.log('Staff resources: disabled grey resource and Available soon when missing; active link once configured.');

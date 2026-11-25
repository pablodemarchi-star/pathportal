const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/js/tower_live.js','utf8');
function scenario(){
 let listener,current,label='Initial table';const jobs=[],installed=[];
 const childWindow={};const modal={querySelector:()=>({contentWindow:childWindow})};
 const region=value=>({querySelectorAll:()=>[],replaceWith(fresh){current=fresh;label=fresh.label;installed.push(label);},label:value});
 current=region(label);
 const document={body:{matches:()=>false},currentScript:{src:'https://portal.test/static/js/tower_live.js'},querySelectorAll:()=>[modal],querySelector:()=>current,getElementById:()=>null};
 const window={location:{href:'https://portal.test/pre-session-control-tower?view=sessions',origin:'https://portal.test'},fetch:()=>new Promise(resolve=>jobs.push(resolve)),addEventListener:(name,callback)=>{if(name==='message')listener=callback;}};
 class DOMParser{parseFromString(value){return{querySelector:()=>region(value),querySelectorAll:()=>[]};}}
 vm.runInNewContext(source,{window,document,DOMParser,URL});
 const saved=()=>listener({origin:window.location.origin,source:childWindow,data:{type:'tower-session-saved'}});
 const finish=(index,value,ok=true)=>jobs[index]({ok,text:async()=>value});
 return{saved,finish,jobs,installed,label:()=>label};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const pen=scenario();pen.saved();assert.equal(pen.jobs.length,1);
 // The candidate save starts a slow table refresh; the checkbox is confirmed before it returns.
 pen.saved();pen.finish(0,'MANAGEMENT · Finalise exam arrangements for candidates with PEN');await settle();
 assert.equal(pen.jobs.length,2,'The PEN confirmation must queue a fresh table request while the previous candidate-save refresh is pending');
 assert.equal(pen.installed.length,0,'A response from before the confirmation must not overwrite the current table');
 pen.finish(1,'PEN completed — no pending Management action');await settle();
 assert.equal(pen.label(),'PEN completed — no pending Management action');
 const multiple=scenario();multiple.saved();multiple.saved();multiple.saved();multiple.finish(0,'Outdated');await settle();assert.equal(multiple.jobs.length,2);
 multiple.finish(1,'Latest');await settle();assert.deepEqual(multiple.installed,['Latest']);
 multiple.saved();assert.equal(multiple.jobs.length,3);multiple.finish(2,'Finalise exam arrangements for candidates with PEN');await settle();
 assert.match(multiple.label(),/Finalise/,'Unchecking verification or editing a candidate must restore the current action');
 const failure=scenario();failure.saved();failure.saved();failure.finish(0,'',false);await settle();assert.equal(failure.jobs.length,2);failure.finish(1,'Latest after failure');await settle();assert.equal(failure.label(),'Latest after failure');
 console.log('Tower summary: queued PEN confirmation refresh, discarded stale table, coalesced saves, reopened action and failure recovery passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

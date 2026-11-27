const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/js/tower_live.js','utf8');
function scenario(mode='staffing', online=true){
 let listener,current,staged,editing=false;
 const timers=[],messages=[];
 const childWindow={location:{href:`https://portal.test/${online?'pre-online-session-control-tower':'pre-session-control-tower'}?session_modal=10&session_year=2026&view=sessions`},scrollY:42,
   towerHasUnsavedChanges:()=>editing,postMessage:message=>messages.push(message)};
 const previous={hidden:false,title:'London Bridge',contentWindow:childWindow,contentDocument:{activeElement:{matches:()=>false}},
   parentElement:{append:frame=>{staged=frame;}},replaceWith:frame=>{current=frame;}};
 current=previous;
 const modal={dataset:{towerSession:'10'},classList:{contains:name=>name==='is-open'||name===`is-${mode}-only`},querySelector:()=>current};
 const document={body:{matches:()=>false},currentScript:{src:'https://portal.test/static/js/tower_live.js'},
   querySelectorAll:()=>[modal],createElement:()=>({setAttribute(){},remove(){this.removed=true;},
     contentWindow:{scrollTo(x,y){this.restored=y;}}})};
 const window={location:{href:'https://portal.test/pre-online-session-control-tower',origin:'https://portal.test'},
   fetch:async()=>({ok:false}),setTimeout:fn=>timers.push(fn),addEventListener:(type,fn)=>{if(type==='message')listener=fn;}};
 vm.runInNewContext(source,{window,document,URL});
 const request=()=>listener({origin:window.location.origin,source:childWindow,data:{type:'tower-session-refresh-request'}});
 const ready=()=>{const url=new URL(staged.src);staged.contentDocument={body:{matches:()=>true},querySelector:()=>url.searchParams.get('open_schedule_modal')==='10'?{}:null};staged.onload();};
 return {request,ready,timers,messages,previous,modal,current:()=>current,staged:()=>staged,edit:()=>{editing=true;}};
}
const failure=scenario();failure.request();
assert.equal(failure.current(),failure.previous);
assert.equal(failure.staged().hidden,true);
failure.staged().contentDocument={body:{matches:()=>false},querySelector:()=>null};failure.staged().onload();
assert.equal(failure.current(),failure.previous);assert.equal(failure.previous.hidden,false);
assert.equal(failure.messages[0].type,'tower-refresh-failed');assert.ok(failure.staged().removed);
const success=scenario();success.request();success.ready();
assert.equal(success.current(),success.staged());assert.equal(success.current().hidden,false);
assert.equal(success.current().contentWindow.restored,42);
const typing=scenario();typing.request();typing.edit();typing.ready();
assert.equal(typing.current(),typing.previous);assert.equal(typing.messages[0].type,'tower-refresh-deferred');
const timeout=scenario();timeout.request();timeout.timers[0]();timeout.ready();
assert.equal(timeout.current(),timeout.previous);assert.ok(timeout.staged().removed);
console.log('Safe automatic refresh preserves London Bridge view on errors/timeouts, protects new edits and swaps only a valid ready modal.');

for(const online of [false,true]) for(const mode of ['schedule','staffing','packages','shipments','logistics','finance','sinapsis','communications']){
 const preserved=scenario(mode,online);preserved.request();const url=new URL(preserved.staged().src);
 assert.equal(url.searchParams.get('session_modal'),'10');assert.equal(url.searchParams.get('open_schedule_modal'),'10');
 assert.equal(url.searchParams.get('session_year'),'2026');assert.equal(url.searchParams.get('view'),'sessions');
 for(const other of ['schedule','staffing','packages','shipments','logistics','finance','sinapsis','communications'])assert.equal(url.searchParams.get(other+'_only'),other===mode?'1':null);
 preserved.ready();assert.equal(preserved.current(),preserved.staged());assert.equal(preserved.messages.length,0);
}
const blank=scenario();blank.request();blank.staged().contentDocument={URL:'about:blank'};blank.staged().onload();
assert.equal(blank.current(),blank.previous);assert.equal(blank.messages.length,0);assert(!blank.staged().removed);
blank.ready();assert.equal(blank.current(),blank.staged());assert.equal(blank.messages.length,0);
console.log('Onsite/Online refresh reconstructs stripped modal parameters, preserves every block and ignores initial about:blank loads without false warnings.');
const switched=scenario('staffing');
switched.previous.contentDocument.querySelector=()=>({id:'schedule-workflow-10',classList:{contains:name=>name==='is-finance-only'}});
switched.request();const switchedURL=new URL(switched.staged().src);
assert.equal(switchedURL.searchParams.get('finance_only'),'1');assert.equal(switchedURL.searchParams.get('staffing_only'),null);
const examRecords=scenario();
examRecords.previous.contentDocument.querySelector=()=>({id:'exam-records-10',classList:{contains:()=>false}});
examRecords.request();assert.equal(new URL(examRecords.staged().src).searchParams.get('open_modal_target'),'exam-records');

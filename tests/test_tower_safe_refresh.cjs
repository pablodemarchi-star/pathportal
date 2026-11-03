const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/js/tower_live.js','utf8');
function scenario(){
 let listener,current,staged,editing=false;
 const timers=[],messages=[];
 const childWindow={location:{href:'https://portal.test/modal?session_modal=10&staffing_only=1'},scrollY:42,
   towerHasUnsavedChanges:()=>editing,postMessage:message=>messages.push(message)};
 const previous={hidden:false,title:'London Bridge',contentWindow:childWindow,contentDocument:{activeElement:{matches:()=>false}},
   parentElement:{append:frame=>{staged=frame;}},replaceWith:frame=>{current=frame;}};
 current=previous;
 const modal={dataset:{towerSession:'10'},classList:{contains:()=>true},querySelector:()=>current};
 const document={body:{matches:()=>false},currentScript:{src:'https://portal.test/static/js/tower_live.js'},
   querySelectorAll:()=>[modal],createElement:()=>({setAttribute(){},remove(){this.removed=true;},
     contentWindow:{scrollTo(x,y){this.restored=y;}}})};
 const window={location:{href:'https://portal.test/pre-online-session-control-tower',origin:'https://portal.test'},
   fetch:async()=>({ok:false}),setTimeout:fn=>timers.push(fn),addEventListener:(type,fn)=>{if(type==='message')listener=fn;}};
 vm.runInNewContext(source,{window,document,URL});
 const request=()=>listener({origin:window.location.origin,source:childWindow,data:{type:'tower-session-refresh-request'}});
 const ready=()=>{staged.contentDocument={body:{matches:()=>true},querySelector:()=>({})};staged.onload();};
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

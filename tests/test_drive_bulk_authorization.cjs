const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const element=()=>({dataset:{},children:[],addEventListener(event,fn){this[event]=fn;},append(...items){this.children.push(...items);},appendChild(item){this.children.push(item);},replaceChildren(){this.children=[];}});
const inputs=Array.from({length:4},(_,i)=>({...element(),value:String(i+1),checked:false}));
const all=element(),start=element(),clear=element(),close=element(),count={},status={},list=element();
const menu={open:true};start.closest=()=>menu;
const dialog={open:false,showModal(){this.open=true;},close(){this.open=false;}};
const root={dataset:{csrf:'test',prepareUrl:'/prepare',verifyUrl:'/verify',tokenUrl:'/token'},querySelector:key=>({'[data-drive-bulk-start]':start,'[data-drive-bulk-clear]':clear,'[data-drive-bulk-dialog]':dialog,'[data-drive-bulk-status]':status,'[data-drive-bulk-results]':list,'[data-drive-bulk-count]':count,'[data-drive-bulk-close]':close}[key])};
let picker;
class DocsView{setIncludeFolders(){return this;}setSelectFolderEnabled(){return this;}setFileIds(ids){this.ids=ids;return this;}}
class PickerBuilder{
 constructor(){this.views=[];}
 setAppId(){return this;}setDeveloperKey(){return this;}setOAuthToken(){return this;}setOrigin(){return this;}setTitle(){return this;}setSelectableMimeTypes(){return this;}
 enableFeature(feature){assert.equal(feature,'multiple');this.multiple=true;return this;}addView(view){this.views.push(view);return this;}setCallback(fn){this.callback=fn;return this;}
 build(){picker=this;return {dispose(){},setVisible(value){assert.equal(value,true);assert.equal(dialog.open,false);}};}
}
const requests=[];
const fetch=async(url,options)=>{
 requests.push({url,body:options.body});assert.equal(options.body.get('csrf_token'),'test');
 let result;
 if(url==='/prepare')result={ok:true,folders:[{folder_id:'shared-folder-12345',session_names:['Session 1','Session 2']},{folder_id:'other-folder-12345',session_names:['Session 3']}],issues:[{session_name:'Session 4',error:'Folder missing'}]};
 else if(url==='/token')result={ok:true,app_id:'123',api_key:'test',access_token:'test'};
 else result=options.body.get('folder_ids')==='other-folder-12345'?{ok:true,results:[{folder_id:'other-folder-12345',status:'failed',error:'Editor access required'}]}:{ok:true,results:[{folder_id:'shared-folder-12345',status:'authorized'}]};
 return {ok:true,headers:{get:()=> 'application/json'},json:async()=>result};
};
const document={querySelector:key=>key==='[data-drive-bulk]'?root:all,querySelectorAll:()=>inputs,createElement:()=>element()};
const window={location:{origin:'https://portal.test'},google:{picker:{DocsView,PickerBuilder,ViewId:{FOLDERS:'folders'},Action:{PICKED:'picked',CANCEL:'cancel'},Feature:{MULTISELECT_ENABLED:'multiple'}}}};
vm.runInNewContext(fs.readFileSync('app/static/js/drive_bulk_authorization.js','utf8'),{window,document,fetch,FormData,Promise,setTimeout,clearTimeout});
(async()=>{
 assert.equal(start.disabled,true);
 all.checked=true;all.change();assert.equal(start.disabled,false);assert.equal(count.textContent,'4 sessions selected');
 await start.click();assert.equal(picker.multiple,true);assert.equal(picker.views[0].ids,'shared-folder-12345,other-folder-12345');
 assert.deepEqual(requests[0].body.getAll('session_ids'),['1','2','3','4']);
 await picker.callback({action:'picked',docs:[{id:'shared-folder-12345'},{id:'shared-folder-12345'},{id:'unrelated-folder-12345'}]});
 assert.equal(requests.filter(item=>item.url==='/verify').length,1);
 assert.match(status.textContent,/1 folder\(s\) authorized/);assert.match(status.textContent,/1 not selected/);assert.match(status.textContent,/1 unrelated folder/);
 assert.equal(dialog.open,true);assert.equal(start.disabled,false);
 await start.click();const before=requests.filter(item=>item.url==='/verify').length;
 await picker.callback({action:'cancel'});assert.equal(requests.filter(item=>item.url==='/verify').length,before);assert.match(status.textContent,/cancelled/);
 await start.click();
 await picker.callback({action:'picked',docs:[{id:'shared-folder-12345'},{id:'other-folder-12345'}]});
 assert.match(status.textContent,/1 folder\(s\) authorized/);assert.match(status.textContent,/1 failed/);
 clear.click();assert.equal(start.disabled,true);assert.ok(inputs.every(input=>!input.checked));
 console.log('Bulk Drive: session selection, targeted multiselect, shared-folder deduplication, partial selection and cancellation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

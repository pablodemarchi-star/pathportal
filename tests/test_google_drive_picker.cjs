const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/google_drive.js','utf8');
let activePicker;
const requests=[];
class DocsView {
  setIncludeFolders(value){assert.equal(value,true);return this;}
  setSelectFolderEnabled(value){assert.equal(value,true);return this;}
  setFileIds(value){assert.equal(typeof value,'string');this.selected=value;return this;}
}
class PickerBuilder {
  constructor(){this.views=[];}
  setAppId(value){assert.equal(value,'197615227759');return this;}
  setDeveloperKey(value){assert.equal(value,'restricted-browser-key');return this;}
  setOAuthToken(value){assert.equal(value,'short-lived-access');return this;}
  setOrigin(value){assert.equal(value,'https://portal.test');return this;}
  setTitle(){return this;}
  setSelectableMimeTypes(value){assert.equal(value,'application/vnd.google-apps.folder');return this;}
  addView(view){this.views.push(view);return this;}
  setCallback(fn){this.callback=fn;return this;}
  build(){activePicker=this;return {setVisible:value=>assert.equal(value,true),dispose(){}};}
}
const cards=['supporting','receipts'].map(key=>{
  const message={};const current={replaceChildren(link){this.link=link;}};
  const card={dataset:{saveUrl:'/save/'+key,suggestedId:'suggested-'+key},querySelector:selector=>selector==='[data-drive-message]'?message:current};
  const button={disabled:false,closest:()=>card,addEventListener:(type,fn)=>{button.click=fn;}};
  return {button,card,current,message};
});
const root={dataset:{csrf:'csrf-test',tokenUrl:'/picker-token'},querySelectorAll:()=>cards.map(item=>item.button)};
const document={querySelector:()=>root,createElement:()=>({})};
const window={location:{origin:'https://portal.test'},google:{picker:{DocsView,PickerBuilder,ViewId:{FOLDERS:'folders'},Action:{PICKED:'picked',CANCEL:'cancel'}}}};
const fetch=async(url,options)=>{
  assert.equal(options.method,'POST');assert.equal(options.body.get('csrf_token'),'csrf-test');
  requests.push(url);
  const data=url==='/picker-token'?{ok:true,api_key:'restricted-browser-key',access_token:'short-lived-access',app_id:'197615227759'}:
    {ok:true,name:'Verified folder',url:'https://drive.google.com/drive/folders/'+options.body.get('folder_id')};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
};
vm.runInNewContext(source,{window,document,fetch,FormData,Promise,Error,setTimeout,clearTimeout});
(async()=>{
  for(const item of cards){
    await item.button.click();
    assert.equal(activePicker.views.length,2);
    assert.equal(activePicker.views[0].selected,item.card.dataset.suggestedId);
    await activePicker.callback({action:'picked',docs:[{id:'authorized-'+item.card.dataset.suggestedId}]});
    assert.equal(item.button.disabled,false);
    assert.equal(item.current.link.textContent,'Verified folder');
    assert.equal(requests.at(-1),item.card.dataset.saveUrl);
  }
  const savedLink=cards[0].current.link;
  await cards[0].button.click();
  await activePicker.callback({action:'cancel'});
  assert.equal(cards[0].current.link,savedLink);
  assert.equal(cards[0].button.disabled,false);
  console.log('Drive Picker: folder authorization, per-destination saving, and cancellation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

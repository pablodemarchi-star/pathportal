const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/static/js/app.js','utf8');
const extract=(name,next)=>source.slice(source.indexOf(`const ${name} =`),source.indexOf(`const ${next} =`,source.indexOf(`const ${name} =`)));
const context={rowIsRemoteSupervisor:()=>false,rowFeesAreLocked:()=>false,rowHasManualFeeOverride:()=>false,
  rowTimeRangeMinutes:row=>row.minutes,formatMoney:value=>new Intl.NumberFormat('es-AR',{maximumFractionDigits:2}).format(value),
  formatDecimalNumber:value=>String(value),syncSeniority:()=>{},syncAssignmentTotalFee:()=>{}};
vm.createContext(context);
vm.runInContext(extract('parseRoleFeeBase','currencyForAssignmentCost')+extract('roleFeeSettings','clearRemoteDeviceDep')+
  extract('syncSupervisorRoleFee','syncSupervisorRoleFeePlaceholder')+'\nthis.sync=syncSupervisorRoleFee;',context);
for(const format of ['Online','Online at exam centre','Onsite']){
 for(const role of ['supervisor','examiner','intern']){
  for(const minutes of [60,120]){
   const fields=new Map();
   for(const key of ['display','input','currency-input','base-input','unit-input'])fields.set(`[data-role-fee-${key}]`,{});
   const settings={roleFeeLabel:role,roleFeeCurrency:'ARS',roleFeeValue:'25.000',roleFeeUnit:'per hour'};
   const row={minutes,dataset:{sectionKey:role},closest:selector=>({dataset:selector==='.session-member-section'?settings:{sessionFormat:format}}),querySelector:selector=>fields.get(selector)};
   context.sync(row);
   const amount=(25000*minutes/60)*(role==='supervisor'&&format==='Online'?.65:1);
   assert.equal(fields.get('[data-role-fee-input]').value,'ARS '+new Intl.NumberFormat('es-AR').format(amount));
   assert.equal(settings.roleFeeValue,'25.000');
   if(role==='supervisor'&&format==='Online')assert.ok(fields.get('[data-role-fee-display]').title.includes('65%'));
  }
 }
}
console.log('Automatic card fee: Online Supervisor 65%; all other tested formats and roles 100%.');

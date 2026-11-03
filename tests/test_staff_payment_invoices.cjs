const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const eventNode=()=>({listeners:{},addEventListener(type,callback){this.listeners[type]=callback;}});
const frame={removeAttribute(name){delete this[name];}},title={},fallback={},download={},closer=eventNode();
const nodes={'[data-staff-invoice-preview-frame]':frame,'#staff-invoice-preview-title':title,
 '[data-staff-invoice-preview-fallback]':fallback,'[data-staff-invoice-preview-download]':download,'[data-staff-invoice-preview-close]':closer};
const dialog={...eventNode(),querySelector:selector=>nodes[selector],showModal(){this.open=true;},close(){this.open=false;this.listeners.close();}};
let focused=0;
const pdf={...eventNode(),href:'https://portal.test/staff-payments/10/2026/invoice',dataset:{invoiceName:'Invoice.pdf',invoicePreviewable:'true'},focus(){focused++;}};
const doc={...eventNode(),href:'https://portal.test/staff-payments/11/2026/invoice',dataset:{invoiceName:'Invoice.docx',invoicePreviewable:'false'},focus(){focused++;}};
const removeButton={};const removeForm={...eventNode(),querySelector:()=>removeButton};
const document={querySelector:()=>dialog,querySelectorAll:selector=>selector==='[data-staff-invoice-view]'?[pdf,doc]:[removeForm]};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_payment_invoices.js','utf8'),{document});
pdf.listeners.click({preventDefault(){}});assert.equal(dialog.open,true);assert.equal(frame.src,pdf.href);assert.equal(title.textContent,'Invoice.pdf');assert.equal(fallback.hidden,true);
dialog.listeners.click({target:frame});assert.equal(dialog.open,true);
dialog.listeners.click({target:dialog});assert.equal(dialog.open,false);assert.equal(frame.src,undefined);assert.equal(focused,1);
pdf.listeners.click({preventDefault(){}});closer.listeners.click();assert.equal(dialog.open,false);
doc.listeners.click({preventDefault(){}});assert.equal(frame.hidden,true);assert.equal(fallback.hidden,false);assert.equal(download.href,doc.href);
removeForm.listeners.submit();assert.equal(removeButton.disabled,true);
console.log('Invoice modal: View, close button, backdrop dismissal, non-previewable download and removal submit verified.');

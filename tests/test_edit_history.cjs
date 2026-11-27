/* Browser regression: run with PLAYWRIGHT_MODULE pointing to Playwright if not installed locally. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const http = require('node:http');
const root = process.env.KNOWLEDGE_TEST_ROOT || path.resolve(__dirname, '..');
const file = p => path.join(root,p);
const server = http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><html lang="zh-CN"><body><main id="content"></main></body></html>');});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,args:['--no-proxy-server']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>{errors.push(String(e));console.error('PAGE ERROR',e)});
 const url='http://127.0.0.1:'+server.address().port;
 let caseId=0;
 async function fresh(hash='') {await page.goto(url+'/case-'+(++caseId)+hash);await page.addScriptTag({path:file('core/deskcore/static/edit-history.js')});}
 const pause=()=>page.waitForTimeout(30);
 async function value(selector,expected){assert.equal(await page.locator(selector).inputValue(),expected);}
 async function paste(selector,text) {
  await page.locator(selector).focus();
  await page.locator(selector).evaluate((el,text)=>{
   el.setSelectionRange?.(0,el.value.length);
   el.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,cancelable:true,inputType:'insertFromPaste',data:text}));
   el.value=text;
   if(typeof el.selectionStart==='number')el.setSelectionRange(text.length,text.length);
   el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertFromPaste',data:text}));
  },text);
 }
 const undo=scope=>page.locator(scope+' [data-edit-history-action=undo]').click();
 const redo=scope=>page.locator(scope+' [data-edit-history-action=redo]').click();
 await fresh();
 await page.locator('#content').evaluate(el=>el.innerHTML='<form id="edit"><input name="title" value="Original"><textarea name="body">Original paragraph</textarea><button type="submit">Save</button></form><form id="settings"><input name="api_key" type="password" value="test-only"><input name="model" value="model"></form><input id="search" value=""><textarea id="paper-chat-question"></textarea>');
 await pause();
 assert.equal(await page.locator('#edit .edit-history-tools').count(),1);
 assert.equal(await page.locator('#paper-chat-question').evaluate(el=>el.previousElementSibling?.className),'');
 await paste('#edit textarea','Replacement one');await paste('#edit textarea','Replacement two');
 await undo('#edit');await value('#edit textarea','Replacement one');
 await undo('#edit');await value('#edit textarea','Original paragraph');
 await redo('#edit');await value('#edit textarea','Replacement one');
 await page.locator('#edit textarea').press('Control+Shift+Z');await value('#edit textarea','Replacement two');
 await page.locator('#edit textarea').press('Control+z');await paste('#edit textarea','New branch');
 assert.equal(await page.locator('#edit [data-edit-history-action=redo]').isDisabled(),true);
 // Redraw same editor keeps history, including return value on ordinary input handlers.
 await page.evaluate(()=>{const form=document.querySelector('#edit');const body=form.querySelector('textarea').value;form.outerHTML='<form id="edit"><input name="title" value="Original"><textarea name="body">'+body+'</textarea><button>Save</button></form>';window.model='';document.querySelector('#edit').oninput=e=>window.model=e.target.value;});
 await pause();await undo('#edit');await value('#edit textarea','Replacement one');assert.equal(await page.evaluate(()=>window.model),'Replacement one');
 // Continuous typing is one step; IME composition is one separate step.
 await page.evaluate(()=>window.EditHistory.clear());await pause();await page.locator('#edit textarea').press('End');await page.locator('#edit textarea').pressSequentially('abc');
 await undo('#edit');await value('#edit textarea','Replacement one');
 await page.locator('#edit textarea').evaluate(el=>{
  el.focus();el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));
  for(const suffix of ['中','中文']){el.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,inputType:'insertCompositionText',isComposing:true}));el.value='Replacement one'+suffix;el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertCompositionText',isComposing:true}));}
  el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'中文'}));
 });
 await undo('#edit');await value('#edit textarea','Replacement one');
 // Removing and reopening or navigating must not resurrect another session's edits.
 await paste('#edit textarea','Leave me');await page.locator('#edit').evaluate(el=>el.remove());await pause();
 await page.locator('#content').evaluate(el=>el.insertAdjacentHTML('beforeend','<form id="edit"><textarea name="body">New session</textarea></form>'));await pause();
 assert.equal(await page.locator('#edit [data-edit-history-action=undo]').isDisabled(),true);
 await paste('#edit textarea','Changed');await page.evaluate(()=>location.hash='other');await pause();
 assert.equal(await page.locator('#edit [data-edit-history-action=undo]').isDisabled(),true);
 // Secrets do not participate in history; modifying a nonsecret field never restores a secret.
 await page.locator('#settings [name=api_key]').fill('changed-test-only');await page.locator('#settings [name=model]').fill('new-model');await undo('#settings');
 await value('#settings [name=api_key]','changed-test-only');await value('#settings [name=model]','model');
 // Cap history to 50 changes.
 await page.evaluate(()=>window.EditHistory.clear());await pause();
 for(let i=0;i<55;i++)await paste('#edit textarea','Value '+i);
 for(let i=0;i<50;i++)await undo('#edit');
 assert.equal(await page.locator('#edit [data-edit-history-action=undo]').isDisabled(),true);await value('#edit textarea','Value 4');
 // Loading a saved note must not create an undo step back to the loading placeholder.
 await page.locator('#content').evaluate(el=>el.insertAdjacentHTML('beforeend','<form id="loaded-note"><textarea disabled></textarea></form>'));await pause();
 await page.locator('#loaded-note textarea').evaluate(el=>{el.value='Loaded saved note';el.disabled=false;});
 await page.locator('#loaded-note textarea').focus();
 assert.equal(await page.locator('#loaded-note [data-edit-history-action=undo]').isDisabled(),true);
 await paste('#loaded-note textarea','Edited loaded note');await undo('#loaded-note');await value('#loaded-note textarea','Loaded saved note');
 // Adding fields must not restore missing properties as the literal string "undefined".
 await page.locator('#loaded-note').evaluate(el=>el.insertAdjacentHTML('beforeend','<input name="extra" value="Extra field">'));await pause();
 assert.equal(await page.locator('#loaded-note [data-edit-history-action=undo]').isDisabled(),true);
 await page.locator('#loaded-note [name=extra]').fill('Changed extra');await undo('#loaded-note');await value('#loaded-note [name=extra]','Extra field');
 console.log('PASS: multi-step, redo branching, redraw, typing, IME, exit, secrets, bounded history, async baseline and form shape');

 assert.deepEqual(errors,[]);
 await browser.close();server.close();
})().catch(e=>{console.error(e);process.exit(1)});

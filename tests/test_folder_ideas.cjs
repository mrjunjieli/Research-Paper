const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..'),file=p=>path.join(root,p);
const app=fs.readFileSync(file('core/deskcore/static/app.js'),'utf8');
const bar=app.slice(app.indexOf('function libraryActionBar()'),app.indexOf('\nfunction favoriteFolderBadge'));
const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<html lang="zh-CN"><body><main id="content"></main></body></html>')});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,args:['--no-proxy-server']});
 try{
 const context=await browser.newContext();const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const data={a:{folder_id:'a',content:'',revision:0},b:{folder_id:'b',content:'',revision:0}};
 let offline=false,failGet=false,gets=0,posts=0,saveDelay=100;
 await context.route('**/api/folder-ideas?*',async route=>{
  const req=route.request(),id=new URL(req.url()).searchParams.get('folder_id');
  if(req.method()==='GET'){gets++;if(failGet)return route.fulfill({status:503,json:{error:'offline'}});return route.fulfill({json:data[id]});}
  posts++;if(offline)return route.fulfill({status:503,json:{error:'offline'}});
  const body=req.postDataJSON();assert.equal(body.folder_id,id);
  if(body.content!==data[id].content&&body.revision!==data[id].revision)return route.fulfill({status:409,json:{error:'conflict',conflict:true}});
  if(body.content!==data[id].content)data[id]={folder_id:id,content:body.content,revision:data[id].revision+1};
  await new Promise(r=>setTimeout(r,saveDelay));return route.fulfill({json:data[id]});
 });
 let visit=0;
 async function fresh(){
  await page.goto('http://127.0.0.1:'+server.address().port+'/case'+(++visit));
  await page.addScriptTag({content:`window.state={items:[],folders:[{id:'a',name:'Speech',count:0},{id:'b',name:'Models',count:0}]};window.libraryFolder='all';window.esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));${bar};window.renderFolder=id=>{window.libraryFolder=id;document.querySelector('#content').innerHTML=libraryActionBar();};`});
  await page.addScriptTag({path:file('core/deskcore/static/edit-history.js')});
  await page.addScriptTag({path:file('core/deskcore/static/folder-ideas.js')});
 }
 async function render(id){await page.evaluate(id=>window.renderFolder(id),id);if(!['all','unfiled'].includes(id))await page.waitForFunction(()=>document.querySelector('#folder-idea-text')&&!document.querySelector('#folder-idea-text').disabled);}
 const input=()=>page.locator('#folder-idea-text');
 const edit=async()=>{if(await input().evaluate(el=>el.readOnly))await page.locator('[data-idea-edit]').click();};
 const waitLocked=()=>page.waitForFunction(()=>document.querySelector('#folder-idea-text').readOnly);
 const waitSave=()=>page.waitForFunction(()=>document.querySelector('[data-idea-status]').textContent==='已保存到此收藏夹');
 await fresh();await render('all');assert.equal(await page.locator('.folder-ideas').count(),0);await render('unfiled');assert.equal(await page.locator('.folder-ideas').count(),0);assert.equal(gets,0);
 await render('a');assert.equal(await input().evaluate(el=>el.readOnly),true);assert.equal(await page.locator('[data-idea-save]').isDisabled(),true);assert.match(await page.locator('.folder-ideas p').first().textContent(),/仅属于收藏夹「Speech」/);
 await edit();await input().fill('First Speech idea');await waitSave();assert.equal(data.a.content,'First Speech idea');
 assert.equal(await input().evaluate(el=>el.readOnly),false); // Autosave does not end editing.
 await page.locator('[data-idea-save]').click();await waitLocked();
 await input().focus();await page.keyboard.type(' accidental');assert.equal(await input().inputValue(),'First Speech idea');
 await edit();await page.waitForTimeout(30);assert.equal(await page.locator('[data-edit-history-action=undo]').isDisabled(),true);
 await input().fill('Explicit save');await page.locator('[data-idea-save]').click();await waitLocked();assert.equal(data.a.content,'Explicit save');
 await edit();assert.equal(await input().evaluate(el=>el.readOnly),false);
 saveDelay=500;const inFlight=page.waitForRequest(r=>r.url().includes('/api/folder-ideas')&&r.method()==='POST');
 await input().fill('Saving first version');await inFlight;await page.locator('[data-idea-save]').click();
 await input().fill('Newest version while saving');await waitLocked();assert.equal(data.a.content,'Newest version while saving');saveDelay=100;
 await edit();await input().fill('New Speech idea');await render('b');await edit();await input().fill('Model idea');await waitSave();assert.equal(data.a.content,'New Speech idea');assert.equal(data.b.content,'Model idea');
 await page.locator('[data-edit-history-action=undo]').click();await waitSave();assert.equal(data.b.content,'');
 await page.locator('[data-edit-history-action=redo]').click();await waitSave();assert.equal(data.b.content,'Model idea');
 await render('a');assert.equal(await input().inputValue(),'New Speech idea');
 // A transient save failure keeps a per-folder browser draft across a reload.
 offline=true;await edit();await input().fill('Offline Speech draft');await page.waitForFunction(()=>document.querySelector('[data-idea-retry]')&&!document.querySelector('[data-idea-retry]').hidden);
 await page.locator('[data-idea-save]').click();await page.waitForTimeout(150);assert.equal(await input().evaluate(el=>el.readOnly),false);assert.equal(await page.locator('[data-idea-save]').isDisabled(),false);
 assert.equal(JSON.parse(await page.evaluate(()=>localStorage.getItem('knowledge-folder-ideas-v1:a'))).content,'Offline Speech draft');
 offline=false;await fresh();await render('a');await waitSave();assert.equal(await input().evaluate(el=>el.readOnly),true);assert.equal(data.a.content,'Offline Speech draft');assert.equal(data.b.content,'Model idea');
 // A stale browser tab cannot silently overwrite newer saved text.
 data.a={...data.a,content:'Other tab idea',revision:data.a.revision+1};await edit();await input().fill('My conflicting draft');
 await page.waitForFunction(()=>document.querySelector('[data-idea-status]').textContent.includes('另一页面'));
 assert.equal(data.a.content,'Other tab idea');assert.equal(await input().inputValue(),'My conflicting draft');
 page.on('dialog',d=>d.accept());failGet=true;await page.locator('[data-idea-retry]').click();await page.waitForTimeout(150);
 assert.equal(await input().inputValue(),'My conflicting draft');assert.ok(await page.evaluate(()=>localStorage.getItem('knowledge-folder-ideas-v1:a')));
 failGet=false;await page.locator('[data-idea-retry]').click();await waitSave();assert.equal(await input().inputValue(),'Other tab idea');
 assert.equal(await page.locator('[data-edit-history-action=undo]').isDisabled(),true);
 // Failed initial loading must not overwrite existing notes when the connection returns.
 failGet=true;await fresh();await render('b');await edit();await input().fill('Unknown base offline edit');await page.waitForTimeout(750);
 failGet=false;await page.locator('[data-idea-retry]').click();await page.waitForFunction(()=>document.querySelector('[data-idea-status]').textContent.includes('另一页面'));
 assert.equal(data.b.content,'Model idea');
 await render('all');assert.equal(await page.locator('.folder-ideas').count(),0);
 assert.deepEqual(errors,[]);
 if(process.env.IDEA_SCREENSHOT){await render('a');await page.addStyleTag({path:file('core/deskcore/static/style.css')});await page.addStyleTag({path:file('core/deskcore/static/edit-history.css')});await page.addStyleTag({path:file('core/deskcore/static/folder-ideas.css')});await page.locator('.folder-ideas').screenshot({path:process.env.IDEA_SCREENSHOT});}
 console.log('PASS: default readonly, edit/save locking, re-edit history, failed save stays editable, folder-only visibility, autosave, switching isolation, undo/redo, reload recovery, conflict protection, offline-load protection; '+posts+' save requests');
 } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exit(1)});

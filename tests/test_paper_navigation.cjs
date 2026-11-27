// Run with: node --test tests/test_paper_navigation.cjs
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../core/deskcore/static/app.js'),'utf8');
const navigation=source.slice(source.indexOf('let itemNavigationVersion='),source.indexOf('\n',source.indexOf('\n}',source.indexOf('let itemNavigationVersion='))+1));
const stateReads=source.slice(source.indexOf('const stateRequests='),source.indexOf('\nfunction title(',source.indexOf('const stateRequests=')));
function context(api){
 const rendered=[],toasts=[];
 const c={state:{items:[{id:'a'},{id:'b'}],jobs:[]},selected:null,view:'paper',libraryReturnHash:'#paper',libraryHash:()=> '#paper?folder=example',history:{state:null,replaceState(s){this.state=s}},workspace:'research',location:{hash:'',href:'http://127.0.0.1:8765/research'},window:{scrollTo(){},UII18N:{locale:()=> 'en'}},api,reload:async()=>{},loadPaperDetails(){},detail(){rendered.push(c.selected)},toast:s=>toasts.push(s),$:()=>({innerHTML:''}),esc:String,draw(){}};
 vm.createContext(c);vm.runInContext(navigation,c);return {c,rendered,toasts};
}
test('cached papers open before bookkeeping finishes, and logging failure preserves reading',async()=>{
 let reject;const pending=new Promise((_,r)=>reject=r);const {c,rendered,toasts}=context(()=>pending);
 const work=c.openItem('a');assert.deepEqual(rendered,['a']);assert.equal(c.location.hash,'item/a');
 reject(Error('offline'));await work;assert.equal(c.selected,'a');assert.match(toasts[0],/Paper opened/);
});
test('a delayed earlier open cannot move the user away from a newer paper',async()=>{
 let release;const pending=new Promise(r=>release=r);const {c,rendered}=context(()=>pending);
 const a=c.openItem('a'),b=c.openItem('b');assert.deepEqual(rendered,['a','b']);release({ok:true});await Promise.all([a,b]);assert.equal(c.selected,'b');
});
test('unknown paper fetch does not override navigation away',async()=>{
 let release;const {c,rendered}=context(async()=>({ok:true}));c.reload=()=>new Promise(r=>release=r);
 const work=c.openItem('missing');c.selected=null;c.location.hash='inbox';release();await work;assert.deepEqual(rendered,[]);
});
test('simultaneous library reads share one request and recover after a failure',async()=>{
 let calls=0,reject;const {c}=context(()=>{calls++;return new Promise((_,r)=>reject=r)});vm.runInContext(stateReads,c);
 const a=c.readState(),b=c.readState();assert.equal(a,b);assert.equal(calls,1);reject(Error('offline'));await assert.rejects(a);
 c.api=async()=>{calls++;return {workspace:'research'}};await c.readState();assert.equal(calls,2);
});

test('opening a paper retains the filtered collection return link',async()=>{
 const {c}=context(async()=>({ok:true}));await c.openItem('a');assert.equal(c.history.state.libraryReturn,'#paper?folder=example');
});

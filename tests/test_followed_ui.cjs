// 收藏作者：侧栏入口、收藏页、每日推荐新栏目、作者页收藏按钮、关系图图例。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../core/deskcore/static/app.js'),'utf8');

test('a sidebar page exists for collected authors',()=>{
 assert.ok(src.includes("collected:'我收藏的作者'"),'label');
 assert.ok(src.includes("['collected','star','我收藏的作者']"),'sidebar entry');
 assert.ok(src.includes("if(view==='collected')return followedAuthorsPage();"),'route');
});

test('the collected page offers checking, notes and per-author papers',()=>{
 const page=src.slice(src.indexOf('async function followedAuthorsPage'),src.indexOf('function resizeGraphLabels'));
 for(const token of ['/api/followed-authors','/api/followed-authors/check','data-followed-note-edit','这位作者的论文','作者页'])
  assert.ok(page.includes(token),'missing '+token);
 assert.ok(page.includes('每 7 天自动检查一次'),'explains the weekly cadence');
});

test('only verified authors can be collected from the author page',()=>{
 assert.ok(src.includes('a.verified?`<button type="button" class="primary" id="author-follow">'));
 assert.ok(src.includes('只有身份已核实的作者才能收藏'),'explains why the button is missing');
 assert.ok(src.includes("a.followed?'unfollow':'follow'"),'toggles');
});

test('daily recommendations gain a collected-authors section with its own label',()=>{
 assert.ok(src.includes("section('followed',t2('关注的作者','Collected authors')"),'section');
 assert.ok(src.includes('不占每日配额'));
 assert.ok(src.includes("sourceGroups={field:'每日 arXiv',hot:'热点论文',followed:'关注的作者'"),'source label');
});

test('settings expose a separate quota for collected-author papers',()=>{
 assert.ok(src.includes('name="followed_limit"'),'input');
 assert.ok(src.includes('独立配额'));
});

test('the graph marks collected authors with vermilion and a halo',()=>{
 const graph=fs.readFileSync(path.join(__dirname,'../core/deskcore/static/network-3d.js'),'utf8');
 assert.ok(graph.includes("node.followed"),'uses the followed flag');
 assert.ok(graph.includes("'#c8463b'"),'vermilion');
 assert.ok(graph.includes("'node-star'"),'star node');
 assert.ok(src.includes('legend-follow')&&src.includes('星形'),'legend entry');
});

test('each collected card can uncollect with a second-click confirmation',()=>{
 const page=src.slice(src.indexOf('async function followedAuthorsPage'),src.indexOf('function resizeGraphLabels'));
 assert.ok(page.includes('data-followed-remove'),'button on every card');
 assert.ok(page.includes("action:'unfollow'"),'posts unfollow');
 assert.ok(page.includes('再点一次取消收藏'),'two-step confirmation');
});

test('the sidebar entry and the page title have a real star icon',()=>{
 const sprite=fs.readFileSync(path.join(__dirname,'../projects/research/static/index.html'),'utf8');
 assert.ok(sprite.includes('id="i-star"'),'star symbol exists in the sprite');
 const used=[...new Set([...src.matchAll(/uiIcon\('([a-z-]+)'/g)].map(m=>m[1]))];
 const nav=['inbox','book','star','tag','network','flow','newspaper','calendar','pen','flask'];
 for(const name of [...used,...nav])assert.ok(sprite.includes('id="i-'+name+'"'),'sprite provides i-'+name);
});

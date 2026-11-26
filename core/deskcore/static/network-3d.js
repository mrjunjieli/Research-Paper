/* Local 3D coordinates + perspective projection; no remote rendering dependencies. */
function networkAuthorRadius(count,maximum){
 const papers=Number.isFinite(count)?Math.max(1,count):1;
 return 8+18*Math.sqrt((papers-1)/Math.max(1,maximum-1));
}
function networkPaperRadius(citations,maximum){
 const count=Number.isFinite(citations)&&citations>=0?citations:0;
 return 7+18*Math.log1p(count)/Math.log1p(Math.max(1,maximum));
}
class PaperNetwork3D {
 constructor(svg,nodes,edges,mode,onNode,onEdge){this.svg=svg;this.mode=mode;this.nodes=nodes;this.edges=edges;this.onNode=onNode;this.onEdge=onEdge;this.maxAuthorPapers=Math.max(1,...nodes.map(n=>Number.isFinite(n.count)?n.count:0));this.maxCitations=Math.max(1,...nodes.map(n=>Number.isFinite(n.citations)?n.citations:0));this.yaw=.28;this.pitch=-.18;this.zoom=this.targetZoom=1;this.pan={x:0,y:0};this.frame=0;this.drag=null;this.suppressClick=false;this.positions=this.layout();this.range=Math.max(80,...this.positions.map(p=>Math.hypot(p.x,p.y,p.z)));this.build();this.resizeObserver=new ResizeObserver(()=>this.draw());this.resizeObserver.observe(svg);this.bind();this.draw()}
 layout(){const n=this.nodes.length,p=this.nodes.map((node,i)=>{const y=1-2*(i+.5)/n,a=i*Math.PI*(3-Math.sqrt(5)),r=Math.sqrt(1-y*y);return{x:180*Math.cos(a)*r,y:180*y,z:180*Math.sin(a)*r}}),index=new Map(this.nodes.map((n,i)=>[n.id,i]));for(let k=0;k<150;k++){const f=p.map(()=>({x:0,y:0,z:0}));for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){const d={x:p[i].x-p[j].x,y:p[i].y-p[j].y,z:p[i].z-p[j].z},length=Math.max(8,Math.hypot(d.x,d.y,d.z)),force=1200/(length*length);for(const axis of ['x','y','z']){f[i][axis]+=d[axis]/length*force;f[j][axis]-=d[axis]/length*force}}for(const e of this.edges){const i=index.get(e.src),j=index.get(e.dst),d={x:p[j].x-p[i].x,y:p[j].y-p[i].y,z:p[j].z-p[i].z},length=Math.max(1,Math.hypot(d.x,d.y,d.z)),force=(length-150)*.012;for(const axis of ['x','y','z']){f[i][axis]+=d[axis]/length*force;f[j][axis]-=d[axis]/length*force}}for(let i=0;i<n;i++)for(const axis of ['x','y','z'])p[i][axis]+=Math.max(-3,Math.min(3,f[i][axis]-p[i][axis]*.001))}return p}
 element(tag,attrs,parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e}
 build(){this.svg.replaceChildren();this.svg.classList.add('network-3d');this.svg.setAttribute('tabindex','0');const defs=this.element('defs',{},this.svg),marker=this.element('marker',{id:'network-3d-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto'},defs);this.element('path',{d:'M0 0L10 5L0 10',fill:'#b3bcc8'},marker);this.edgeLayer=this.element('g',{},this.svg);this.nodeLayer=this.element('g',{id:'graph-stage'},this.svg);this.lines=this.edges.map((edge,i)=>{const e=this.element('line',{class:'graph-edge','data-edge':i,stroke:'#c9d1dc','stroke-width':this.mode==='authors'?Math.min(4,1+Math.log1p(edge.weight||1)):1.5,...(this.mode==='papers'?{'marker-end':'url(#network-3d-arrow)'}:{})},this.edgeLayer);this.element('title',{},e).textContent=edge.evidence||'文库共同署名 '+edge.weight+' 次';return e});this.groups=this.nodes.map((node,i)=>{const group=this.element('g',{class:'graph-node','data-node':node.id,tabindex:0,role:'button','aria-label':node.name},this.nodeLayer);const clusterIndex=Number.isInteger(node.cluster)?node.cluster%6:0;const palette=this.mode==='authors'?['#3d7a5a','#4b7a93','#7a6a3f','#6c5b8c','#3f6f6c','#8a5a4f']:['#2a4d85','#3d7a5a','#6c5b8c','#8a5a4f','#3f6f6c','#4b7a93'];const color=palette[clusterIndex];this.element('line',{class:'network-label-guide',stroke:'#dfe3e8','stroke-width':1},group);this.element('circle',{r:12,fill:color,stroke:'#fff','stroke-width':2,'stroke-dasharray':(this.mode==='authors'?!node.verified:!Number.isFinite(node.citations))?'3 2':''},group);const text=this.element('text',{'text-anchor':'middle','font-size':12,fill:'#444c56'},group);this.element('circle',{class:'node-hit',r:18,fill:'transparent','pointer-events':'all'},group);const limit=this.mode==='authors'?22:28;text.textContent=node.name.length>limit?node.name.slice(0,limit-1)+'…':node.name;this.element('title',{},group).textContent=node.name+(this.mode==='authors'?' · 文库 '+node.count+' 篇 · '+(node.verified?'身份已核实':'身份待核实，未按同名合并'):' · 被引用 '+(Number.isFinite(node.citations)?node.citations+' 次':'数据未知')+' · '+(node.citation_source||'来源待获取'));return group});this.markKeyNodes()}
 project(p){const c=Math.cos(this.yaw),s=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch),x=p.x*c+p.z*s,z=-p.x*s+p.z*c,y=p.y*cp-z*sp,depth=p.y*sp+z*cp,camera=this.range*4,perspective=camera/(camera-depth),scale=Math.min(this.width,this.height)*.34/this.range*this.zoom;return{x:this.width/2+this.pan.x+x*scale*perspective,y:this.height/2+this.pan.y+y*scale*perspective,z:depth,depthScale:perspective}}
 draw(){if(!this.svg.isConnected){this.destroy();return}this.width=Math.max(200,this.svg.getBoundingClientRect().width);this.height=this.svg.getBoundingClientRect().height||540;this.svg.setAttribute('viewBox',`0 0 ${this.width} ${this.height}`);this.svg.dataset.zoom=this.zoom.toFixed(4);this.svg.classList.toggle('is-zoomed',this.zoom>=1.5);this.svg.dataset.yaw=this.yaw.toFixed(4);this.svg.dataset.pitch=this.pitch.toFixed(4);const points=this.positions.map(p=>this.project(p)),index=new Map(this.nodes.map((n,i)=>[n.id,i]));this.groups.forEach((group,i)=>{const p=points[i],n=this.nodes[i],radius=this.mode==='authors'?networkAuthorRadius(n.count,this.maxAuthorPapers):networkPaperRadius(n.citations,this.maxCitations);group.setAttribute('transform',`translate(${p.x},${p.y})`);group.dataset.depth=p.z.toFixed(3);group.querySelector('circle').setAttribute('r',radius);group.dataset.citations=Number.isFinite(n.citations)?n.citations:'unknown';group.dataset.paperCount=n.count||0;const hit=group.querySelectorAll('circle')[1];if(hit)hit.setAttribute('r',radius+7);const text=group.querySelector('text');text.setAttribute('y',radius+17);text.setAttribute('font-size','12');const depthMix=Math.max(0,Math.min(1,(p.depthScale-.8)/.5));group.style.opacity=String(.55+.45*depthMix);group.style.filter=depthMix<.35?`saturate(${.5+.5*depthMix})`:'none'});this.lines.forEach((line,i)=>{const e=this.edges[i],a=points[index.get(e.src)],b=points[index.get(e.dst)],distance=Math.max(1,Math.hypot(b.x-a.x,b.y-a.y)),radius=Number(this.groups[index.get(e.dst)].querySelector('circle').getAttribute('r'))+3;for(const[k,v]of Object.entries({x1:a.x,y1:a.y,x2:b.x-(b.x-a.x)/distance*radius,y2:b.y-(b.y-a.y)/distance*radius})){line.setAttribute(k,v)}});this.applySelection();this.placeLabels(points);points.map((p,i)=>({p,i})).sort((a,b)=>a.p.z-b.p.z).forEach(({i})=>this.nodeLayer.append(this.groups[i]))}

 // Choose nearby screen-space label positions after projection to avoid unreadable overlaps.
 placeLabels(points){
  const occupied=[],padding=7;
  this.labelWidths ||= this.groups.map(g=>Math.max(20,g.querySelector('text').getComputedTextLength()));
  const overlaps=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
  const circles=points.map((p,i)=>{const r=Number(this.groups[i].querySelector('circle').getAttribute('r'));return{x:p.x-r,y:p.y-r,w:2*r,h:2*r}});
  const order=points.map((p,i)=>({p,i})).sort((a,b)=>(this.nodes[b.i].count||0)-(this.nodes[a.i].count||0)||b.p.z-a.p.z);
  for(const{p,i}of order){
   const group=this.groups[i],text=group.querySelector('text'),radius=circles[i].w/2,width=this.labelWidths[i],height=16;
   let best=null;
   for(let ring=0;ring<7;ring++){
    const gap=ring*18;
    for(const[x,y]of [[0,radius+17+gap],[radius+width/2+padding+gap,4],[-radius-width/2-padding-gap,4],[0,-radius-8-gap]]){
     const rect={x:p.x+x-width/2-3,y:p.y+y-13,w:width+6,h:height};
     const collisions=occupied.filter(b=>overlaps(rect,b)).length+circles.filter(b=>overlaps(rect,b)).length;
     const outside=rect.x<5||rect.y<5||rect.x+rect.w>this.width-5||rect.y+rect.h>this.height-5;
     const score=collisions*10000+(outside?100000:0)+Math.hypot(x,y);
     if(!best||score<best.score)best={x,y,rect,score};
    }
   }
   text.setAttribute('x',best.x);text.setAttribute('y',best.y);occupied.push(best.rect);
   const guide=group.querySelector('.network-label-guide');guide.setAttribute('x1',0);guide.setAttribute('y1',0);guide.setAttribute('x2',best.x);guide.setAttribute('y2',best.y-5);
   guide.style.display=Math.hypot(best.x,best.y)>radius+30?'':'none';
  }
 }
 markKeyNodes(){
  // 节点多时（尤其作者关系），只常驻显示最重要的标签，其余悬停或选中时出现。
  const dense=this.nodes.length>Math.max(14,this.mode==='authors'?14:22);
  this.svg.classList.toggle('is-dense',dense);
  if(!dense)return;
  const metric=n=>this.mode==='authors'?(Number(n.count)||0):(Number.isFinite(n.citations)?n.citations:0);
  const keep=this.mode==='authors'?Math.min(16,Math.ceil(this.nodes.length*.35)):Math.min(22,Math.ceil(this.nodes.length*.5));
  [...this.nodes.keys()].sort((a,b)=>metric(this.nodes[b])-metric(this.nodes[a])).slice(0,keep)
   .forEach(i=>this.groups[i].classList.add('is-key'));
 }
 select(id){this.selectedId=id;this.applySelection()}
 filterCluster(index){this.clusterFilter=index;this.applySelection()}
 applySelection(){
  const id=this.selectedId,neighbors=new Set([id]);
  if(id)for(const e of this.edges){if(e.src===id)neighbors.add(e.dst);if(e.dst===id)neighbors.add(e.src)}
  const cluster=this.clusterFilter;
  this.groups.forEach((g,i)=>{const n=this.nodes[i],active=n.id===id;
   g.classList.toggle('is-selected',active);
   const hiddenByCluster=cluster!=null&&Number(n.cluster)!==cluster;
   g.style.opacity=hiddenByCluster?'.07':(id&&!neighbors.has(n.id)?'.16':'1');
   if(!hiddenByCluster&&!id){const depthMix=Math.max(0,Math.min(1,(Number(g.dataset.depth||0)+this.range)/(this.range*2)));g.style.opacity=String(.55+.45*depthMix)}
   g.querySelector('circle').setAttribute('stroke',active?'#1e3a66':(this.mode==='authors'?!n.verified:!Number.isFinite(n.citations))?'#6c7c73':'#fff');
   g.querySelector('circle').setAttribute('stroke-width',active?4:2);g.setAttribute('aria-pressed',String(active));
  });
  this.lines.forEach((line,i)=>{const e=this.edges[i],active=id&&(e.src===id||e.dst===id);
   line.style.opacity=id?(active?'.95':'.06'):(this.mode==='authors'?'.34':'.3');
   line.setAttribute('stroke',active?'#1e3a66':'#c9d1dc');
  });
 }

 animate(){if(this.frame)return;const step=()=>{this.frame=0;this.zoom+=(this.targetZoom-this.zoom)*.25;if(Math.abs(this.targetZoom-this.zoom)<.0002)this.zoom=this.targetZoom;this.draw();if(this.zoom!==this.targetZoom&&this.svg.isConnected)this.frame=requestAnimationFrame(step)};this.frame=requestAnimationFrame(step)}
 zoomBy(factor){this.targetZoom=Math.max(.45,Math.min(3,this.targetZoom*factor));this.animate()}
 reset(){this.yaw=.28;this.pitch=-.18;this.pan={x:0,y:0};this.targetZoom=1;this.animate();this.draw()}
 bind(){this.svg.oncontextmenu=e=>e.preventDefault();this.svg.onwheel=e=>{e.preventDefault();const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?this.height:1);this.zoomBy(Math.exp(Math.max(-.22,Math.min(.22,-delta*.0018))))};this.svg.onpointerdown=e=>{if(e.button!==0&&e.button!==2)return;this.drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,pan:e.shiftKey||e.button===2};this.suppressClick=false};this.svg.onpointermove=e=>{if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(Math.hypot(e.clientX-this.drag.startX,e.clientY-this.drag.startY)>5){this.suppressClick=true;this.svg.setPointerCapture(e.pointerId)}this.drag.x=e.clientX;this.drag.y=e.clientY;if(this.drag.pan){this.pan.x+=dx;this.pan.y+=dy}else{this.yaw+=dx*.005;this.pitch=Math.max(-1.4,Math.min(1.4,this.pitch+dy*.005))}this.draw()};this.svg.onpointerup=e=>{this.drag=null;if(this.svg.hasPointerCapture(e.pointerId))this.svg.releasePointerCapture(e.pointerId)};this.svg.onpointercancel=()=>{this.drag=null;this.suppressClick=true};this.svg.onclick=e=>{if(this.suppressClick){this.suppressClick=false;return}const node=e.target.closest('[data-node]'),edge=e.target.closest('[data-edge]');if(node)this.onNode(node.dataset.node);else if(edge)this.onEdge(this.edges[Number(edge.dataset.edge)])};this.svg.onkeydown=e=>{if(['Enter',' '].includes(e.key)&&e.target.closest('[data-node]')){e.preventDefault();this.onNode(e.target.closest('[data-node]').dataset.node)}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();if(e.key==='ArrowLeft')this.yaw-=.1;if(e.key==='ArrowRight')this.yaw+=.1;if(e.key==='ArrowUp')this.pitch-=.1;if(e.key==='ArrowDown')this.pitch+=.1;this.draw()}else if(e.key==='+')this.zoomBy(1.3);else if(e.key==='-')this.zoomBy(1/1.3)}}
 destroy(){if(this.frame)cancelAnimationFrame(this.frame);this.resizeObserver?.disconnect()}
}
window.PaperNetwork3D=PaperNetwork3D;

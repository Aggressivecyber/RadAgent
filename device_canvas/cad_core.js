/* Core CAD helpers shared by the canvas UI. Keep this file DOM-free. */
const MAT_COLORS={silicon:"#4a90a4",si:"#4a90a4",sio2:"#6fbfbf","silicon dioxide":"#6fbfbf",oxide:"#6fbfbf",si3n4:"#7aa874","silicon nitride":"#7aa874",nitride:"#7aa874",polysilicon:"#6a6a78",poly:"#6a6a78",aluminum:"#c0c4cc",al:"#c0c4cc",copper:"#b87333",cu:"#b87333",tungsten:"#8a8f99",w:"#8a8f99",titanium:"#b0b6c0",ti:"#b0b6c0",gold:"#e3c163",au:"#e3c163",air:"transparent",vacuum:"transparent",water:"#3a6f8f",epoxy:"#5a4a3a",kapton:"#caa84a",sapphire:"#5a7fb0",germanium:"#6a7a8a",ge:"#6a7a8a",gaas:"#8a6a9a"};
const MAT_DEFAULTS=["Silicon","SiO2","Si3N4","Polysilicon","Aluminum","Copper","Tungsten","Titanium","Gold","Air","Sapphire","Germanium","GaAs","Epoxy","Kapton","Water"];
const OUTLINE="#2563eb";
const ACCENT="#1d4ed8";
const AXIS_IDX={x:0,y:1,z:2};
const DIM_KEY={x:"dx",y:"dy",z:"dz"};

function matColor(id){const k=(id||"").toLowerCase().replace(/_/g," ");if(MAT_COLORS[k])return MAT_COLORS[k];for(const key in MAT_COLORS)if(k.includes(key))return MAT_COLORS[key];let h=0;for(const c of id||"?")h=(h*31+c.charCodeAt(0))>>>0;return `hsl(${h%360} 45% 55%)`;}
const isWorld=c=>c.component_type==="world";
function cadStrokeWidth(pxW,pxH,{selected=false,world=false,overlap=false}={}){
  if(world)return 0.6;
  const minPx=Math.max(0,Math.min(Math.abs(pxW||0),Math.abs(pxH||0)));
  if(minPx<2)return 0;
  if(minPx<6)return Math.min(overlap?0.7:(selected?0.8:0.55),minPx*0.22);
  if(overlap)return 0.8;
  return selected?0.9:0.65;
}
function cadFillOpacity(pxW,pxH,{world=false}={}){
  if(world)return 0.35;
  const minPx=Math.max(0,Math.min(Math.abs(pxW||0),Math.abs(pxH||0)));
  if(minPx>0&&minPx<2)return Math.max(0.06,Math.min(0.2,0.06+minPx*0.07));
  if(minPx<6)return Math.min(0.58,0.24+minPx*0.06);
  return 0.78;
}
function cadHitWidth(pxW,pxH){
  const minPx=Math.max(0,Math.min(Math.abs(pxW||0),Math.abs(pxH||0)));
  if(minPx>0&&minPx<2)return 6;
  return 8;
}
function fmt(v){const a=Math.abs(v);if(a>=1000)return(v/1000).toFixed(1)+"k";if(a>=10)return v.toFixed(0);if(a>=1)return v.toFixed(1);return v.toFixed(2);}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));}
function bbox3D(c){
  const p=c.placement.position;
  let min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  if(c.polygon&&c.polygon.length){
    for(const pt of c.polygon){
      for(let i=0;i<3;i++){min[i]=Math.min(min[i],pt[i]);max[i]=Math.max(max[i],pt[i]);}
    }
    for(let i=0;i<3;i++){
      if(!isFinite(min[i])||!isFinite(max[i])||min[i]===max[i]){
        const half=((c.dimensions&&[c.dimensions.dx,c.dimensions.dy,c.dimensions.dz][i])||0)/2;
        min[i]=p[i]-half;max[i]=p[i]+half;
      }
    }
  }else{
    const d=[c.dimensions.dx||0,c.dimensions.dy||0,c.dimensions.dz||0];
    for(let i=0;i<3;i++){min[i]=p[i]-d[i]/2;max[i]=p[i]+d[i]/2;}
  }
  return {min,max};
}
function aabbOverlap3D(a,b){
  const eps=1e-9;
  return a.min[0]<b.max[0]-eps&&a.max[0]>b.min[0]+eps&&
         a.min[1]<b.max[1]-eps&&a.max[1]>b.min[1]+eps&&
         a.min[2]<b.max[2]-eps&&a.max[2]>b.min[2]+eps;
}
function aabbContains(outer,inner){
  const eps=1e-9;
  return inner.min[0]>=outer.min[0]-eps&&inner.max[0]<=outer.max[0]+eps&&
         inner.min[1]>=outer.min[1]-eps&&inner.max[1]<=outer.max[1]+eps&&
         inner.min[2]>=outer.min[2]-eps&&inner.max[2]<=outer.max[2]+eps;
}
function boxesOverlapOnAxes(a,b,axesIdx){
  const eps=1e-9;
  return axesIdx.every(i=>a.min[i]<b.max[i]-eps&&a.max[i]>b.min[i]+eps);
}
function sameMotherScope(a,b){
  return !(a.mother_volume&&b.mother_volume&&a.mother_volume!==b.mother_volume);
}
function detectOverlaps3D(components,{includeWorld=false,stats=null}={}){
  const comps=(components||[]).filter(c=>includeWorld||!isWorld(c));
  const pairs=[],ids=new Set();
  const boxes=new Map(comps.map(c=>[c.component_id,bbox3D(c)]));
  const order=new Map(comps.map((c,i)=>[c.component_id,i]));
  if(stats){
    stats.components=comps.length;
    stats.brutePairs=comps.length*(comps.length-1)/2;
    stats.candidates=0;
    stats.sweepAxis="x";
  }
  const entries=comps
    .map(c=>({component:c,box:boxes.get(c.component_id)}))
    .sort((a,b)=>(a.box.min[0]-b.box.min[0])||(a.box.max[0]-b.box.max[0])||String(a.component.component_id).localeCompare(String(b.component.component_id)));
  const active=[];
  const eps=1e-9;
  for(const entry of entries){
    for(let i=active.length-1;i>=0;i--){
      if(active[i].box.max[0]<=entry.box.min[0]+eps)active.splice(i,1);
    }
    for(const candidate of active){
      const a=candidate.component,b=entry.component;
      if(!sameMotherScope(a,b))continue;
      if(stats)stats.candidates++;
      if(!boxesOverlapOnAxes(candidate.box,entry.box,[1,2]))continue;
      if(aabbOverlap3D(candidate.box,entry.box)){
        const ai=order.get(a.component_id),bi=order.get(b.component_id);
        const first=ai<bi?a:b,second=ai<bi?b:a;
        pairs.push([first,second]);
        ids.add(a.component_id);ids.add(b.component_id);
      }
    }
    active.push(entry);
  }
  pairs.sort((a,b)=>(order.get(a[0].component_id)-order.get(b[0].component_id))||(order.get(a[1].component_id)-order.get(b[1].component_id)));
  return {pairs,ids};
}
function detectSmallGaps3DCore(components,axis,minGap){
  const threshold=Math.max(0,Number(minGap)||0);
  if(threshold<=0)return [];
  const idx=AXIS_IDX[axis],other=[0,1,2].filter(i=>i!==idx);
  const comps=(components||[]).filter(c=>!isWorld(c));
  const boxes=new Map(comps.map(c=>[c.component_id,bbox3D(c)]));
  const gaps=[];
  for(let i=0;i<comps.length;i++)for(let j=i+1;j<comps.length;j++){
    const a=comps[i],b=comps[j];
    if(!sameMotherScope(a,b))continue;
    const ab=boxes.get(a.component_id),bb=boxes.get(b.component_id);
    if(!boxesOverlapOnAxes(ab,bb,other))continue;
    const gap=bb.min[idx]>=ab.max[idx]?bb.min[idx]-ab.max[idx]:ab.min[idx]>=bb.max[idx]?ab.min[idx]-bb.max[idx]:-1;
    if(gap>1e-9&&gap<threshold-1e-9)gaps.push({a,b,gap,axis});
  }
  return gaps;
}
function stackIntervals3D(components,axis,{includeWorld=false}={}){
  const idx=AXIS_IDX[axis];
  return (components||[])
    .filter(c=>includeWorld||!isWorld(c))
    .map(c=>{
      const box=bbox3D(c);
      return {
        component:c,
        box,
        axis,
        min:box.min[idx],
        max:box.max[idx],
        center:(box.min[idx]+box.max[idx])/2,
        thickness:box.max[idx]-box.min[idx],
      };
    })
    .sort((a,b)=>(a.min-b.min)||(a.max-b.max)||a.component.component_id.localeCompare(b.component.component_id));
}
function classifyStackRelation3D(prev,next,axis,{minGap=0,format=fmt}={}){
  const idx=AXIS_IDX[axis],other=[0,1,2].filter(i=>i!==idx);
  const overlapsOtherAxes=boxesOverlapOnAxes(prev.box,next.box,other);
  const rawGap=next.min-prev.max;
  const gap=Math.max(0,rawGap);
  let kind,label,severity;
  if(!overlapsOtherAxes){
    kind="off_axis";label="横向不相交";severity="muted";
  }else if(rawGap<-1e-9){
    kind="overlap";label=`重叠 ${format(-rawGap)} μm`;severity="err";
  }else if(Math.abs(rawGap)<=1e-4){
    kind="touching";label="接触";severity="ok";
  }else{
    const threshold=Math.max(0,Number(minGap)||0);
    kind=threshold>0&&rawGap<threshold-1e-9?"small_gap":"gap";
    label=kind==="small_gap"?`小间隙 ${format(rawGap)} μm < ${format(threshold)} μm`:`间隙 ${format(rawGap)} μm`;
    severity=kind==="small_gap"?"warn":"ok";
  }
  return {a:prev,b:next,axis,gap,rawGap,overlapsOtherAxes,kind,label,severity};
}
function stackRelations3D(rowsOrComponents,axis,options={}){
  const rows=rowsOrComponents&&rowsOrComponents[0]&&rowsOrComponents[0].component&&rowsOrComponents[0].box
    ? rowsOrComponents
    : stackIntervals3D(rowsOrComponents,axis,options);
  const rels=[];
  const other=[0,1,2].filter(i=>i!==AXIS_IDX[axis]);
  for(let i=1;i<rows.length;i++){
    let prev=rows[i-1];
    for(let j=i-1;j>=0;j--){
      if(boxesOverlapOnAxes(rows[j].box,rows[i].box,other)){prev=rows[j];break;}
    }
    rels.push(classifyStackRelation3D(prev,rows[i],axis,options));
  }
  return rels;
}
function serializeComp(c){
  const o={...c};
  delete o.hidden;delete o.locked;
  if(c.polygon){
    o.cross_section_polygon=c.polygon.map(p=>[+p[0].toFixed(4),+p[1].toFixed(4),+p[2].toFixed(4)]);
    o.cross_section_polygon_axes=c.polygonAxes;
    o.open_issues=[...(c.open_issues||[]),`截面为多边形(${c.polygon.length}顶点,${c.polygonAxes.lateral}×${c.polygonAxes.depth}),bbox 见 dimensions`];
    delete o.polygon;delete o.polygonAxes;
  }
  return o;
}

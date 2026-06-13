/* ============================================================
 * 半导体器件截面画布 v2 (Konva)
 * 数据层(全 3D ComponentSpec)与视图层(像素)分离。
 * 新增:吸附 / 多选对齐 / 居中 / 多边形节点编辑。
 * ============================================================ */

if (typeof Konva === "undefined") {
  document.body.innerHTML = '<div class="loadfail">⚠ 无法加载 konva.min.js,请确认它与本文件同目录。</div>';
  throw new Error("Konva missing");
}

/* ---------- 状态 ---------- */
let model=null;
let selectedIds=new Set();    // 多选
let primaryId=null;           // 主选(编辑面板显示)
let polyEditId=null;          // 当前多边形编辑中的组件
let selectedPolygonVertexIndex=null;
const axes={lateral:"x",depth:"z"};
let alignRef="bbox";          // bbox | world
let last3DOverlapIds=new Set();
let preview3DVisible=false;
let preview3DAngle=35;
let preview3DView="iso";
let last3DHitRegions=[];
let last3DStrokeSamples=[];
let toolMode="select";
let measureState={start:null,end:null,preview:null};
let dimensionAnnotations=[];
let sliceState={enabled:false,pos:0,thickness:1};
const DRC_RULE_DECKS={
  custom:{label:"Custom",minGap:null},
  detector_default:{label:"Detector default",minGap:2},
  tight_stack:{label:"Tight stack",minGap:0.5},
  loose_assembly:{label:"Loose assembly",minGap:5},
};
let drcSettings={minGap:0,ruleDeck:"custom"};
let stackAxisMode="auto";
let transformSettings={constrainWorld:true,boundaryMode:"block"};
let snapSettings={enabled:true,grid:true,components:true,canvas:true,gridStep:100,gridOriginLat:0,gridOriginDep:0,thresholdPx:7};
let componentClipboard={items:[],axes:null,sourceIds:[]};
let isolationState={active:false,snapshot:null};
let selectionSets=[];
let viewStates=[];
let layerGroupMode="material";
let componentListFilterState={status:"all"};
let drcWaivers=[];
let issueBrowserState={filter:"all",cursor:0};
let cadStatusCursor=null;
const ISSUE_FILTERS=new Set(["all","err","warn","fixable","waived"]);
const FIXABLE_ISSUE_CODES=new Set(["outside_world","overlap3d","small_gap3d"]);
const ULTRATHIN_STROKE_SUPPRESS_PX=1;
const MARQUEE_DRAG_THRESHOLD_PX=4;
const POLY_NODE_RADIUS_PX=2.6;
const POLY_NODE_HIT_PX=14;
function buildDeviceCanvasState(){
  const layers={};
  if(model){
    for(const c of model.components){
      const s={};
      if(c.hidden)s.hidden=true;
      if(c.locked)s.locked=true;
      if(Object.keys(s).length)layers[c.component_id]=s;
    }
  }
  return {
    version:1,
    axes:{lateral:axes.lateral,depth:axes.depth},
    slice:JSON.parse(JSON.stringify(sliceState)),
    drc:JSON.parse(JSON.stringify(drcSettings)),
    stack:{axisMode:stackAxisMode},
    transform:JSON.parse(JSON.stringify(transformSettings)),
    snap:JSON.parse(JSON.stringify(snapSettings)),
    layers,
    selectionSets:serializeSelectionSets(),
    viewStates:serializeViewStates(),
    annotations:JSON.parse(JSON.stringify(dimensionAnnotations)),
    drcWaivers:serializeDrcWaivers(),
  };
}
function applyDeviceCanvasState(state){
  if(!state||typeof state!=="object")return;
  if(state.axes&&state.axes.lateral&&state.axes.depth&&state.axes.lateral!==state.axes.depth){
    axes.lateral=state.axes.lateral;axes.depth=state.axes.depth;
  }
  if(state.slice){
    sliceState={
      enabled:!!state.slice.enabled,
      pos:Number(state.slice.pos)||0,
      thickness:Math.max(0,Number(state.slice.thickness)||0),
    };
  }
  if(state.drc){
    drcSettings.minGap=Math.max(0,Number(state.drc.minGap)||0);
    drcSettings.ruleDeck=DRC_RULE_DECKS[state.drc.ruleDeck]?state.drc.ruleDeck:"custom";
    issueBrowserState={filter:"all",cursor:0};
  }
  if(state.stack&&["auto","x","y","z"].includes(state.stack.axisMode)){
    stackAxisMode=state.stack.axisMode;
  }
  if(state.transform&&typeof state.transform==="object"){
    transformSettings.constrainWorld=state.transform.constrainWorld!==false;
    transformSettings.boundaryMode=state.transform.boundaryMode==="clamp"?"clamp":"block";
  }
  if(state.snap&&typeof state.snap==="object"){
    snapSettings.enabled=state.snap.enabled!==false;
    snapSettings.grid=state.snap.grid!==false;
    snapSettings.components=state.snap.components!==false;
    snapSettings.canvas=state.snap.canvas!==false;
    snapSettings.gridStep=Math.max(0,Number(state.snap.gridStep)||0);
    snapSettings.gridOriginLat=Number.isFinite(Number(state.snap.gridOriginLat))?Number(state.snap.gridOriginLat):0;
    snapSettings.gridOriginDep=Number.isFinite(Number(state.snap.gridOriginDep))?Number(state.snap.gridOriginDep):0;
    snapSettings.thresholdPx=Math.max(0,Number(state.snap.thresholdPx)||0);
  }
  if(state.layers&&model){
    for(const c of model.components){
      const layer=state.layers[c.component_id];
      if(layer){c.hidden=!!layer.hidden;c.locked=!!layer.locked;}
    }
  }
  if(Array.isArray(state.selectionSets))selectionSets=normalizeSelectionSets(state.selectionSets);
  if(Array.isArray(state.viewStates))viewStates=normalizeViewStates(state.viewStates);
  if(Array.isArray(state.annotations))dimensionAnnotations=JSON.parse(JSON.stringify(state.annotations));
  if(Array.isArray(state.drcWaivers))drcWaivers=normalizeDrcWaivers(state.drcWaivers);
}

/* ---------- 撤销 / 重做 ---------- */
const history={stack:[],ptr:-1,max:100};
function snapshot(){return model?JSON.parse(JSON.stringify({components:model.components,dimensionAnnotations,drcWaivers})):null;}
function pushHistory(){
  if(!model)return;
  history.stack=history.stack.slice(0,history.ptr+1);
  history.stack.push(snapshot());
  if(history.stack.length>history.max){history.stack.shift();}
  else{history.ptr++;}
  updateUndoRedoUI();
}
function restore(snap){
  if(!snap)return;
  model.components=JSON.parse(JSON.stringify(snap.components));
  dimensionAnnotations=JSON.parse(JSON.stringify(snap.dimensionAnnotations||[]));
  drcWaivers=normalizeDrcWaivers(snap.drcWaivers||[]);
  pruneSelectionSets();
  selectedIds.clear();primaryId=null;polyEditId=null;cadStatusCursor=null;
  isolationState={active:false,snapshot:null};
  updateSliceUI();updateDrcUI();updateStackUI();updateTransformConstraintUI();updateSnapUI();resetView();refreshSelectionViews();renderAnnotationsPanel();renderSelectionSets();renderAssemblyTree();updateModelHealth();draw3DPreview();
}
function undo(){if(history.ptr<=0){toast("没有可撤销");return;}history.ptr--;restore(history.stack[history.ptr]);updateUndoRedoUI();toast("撤销");}
function redo(){if(history.ptr>=history.stack.length-1){toast("没有可重做");return;}history.ptr++;restore(history.stack[history.ptr]);updateUndoRedoUI();toast("重做");}
function updateUndoRedoUI(){const u=document.getElementById("btnUndo"),r=document.getElementById("btnRedo");if(u)u.disabled=history.ptr<=0;if(r)r.disabled=history.ptr>=history.stack.length-1;}
let editDebounce=null;
function recordEdit(){clearTimeout(editDebounce);editDebounce=setTimeout(pushHistory,400);}

/* camera: layer 本地像素 ↔ 数据 μm */
const camera={minLat:0,maxLat:0,minDep:0,maxDep:0,sLat:1,sDep:1,ox:0,oy:0};
function dataBounds(){
  let mL=Infinity,ML=-Infinity,mD=Infinity,MD=-Infinity;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  for(const c of model.components){
    if(!visibleInCurrentSection(c))continue;
    const dLat=c.dimensions[DIM_KEY[axes.lateral]]||0,dDep=c.dimensions[DIM_KEY[axes.depth]]||0;
    const pLat=c.placement.position[li],pDep=c.placement.position[di];
    // 多边形:用 polygon 的 bbox
    if(c.polygon&&polygonAxesMatch(c)){const b=polyBBox(c);mL=Math.min(mL,b.minLat);ML=Math.max(ML,b.maxLat);mD=Math.min(mD,b.minDep);MD=Math.max(MD,b.maxDep);continue;}
    mL=Math.min(mL,pLat-dLat/2);ML=Math.max(ML,pLat+dLat/2);mD=Math.min(mD,pDep-dDep/2);MD=Math.max(MD,pDep+dDep/2);
  }
  if(!isFinite(mL)){mL=-10;ML=10;mD=-10;MD=10;}
  return {minLat:mL,maxLat:ML,minDep:mD,maxDep:MD};
}
function fitCamera(){
  if(!model||!model.components.length){Object.assign(camera,{minLat:-10,maxLat:10,minDep:-10,maxDep:10,sLat:1,sDep:1,ox:0,oy:0});return;}
  const {minLat,maxLat,minDep,maxDep}=dataBounds();
  const W=stage.width(),H=stage.height();
  const padL=(maxLat-minLat)*0.08+1e-6,padD=(maxDep-minDep)*0.12+1e-6;
  const mL=minLat-padL,ML=maxLat+padL,mD=minDep-padD,MD=maxDep+padD;
  Object.assign(camera,{minLat:mL,maxLat:ML,minDep:mD,maxDep:MD});
  const equal=document.getElementById("equalScale").checked;
  if(equal){const s=Math.min(W/(ML-mL),H/(MD-mD));camera.sLat=s;camera.sDep=s;}
  else{camera.sLat=W/(ML-mL);camera.sDep=H/(MD-mD);}
  camera.ox=(W-(ML-mL)*camera.sLat)/2;camera.oy=(H-(MD-mD)*camera.sDep)/2;
}
const X=lat=>camera.ox+(lat-camera.minLat)*camera.sLat;
const Y=dep=>camera.oy+(camera.maxDep-dep)*camera.sDep;
const toDataX=px=>(px-camera.ox)/camera.sLat+camera.minLat;
const toDataY=py=>camera.maxDep-(py-camera.oy)/camera.sDep;
function syncSnapSettingsFromUI(){
  const enabled=document.getElementById("snapOn");
  const grid=document.getElementById("snapGrid");
  const components=document.getElementById("snapComponents");
  const canvas=document.getElementById("snapCanvas");
  const gridStepEl=document.getElementById("gridStep");
  const originLat=document.getElementById("gridOriginLat");
  const originDep=document.getElementById("gridOriginDep");
  const threshold=document.getElementById("snapPx");
  if(enabled)snapSettings.enabled=!!enabled.checked;
  if(grid)snapSettings.grid=!!grid.checked;
  if(components)snapSettings.components=!!components.checked;
  if(canvas)snapSettings.canvas=!!canvas.checked;
  if(gridStepEl)snapSettings.gridStep=Math.max(0,Number(gridStepEl.value)||0);
  if(originLat)snapSettings.gridOriginLat=Number.isFinite(Number(originLat.value))?Number(originLat.value):0;
  if(originDep)snapSettings.gridOriginDep=Number.isFinite(Number(originDep.value))?Number(originDep.value):0;
  if(threshold)snapSettings.thresholdPx=Math.max(0,Number(threshold.value)||0);
  return snapSettings;
}
function updateSnapUI(){
  const enabled=document.getElementById("snapOn");
  const grid=document.getElementById("snapGrid");
  const components=document.getElementById("snapComponents");
  const canvas=document.getElementById("snapCanvas");
  const gridStepEl=document.getElementById("gridStep");
  const originLat=document.getElementById("gridOriginLat");
  const originDep=document.getElementById("gridOriginDep");
  const threshold=document.getElementById("snapPx");
  if(enabled)enabled.checked=!!snapSettings.enabled;
  if(grid)grid.checked=!!snapSettings.grid;
  if(components)components.checked=!!snapSettings.components;
  if(canvas)canvas.checked=!!snapSettings.canvas;
  if(gridStepEl&&document.activeElement!==gridStepEl)gridStepEl.value=snapSettings.gridStep;
  if(originLat&&document.activeElement!==originLat)originLat.value=snapSettings.gridOriginLat;
  if(originDep&&document.activeElement!==originDep)originDep.value=snapSettings.gridOriginDep;
  if(threshold&&document.activeElement!==threshold)threshold.value=snapSettings.thresholdPx;
}
function onSnapSettingsChange(){
  syncSnapSettingsFromUI();
  if(model){drawBackground();drawComponents();}
  updateCadStatus();
}
function snapPx(){return Math.max(0,Number(snapSettings.thresholdPx)||0);}
function gridStep(){return Math.max(0,Number(snapSettings.gridStep)||0);}
function gridOriginLat(){return Number.isFinite(Number(snapSettings.gridOriginLat))?Number(snapSettings.gridOriginLat):0;}
function gridOriginDep(){return Number.isFinite(Number(snapSettings.gridOriginDep))?Number(snapSettings.gridOriginDep):0;}
function nearestGridValue(value,origin,step){
  return origin+Math.round((value-origin)/step)*step;
}
function onGridSettingsChange(){onSnapSettingsChange();}
function sliceAxis(){return ["x","y","z"].find(a=>a!==axes.lateral&&a!==axes.depth)||"y";}
function updateCadStatus(cursor,opts={}){
  const hud=document.getElementById("hudCoord");if(!hud)return;
  if(opts.clearCursor)cadStatusCursor=null;
  else if(cursor)cadStatusCursor={lat:Number(cursor.lat),dep:Number(cursor.dep)};
  const coord=cadStatusCursor&&Number.isFinite(cadStatusCursor.lat)&&Number.isFinite(cadStatusCursor.dep)
    ?`${axes.lateral} ${fmt(cadStatusCursor.lat)}, ${axes.depth} ${fmt(cadStatusCursor.dep)}`
    :"--";
  const snap=snapSettings.enabled?"on":"off";
  const slice=sliceState.enabled?` | slice ${sliceAxis()} ${fmt(sliceState.pos)}±${fmt(Math.max(0,Number(sliceState.thickness)||0)/2)}`:"";
  hud.textContent=`cursor: ${coord} μm | axis ${axes.lateral}/${axes.depth} | third ${sliceAxis()} | snap ${snap} | grid ${fmt(gridStep())} | sel ${selectedIds.size}${slice}`;
}
function sliceBounds(){
  const pos=Number(sliceState.pos)||0;
  const half=Math.max(0,Number(sliceState.thickness)||0)/2;
  return {axis:sliceAxis(),idx:AXIS_IDX[sliceAxis()],min:pos-half,max:pos+half,pos,thickness:half*2};
}
function visibleInCurrentSection(c){
  if(c.hidden)return false;
  if(!sliceState.enabled||isWorld(c))return true;
  const s=sliceBounds();
  const b=bbox3D(c);
  const eps=1e-9;
  return b.min[s.idx]<=s.max+eps&&b.max[s.idx]>=s.min-eps;
}
function sectionComponents(includeWorld=true){
  if(!model)return [];
  return model.components.filter(c=>(includeWorld||!isWorld(c))&&visibleInCurrentSection(c));
}
function hasAnyThinProjection(){
  return thinProjectionMinPx()!==null;
}
function cadLineProps(strokeWidth,extra={}){
  return {strokeWidth,strokeScaleEnabled:false,listening:false,...extra};
}
function gridLineProps(){
  const thin=thinProjectionMinPx();
  return cadLineProps(thin===null?0.75:sectionHairlineCap(0.35),{stroke:"#e0e6ef",opacity:thin===null?1:0.3});
}

/* ---------- Konva 舞台 ---------- */
const stageW=()=>document.getElementById("stageWrap").clientWidth;
const stageH=()=>document.getElementById("stageWrap").clientHeight;
const stage=new Konva.Stage({container:"konva-container",width:stageW(),height:stageH()});
const bgLayer=new Konva.Layer();stage.add(bgLayer);
const compLayer=new Konva.Layer();stage.add(compLayer);
const uiLayer=new Konva.Layer();stage.add(uiLayer);   // 参考线 / 顶点
const tr=new Konva.Transformer({rotateEnabled:false,keepRatio:false,borderStroke:"#2563eb",anchorStroke:"#2563eb",anchorFill:"#2563eb",anchorSize:9,ignoreStroke:true});
uiLayer.add(tr);
const snapGroup=new Konva.Group();uiLayer.add(snapGroup);
const overlapGroup=new Konva.Group();uiLayer.add(overlapGroup);
const thinSelectionGroup=new Konva.Group();uiLayer.add(thinSelectionGroup);
const measureGroup=new Konva.Group();uiLayer.add(measureGroup);
const annotationGroup=new Konva.Group();uiLayer.add(annotationGroup);
const marqueeGroup=new Konva.Group();uiLayer.add(marqueeGroup);

/* ---------- 背景 ---------- */
let bgGroup=new Konva.Group();bgLayer.add(bgGroup);
function niceStep(raw){const p=Math.pow(10,Math.floor(Math.log10(raw)));const n=raw/p;return(n<1.5?1:n<3?2:n<7?5:10)*p;}
function drawBackground(){
  bgGroup.destroyChildren();const W=stage.width(),H=stage.height();
  bgGroup.add(new Konva.Rect({x:0,y:0,width:W,height:H,fill:"#f7f9fc",listening:false}));
  const lineProps=gridLineProps();
  const viewSpanLat=(camera.maxLat-camera.minLat)/(stage.scaleX()||1);
  const configuredStep=gridStep();
  const step=configuredStep>0?configuredStep:niceStep(viewSpanLat/10);
  const latOrigin=configuredStep>0?gridOriginLat():0;
  for(let v=latOrigin+Math.ceil((camera.minLat-latOrigin)/step)*step;v<=camera.maxLat;v+=step){const px=X(v);bgGroup.add(new Konva.Line({points:[px,0,px,H],...lineProps}));bgGroup.add(new Konva.Text({x:px+4,y:H-16,text:fmt(v),fontSize:9,fill:"#667085",listening:false}));}
  const viewSpanDep=(camera.maxDep-camera.minDep)/(stage.scaleY()||1);
  const stepD=configuredStep>0?configuredStep:niceStep(viewSpanDep/8);
  const depOrigin=configuredStep>0?gridOriginDep():0;
  for(let v=depOrigin+Math.ceil((camera.minDep-depOrigin)/stepD)*stepD;v<=camera.maxDep;v+=stepD){const py=Y(v);bgGroup.add(new Konva.Line({points:[0,py,W,py],...lineProps}));bgGroup.add(new Konva.Text({x:6,y:py-13,text:fmt(v),fontSize:9,fill:"#667085",listening:false}));}
  bgLayer.batchDraw();
}

/* ---------- 多边形辅助 ---------- */
function polygonAxesMatch(c){return c.polygonAxes&&c.polygonAxes.lateral===axes.lateral&&c.polygonAxes.depth===axes.depth;}
function polyBBox(c){
  let mL=Infinity,ML=-Infinity,mD=Infinity,MD=-Infinity;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  for(const p of c.polygon){mL=Math.min(mL,p[li]);ML=Math.max(ML,p[li]);mD=Math.min(mD,p[di]);MD=Math.max(MD,p[di]);}
  return {minLat:mL,maxLat:ML,minDep:mD,maxDep:MD};
}

/* ---------- 渲染 ---------- */
const rectNodes=new Map();   // id -> {shape, kind:'rect'|'poly', label, matLabel, depLabel}
function relayout(){if(!model)return;fitCamera();drawBackground();drawComponents();}
function drawComponents(){
  for(const [,n] of rectNodes){n.shape.destroy();["label","matLabel","depLabel"].forEach(k=>n[k]&&n[k].destroy());}
  rectNodes.clear();tr.nodes([]);
  thinSelectionGroup.destroyChildren();
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const ov=typeof polygonClipping!=="undefined"?detectSectionOverlaps():{pairs:[],regions:[],ids:new Set()};
  if(model){last3DOverlapIds=detect3DOverlaps().ids;}
  const ordered=sectionComponents(true).sort((a,b)=>(isWorld(a)?-1:0)-(isWorld(b)?-1:0));
  for(const c of ordered){
    const world=isWorld(c);
    const sel=selectedIds.has(c.component_id);
    const ovlp=ov.ids.has(c.component_id);
    const col=c.color?`rgb(${c.color.map(v=>Math.round(v*255)).join(",")})`:matColor(c.material_id);
    // 当前截面投影重叠只作为提示；真实模型检查用 3D AABB。
    const strokeC=world?"#98a2b3":(ovlp?"#b7791f":(sel?ACCENT:OUTLINE));
    const dash=world?[5,4]:(sel?[6,3]:undefined);  // 仅选中用虚线(流动);其余实线
    let shape;
    const usePoly=c.polygon&&polygonAxesMatch(c);
    if(usePoly){
      const pts=[];
      for(const p of c.polygon)pts.push(X(p[li]),Y(p[di]));
      const bb=shapeBBoxPx(c);
      const sw=sectionStrokeWidth(bb.w,bb.h,{selected:sel,world,overlap:ovlp});
      shape=new Konva.Line({points:pts,closed:true,fill:col,opacity:sectionFillOpacity(bb.w,bb.h,{world}),stroke:strokeC,strokeWidth:sw,strokeScaleEnabled:false,dash:dash,draggable:!world&&!c.locked,name:"comp",hitStrokeWidth:sectionHitWidth(bb.w,bb.h)});
    } else {
      let dLat,dDep;
      if(c.polygon){const b=polyBBox(c);dLat=b.maxLat-b.minLat;dDep=b.maxDep-b.minDep;}
      else{dLat=c.dimensions[DIM_KEY[axes.lateral]]||0;dDep=c.dimensions[DIM_KEY[axes.depth]]||0;}
      let cx,cy;
      if(c.polygon){const b=polyBBox(c);cx=(b.minLat+b.maxLat)/2;cy=(b.minDep+b.maxDep)/2;}
      else{cx=c.placement.position[li];cy=c.placement.position[di];}
      const rawW=dLat*camera.sLat,rawH=dDep*camera.sDep;
      const w=Math.max(rawW,0.01),h=Math.max(rawH,0.01);
      const sw=sectionStrokeWidth(rawW,rawH,{selected:sel,world,overlap:ovlp});
      shape=new Konva.Rect({x:X(cx)-w/2,y:Y(cy)-h/2,width:w,height:h,fill:world?"rgba(0,0,0,0)":col,opacity:sectionFillOpacity(rawW,rawH,{world}),stroke:strokeC,strokeWidth:sw,strokeScaleEnabled:false,dash:dash,draggable:!world&&!c.locked,name:"comp",cornerRadius:0,hitStrokeWidth:sectionHitWidth(rawW,rawH)});
    }
    shape.setAttr("cid",c.component_id);
    compLayer.add(shape);
    // 标签(基于 bbox)
    const bb=shapeBBoxPx(c);
    let label=null,matLabel=null,depLabel=null;
    if(bb.w>36&&bb.h>16&&!world){
      const suffix=c.polygon?` ◇${c.polygon.length}pt`:(c.geometry_type!=="box"?` (${c.geometry_type})`:"");
      label=new Konva.Text({x:bb.x+5,y:bb.y+4,text:c.display_name,fontSize:12,fontStyle:600,fill:"#101828",listening:false});
      matLabel=new Konva.Text({x:bb.x+5,y:bb.y+20,text:c.material_id+suffix,fontSize:10.5,fill:"#344054",listening:false});
      const dk=DIM_KEY[axes.depth];
      const depTxt=c.polygon?`${fmt(bb.h/camera.sDep)}μm`:`${fmt(c.dimensions[dk])}μm`;
      depLabel=new Konva.Text({x:bb.x+bb.w-6,y:bb.y+bb.h/2-6,width:Math.max(bb.w-10,20),align:"right",text:depTxt,fontSize:10,fill:"#475467",listening:false});
      compLayer.add(label);compLayer.add(matLabel);compLayer.add(depLabel);
    }
    rectNodes.set(c.component_id,{shape,kind:usePoly?"poly":"rect",label,matLabel,depLabel});
    drawThinSelectionGuide(c,bb);
    shape.on("click tap",e=>{if(toolMode==="measure")return;e.cancelBubble=true;onShapeClick(c.component_id,e.evt&&(e.evt.shiftKey||e.evt.ctrlKey||e.evt.metaKey));});
    shape.on("dblclick dbltap",e=>{if(toolMode==="measure")return;e.cancelBubble=true;onShapeDblClick(c.component_id,e);});
    shape.on("dragmove",()=>onShapeDrag(c));
    shape.on("dragend",()=>{onShapeDragEnd(c);pushHistory();});
    shape.on("transform",()=>onShapeTransform(c));
    shape.on("transformend",()=>pushHistory());
  }
  refreshTransformer();
  drawPolyAnchors();
  drawOverlapRegions(ov.regions);
  updateOverlapHUD(ov.pairs.length);
  drawAnnotations();
  updateModelHealth();
  draw3DPreview();
  compLayer.batchDraw();uiLayer.batchDraw();
}
function shapeBBoxPx(c){
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  let mL,ML,mD,MD;
  if(c.polygon&&polygonAxesMatch(c)){const b=polyBBox(c);mL=b.minLat;ML=b.maxLat;mD=b.minDep;MD=b.maxDep;}
  else if(c.polygon){const b=polyBBox(c);mL=b.minLat;ML=b.maxLat;mD=b.minDep;MD=b.maxDep;}
  else{const dLat=c.dimensions[DIM_KEY[axes.lateral]]||0,dDep=c.dimensions[DIM_KEY[axes.depth]]||0;mL=c.placement.position[li]-dLat/2;ML=c.placement.position[li]+dLat/2;mD=c.placement.position[di]-dDep/2;MD=c.placement.position[di]+dDep/2;}
  return {x:X(mL),y:Y(MD),w:(ML-mL)*camera.sLat,h:(MD-mD)*camera.sDep};
}
function screenScaleX(){const s=Math.abs(Number(stage.scaleX&&stage.scaleX())||1);return s>0?s:1;}
function screenScaleY(){const s=Math.abs(Number(stage.scaleY&&stage.scaleY())||1);return s>0?s:1;}
function screenProjectionPx(pxW,pxH){
  return {w:Math.abs(pxW||0)*screenScaleX(),h:Math.abs(pxH||0)*screenScaleY()};
}
function screenProjectionMinPx(pxW,pxH){
  const s=screenProjectionPx(pxW,pxH);
  return Math.max(0,Math.min(s.w,s.h));
}
function screenProjectionMaxPx(pxW,pxH){
  const s=screenProjectionPx(pxW,pxH);
  return Math.max(s.w,s.h);
}
function projectionMinPx(c){
  const bb=shapeBBoxPx(c);
  return screenProjectionMinPx(bb.w,bb.h);
}
function thinProjectionMinPx(){
  let min=Infinity;
  for(const c of sectionComponents(false)){
    const px=projectionMinPx(c);
    if(px>0&&px<2)min=Math.min(min,px);
  }
  return isFinite(min)?min:null;
}
function hasThinProjection(c){
  return projectionMinPx(c)<2;
}
function sectionHairlineCap(base,factor=0.7){
  const thin=thinProjectionMinPx();
  if(thin===null||base<=0)return base;
  if(thin<ULTRATHIN_STROKE_SUPPRESS_PX)return 0;
  return Math.min(base,thin*factor);
}
function sectionStrokeWidth(pxW,pxH,opts={}){
  const s=screenProjectionPx(pxW,pxH);
  return sectionHairlineCap(cadStrokeWidth(s.w,s.h,opts));
}
function sectionFillOpacity(pxW,pxH,opts={}){
  const s=screenProjectionPx(pxW,pxH);
  return cadFillOpacity(s.w,s.h,opts);
}
function sectionHitWidth(pxW,pxH){
  const s=screenProjectionPx(pxW,pxH);
  return cadHitWidth(s.w,s.h);
}
function drawThinSelectionGuide(c,bb){
  if(!selectedIds.has(c.component_id)||isWorld(c)||!hasThinProjection(c))return;
  const minDim=screenProjectionMinPx(bb.w,bb.h);
  const maxDim=screenProjectionMaxPx(bb.w,bb.h);
  if(maxDim<2||minDim>=2)return;
  const pad=5,tick=7,stroke=ACCENT,strokeWidth=sectionHairlineCap(0.35),opacity=thinProjectionMinPx()===null?0.65:0.5;
  const x0=bb.x,x1=bb.x+bb.w,y0=bb.y,y1=bb.y+bb.h;
  const lines=[];
  if(Math.abs(bb.h)<=Math.abs(bb.w)){
    lines.push([x0,y0-pad,x0,y0-pad-tick],[x1,y0-pad,x1,y0-pad-tick],[x0,y1+pad,x0,y1+pad+tick],[x1,y1+pad,x1,y1+pad+tick]);
  }else{
    lines.push([x0-pad,y0,x0-pad-tick,y0],[x0-pad,y1,x0-pad-tick,y1],[x1+pad,y0,x1+pad+tick,y0],[x1+pad,y1,x1+pad+tick,y1]);
  }
  for(const pts of lines){
    thinSelectionGroup.add(new Konva.Line({points:pts,stroke,strokeWidth,opacity,strokeScaleEnabled:false,listening:false}));
  }
}
function refreshTransformer(){
  const nodes=[];
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);const n=rectNodes.get(id);
    // 锁定尺寸 / 多边形 / world 不挂缩放手柄
    if(n&&c&&!c.polygon&&!isWorld(c)&&!c.locked&&!c.hidden&&!hasThinProjection(c))nodes.push(n.shape);
  }
  tr.nodes(nodes);
  tr.borderStrokeWidth(nodes.length?1:0);
  tr.anchorSize(nodes.length?9:0);
  const r=document.getElementById("ratioScale");if(r)tr.keepRatio(r.checked);
}

/* ---------- 多边形顶点(编辑模式) ---------- */
function drawPolyAnchors(){
  // 清除旧 anchor(除 snapGroup、tr 外的 uiLayer 子节点)
  uiLayer.find(".anchor").forEach(a=>a.destroy());
  if(!polyEditId)return;
  const c=model.components.find(c=>c.component_id===polyEditId);
  if(!c||!c.polygon||!polygonAxesMatch(c))return;
  clampSelectedPolygonVertex(c);
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  c.polygon.forEach((p,idx)=>{
    const active=idx===selectedPolygonVertexIndex;
    const a=new Konva.Circle({x:X(p[li]),y:Y(p[di]),radius:active?POLY_NODE_RADIUS_PX+0.8:POLY_NODE_RADIUS_PX,fill:active?"#155eef":ACCENT,stroke:"#ffffff",strokeWidth:0.8,strokeScaleEnabled:false,draggable:true,name:"anchor",hitStrokeWidth:POLY_NODE_HIT_PX});
    a.setAttr("pidx",idx);
    a.on("click tap",e=>{e.cancelBubble=true;selectPolygonVertex(+a.getAttr("pidx"));});
    a.on("dragmove",()=>{
      const i=+a.getAttr("pidx");
      syncTransformConstraintFromUI();
      const snapped=polyAnchorSnapPoint(a.x(),a.y());
      if(snapped.snapped){a.x(snapped.x);a.y(snapped.y);showSnapLines(snapped.lines);}
      else{snapGroup.destroyChildren();}
      const next=c.polygon.map(p=>p.slice());
      next[i][li]=toDataX(a.x());next[i][di]=toDataY(a.y());
      if(!transformFitsContainer(c,bboxFromPolygonPoints(next,c))){
        a.x(X(c.polygon[i][li]));a.y(Y(c.polygon[i][di]));
        toast("目标会越出 mother/World 边界","err");
        uiLayer.batchDraw();
        return;
      }
      c.polygon=next;
      updatePolygonShape(c);
      renderEditValues(c);
      refreshSelectionSummary();
      refreshAnnotationViews();
      uiLayer.batchDraw();compLayer.batchDraw();
    });
    a.on("dragend",()=>{drawComponents();renderEdit();pushHistory();});
    a.on("dblclick dbltap",e=>{e.cancelBubble=true;removePolyNode(c.component_id,+a.getAttr("pidx"));});
    uiLayer.add(a);
  });
  // anchor 在 tr 之上
  uiLayer.find(".anchor").forEach(a=>a.moveToTop());
  uiLayer.batchDraw();
}
function polyAnchorSnapPoint(xPx,yPx){
  syncSnapSettingsFromUI();
  if(!snapSettings.enabled||!snapSettings.grid||gridStep()<=0)return {x:xPx,y:yPx,snapped:false,lines:[]};
  const thr=snapPx()/(stage.scaleX()||1);
  const lat=toDataX(xPx),dep=toDataY(yPx);
  const gs=gridStep();
  const sx=X(nearestGridValue(lat,gridOriginLat(),gs)),sy=Y(nearestGridValue(dep,gridOriginDep(),gs));
  const dx=sx-xPx,dy=sy-yPx;
  const out={x:xPx,y:yPx,snapped:false,lines:[]};
  if(Math.abs(dx)<=thr){out.x=sx;out.snapped=true;out.lines.push({axis:"x",pos:sx});}
  if(Math.abs(dy)<=thr){out.y=sy;out.snapped=true;out.lines.push({axis:"y",pos:sy});}
  return out;
}
function updatePolygonShape(c){
  if(!c||!c.polygon||!polygonAxesMatch(c))return;
  const n=rectNodes.get(c.component_id);if(!n)return;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const pts=[];
  for(const p of c.polygon)pts.push(X(p[li]),Y(p[di]));
  n.shape.points(pts);
  moveLabels(n,c);
}
function refreshAnnotationViews(){
  drawAnnotations();
  renderAnnotationsPanel();
}
function refreshSelectionViews(){
  renderList();
  renderAssemblyTree();
  renderLayerGroups();
  renderViewStates();
  renderEdit();
  renderStackInspector();
  updateCadStatus();
}
function refreshSelectionCanvasDecorations(){
  if(!model)return;
  thinSelectionGroup.destroyChildren();
  for(const [id,n] of rectNodes){
    const c=model.components.find(c=>c.component_id===id);
    if(!c||!visibleInCurrentSection(c))continue;
    const world=isWorld(c);
    const sel=selectedIds.has(id);
    const ovlp=lastOverlapIds.has(id);
    const bb=shapeBBoxPx(c);
    const strokeC=world?"#98a2b3":(ovlp?"#b7791f":(sel?ACCENT:OUTLINE));
    const dash=world?[5,4]:(sel?[6,3]:undefined);
    n.shape.stroke(strokeC);
    n.shape.strokeWidth(sectionStrokeWidth(bb.w,bb.h,{selected:sel,world,overlap:ovlp}));
    n.shape.opacity(sectionFillOpacity(bb.w,bb.h,{world}));
    n.shape.dash(dash);
    n.shape.hitStrokeWidth(sectionHitWidth(bb.w,bb.h));
    drawThinSelectionGuide(c,bb);
  }
  refreshTransformer();
  drawPolyAnchors();
  compLayer.batchDraw();
  uiLayer.batchDraw();
}

/* ---------- 选择 ---------- */
function onShapeClick(id,additive){
  const clicked=model.components.find(c=>c.component_id===id);
  if(!clicked||!visibleInCurrentSection(clicked))return;
  if(additive){
    if(selectedIds.has(id))selectedIds.delete(id);else selectedIds.add(id);
    if(selectedIds.size===0){primaryId=null;polyEditId=null;}
    else{primaryId=[...selectedIds].pop();}
  }else{
    selectedIds=new Set([id]);primaryId=id;
  }
  // 多边形编辑:选中单个多边形时自动进入
  const c=model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
  refreshSelectionViews();refreshSelectionCanvasDecorations();draw3DPreview();
}
function selectOnly(id){
  const c=model.components.find(c=>c.component_id===id);
  if(!c||!visibleInCurrentSection(c))return;
  selectedIds=new Set([id]);primaryId=id;
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c))?id:null;
  refreshSelectionViews();refreshSelectionCanvasDecorations();draw3DPreview();
}
function normalizeMarqueeRect(rect){
  const x1=Number(rect&&rect.x1)||0,y1=Number(rect&&rect.y1)||0,x2=Number(rect&&rect.x2)||0,y2=Number(rect&&rect.y2)||0;
  return {x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1),h:Math.abs(y2-y1)};
}
function rectsIntersect2D(a,b){
  return a.x<=b.x+b.w&&a.x+a.w>=b.x&&a.y<=b.y+b.h&&a.y+a.h>=b.y;
}
function setSelectionFromIds(ids,{additive=false}={}){
  const next=additive?new Set(selectedIds):new Set();
  for(const id of ids)next.add(id);
  selectedIds=next;
  if(ids.length)primaryId=ids[0];
  else if(!additive)primaryId=null;
  else if(primaryId&&!selectedIds.has(primaryId))primaryId=[...selectedIds][0]||null;
  const c=model&&model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
  refreshSelectionViews();refreshSelectionCanvasDecorations();draw3DPreview();
}
function selectByMarqueeRect(rect,opts={}){
  if(!model)return [];
  const r=normalizeMarqueeRect(rect);
  const ids=[];
  if(r.w>0&&r.h>0){
    for(const c of sectionComponents(false)){
      if(isWorld(c)||c.locked&&opts.skipLocked)continue;
      const bb=shapeBBoxPx(c);
      if(rectsIntersect2D(r,{x:bb.x,y:bb.y,w:bb.w,h:bb.h}))ids.push(c.component_id);
    }
  }
  setSelectionFromIds(ids,{additive:!!opts.additive});
  return ids;
}

/* ---------- 拖动 + 吸附 ---------- */
function onShapeDrag(c){
  const n=rectNodes.get(c.component_id);if(!n)return;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  // 多边形:dragmove 不碰数据(Konva 用 position 视觉跟随),dragend 落位
  if(c.polygon&&polygonAxesMatch(c))return;
  syncTransformConstraintFromUI();
  syncSnapSettingsFromUI();
  // 矩形:读形状中心像素 → 数据
  const snap=snapSettings.enabled;
  const shape=n.shape;
  let cxPx=shape.x()+shape.width()/2, cyPx=shape.y()+shape.height()/2;
  if(snap){
    const snapRes=computeSnap(c,cxPx,cyPx);
    if(snapRes.dx!==0)shape.x(shape.x()+snapRes.dx);
    if(snapRes.dy!==0)shape.y(shape.y()+snapRes.dy);
    cxPx=shape.x()+shape.width()/2;cyPx=shape.y()+shape.height()/2;
    showSnapLines(snapRes.lines);
  } else {snapGroup.destroyChildren();uiLayer.batchDraw();}
  const nextPos=c.placement.position.slice();
  nextPos[li]=toDataX(cxPx);
  nextPos[di]=toDataY(cyPx);
  if(!transformFitsContainer(c,bboxForComponentState(c,nextPos,c.dimensions))){
    if(transformSettings.constrainWorld&&transformSettings.boundaryMode==="clamp"){
      const delta=[0,0,0];delta[li]=nextPos[li]-c.placement.position[li];delta[di]=nextPos[di]-c.placement.position[di];
      const clamped=clampTranslationToContainer(c,delta);
      nextPos[li]=c.placement.position[li]+clamped.delta[li];
      nextPos[di]=c.placement.position[di]+clamped.delta[di];
      shape.x(X(nextPos[li])-shape.width()/2);
      shape.y(Y(nextPos[di])-shape.height()/2);
      if(clamped.blocked){snapGroup.destroyChildren();uiLayer.batchDraw();return;}
    }else{
      shape.x(X(c.placement.position[li])-shape.width()/2);
      shape.y(Y(c.placement.position[di])-shape.height()/2);
      snapGroup.destroyChildren();uiLayer.batchDraw();
      return;
    }
  }
  c.placement.position[li]=nextPos[li];
  c.placement.position[di]=nextPos[di];
  moveLabels(n,c);renderEditValues(c);refreshSelectionSummary();renderStackInspector();refreshAnnotationViews();
}
function computeSnap(c,cxPx,cyPx){
  syncSnapSettingsFromUI();
  if(!snapSettings.enabled)return{dx:0,dy:0,lines:[]};
  const thr=snapPx()/(stage.scaleX()||1);  // 屏幕阈值→layer 本地
  const w=c.dimensions[DIM_KEY[axes.lateral]]*camera.sLat;
  const h=c.dimensions[DIM_KEY[axes.depth]]*camera.sDep;
  // 该矩形的 左/右/中心 (layer 本地像素)
  const myL=cxPx-w/2,myR=cxPx+w/2;
  const myT=cyPx-h/2,myB=cyPx+h/2;
  // 收集其它模块的 左/右/中心、顶/底/中心
  const edgeXTars=[],edgeYTars=[],centerXTars=[],centerYTars=[];
  if(snapSettings.components){
    for(const oc of model.components){
      if(!visibleInCurrentSection(oc))continue;
      if(oc.component_id===c.component_id)continue;
      const bb=shapeBBoxPx(oc);
      edgeXTars.push(bb.x,bb.x+bb.w,bb.x+bb.w/2);
      edgeYTars.push(bb.y,bb.y+bb.h,bb.y+bb.h/2);
    }
  }
  if(snapSettings.canvas){
    centerXTars.push(stage.width()/2);   // 画布中心
    centerYTars.push(stage.height()/2);
  }
  const gs=gridStep();
  if(snapSettings.grid&&gs>0){
    const lat=toDataX(cxPx),dep=toDataY(cyPx);
    const gx=X(nearestGridValue(lat,gridOriginLat(),gs)),gy=Y(nearestGridValue(dep,gridOriginDep(),gs));
    centerXTars.push(gx);centerYTars.push(gy);
  }
  // x 方向独立找最近
  let bx={d:thr+1,target:null};
  for(const mv of [myL,myR,cxPx])for(const tv of edgeXTars){const d=tv-mv;if(Math.abs(d)<Math.abs(bx.d)){bx={d,target:tv};}}
  for(const tv of centerXTars){const d=tv-cxPx;if(Math.abs(d)<Math.abs(bx.d)){bx={d,target:tv};}}
  // y 方向独立找最近
  let by={d:thr+1,target:null};
  for(const mv of [myT,myB,cyPx])for(const tv of edgeYTars){const d=tv-mv;if(Math.abs(d)<Math.abs(by.d)){by={d,target:tv};}}
  for(const tv of centerYTars){const d=tv-cyPx;if(Math.abs(d)<Math.abs(by.d)){by={d,target:tv};}}
  const lines=[];let dx=0,dy=0;
  if(bx.target!==null&&Math.abs(bx.d)<=thr){dx=bx.d;lines.push({axis:"x",pos:bx.target});}
  if(by.target!==null&&Math.abs(by.d)<=thr){dy=by.d;lines.push({axis:"y",pos:by.target});}
  return{dx,dy,lines};
}
function showSnapLines(lines){
  snapGroup.destroyChildren();
  const W=stage.width(),H=stage.height();
  const lineProps=cadLineProps(sectionHairlineCap(1),{stroke:"#ffd23f",dash:[4,3],opacity:thinProjectionMinPx()===null?1:0.72});
  for(const ln of lines){
    if(ln.axis==="x"){const px=ln.pos;snapGroup.add(new Konva.Line({points:[px,0,px,H],...lineProps}));}
    else{const py=ln.pos;snapGroup.add(new Konva.Line({points:[0,py,W,py],...lineProps}));}
  }
  uiLayer.batchDraw();
}
function moveLabels(n,c){const bb=shapeBBoxPx(c);if(n.label){n.label.x(bb.x+5);n.label.y(bb.y+4);}if(n.matLabel){n.matLabel.x(bb.x+5);n.matLabel.y(bb.y+20);}if(n.depLabel){n.depLabel.x(bb.x+bb.w-6);n.depLabel.y(bb.y+bb.h/2-6);}}
function fitCameraNotZoom(){fitCamera();drawBackground();}

/* ---------- 测量工具 ---------- */
function setToolMode(mode){
  toolMode=mode;
  document.getElementById("toolSelect")?.classList.toggle("on",mode==="select");
  document.getElementById("toolMeasure")?.classList.toggle("on",mode==="measure");
  const label=document.getElementById("measureLabel");
  if(mode==="measure"){if(label){label.textContent="测量: 点击第一点";label.classList.add("show");}}
  else{measureState={start:null,end:null,preview:null};drawMeasurement();if(label)label.classList.remove("show");}
}
function measurementPoint(){
  const pos=compLayer.getRelativePointerPosition();
  if(!pos)return null;
  return {lat:toDataX(pos.x),dep:toDataY(pos.y),x:pos.x,y:pos.y};
}
function handleMeasureClick(){
  const p=measurementPoint();if(!p)return;
  if(!measureState.start||measureState.end){
    measureState={start:p,end:null,preview:null};
    updateMeasureLabel("测量: 选择第二点");
  }else{
    measureState.end=p;measureState.preview=null;
    updateMeasureLabel(formatMeasure(measureState.start,measureState.end));
  }
  drawMeasurement();
}
function handleMeasureMove(){
  if(toolMode!=="measure"||!measureState.start||measureState.end)return;
  measureState.preview=measurementPoint();drawMeasurement();
  if(measureState.preview)updateMeasureLabel(formatMeasure(measureState.start,measureState.preview));
}
function formatMeasure(a,b){
  const dLat=b.lat-a.lat,dDep=b.dep-a.dep,dist=Math.hypot(dLat,dDep);
  return `Δ${axes.lateral}: ${fmt(dLat)} μm · Δ${axes.depth}: ${fmt(dDep)} μm · L: ${fmt(dist)} μm`;
}
function updateMeasureLabel(text){const label=document.getElementById("measureLabel");if(label){label.textContent=text;label.classList.add("show");}}
function drawMeasurement(){
  measureGroup.destroyChildren();
  const a=measureState.start,b=measureState.end||measureState.preview;
  if(a&&b){
    measureGroup.add(new Konva.Line({points:[X(a.lat),Y(a.dep),X(b.lat),Y(b.dep)],...cadLineProps(sectionHairlineCap(0.8),{stroke:"#111827",dash:[5,4]})}));
    measureGroup.add(new Konva.Circle({x:X(a.lat),y:Y(a.dep),radius:4,fill:"#111827",listening:false}));
    measureGroup.add(new Konva.Circle({x:X(b.lat),y:Y(b.dep),radius:4,fill:"#111827",listening:false}));
    const mid={x:(X(a.lat)+X(b.lat))/2,y:(Y(a.dep)+Y(b.dep))/2};
    measureGroup.add(new Konva.Label({x:mid.x+8,y:mid.y-18,listening:false}));
    const label=measureGroup.children[measureGroup.children.length-1];
    label.add(new Konva.Tag({fill:"#ffffff",stroke:"#b9c3d0",strokeWidth:sectionHairlineCap(0.7),cornerRadius:4,shadowColor:"rgba(16,24,40,.16)",shadowBlur:6,shadowOffset:{x:0,y:2}}));
    label.add(new Konva.Text({text:`L ${fmt(Math.hypot(b.lat-a.lat,b.dep-a.dep))} μm`,fontSize:11,fill:"#101828",padding:5}));
  }else if(a){
    measureGroup.add(new Konva.Circle({x:X(a.lat),y:Y(a.dep),radius:4,fill:"#111827",listening:false}));
  }
  measureGroup.moveToTop();
  uiLayer.batchDraw();
}
function clearMeasureState(){
  measureState={start:null,end:null,preview:null};
  if(toolMode==="measure")updateMeasureLabel("测量: 点击第一点");
  drawMeasurement();
}
function createDimensionFromMeasure(){
  if(!measureState.start||!measureState.end){toast("先用测量工具选两点","err");return;}
  const a=measureState.start,b=measureState.end;
  dimensionAnnotations.push({
    id:uniqueAnnotationId(),
    axes:{lateral:axes.lateral,depth:axes.depth},
    start:{lat:a.lat,dep:a.dep},
    end:{lat:b.lat,dep:b.dep},
    label:formatMeasure(a,b),
  });
  drawAnnotations();renderAnnotationsPanel();pushHistory();toast("已创建尺寸标注");
}
function uniqueAnnotationId(){let i=dimensionAnnotations.length+1,id=`dim_${i}`;while(dimensionAnnotations.some(a=>a.id===id))id=`dim_${++i}`;return id;}
function sameAnnotationAxes(a,b){
  return a&&b&&a.lateral===b.lateral&&a.depth===b.depth;
}
function selectedPairDominantAxis(report=buildSelectionReport()){
  const probe=report&&report.pairProbe;
  if(!probe)return axes.lateral;
  const visibleAxes=[axes.lateral,axes.depth];
  const gaps=probe.axes.filter(item=>item.state==="gap"&&visibleAxes.includes(item.axis)).sort((a,b)=>b.gap-a.gap);
  if(gaps.length)return gaps[0].axis;
  const overlaps=probe.axes.filter(item=>item.state==="overlap"&&visibleAxes.includes(item.axis)).sort((a,b)=>b.overlap-a.overlap);
  if(overlaps.length)return overlaps[0].axis;
  return visibleAxes[0];
}
function createPairGapAnnotation(){
  if(!model||selectedIds.size!==2){toast("需恰好选中 2 个组件","err");return false;}
  const comps=selectedComponents([...selectedIds],false);
  if(comps.length!==2){toast("需选中当前截面中的 2 个非 world 组件","err");return false;}
  const report=buildSelectionReport(comps.map(c=>c.component_id));
  const axis=selectedPairDominantAxis(report);
  const exists=dimensionAnnotations.some(a=>a.kind==="pair_gap"&&
    ((a.a_id===comps[0].component_id&&a.b_id===comps[1].component_id)||(a.a_id===comps[1].component_id&&a.b_id===comps[0].component_id))&&
    a.axis===axis&&sameAnnotationAxes(a.axes,{lateral:axes.lateral,depth:axes.depth}));
  if(exists){toast("这组组件已有间隙标注");return false;}
  dimensionAnnotations.push({
    id:`pair_gap:${comps[0].component_id}:${comps[1].component_id}:${axis}`,
    kind:"pair_gap",
    a_id:comps[0].component_id,
    b_id:comps[1].component_id,
    axis,
    axes:{lateral:axes.lateral,depth:axes.depth},
    offsetPx:18,
  });
  drawAnnotations();renderAnnotationsPanel();pushHistory();toast("已创建两组件间隙标注");
  return true;
}
function createDimensionsForSelection(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  const axesNow={lateral:axes.lateral,depth:axes.depth};
  const comps=selectedComponents([...selectedIds],false);
  let added=0;
  for(const c of comps){
    for(const dimension of ["lateral","depth"]){
      const exists=dimensionAnnotations.some(a=>a.kind==="component_dimension"&&a.component_id===c.component_id&&a.dimension===dimension&&sameAnnotationAxes(a.axes,axesNow));
      if(exists)continue;
      dimensionAnnotations.push({
        id:uniqueAnnotationId(),
        kind:"component_dimension",
        component_id:c.component_id,
        axes:{...axesNow},
        dimension,
        offsetPx:dimension==="lateral"?14:16,
      });
      added++;
    }
  }
  if(!added){toast("选区已有尺寸标注");return;}
  drawAnnotations();renderAnnotationsPanel();pushHistory();toast(`已创建 ${added} 个绑定尺寸标注`);
}
function annotationFallbackLabel(ann){
  if(ann.kind==="component_dimension"){
    const ax=ann.axes||{};
    const axis=ann.dimension==="depth"?ax.depth:ax.lateral;
    return `${axis||"?"} 尺寸`;
  }
  if(ann.kind==="pair_gap"){
    return `${ann.axis||"?"} 两组件间隙`;
  }
  const a=ann.start,b=ann.end;
  if(a&&b)return `${fmt(Math.hypot(b.lat-a.lat,b.dep-a.dep))} μm`;
  return ann.id||"尺寸标注";
}
function pairGapAnnotationGeometry(ann){
  if(!ann||ann.kind!=="pair_gap"||!model)return null;
  if(!ann.axes||ann.axes.lateral!==axes.lateral||ann.axes.depth!==axes.depth)return null;
  if(ann.axis!==axes.lateral&&ann.axis!==axes.depth)return null;
  const a=model.components.find(c=>c.component_id===ann.a_id);
  const b=model.components.find(c=>c.component_id===ann.b_id);
  if(!a||!b||!visibleInCurrentSection(a)||!visibleInCurrentSection(b))return null;
  const aBox=bbox3D(a),bBox=bbox3D(b);
  const axis=ann.axis;
  const item=pairAxisProbe(axis,aBox,bBox);
  const axisIdx=AXIS_IDX[axis],latIdx=AXIS_IDX[axes.lateral],depIdx=AXIS_IDX[axes.depth];
  const axisIsLat=axis===axes.lateral;
  const crossAxis=axisIsLat?axes.depth:axes.lateral;
  const crossIdx=AXIS_IDX[crossAxis];
  const start3=[0,0,0],end3=[0,0,0];
  const aCenter=aBox.max.map((v,i)=>(v+aBox.min[i])/2);
  const bCenter=bBox.max.map((v,i)=>(v+bBox.min[i])/2);
  let value,labelState;
  if(item.state==="gap"){
    value=item.gap;labelState="gap";
    if(item.order==="a_before_b"){
      start3[axisIdx]=aBox.max[axisIdx];end3[axisIdx]=bBox.min[axisIdx];
    }else{
      start3[axisIdx]=bBox.max[axisIdx];end3[axisIdx]=aBox.min[axisIdx];
    }
  }else if(item.state==="overlap"){
    value=item.overlap;labelState="overlap";
    start3[axisIdx]=Math.max(aBox.min[axisIdx],bBox.min[axisIdx]);
    end3[axisIdx]=Math.min(aBox.max[axisIdx],bBox.max[axisIdx]);
  }else{
    value=0;labelState="touch";
    start3[axisIdx]=end3[axisIdx]=Math.max(aBox.min[axisIdx],bBox.min[axisIdx]);
  }
  const cross=(aCenter[crossIdx]+bCenter[crossIdx])/2;
  start3[crossIdx]=cross;end3[crossIdx]=cross;
  const thirdIdx=3-latIdx-depIdx;
  start3[thirdIdx]=(aCenter[thirdIdx]+bCenter[thirdIdx])/2;
  end3[thirdIdx]=start3[thirdIdx];
  const baseStart={lat:start3[latIdx],dep:start3[depIdx]};
  const baseEnd={lat:end3[latIdx],dep:end3[depIdx]};
  const gap=Math.max(8,Number(ann.offsetPx)||18);
  const screenStart={x:X(baseStart.lat),y:Y(baseStart.dep)};
  const screenEnd={x:X(baseEnd.lat),y:Y(baseEnd.dep)};
  const extensions=[];
  if(axisIsLat){
    screenStart.y-=gap;screenEnd.y-=gap;
    extensions.push([X(baseStart.lat),Y(baseStart.dep),screenStart.x,screenStart.y]);
    extensions.push([X(baseEnd.lat),Y(baseEnd.dep),screenEnd.x,screenEnd.y]);
  }else{
    screenStart.x+=gap;screenEnd.x+=gap;
    extensions.push([X(baseStart.lat),Y(baseStart.dep),screenStart.x,screenStart.y]);
    extensions.push([X(baseEnd.lat),Y(baseEnd.dep),screenEnd.x,screenEnd.y]);
  }
  const stateLabel=labelState==="overlap"?"overlap":labelState==="touch"?"touch":"gap";
  return {
    ann,kind:"pair_gap",axis,state:labelState,start:baseStart,end:baseEnd,dist:normalizeNumber(value),
    label:`${axis} ${stateLabel} ${fmtProbeNumber(value)} μm`,
    meta:`${a.display_name} / ${b.display_name} · ${axis} ${stateLabel}`,
    screenStart,screenEnd,extensions,
  };
}
function annotationGeometry(ann){
  if(!ann||!ann.axes||ann.axes.lateral!==axes.lateral||ann.axes.depth!==axes.depth)return null;
  if(ann.kind==="pair_gap")return pairGapAnnotationGeometry(ann);
  if(ann.kind==="component_dimension"){
    const c=model&&model.components.find(c=>c.component_id===ann.component_id);
    if(!c||!visibleInCurrentSection(c))return null;
    const b=bboxOf(c);
    const gap=Math.max(8,Number(ann.offsetPx)||14);
    const dimension=ann.dimension==="depth"?"depth":"lateral";
    if(dimension==="lateral"){
      const start={lat:b.minLat,dep:b.maxDep};
      const end={lat:b.maxLat,dep:b.maxDep};
      const y=Y(b.maxDep)-gap;
      const sx=X(start.lat),ex=X(end.lat),ey=Y(b.maxDep);
      const dist=Math.abs(end.lat-start.lat);
      return {
        ann,kind:"component_dimension",component:c,dimension,start,end,dist,
        label:`${axes.lateral} ${fmt(dist)} μm`,
        meta:`${c.display_name} · ${axes.lateral} 尺寸`,
        screenStart:{x:sx,y},screenEnd:{x:ex,y},
        extensions:[[sx,ey,sx,y],[ex,ey,ex,y]],
      };
    }
    const start={lat:b.maxLat,dep:b.minDep};
    const end={lat:b.maxLat,dep:b.maxDep};
    const x=X(b.maxLat)+gap;
    const sy=Y(start.dep),ey=Y(end.dep),ex=X(b.maxLat);
    const dist=Math.abs(end.dep-start.dep);
    return {
      ann,kind:"component_dimension",component:c,dimension,start,end,dist,
      label:`${axes.depth} ${fmt(dist)} μm`,
      meta:`${c.display_name} · ${axes.depth} 尺寸`,
      screenStart:{x,y:sy},screenEnd:{x,y:ey},
      extensions:[[ex,sy,x,sy],[ex,ey,x,ey]],
    };
  }
  const a=ann.start,b=ann.end;
  if(!a||!b)return null;
  const dist=Math.hypot(b.lat-a.lat,b.dep-a.dep);
  return {
    ann,kind:"free_dimension",start:a,end:b,dist,
    label:ann.label||`${fmt(dist)} μm`,
    meta:"自由测量",
    screenStart:{x:X(a.lat),y:Y(a.dep)},
    screenEnd:{x:X(b.lat),y:Y(b.dep)},
    extensions:[],
  };
}
function drawAnnotations(){
  annotationGroup.destroyChildren();
  for(const ann of dimensionAnnotations){
    const g=annotationGeometry(ann);
    if(!g)continue;
    const stroke=g.kind==="pair_gap"?"#c2410c":(g.kind==="component_dimension"?"#155eef":"#0f172a");
    const thin=thinProjectionMinPx();
    for(const pts of g.extensions){
      annotationGroup.add(new Konva.Line({points:pts,...cadLineProps(sectionHairlineCap(0.55),{stroke,opacity:thin===null?0.65:0.5,dash:[3,3]})}));
    }
    const ax=g.screenStart.x,ay=g.screenStart.y,bx=g.screenEnd.x,by=g.screenEnd.y;
    annotationGroup.add(new Konva.Line({points:[ax,ay,bx,by],...cadLineProps(sectionHairlineCap(0.75),{stroke})}));
    annotationGroup.add(new Konva.Circle({x:ax,y:ay,radius:2.5,fill:"#ffffff",stroke,strokeWidth:sectionHairlineCap(0.7),strokeScaleEnabled:false,listening:false}));
    annotationGroup.add(new Konva.Circle({x:bx,y:by,radius:2.5,fill:"#ffffff",stroke,strokeWidth:sectionHairlineCap(0.7),strokeScaleEnabled:false,listening:false}));
    const mid={x:(ax+bx)/2,y:(ay+by)/2};
    const label=new Konva.Label({x:mid.x+8,y:mid.y+8,listening:false});
    label.add(new Konva.Tag({fill:"#fff",stroke:g.kind==="pair_gap"?"#fdba74":(g.kind==="component_dimension"?"#93c5fd":"#667085"),strokeWidth:sectionHairlineCap(0.7),cornerRadius:4}));
    label.add(new Konva.Text({text:g.label,fontSize:11,fill:"#0f172a",padding:5}));
    annotationGroup.add(label);
  }
  annotationGroup.moveToTop();uiLayer.batchDraw();
}
function renderAnnotationsPanel(){
  const root=document.getElementById("annotationList");if(!root)return;
  if(!dimensionAnnotations.length){root.innerHTML='<div class="empty-side">无尺寸标注</div>';return;}
  root.innerHTML="";
  for(const ann of dimensionAnnotations){
    const geom=annotationGeometry(ann);
    const active=!!geom;
    const row=document.createElement("div");
    row.className="annotation-row"+(active?"":" muted");
    const text=document.createElement("div");
    const title=document.createElement("b");
    title.textContent=geom?geom.label:annotationFallbackLabel(ann);
    const meta=document.createElement("small");
    meta.textContent=`${geom?.meta||"非当前截面"} · ${ann.axes?.lateral||"?"}×${ann.axes?.depth||"?"} · ${ann.id}`;
    text.appendChild(title);text.appendChild(meta);row.appendChild(text);
    const del=document.createElement("button");
    del.className="ghost";
    del.textContent="删除";
    del.onclick=()=>deleteAnnotation(ann.id);
    row.appendChild(del);
    root.appendChild(row);
  }
}
function deleteAnnotation(id){
  const before=dimensionAnnotations.length;
  dimensionAnnotations=dimensionAnnotations.filter(a=>a.id!==id);
  if(dimensionAnnotations.length===before)return;
  drawAnnotations();renderAnnotationsPanel();pushHistory();toast("已删除尺寸标注");
}

/* ---------- 精确变换 ---------- */
function nudgeSelection(dxSign,dySign){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  syncTransformConstraintFromUI();
  const step=Number(document.getElementById("nudgeStep")?.value||0);
  if(!Number.isFinite(step)||step===0){toast("步长无效","err");return;}
  let moved=0,blocked=0;
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c)||c.locked)continue;
    const result=translateComp(c,dxSign*step,dySign*step);
    if(result.changed)moved++;
    if(result.blocked)blocked++;
  }
  if(!moved){report3DTransformResult("移动",moved,blocked);return;}
  drawComponents();renderEdit();pushHistory();
  if(blocked)toast(`已移动 ${moved} 个,阻止 ${blocked} 个越界`);
}
function scaleSelectionByInput(invert=0){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  let factor=Number(document.getElementById("scaleFactor")?.value||1);
  if(!Number.isFinite(factor)||factor<=0){toast("缩放系数无效","err");return;}
  if(invert<0)factor=1/factor;
  scaleSelection(factor,factor);
}
function scaleSelection(fLat,fDep){
  syncTransformConstraintFromUI();
  const b=bboxOfSelection();if(!b)return;
  const cLat=(b.minLat+b.maxLat)/2,cDep=(b.minDep+b.maxDep)/2;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  let changed=0,blocked=0;
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c)||c.locked)continue;
    const proposal=scaledComponentProjection(c,cLat,cDep,fLat,fDep,li,di);
    if(!transformFitsContainer(c,proposal.box)){blocked++;continue;}
    if(c.polygon&&polygonAxesMatch(c)){
      c.polygon=proposal.polygon;
    }else{
      c.placement.position[li]=proposal.position[li];
      c.placement.position[di]=proposal.position[di];
      c.dimensions[DIM_KEY[axes.lateral]]=proposal.dimensions[DIM_KEY[axes.lateral]];
      c.dimensions[DIM_KEY[axes.depth]]=proposal.dimensions[DIM_KEY[axes.depth]];
    }
    changed++;
  }
  if(!changed){report3DTransformResult("缩放",changed,blocked);return;}
  drawComponents();renderEdit();pushHistory();
  if(blocked)toast(`已缩放 ${changed} 个,阻止 ${blocked} 个越界`);
}
function fitSelectionToInputs(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  const b=bboxOfSelection();if(!b)return;
  const targetLat=Number(document.getElementById("targetLatSize")?.value||0);
  const targetDep=Number(document.getElementById("targetDepSize")?.value||0);
  const curLat=b.maxLat-b.minLat,curDep=b.maxDep-b.minDep;
  const fLat=targetLat>0?targetLat/curLat:1;
  const fDep=targetDep>0?targetDep/curDep:1;
  if(!Number.isFinite(fLat)||!Number.isFinite(fDep)||fLat<=0||fDep<=0){toast("目标尺寸无效","err");return;}
  scaleSelection(fLat,fDep);
}
function mirrorSelection2D(axis){
  transformSelection2D(axis==="dep"?"mirror_dep":"mirror_lat");
}
function rotateSelection2D(dir){
  transformSelection2D(dir==="ccw"?"rotate_ccw":"rotate_cw");
}
function transformSelection2D(mode){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  syncTransformConstraintFromUI();
  const b=bboxOfSelection();if(!b)return;
  const cLat=(b.minLat+b.maxLat)/2,cDep=(b.minDep+b.maxDep)/2;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  let changed=0,blocked=0;
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c)||c.locked)continue;
    const proposal=component2DTransformProposal(c,mode,cLat,cDep,li,di);
    if(!proposal||!transformFitsContainer(c,proposal.box)){blocked++;continue;}
    apply2DTransformProposal(c,proposal,li,di);
    changed++;
  }
  if(!changed){report3DTransformResult(transformModeLabel(mode),changed,blocked);return;}
  drawComponents();renderEdit();renderList();refreshSelectionSummary();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已${transformModeLabel(mode)} ${changed} 个,阻止 ${blocked} 个越界`:`已${transformModeLabel(mode)} ${changed} 个组件`);
}
function transformModeLabel(mode){
  return {mirror_lat:"水平镜像",mirror_dep:"垂直镜像",rotate_cw:"顺时针旋转",rotate_ccw:"逆时针旋转"}[mode]||"变换";
}
function transformPoint2D(lat,dep,mode,cLat,cDep){
  const dx=lat-cLat,dy=dep-cDep;
  if(mode==="mirror_lat")return [cLat-dx,dep];
  if(mode==="mirror_dep")return [lat,cDep-dy];
  if(mode==="rotate_cw")return [cLat+dy,cDep-dx];
  if(mode==="rotate_ccw")return [cLat-dy,cDep+dx];
  return [lat,dep];
}
function component2DTransformProposal(c,mode,cLat,cDep,li,di){
  if(c.polygon&&polygonAxesMatch(c)){
    const polygon=c.polygon.map(p=>{
      const next=p.slice();
      const [lat,dep]=transformPoint2D(p[li],p[di],mode,cLat,cDep);
      next[li]=lat;next[di]=dep;
      return next;
    });
    const position=c.placement.position.slice();
    const [pLat,pDep]=transformPoint2D(position[li],position[di],mode,cLat,cDep);
    position[li]=pLat;position[di]=pDep;
    return {polygon,position,box:bboxFromPolygonPoints(polygon,c)};
  }
  const position=c.placement.position.slice();
  const dimensions={...c.dimensions};
  const [lat,dep]=transformPoint2D(position[li],position[di],mode,cLat,cDep);
  position[li]=lat;position[di]=dep;
  if(mode==="rotate_cw"||mode==="rotate_ccw"){
    const latKey=DIM_KEY[axes.lateral],depKey=DIM_KEY[axes.depth];
    const oldLat=dimensions[latKey];
    dimensions[latKey]=dimensions[depKey];
    dimensions[depKey]=oldLat;
  }
  return {position,dimensions,box:bboxForComponentState(c,position,dimensions)};
}
function apply2DTransformProposal(c,proposal,li,di){
  c.placement.position[li]=proposal.position[li];
  c.placement.position[di]=proposal.position[di];
  if(proposal.polygon)c.polygon=proposal.polygon;
  if(proposal.dimensions)c.dimensions=proposal.dimensions;
}
function selectedEditable3D(includePolygons=true){
  if(!model)return [];
  return [...selectedIds].map(id=>model.components.find(c=>c.component_id===id))
    .filter(c=>c&&!isWorld(c)&&!c.locked&&(includePolygons||!c.polygon));
}
function syncTransformConstraintFromUI(){
  const el=document.getElementById("constrain3dWorld");
  if(el)transformSettings.constrainWorld=!!el.checked;
  const mode=document.getElementById("constraintBoundaryMode");
  if(mode)transformSettings.boundaryMode=mode.value==="clamp"?"clamp":"block";
  return transformSettings.constrainWorld;
}
function updateTransformConstraintUI(){
  const el=document.getElementById("constrain3dWorld");
  if(el)el.checked=!!transformSettings.constrainWorld;
  const mode=document.getElementById("constraintBoundaryMode");
  if(mode)mode.value=transformSettings.boundaryMode==="clamp"?"clamp":"block";
}
function bboxTranslated3D(box,delta){
  return {
    min:box.min.map((v,i)=>v+(delta[i]||0)),
    max:box.max.map((v,i)=>v+(delta[i]||0)),
  };
}
function bboxForResizedBox(c,target){
  const p=c.placement.position;
  const dims=[target.dx,target.dy,target.dz];
  return {
    min:dims.map((d,i)=>p[i]-d/2),
    max:dims.map((d,i)=>p[i]+d/2),
  };
}
function bboxFromPolygonPoints(points,c){
  const saved=c.polygon;
  c.polygon=points;
  const box=bbox3D(c);
  c.polygon=saved;
  return box;
}
function scaledComponentProjection(c,cLat,cDep,fLat,fDep,li,di){
  if(c.polygon&&polygonAxesMatch(c)){
    const polygon=c.polygon.map(p=>{
      const next=p.slice();
      next[li]=cLat+(p[li]-cLat)*fLat;
      next[di]=cDep+(p[di]-cDep)*fDep;
      return next;
    });
    return {polygon,box:bboxFromPolygonPoints(polygon,c)};
  }
  const position=c.placement.position.slice();
  const dimensions={...c.dimensions};
  position[li]=cLat+(position[li]-cLat)*fLat;
  position[di]=cDep+(position[di]-cDep)*fDep;
  dimensions[DIM_KEY[axes.lateral]]*=fLat;
  dimensions[DIM_KEY[axes.depth]]*=fDep;
  return {position,dimensions,box:bboxForComponentState(c,position,dimensions)};
}
function bboxForComponentState(c,position,dimensions){
  if(c.polygon)return bbox3D(c);
  const dims=[dimensions.dx||0,dimensions.dy||0,dimensions.dz||0];
  return {
    min:dims.map((d,i)=>position[i]-d/2),
    max:dims.map((d,i)=>position[i]+d/2),
  };
}
function projectedBoxEditBBox(c,position,dLat,dDep,li,di){
  const dims={...c.dimensions};
  dims[DIM_KEY[axes.lateral]]=dLat;
  dims[DIM_KEY[axes.depth]]=dDep;
  return bboxForComponentState(c,position,dims);
}
function transformFitsContainer(c,nextBox){
  if(!transformSettings.constrainWorld)return true;
  const container=containerBoundsFor(c);
  return !container||aabbContains(container,nextBox);
}
function clampTranslationToContainer(c,delta){
  const requested=delta.map(v=>Number(v)||0);
  if(!transformSettings.constrainWorld)return {delta:requested,clamped:false,blocked:false};
  const container=containerBoundsFor(c);
  if(!container)return {delta:requested,clamped:false,blocked:false};
  const box=bbox3D(c);
  const out=requested.slice();
  let clamped=false;
  for(let i=0;i<3;i++){
    const minDelta=container.min[i]-box.min[i];
    const maxDelta=container.max[i]-box.max[i];
    const next=Math.max(minDelta,Math.min(maxDelta,out[i]));
    if(Math.abs(next-out[i])>1e-9)clamped=true;
    out[i]=next;
  }
  const blocked=out.every(v=>Math.abs(v)<1e-12)&&requested.some(v=>Math.abs(v)>1e-12);
  return {delta:out,clamped,blocked};
}
function translateComp3DConstrained(c,delta){
  if(delta.every(v=>Math.abs(v)<1e-12))return {changed:false,blocked:false};
  if(transformSettings.constrainWorld&&transformSettings.boundaryMode==="clamp"){
    const result=clampTranslationToContainer(c,delta);
    if(result.blocked)return {changed:false,blocked:true,clamped:result.clamped};
    translateComp3D(c,result.delta);
    return {changed:true,blocked:false,clamped:result.clamped};
  }
  const next=bboxTranslated3D(bbox3D(c),delta);
  if(!transformFitsContainer(c,next))return {changed:false,blocked:true};
  translateComp3D(c,delta);
  return {changed:true,blocked:false};
}
function report3DTransformResult(action,moved,blocked){
  if(!moved&&blocked){toast("目标会越出 mother/World 边界","err");return;}
  if(!moved){toast(`没有组件需要 ${action}`,"err");return;}
  toast(blocked?`已${action} ${moved} 个,阻止 ${blocked} 个越界`:`已${action} ${moved} 个组件`);
}
function move3DSelection(){
  const comps=selectedEditable3D(true);
  if(!comps.length){toast("先选中可移动组件","err");return;}
  syncTransformConstraintFromUI();
  const delta=[
    Number(document.getElementById("move3dDx")?.value||0),
    Number(document.getElementById("move3dDy")?.value||0),
    Number(document.getElementById("move3dDz")?.value||0),
  ];
  if(delta.some(v=>!Number.isFinite(v))){toast("3D 位移无效","err");return;}
  if(delta.every(v=>Math.abs(v)<1e-12)){toast("3D 位移为 0","err");return;}
  let moved=0,blocked=0;
  for(const c of comps){
    const result=translateComp3DConstrained(c,delta);
    if(result.changed)moved++;
    if(result.blocked)blocked++;
  }
  if(!moved){report3DTransformResult("移动",moved,blocked);return;}
  drawComponents();renderEdit();renderList();refreshSelectionSummary();updateModelHealth();draw3DPreview();pushHistory();
  report3DTransformResult("移动",moved,blocked);
}
function apply3DSizeToSelection(){
  const comps=selectedEditable3D(false);
  if(!comps.length){toast("先选中可改尺寸的 box 组件","err");return;}
  syncTransformConstraintFromUI();
  const target={
    dx:Number(document.getElementById("target3dDx")?.value||0),
    dy:Number(document.getElementById("target3dDy")?.value||0),
    dz:Number(document.getElementById("target3dDz")?.value||0),
  };
  if(Object.values(target).some(v=>!Number.isFinite(v)||v<=0)){toast("3D 目标尺寸无效","err");return;}
  let changed=0,blocked=0;
  for(const c of comps){
    if(!transformFitsContainer(c,bboxForResizedBox(c,target))){blocked++;continue;}
    c.dimensions.dx=target.dx;
    c.dimensions.dy=target.dy;
    c.dimensions.dz=target.dz;
    changed++;
  }
  if(!changed){report3DTransformResult("改尺寸",changed,blocked);return;}
  drawComponents();renderEdit();renderList();refreshSelectionSummary();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已更新 ${changed} 个 box 尺寸,阻止 ${blocked} 个越界`:`已更新 ${changed} 个 box 尺寸`);
}
function set3DCenterForSelection(){
  const comps=selectedEditable3D(true);
  if(!comps.length){toast("先选中可定位组件","err");return;}
  syncTransformConstraintFromUI();
  const raw=[
    document.getElementById("center3dX")?.value,
    document.getElementById("center3dY")?.value,
    document.getElementById("center3dZ")?.value,
  ];
  const targets=raw.map(v=>String(v??"").trim()===""?null:Number(v));
  if(targets.every(v=>v===null)){toast("至少填写一个 3D 中心坐标","err");return;}
  if(targets.some(v=>v!==null&&!Number.isFinite(v))){toast("3D 中心坐标无效","err");return;}
  let moved=0,blocked=0;
  for(const c of comps){
    const box=bbox3D(c);
    const center=box.min.map((v,i)=>(v+box.max[i])/2);
    const delta=[0,0,0];
    for(let i=0;i<3;i++)if(targets[i]!==null)delta[i]=targets[i]-center[i];
    const result=translateComp3DConstrained(c,delta);
    if(result.changed)moved++;
    if(result.blocked)blocked++;
  }
  if(!moved){report3DTransformResult("定位",moved,blocked);return;}
  drawComponents();renderEdit();renderList();refreshSelectionSummary();updateModelHealth();draw3DPreview();pushHistory();
  report3DTransformResult("定位",moved,blocked);
}

/* ---------- 缩放手柄 ---------- */
function onShapeTransform(c){
  const n=rectNodes.get(c.component_id);if(!n)return;
  if(c.polygon){/* 多边形不支持手柄缩放,跳过(保留矩形才进 Transformer)*/ tr.nodes([]);return;}
  syncTransformConstraintFromUI();
  const r=n.shape;
  const newW=r.width()*r.scaleX(),newH=r.height()*r.scaleY();
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const nextPos=c.placement.position.slice();
  const nextLat=toDataX(r.x()+Math.max(newW,1)/2);
  const nextDep=toDataY(r.y()+Math.max(newH,1)/2);
  nextPos[li]=nextLat;nextPos[di]=nextDep;
  const nextLatSize=Math.max(newW,1)/camera.sLat,nextDepSize=Math.max(newH,1)/camera.sDep;
  if(!transformFitsContainer(c,projectedBoxEditBBox(c,nextPos,nextLatSize,nextDepSize,li,di))){
    r.scaleX(1);r.scaleY(1);
    const dLat=c.dimensions[DIM_KEY[axes.lateral]]||0,dDep=c.dimensions[DIM_KEY[axes.depth]]||0;
    r.width(Math.max(dLat*camera.sLat,0.01));r.height(Math.max(dDep*camera.sDep,0.01));
    r.x(X(c.placement.position[li])-r.width()/2);r.y(Y(c.placement.position[di])-r.height()/2);
    toast("目标会越出 mother/World 边界","err");
    return;
  }
  r.width(Math.max(newW,1));r.height(Math.max(newH,1));r.scaleX(1);r.scaleY(1);
  c.dimensions[DIM_KEY[axes.lateral]]=nextLatSize;
  c.dimensions[DIM_KEY[axes.depth]]=nextDepSize;
  c.placement.position[li]=nextLat;
  c.placement.position[di]=nextDep;
  moveLabels(n,c);renderEditValues(c);refreshSelectionSummary();refreshAnnotationViews();
}
/* 多边形拖动落位:把 Konva position 偏移转回 polygon 数据 */
function onShapeDragEnd(c){
  if(!(c.polygon&&polygonAxesMatch(c)))return;
  const n=rectNodes.get(c.component_id);if(!n)return;
  const shape=n.shape;
  const dxPx=shape.x(),dyPx=shape.y();
  const dLat=dxPx/camera.sLat,dDep=-dyPx/camera.sDep;
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  if(dLat||dDep){
    syncTransformConstraintFromUI();
    const delta=[0,0,0];delta[li]=dLat;delta[di]=dDep;
    if(!transformFitsContainer(c,bboxTranslated3D(bbox3D(c),delta))){
      shape.position({x:0,y:0});
      const pts=[];for(const p of c.polygon)pts.push(X(p[li]),Y(p[di]));
      shape.points(pts);
      toast("目标会越出 mother/World 边界","err");
      compLayer.batchDraw();uiLayer.batchDraw();
      return;
    }
    for(const p of c.polygon){p[li]+=dLat;p[di]+=dDep;}
  }
  shape.position({x:0,y:0});
  const pts=[];for(const p of c.polygon)pts.push(X(p[li]),Y(p[di]));
  shape.points(pts);
  moveLabels(n,c);drawPolyAnchors();renderEditValues(c);refreshSelectionSummary();refreshAnnotationViews();
  compLayer.batchDraw();uiLayer.batchDraw();
}

/* ---------- 双击:加多边形节点 ---------- */
function onShapeDblClick(id,e){
  const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c))return;
  // 用 layer 相对坐标(已反 stage 缩放/平移),与 camera 坐标系一致
  const pos=compLayer.getRelativePointerPosition();if(!pos)return;
  const lat=toDataX(pos.x),dep=toDataY(pos.y);
  // 首次:从矩形生成多边形(轴正确映射的 4 顶点)
  if(!c.polygon){
    c.polygon=makeRectPolygon(c);
    c.polygonAxes={lateral:axes.lateral,depth:axes.depth};
    c.geometry_type="polycone";
  }
  if(!polygonAxesMatch(c)){toast(`多边形定义在 ${c.polygonAxes.lateral}×${c.polygonAxes.depth},切到该截面再编辑`,"err");return;}
  // 新顶点投影到最近边(初始不变形,用户再拖出台阶)
  const inserted=insertPolyNodeNear(c,lat,dep);
  if(!inserted){toast("双击组件边界附近才能加节点","err");drawComponents();return;}
  polyEditId=id;selectedIds=new Set([id]);primaryId=id;
  drawComponents();pushHistory();
  toast(`已加节点(共 ${c.polygon.length} 个),拖紫色点变形,双击点删除`);
}
/* 把矩形按当前轴映射成 4 顶点(每个顶点为 [x,y,z],含正确第三轴) */
function makeRectPolygon(c){
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const dLat=c.dimensions[DIM_KEY[axes.lateral]]||0,dDep=c.dimensions[DIM_KEY[axes.depth]]||0;
  const p=c.placement.position;
  const corners=[[-0.5,-0.5],[0.5,-0.5],[0.5,0.5],[-0.5,0.5]];
  return corners.map(([fl,fd])=>{
    const v=[p[0],p[1],p[2]];
    v[li]=p[li]+fl*dLat; v[di]=p[di]+fd*dDep;
    return v;
  });
}
function centerThird(c){const m={x:0,y:1,z:2};const other=["x","y","z"].find(a=>a!==axes.lateral&&a!==axes.depth);return c.placement.position[m[other]];}
function insertPolyNodeNear(c,lat,dep){
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const thirdIdx=3-li-di;   // 第三轴索引(0+1+2=3)
  const third=centerThird(c);
  let bestI=0,bestD=Infinity,bestProj=null;
  const n=c.polygon.length;
  for(let i=0;i<n;i++){const a=c.polygon[i],b=c.polygon[(i+1)%n];
    const pr=projectOnSeg(lat,dep,a[li],a[di],b[li],b[di]);
    if(pr.dist<bestD){bestD=pr.dist;bestI=i;bestProj=pr;}
  }
  const b=polyBBox(c);
  const edgeTol=(Math.max(6,snapPx())/Math.max(camera.sLat,camera.sDep,1e-9));
  if(bestD>edgeTol)return false;
  const np=[0,0,0]; np[li]=bestProj.x; np[di]=bestProj.y; np[thirdIdx]=third;
  c.polygon.splice(bestI+1,0,np);
  return true;
}
function projectOnSeg(px,py,ax,ay,bx,by){
  const dx=bx-ax,dy=by-ay,l2=dx*dx+dy*dy;
  if(l2===0)return{x:ax,y:ay,dist:Math.hypot(px-ax,py-ay)};
  let t=((px-ax)*dx+(py-ay)*dy)/l2;t=Math.max(0,Math.min(1,t));
  const x=ax+t*dx,y=ay+t*dy;return{x,y,dist:Math.hypot(px-x,py-y)};
}
function removePolyNode(id,idx){
  const c=model.components.find(c=>c.component_id===id);if(!c||!c.polygon)return;
  if(c.polygon.length<=3){toast("多边形至少 3 个顶点","err");return;}
  c.polygon.splice(idx,1);drawComponents();renderList();pushHistory();
}

/* 工具栏:进入"加节点"模式(提示双击) */
function addPolygonNodeMode(){
  if(selectedIds.size!==1){toast("先选中一个组件,再双击它的边加节点","err");return;}
  const c=model.components.find(c=>c.component_id===primaryId);
  if(c.polygon){toast("已是多边形,双击边继续加节点,双击紫点删除");return;}
  toast("已选中 "+c.display_name+" → 双击它的任意位置加第一个节点");
}

/* ---------- 对齐 / 居中 ---------- */
function setAlignRef(r){alignRef=r;document.getElementById("alignRef_bbox").classList.toggle("on",r==="bbox");document.getElementById("alignRef_world").classList.toggle("on",r==="world");}
function alignSel(mode){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  // 计算参考边界
  let ref;
  if(alignRef==="world"||selectedIds.size===1){
    const db=dataBounds(); // 注意:含 world,可能很大。world 居中更合理用 world 组件中心。
    const w=model.components.find(c=>isWorld(c));
    if(w){ref={minLat:w.placement.position[li]-(w.dimensions[DIM_KEY[axes.lateral]]||0)/2,maxLat:w.placement.position[li]+(w.dimensions[DIM_KEY[axes.lateral]]||0)/2,minDep:w.placement.position[di]-(w.dimensions[DIM_KEY[axes.depth]]||0)/2,maxDep:w.placement.position[di]+(w.dimensions[DIM_KEY[axes.depth]]||0)/2};}
    else{ref={minLat:db.minLat,maxLat:db.maxLat,minDep:db.minDep,maxDep:db.maxDep};}
  } else {
    // 选中集 bbox
    let mL=Infinity,ML=-Infinity,mD=Infinity,MD=-Infinity;
    for(const id of selectedIds){const c=model.components.find(c=>c.component_id===id);if(!c)continue;const b=bboxOf(c);mL=Math.min(mL,b.minLat);ML=Math.max(ML,b.maxLat);mD=Math.min(mD,b.minDep);MD=Math.max(MD,b.maxDep);}
    ref={minLat:mL,maxLat:ML,minDep:mD,maxDep:MD};
  }
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c))continue;
    const b=bboxOf(c);
    const cLat=(b.minLat+b.maxLat)/2,cDep=(b.minDep+b.maxDep)/2;
    let dLat=0,dDep=0;
    switch(mode){
      case"left":dLat=ref.minLat-b.minLat;break;
      case"right":dLat=ref.maxLat-b.maxLat;break;
      case"hcenter":dLat=(ref.minLat+ref.maxLat)/2-cLat;break;
      case"top":dDep=ref.maxDep-b.maxDep;break;       // top=深度大的一侧
      case"bottom":dDep=ref.minDep-b.minDep;break;
      case"vcenter":dDep=(ref.minDep+ref.maxDep)/2-cDep;break;
    }
    translateComp(c,dLat,dDep);
  }
  fitCameraNotZoom();drawComponents();pushHistory();toast("已对齐: "+modeLabel(mode));
}
function modeLabel(m){return{left:"左对齐",right:"右对齐",hcenter:"水平居中",top:"顶对齐",bottom:"底对齐",vcenter:"垂直居中"}[m]||m;}
function boxFeatureValue(box,axisIdx,feature){
  if(feature==="min")return box.min[axisIdx];
  if(feature==="max")return box.max[axisIdx];
  return (box.min[axisIdx]+box.max[axisIdx])/2;
}
function align3DSelection(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  syncTransformConstraintFromUI();
  const axis=document.getElementById("align3dAxis")?.value||"z";
  const feature=document.getElementById("align3dFeature")?.value||"center";
  const refMode=document.getElementById("align3dRef")?.value||"world";
  const idx=AXIS_IDX[axis];
  if(idx===undefined||!["min","center","max"].includes(feature)){toast("3D 对齐参数无效","err");return;}
  let refComp=null;
  if(refMode==="primary"){
    refComp=model.components.find(c=>c.component_id===primaryId&&selectedIds.has(c.component_id));
    if(!refComp){toast("主选组件不存在","err");return;}
  }else{
    refComp=model.components.find(c=>isWorld(c)&&!c.hidden);
    if(!refComp){toast("没有可用 World 参考","err");return;}
  }
  const refValue=boxFeatureValue(bbox3D(refComp),idx,feature);
  let moved=0,blocked=0;
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);
    if(!c||isWorld(c)||c.locked)continue;
    if(refMode==="primary"&&c.component_id===refComp.component_id)continue;
    const current=boxFeatureValue(bbox3D(c),idx,feature);
    const delta=[0,0,0];delta[idx]=refValue-current;
    if(Math.abs(delta[idx])<1e-12)continue;
    const result=translateComp3DConstrained(c,delta);
    if(result.changed)moved++;
    if(result.blocked)blocked++;
  }
  if(!moved){report3DTransformResult("3D 对齐",moved,blocked);return;}
  drawComponents();renderEdit();renderList();refreshSelectionSummary();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已 3D 对齐 ${moved} 个组件,阻止 ${blocked} 个越界`:`已 3D 对齐 ${moved} 个组件`);
}
function place3DFeatureSelection(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  syncTransformConstraintFromUI();
  const axis=document.getElementById("place3dAxis")?.value||"z";
  const feature=document.getElementById("place3dFeature")?.value||"center";
  const target=Number(document.getElementById("place3dTarget")?.value);
  const idx=AXIS_IDX[axis];
  if(idx===undefined||!["min","center","max"].includes(feature)||!Number.isFinite(target)){toast("3D 特征目标无效","err");return;}
  let moved=0,blocked=0;
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);
    if(!c||isWorld(c)||c.locked)continue;
    const current=boxFeatureValue(bbox3D(c),idx,feature);
    const delta=[0,0,0];delta[idx]=target-current;
    if(Math.abs(delta[idx])<1e-12)continue;
    const result=translateComp3DConstrained(c,delta);
    if(result.changed)moved++;
    if(result.blocked)blocked++;
  }
  if(!moved){report3DTransformResult("定位",moved,blocked);return;}
  drawComponents();renderEdit();renderList();refreshSelectionSummary();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已定位 ${moved} 个 3D 特征,阻止 ${blocked} 个越界`:`已定位 ${moved} 个 3D 特征`);
}
function distributeSelection3DGapsPlan(axis){
  if(!model)return {ok:false,reason:"missing_model"};
  const ax=AXIS_IDX[axis]===undefined?(document.getElementById("distribute3dAxis")?.value||"x"):axis;
  const idx=AXIS_IDX[ax];
  const comps=selectedComponents([...selectedIds],false);
  if(comps.length<3)return {ok:false,reason:"need_three"};
  syncTransformConstraintFromUI();
  const items=comps.map(c=>({component:c,box:bbox3D(c)}))
    .sort((a,b)=>(a.box.min[idx]-b.box.min[idx])||(a.box.max[idx]-b.box.max[idx])||a.component.component_id.localeCompare(b.component.component_id));
  const first=items[0],last=items[items.length-1];
  const totalSpan=last.box.max[idx]-first.box.min[idx];
  const totalSize=items.reduce((sum,item)=>sum+(item.box.max[idx]-item.box.min[idx]),0);
  const gap=normalizeNumber((totalSpan-totalSize)/(items.length-1));
  if(gap<0)return {ok:false,reason:"negative_gap",axis:ax,gap};
  const moves=[];
  let cursor=first.box.max[idx]+gap;
  for(let i=1;i<items.length-1;i++){
    const item=items[i],c=item.component;
    if(c.locked)return {ok:false,reason:"locked",id:c.component_id,axis:ax};
    const targetMin=normalizeNumber(cursor);
    const deltaValue=normalizeNumber(targetMin-item.box.min[idx]);
    const delta=[0,0,0];delta[idx]=deltaValue;
    if(!transformFitsContainer(c,bboxTranslated3D(item.box,delta))){
      return {ok:false,reason:"no_target",id:c.component_id,axis:ax,delta};
    }
    moves.push({id:c.component_id,delta,targetMin});
    cursor=targetMin+(item.box.max[idx]-item.box.min[idx])+gap;
  }
  return {
    ok:true,
    axis:ax,
    gap,
    ids:items.map(item=>item.component.component_id),
    anchorIds:[first.component.component_id,last.component.component_id],
    moves,
  };
}
function distribute3DFailureMessage(reason){
  return {
    need_three:"需至少选中 3 个当前截面组件",
    locked:"中间组件已锁定",
    negative_gap:"选区端点空间不足,无法等间隙分布",
    no_target:"分布结果会越出 mother/World 边界",
  }[reason]||"无法等间隙分布";
}
function distributeSelection3DGaps(axis){
  const result=distributeSelection3DGapsPlan(axis);
  if(!result.ok){toast(distribute3DFailureMessage(result.reason),"err");return result;}
  let moved=0;
  for(const move of result.moves){
    const c=model.components.find(c=>c.component_id===move.id);
    if(!c)continue;
    if(move.delta.some(v=>Math.abs(v)>1e-12)){
      translateComp3D(c,move.delta);
      moved++;
    }
  }
  drawComponents();refreshSelectionViews();renderAnnotationsPanel();updateModelHealth();draw3DPreview();pushHistory();
  toast(`已沿 ${result.axis} 等间隙分布 ${moved} 个组件,间隙 ${fmtProbeNumber(result.gap)} μm`);
  return {...result,moved};
}
function distributeSelection3DGapsFromUI(){
  const axis=document.getElementById("distribute3dAxis")?.value||"x";
  return distributeSelection3DGaps(axis);
}

/* ---------- 布尔操作 ---------- */
function compToRing(c){
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  let pts3=[];
  if(c.polygon){if(!polygonAxesMatch(c))return null;pts3=c.polygon;}
  else{pts3=makeRectPolygon(c);}
  return pts3.map(p=>[p[li],p[di]]);
}
/* ---------- 当前截面投影提示(不是 3D 模型错误) ---------- */
function ringBBox(ring){let x0=Infinity,x1=-Infinity,y0=Infinity,y1=-Infinity;for(const[x,y]of ring){x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);}return{minX:x0,maxX:x1,minY:y0,maxY:y1};}
function bboxIntersect(a,b){return !(a.maxX<b.minX||b.maxX<a.minX||a.maxY<b.minY||b.maxY<a.minY);}
let lastOverlapIds=new Set();
let overlapCache={key:"",value:{pairs:[],regions:[],ids:new Set()}};
function overlapSignature(){
  if(!model)return "";
  return JSON.stringify({axes:[axes.lateral,axes.depth],slice:sliceState,components:sectionComponents(false).map(c=>({id:c.component_id,box:bbox3D(c),poly:c.polygon||null,pos:c.placement.position,d:c.dimensions,m:c.mother_volume}))});
}
function thirdAxisOverlaps(a,b){
  const third=sliceAxis();
  const idx=AXIS_IDX[third];
  const ab=bbox3D(a),bb=bbox3D(b);
  const eps=1e-9;
  return ab.min[idx]<bb.max[idx]-eps&&ab.max[idx]>bb.min[idx]+eps;
}
function detectSectionOverlaps(){
  const sig=overlapSignature();
  if(sig===overlapCache.key)return overlapCache.value;
  const pairs=[],regions=[],ids=new Set();
  const comps=model?sectionComponents(false):[];
  for(let i=0;i<comps.length;i++)for(let j=i+1;j<comps.length;j++){
    const a=comps[i],b=comps[j];
    if(a.mother_volume&&b.mother_volume&&a.mother_volume!==b.mother_volume)continue;
    if(!thirdAxisOverlaps(a,b))continue;
    const ra=compToRing(a),rb=compToRing(b);
    if(!ra||!rb)continue;
    if(!bboxIntersect(ringBBox(ra),ringBBox(rb)))continue;
    let inter;try{inter=polygonClipping.intersection([ra],[rb]);}catch(e){continue;}
    if(inter&&inter.length){
      pairs.push([a.component_id,b.component_id]);
      ids.add(a.component_id);ids.add(b.component_id);
      inter.forEach(p=>{if(p[0]&&p[0].length>=3)regions.push(p[0]);});
    }
  }
  lastOverlapIds=ids;
  overlapCache={key:sig,value:{pairs,regions,ids}};
  return overlapCache.value;
}
function drawOverlapRegions(regions){
  overlapGroup.destroyChildren();
  for(const ring of regions){
    const pts=[];for(const[x,y]of ring)pts.push(X(x),Y(y));
    const xs=pts.filter((_,i)=>i%2===0),ys=pts.filter((_,i)=>i%2===1);
    const sw=sectionStrokeWidth(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),{overlap:true});
    overlapGroup.add(new Konva.Line({points:pts,closed:true,fill:"rgba(183,121,31,.12)",stroke:"#b7791f",strokeWidth:sw,dash:sw?[3,2]:undefined,listening:false}));
  }
  overlapGroup.moveToTop();
  uiLayer.batchDraw();
}
function updateOverlapHUD(n){
  const el=document.getElementById("hudOverlap");
  if(!el)return;
  if(n>0){el.style.display="";el.innerHTML=`截面投影 ${n}`;el.style.cssText="display:inline;padding:3px 7px;background:#fffbeb;color:#92400e;border:1px solid #fde68a;border-radius:999px;font-family:var(--mono);font-size:11px;font-weight:600";}
  else{el.style.display="none";}
}
function updateSliceUI(){
  const axis=sliceAxis();
  const axisLabel=document.getElementById("sliceAxisLabel");
  const badge=document.getElementById("sliceBadge");
  const enabled=document.getElementById("sliceEnabled");
  const pos=document.getElementById("slicePos");
  const thickness=document.getElementById("sliceThickness");
  if(axisLabel)axisLabel.textContent=axis;
  if(enabled)enabled.checked=!!sliceState.enabled;
  if(pos&&document.activeElement!==pos)pos.value=sliceState.pos;
  if(thickness&&document.activeElement!==thickness)thickness.value=sliceState.thickness;
  if(!badge)return;
  if(sliceState.enabled){
    const s=sliceBounds();
    badge.style.display="";
    badge.innerHTML=`剖切 ${s.axis}=${fmt(s.pos)} · 厚${fmt(s.thickness)} μm · ±${fmt(s.thickness/2)}`;
    badge.style.cssText="display:inline;padding:3px 7px;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:999px;font-family:var(--mono);font-size:11px;font-weight:600";
  }else{
    badge.style.display="none";
  }
}
function onSliceSettingsChange(){
  sliceState.enabled=!!document.getElementById("sliceEnabled")?.checked;
  sliceState.pos=Number(document.getElementById("slicePos")?.value||0);
  sliceState.thickness=Math.max(0,Number(document.getElementById("sliceThickness")?.value||0));
  updateSliceUI();
  updateStackUI();
  if(!model)return;
  selectedIds=new Set([...selectedIds].filter(id=>{
    const c=model.components.find(c=>c.component_id===id);
    return c&&visibleInCurrentSection(c);
  }));
  primaryId=[...selectedIds][0]||null;
  polyEditId=null;
  resetView();renderList();renderEdit();updateCadStatus();updateModelHealth();draw3DPreview();
}
function updateDrcUI(){
  if(!DRC_RULE_DECKS[drcSettings.ruleDeck])drcSettings.ruleDeck="custom";
  const deck=document.getElementById("drcRuleDeck");
  if(deck&&deck.value!==drcSettings.ruleDeck)deck.value=drcSettings.ruleDeck;
  const minGap=document.getElementById("minGapDrc");
  if(minGap&&document.activeElement!==minGap)minGap.value=drcSettings.minGap;
}
function applyDrcSettingsChanged(){
  updateDrcUI();
  updateModelHealth();
  renderStackInspector();
  drawComponents();
}
function onDrcRuleDeckChange(){
  const deck=document.getElementById("drcRuleDeck")?.value||"custom";
  drcSettings.ruleDeck=DRC_RULE_DECKS[deck]?deck:"custom";
  const preset=DRC_RULE_DECKS[drcSettings.ruleDeck];
  if(preset&&preset.minGap!==null)drcSettings.minGap=Math.max(0,Number(preset.minGap)||0);
  applyDrcSettingsChanged();
}
function onDrcSettingsChange(){
  drcSettings.minGap=Math.max(0,Number(document.getElementById("minGapDrc")?.value||0));
  drcSettings.ruleDeck="custom";
  applyDrcSettingsChanged();
}

/* ---------- 3D 模型检查 ---------- */
function detect3DOverlaps(){
  return detectOverlaps3D(model?sectionComponents(false):[]);
}
function detectSmallGaps3D(){
  const minGap=Math.max(0,Number(drcSettings.minGap)||0);
  if(!model||minGap<=0)return [];
  return detectSmallGaps3DCore(sectionComponents(false),sliceAxis(),minGap);
}
function stackAxis(){
  return stackAxisMode==="auto"?sliceAxis():stackAxisMode;
}
function updateStackUI(){
  const axisSel=document.getElementById("stackAxis");
  if(axisSel&&axisSel.value!==stackAxisMode)axisSel.value=stackAxisMode;
  const axisLabel=document.getElementById("stackAxisResolved");
  if(axisLabel)axisLabel.textContent=stackAxis();
}
function collectStackIntervals(axis=stackAxis()){
  return model?stackIntervals3D(sectionComponents(false),axis):[];
}
function collectStackRelations(axis=stackAxis()){
  return stackRelations3D(collectStackIntervals(axis),axis,{minGap:drcSettings.minGap,format:fmt});
}
function renderStackInspector(){
  const axisSel=document.getElementById("stackAxis"),list=document.getElementById("stackList");
  if(!axisSel||!list)return;
  updateStackUI();
  const axis=stackAxis();
  if(!model){
    list.innerHTML='<div class="stack-empty">载入模型后显示真实 3D 层栈。</div>';
    return;
  }
  const rows=collectStackIntervals(axis);
  const rels=collectStackRelations(axis);
  if(!rows.length){
    list.innerHTML='<div class="stack-empty">当前截面没有可见实体。</div>';
    return;
  }
  const relationBefore=new Map(rels.map(r=>[r.b.component.component_id,r]));
  list.innerHTML=rows.map(row=>{
    const c=row.component;
    const rel=relationBefore.get(c.component_id);
    const selected=selectedIds.has(c.component_id)?" selected":"";
    const relHtml=rel?renderStackRelation(rel):"";
    const title=`${axis}: ${fmt(row.min)} → ${fmt(row.max)} μm`;
    return `${relHtml}<button class="stack-row${selected}" data-cid="${esc(c.component_id)}" onclick="selectOnly(this.dataset.cid)" title="${esc(title)}">
      <span class="stack-swatch" style="background:${isWorld(c)?"transparent":esc(matColor(c.material_id))}"></span>
      <span class="stack-main"><b>${esc(c.display_name)}</b><small>${esc(c.component_id)} · ${esc(c.material_id||"")}</small></span>
      <span class="stack-span"><b>${fmt(row.thickness)} μm</b><small>${fmt(row.min)}…${fmt(row.max)}</small></span>
    </button>`;
  }).join("");
}
function stackRelationKey(rel){
  return JSON.stringify([rel.axis,rel.a.component.component_id,rel.b.component.component_id,rel.kind]);
}
function renderStackRelation(rel){
  const key=esc(stackRelationKey(rel));
  const kind=esc(rel.kind);
  const fixable=rel.kind==="small_gap"||rel.kind==="overlap";
  const adjustable=rel.overlapsOtherAxes&&rel.kind!=="overlap"&&rel.kind!=="off_axis";
  const actions=[
    `<button class="stack-action" data-action="select" data-kind="${kind}" onclick="event.stopPropagation();selectStackRelation(this.closest('.stack-relation').dataset.rel)">选择</button>`,
  ];
  if(adjustable&&Math.abs(rel.rawGap)>1e-9)actions.push(`<button class="stack-action" data-action="touch" data-kind="${kind}" onclick="event.stopPropagation();setStackRelationGap(this.closest('.stack-relation').dataset.rel,0)" title="沿该层栈轴设为接触">接触</button>`);
  if(adjustable&&Math.max(0,Number(drcSettings.minGap)||0)>0)actions.push(`<button class="stack-action" data-action="drc-gap" data-kind="${kind}" onclick="event.stopPropagation();setStackRelationGap(this.closest('.stack-relation').dataset.rel,drcSettings.minGap)" title="沿该层栈轴设为当前 DRC 间隙">规则间隙</button>`);
  if(fixable)actions.push(`<button class="stack-action" data-action="fix" data-kind="${kind}" onclick="event.stopPropagation();fixStackRelation(this.closest('.stack-relation').dataset.rel)" title="按当前层栈关系修复">修复</button>`);
  const title=`${rel.axis}: ${rel.a.component.display_name} → ${rel.b.component.display_name}`;
  return `<div class="stack-relation ${rel.severity}" data-rel="${key}" data-kind="${kind}" onclick="selectStackRelation(this.dataset.rel)" title="${esc(title)}">
    <span>${esc(rel.label)}</span>
    <span class="stack-relation-actions">
      ${actions.join("")}
    </span>
  </div>`;
}
function findStackRelationByKey(key){
  return collectStackRelations().find(rel=>stackRelationKey(rel)===key)||null;
}
function selectStackRelation(key){
  if(!model)return;
  const rel=findStackRelationByKey(key);
  if(!rel){toast("层栈关系已变化","err");renderStackInspector();return;}
  selectedIds=new Set([rel.a.component.component_id,rel.b.component.component_id]);
  primaryId=rel.b.component.component_id;
  polyEditId=null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();focusSelection();draw3DPreview();
}
function stackRelationIssue(rel){
  if(rel.kind==="small_gap"){
    return makeIssue("warn","small_gap3d",`3D 间隙过小(${rel.axis}): ${rel.a.component.display_name} / ${rel.b.component.display_name} = ${fmt(rel.gap)} μm < ${fmt(drcSettings.minGap)} μm`,[rel.a.component.component_id,rel.b.component.component_id]);
  }
  if(rel.kind==="overlap"){
    return makeIssue("err","overlap3d",`3D 包围盒重叠: ${rel.a.component.display_name} / ${rel.b.component.display_name}`,[rel.a.component.component_id,rel.b.component.component_id]);
  }
  return null;
}
function fixStackRelation(key){
  if(!model)return;
  const rel=findStackRelationByKey(key);
  if(!rel){toast("层栈关系已变化","err");renderStackInspector();return;}
  const issue=stackRelationIssue(rel);
  if(!issue){selectStackRelation(key);return;}
  const result=applyIssueFix(issue,{axis:rel.axis});
  if(!result.ok){
    const reason={unsupported:"该层栈关系暂无自动修复",missing_component:"关联组件不存在",locked:"目标组件不可自动移动",oversize:"组件大于容器,无法仅靠平移修复",no_target:"未找到可用修复位置",no_delta:"无法计算修复位移"}[result.reason]||"修复失败";
    toast(reason,"err");updateModelHealth();return;
  }
  const fixed=model.components.find(c=>c.component_id===result.id);
  selectedIds=new Set([result.id]);
  primaryId=result.id;
  polyEditId=(fixed&&fixed.polygon&&polygonAxesMatch(fixed))?fixed.component_id:null;
  drawComponents();refreshSelectionViews();updateModelHealth();draw3DPreview();pushHistory();
  toast(`已沿 ${result.axis} 轴修复 ${fixed.display_name}`);
}
function stackActionFailureMessage(reason){
  return {unsupported:"该层栈关系不能直接设定间隙",missing_component:"关联组件不存在",locked:"目标组件不可自动移动",oversize:"组件大于容器,无法仅靠平移修复",no_target:"目标间隙会越出容器",no_delta:"当前已经满足目标间隙"}[reason]||"操作失败";
}
function setStackRelationGap(key,targetGap){
  if(!model)return;
  const rel=findStackRelationByKey(key);
  if(!rel){toast("层栈关系已变化","err");renderStackInspector();return;}
  const result=applyRelationGapAdjustment(rel,targetGap);
  if(!result.ok){
    toast(stackActionFailureMessage(result.reason),"err");
    updateModelHealth();
    return;
  }
  const fixed=model.components.find(c=>c.component_id===result.id);
  selectedIds=new Set([result.id]);
  primaryId=result.id;
  polyEditId=(fixed&&fixed.polygon&&polygonAxesMatch(fixed))?fixed.component_id:null;
  drawComponents();refreshSelectionViews();updateModelHealth();draw3DPreview();pushHistory();
  toast(`已沿 ${result.axis} 轴设为 ${fmt(result.targetGap)} μm 间隙`);
}
function onStackAxisChange(){
  const v=document.getElementById("stackAxis")?.value||"auto";
  stackAxisMode=["auto","x","y","z"].includes(v)?v:"auto";
  renderStackInspector();
  pushHistory();
}
function makeIssue(kind,code,text,ids=[]){
  const cleanIds=[...new Set(ids.filter(Boolean))];
  return {id:`${code}:${cleanIds.join("+")}:${text}`.replace(/\s+/g,"_"),kind,code,text,ids:cleanIds};
}
function issueSignature(issue){
  if(!issue)return "";
  const ids=[...new Set((issue.ids||[]).filter(Boolean))].sort();
  return `${issue.code||"issue"}:${ids.join("+")}`;
}
function normalizeDrcWaivers(items){
  const bySignature=new Map();
  for(const item of items||[]){
    const signature=String(item&&item.signature||"").trim();
    if(!signature)continue;
    const reason=String(item.reason||"已确认可接受").trim().slice(0,240)||"已确认可接受";
    const code=String(item.code||signature.split(":")[0]||"issue");
    const ids=Array.isArray(item.ids)?item.ids.map(String).filter(Boolean):[];
    const waivedAt=String(item.waivedAt||new Date().toISOString());
    bySignature.set(signature,{signature,code,ids,reason,waivedAt});
  }
  return [...bySignature.values()];
}
function serializeDrcWaivers(){
  drcWaivers=normalizeDrcWaivers(drcWaivers);
  return JSON.parse(JSON.stringify(drcWaivers));
}
function drcWaiverBySignature(signature){
  if(!signature)return null;
  drcWaivers=normalizeDrcWaivers(drcWaivers);
  return drcWaivers.find(w=>w.signature===signature)||null;
}
function isIssueWaived(issue){
  return !!drcWaiverBySignature(issueSignature(issue));
}
function waiveIssue(issueId,reason){
  if(!model)return false;
  const issue=typeof issueId==="object"?issueId:collectModelIssues().issues.find(i=>i.id===issueId);
  if(!issue){toast("检查项已变化,请重新检查","err");updateModelHealth();return false;}
  const signature=issueSignature(issue);
  const existing=drcWaiverBySignature(signature);
  let waiverReason=reason;
  if(waiverReason===undefined){
    waiverReason=prompt("豁免理由:",existing?existing.reason:"已确认可接受");
    if(waiverReason===null)return false;
  }
  waiverReason=String(waiverReason||"已确认可接受").trim().slice(0,240)||"已确认可接受";
  const waiver={signature,code:issue.code,ids:(issue.ids||[]).slice(),reason:waiverReason,waivedAt:existing?existing.waivedAt:new Date().toISOString()};
  drcWaivers=drcWaivers.filter(w=>w.signature!==signature);
  drcWaivers.push(waiver);
  issueBrowserState.filter=issueBrowserState.filter==="waived"?"waived":"all";
  updateModelHealth();
  pushHistory();
  toast("已豁免检查项");
  return true;
}
function revokeIssueWaiver(signature){
  const sig=String(signature||"").trim();
  const before=drcWaivers.length;
  drcWaivers=drcWaivers.filter(w=>w.signature!==sig);
  const changed=before!==drcWaivers.length;
  if(changed){
    updateModelHealth();
    pushHistory();
    toast("已撤销豁免");
  }
  return changed;
}
function collectModelIssues(){
  if(!model)return {issues:[],overlaps:{pairs:[],ids:new Set()}};
  const issues=[];
  const ids=new Set();
  const worlds=model.components.filter(c=>isWorld(c)&&!c.hidden);
  for(const c of sectionComponents(true)){
    if(ids.has(c.component_id))issues.push(makeIssue("err","duplicate_id",`重复 component_id: ${c.component_id}`,[c.component_id]));
    ids.add(c.component_id);
    if(!String(c.material_id||"").trim()&&!isWorld(c))issues.push(makeIssue("warn","missing_material",`${c.display_name} 缺少 material_id`,[c.component_id]));
    if(!c.polygon&&!isWorld(c)){
      const d=[c.dimensions.dx,c.dimensions.dy,c.dimensions.dz];
      if(d.some(v=>!Number.isFinite(v)||v<=0))issues.push(makeIssue("warn","bad_dimensions",`${c.display_name} 有非正 3D 尺寸`,[c.component_id]));
    }
    if(c.mother_volume&&c.mother_volume!==c.component_id&&!ids.has(c.mother_volume)&&!model.components.some(x=>x.component_id===c.mother_volume)){
      issues.push(makeIssue("warn","missing_mother",`${c.display_name} 的 mother_volume 不存在: ${c.mother_volume}`,[c.component_id]));
    }
  }
  if(worlds.length===0)issues.push(makeIssue("warn","missing_world","没有 world 容器，建议补充 3D 边界体"));
  if(worlds.length>1)issues.push(makeIssue("warn","multi_world",`存在 ${worlds.length} 个 world 容器`,worlds.map(c=>c.component_id)));
  const world=worlds[0];
  if(world){
    const wb=bbox3D(world);
    for(const c of sectionComponents(false)){
      if(!aabbContains(wb,bbox3D(c)))issues.push(makeIssue("err","outside_world",`${c.display_name} 超出 world 3D 边界`,[c.component_id,world.component_id]));
    }
  }
  const overlaps=detect3DOverlaps();
  for(const [a,b] of overlaps.pairs.slice(0,5)){
    issues.push(makeIssue("err","overlap3d",`3D 包围盒重叠: ${a.display_name} / ${b.display_name}`,[a.component_id,b.component_id]));
  }
  if(overlaps.pairs.length>5)issues.push(makeIssue("err","overlap3d_more",`还有 ${overlaps.pairs.length-5} 组 3D 重叠未显示`,[...overlaps.ids]));
  const gaps=detectSmallGaps3D();
  for(const g of gaps.slice(0,6)){
    issues.push(makeIssue("warn","small_gap3d",`3D 间隙过小(${g.axis}): ${g.a.display_name} / ${g.b.display_name} = ${fmt(g.gap)} μm < ${fmt(drcSettings.minGap)} μm`,[g.a.component_id,g.b.component_id]));
  }
  if(gaps.length>6)issues.push(makeIssue("warn","small_gap3d_more",`还有 ${gaps.length-6} 组 3D 小间隙未显示`,gaps.flatMap(g=>[g.a.component_id,g.b.component_id])));
  return {issues,overlaps};
}
function isIssueFixable(issue){
  return !!issue&&FIXABLE_ISSUE_CODES.has(issue.code);
}
function issueMatchesFilter(issue,filter=issueBrowserState.filter){
  const f=ISSUE_FILTERS.has(filter)?filter:"all";
  const waived=isIssueWaived(issue);
  if(f==="waived")return waived;
  if(waived)return false;
  if(f==="all")return true;
  if(f==="fixable")return isIssueFixable(issue);
  return issue.kind===f;
}
function collectVisibleIssues(issues=null){
  const src=issues||collectModelIssues().issues;
  const f=ISSUE_FILTERS.has(issueBrowserState.filter)?issueBrowserState.filter:"all";
  return src.filter(issue=>issueMatchesFilter(issue,f));
}
function clampIssueCursor(visibleIssues){
  const issues=visibleIssues||collectVisibleIssues();
  if(!issues.length){issueBrowserState.cursor=0;return 0;}
  const n=issues.length;
  issueBrowserState.cursor=((issueBrowserState.cursor%n)+n)%n;
  return issueBrowserState.cursor;
}
function getCurrentIssue(visibleIssues=null){
  const issues=visibleIssues||collectVisibleIssues();
  if(!issues.length)return null;
  return issues[clampIssueCursor(issues)]||null;
}
function updateIssueBrowserUI(visibleIssues,totalIssues){
  const filter=document.getElementById("issueSeverityFilter");
  if(filter&&filter.value!==issueBrowserState.filter)filter.value=issueBrowserState.filter;
  const label=document.getElementById("issueCursorLabel");
  const n=visibleIssues.length;
  if(label)label.textContent=n?`${issueBrowserState.cursor+1}/${n}`:`0/${n}`;
  const disabled=!n;
  document.querySelectorAll('[data-action="issue-prev"],[data-action="issue-next"],[data-action="issue-focus"]').forEach(btn=>{btn.disabled=disabled;});
  const total=document.getElementById("issueFilterCount");
  if(total)total.textContent=`${n}/${totalIssues}`;
}
function setIssueFilter(filter){
  issueBrowserState.filter=ISSUE_FILTERS.has(filter)?filter:"all";
  issueBrowserState.cursor=0;
  updateModelHealth();
}
function onIssueFilterChange(){
  setIssueFilter(document.getElementById("issueSeverityFilter")?.value||"all");
}
function stepIssue(delta,focus=false){
  const visible=collectVisibleIssues();
  if(!visible.length){updateModelHealth();toast("当前过滤条件下没有问题","err");return null;}
  issueBrowserState.cursor=((issueBrowserState.cursor+(Number(delta)||0))%visible.length+visible.length)%visible.length;
  updateModelHealth();
  return focus?focusCurrentIssue():getCurrentIssue();
}
function focusCurrentIssue(){
  const issue=getCurrentIssue();
  if(!issue){toast("当前过滤条件下没有问题","err");return null;}
  selectIssue(issue.id);
  return issue;
}
function renderIssueRow(issue,currentIssueId=null){
  const ids=(issue.ids||[]).filter(Boolean);
  const signature=issueSignature(issue);
  const waiver=drcWaiverBySignature(signature);
  const waived=!!waiver;
  const baseMeta=ids.length?`组件: ${ids.join(", ")}`:"点击复制检查报告";
  const meta=waived?`${baseMeta} · 已豁免: ${waiver.reason}`:baseMeta;
  const actionLabel=issue.code==="outside_world"?"收回":((issue.code==="overlap3d"||issue.code==="small_gap3d")?"修复":"");
  const actionTitle=issue.code==="outside_world"?"最小平移回 mother/world 边界内":(issue.code==="small_gap3d"?"沿当前第三轴补足最小间隙":"沿当前第三轴分离后一组件");
  const issueId=esc(issue.id);
  const waiverAction=waived
    ?`<button class="ghost" onclick="event.stopPropagation();revokeIssueWaiver(this.closest('.issue').dataset.issueSignature)" title="撤销该检查项豁免">撤销</button>`
    :`<button class="ghost" onclick="event.stopPropagation();waiveIssue(this.closest('.issue').dataset.issueId)" title="填写理由并豁免该检查项">豁免</button>`;
  const fix=(actionLabel&&!waived)?`<button class="ghost" onclick="event.stopPropagation();fixIssue(this.closest('.issue').dataset.issueId)" title="${esc(actionTitle)}">${actionLabel}</button>`:"";
  const actions=(fix||waiverAction)?`<span class="issue-actions">${fix}${waiverAction}</span>`:"";
  const cur=issue.id===currentIssueId?" issue-current":"";
  const waivedCls=waived?" issue-waived":"";
  if(!ids.length)return `<div class="issue ${issue.kind}${waivedCls}${cur}" data-issue-id="${issueId}" data-issue-signature="${esc(signature)}"><span class="issue-text">${esc(issue.text)}<small>${esc(meta)}</small></span>${actions}</div>`;
  return `<div class="issue issue-clickable ${issue.kind}${waivedCls}${cur}" data-issue-id="${issueId}" data-issue-signature="${esc(signature)}" onclick="selectIssue(this.dataset.issueId)" title="选中并聚焦相关组件"><span class="issue-text">${esc(issue.text)}<small>${esc(meta)}</small></span>${actions}</div>`;
}
function updateModelHealth(){
  const metrics=document.getElementById("healthMetrics"),list=document.getElementById("issueList");
  if(!metrics||!list)return;
  if(!model){
    metrics.innerHTML='<div class="metric"><b>—</b><span>组件</span></div><div class="metric"><b>—</b><span>材料</span></div><div class="metric"><b>—</b><span>问题</span></div>';
    list.innerHTML='<div class="issue">载入模型后显示 3D 几何和数据检查。</div>';
    return;
  }
  const nonWorld=sectionComponents(false);
  const mats=new Set(nonWorld.map(c=>c.material_id).filter(Boolean));
  const {issues,overlaps}=collectModelIssues();
  const waivedIssues=issues.filter(issue=>isIssueWaived(issue));
  const activeIssues=issues.filter(issue=>!isIssueWaived(issue));
  const visibleIssues=collectVisibleIssues(issues);
  clampIssueCursor(visibleIssues);
  const currentIssue=getCurrentIssue(visibleIssues);
  metrics.innerHTML=`
    <div class="metric"><b>${nonWorld.length}</b><span>有效组件</span></div>
    <div class="metric"><b>${mats.size}</b><span>材料</span></div>
    <div class="metric"><b>${activeIssues.length}</b><span>${waivedIssues.length?"活动问题":"3D 问题"}</span></div>
    ${waivedIssues.length?`<div class="metric"><b>${waivedIssues.length}</b><span>豁免</span></div>`:""}
  `;
  if(!activeIssues.length&&!waivedIssues.length){
    list.innerHTML='<div class="issue">3D 检查未发现包围盒重叠、越界或关键字段问题。</div>';
  }else if(!visibleIssues.length){
    list.innerHTML='<div class="issue">当前过滤条件下没有问题。</div>';
  }else{
    list.innerHTML=visibleIssues.map(issue=>renderIssueRow(issue,currentIssue&&currentIssue.id)).join("");
  }
  updateIssueBrowserUI(visibleIssues,issueBrowserState.filter==="waived"?waivedIssues.length:activeIssues.length);
  last3DOverlapIds=overlaps.ids;
  renderStackInspector();
}
function selectIssue(issueId){
  if(!model)return;
  const issues=collectModelIssues().issues;
  const visible=collectVisibleIssues(issues);
  const visibleIdx=visible.findIndex(i=>i.id===issueId);
  if(visibleIdx>=0)issueBrowserState.cursor=visibleIdx;
  const issue=issues.find(i=>i.id===issueId);
  if(!issue||!issue.ids||!issue.ids.length){toast("该检查项没有关联组件","err");return;}
  const ids=issue.ids.filter(id=>{
    const c=model.components.find(c=>c.component_id===id);
    return c&&visibleInCurrentSection(c);
  });
  if(!ids.length){toast("关联组件不在当前截面/剖切内","err");return;}
  selectedIds=new Set(ids);
  primaryId=ids[0];
  const c=model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&ids.length===1)?primaryId:null;
  refreshTransformer();drawPolyAnchors();renderList();renderEdit();renderStackInspector();focusSelection();draw3DPreview();updateModelHealth();
}
function overlapsExceptAxis(a,b,skipIdx){
  const eps=1e-9;
  for(let i=0;i<3;i++){
    if(i===skipIdx)continue;
    if(!(a.min[i]<b.max[i]-eps&&a.max[i]>b.min[i]+eps))return false;
  }
  return true;
}
function containerBoundsFor(c){
  if(!model)return null;
  if(c.mother_volume){
    const mother=model.components.find(x=>x.component_id===c.mother_volume);
    if(mother)return bbox3D(mother);
  }
  const world=model.components.find(x=>isWorld(x)&&!x.hidden);
  return world?bbox3D(world):null;
}
function translatedBBox(box,axisIdx,delta){
  return {
    min:box.min.map((v,i)=>i===axisIdx?v+delta:v),
    max:box.max.map((v,i)=>i===axisIdx?v+delta:v),
  };
}
function targetCenterOutsideColumn(moving,axisIdx){
  const mb=bbox3D(moving);
  const half=(mb.max[axisIdx]-mb.min[axisIdx])/2;
  let lower=Infinity,upper=-Infinity;
  for(const c of sectionComponents(false)){
    if(c.component_id===moving.component_id)continue;
    if(moving.mother_volume&&c.mother_volume&&moving.mother_volume!==c.mother_volume)continue;
    const cb=bbox3D(c);
    if(!overlapsExceptAxis(mb,cb,axisIdx))continue;
    lower=Math.min(lower,cb.min[axisIdx]);
    upper=Math.max(upper,cb.max[axisIdx]);
  }
  if(!isFinite(lower)&&!isFinite(upper))return null;
  const current=moving.placement.position[axisIdx];
  const span=Math.max(1,mb.max[axisIdx]-mb.min[axisIdx],Math.abs(upper||0),Math.abs(lower||0));
  const eps=span*1e-6;
  const candidates=[];
  if(isFinite(lower))candidates.push(lower-half-eps);
  if(isFinite(upper))candidates.push(upper+half+eps);
  const container=containerBoundsFor(moving);
  return candidates
    .filter(v=>{
      if(!Number.isFinite(v))return false;
      if(!container)return true;
      const delta=v-current;
      return aabbContains(container,translatedBBox(mb,axisIdx,delta));
    })
    .sort((a,b)=>Math.abs(a-current)-Math.abs(b-current))[0]??null;
}
function fitComponentInsideContainer(c){
  const container=containerBoundsFor(c);
  if(!container)return null;
  const b=bbox3D(c);
  const delta=[0,0,0];
  for(let i=0;i<3;i++){
    const size=b.max[i]-b.min[i];
    const limit=container.max[i]-container.min[i];
    if(size>limit+1e-9)return null;
    if(b.min[i]+delta[i]<container.min[i])delta[i]+=container.min[i]-(b.min[i]+delta[i]);
    if(b.max[i]+delta[i]>container.max[i])delta[i]+=container.max[i]-(b.max[i]+delta[i]);
  }
  return delta;
}
function translateComp3D(c,delta){
  for(let i=0;i<3;i++)c.placement.position[i]+=delta[i];
  if(c.polygon){
    for(const p of c.polygon)for(let i=0;i<3;i++)p[i]+=delta[i];
  }
}
function relationGapAdjustment(rel,targetGap){
  if(!rel)return {ok:false,reason:"missing_relation"};
  const gap=Math.max(0,Number(targetGap)||0);
  if(!rel.overlapsOtherAxes||rel.kind==="off_axis")return {ok:false,reason:"unsupported"};
  if(rel.kind==="overlap")return {ok:false,reason:"unsupported"};
  const moving=rel.b.component;
  if(!moving||isWorld(moving))return {ok:false,reason:"missing_component"};
  if(moving.locked)return {ok:false,reason:"locked"};
  const idx=AXIS_IDX[rel.axis];
  const current=rel.b.min-rel.a.max;
  const delta=gap-current;
  if(!Number.isFinite(delta)||Math.abs(delta)<1e-12)return {ok:false,reason:"no_delta"};
  const mb=bbox3D(moving);
  const container=containerBoundsFor(moving);
  if(container&&!aabbContains(container,translatedBBox(mb,idx,delta)))return {ok:false,reason:"no_target"};
  const d3=[0,0,0];d3[idx]=delta;
  return {ok:true,id:moving.component_id,axis:rel.axis,delta:d3,targetGap:gap};
}
function applyRelationGapAdjustment(rel,targetGap){
  const result=relationGapAdjustment(rel,targetGap);
  if(!result.ok)return result;
  const moving=model.components.find(c=>c.component_id===result.id);
  if(!moving)return {ok:false,reason:"missing_component"};
  translateComp3D(moving,result.delta);
  return result;
}
function applyIssueFix(issue,opts={}){
  if(!issue)return {ok:false,reason:"missing_issue"};
  if(issue.code==="outside_world"){
    const targetId=(issue.ids||[]).find(id=>{
      const c=model.components.find(c=>c.component_id===id);
      return c&&!isWorld(c);
    });
    const c=model.components.find(c=>c.component_id===targetId);
    if(!c)return {ok:false,reason:"missing_component"};
    if(c.locked)return {ok:false,reason:"locked"};
    const delta=fitComponentInsideContainer(c);
    if(!delta)return {ok:false,reason:"oversize"};
    if(delta.every(v=>Math.abs(v)<1e-12))return {ok:false,reason:"no_delta"};
    translateComp3D(c,delta);
    return {ok:true,id:c.component_id,code:issue.code};
  }
  if(issue.code==="overlap3d"){
    const [anchorId,movingId]=issue.ids||[];
    const anchor=model.components.find(c=>c.component_id===anchorId);
    const moving=model.components.find(c=>c.component_id===movingId);
    if(!anchor||!moving)return {ok:false,reason:"missing_component"};
    if(isWorld(moving)||moving.locked)return {ok:false,reason:"locked"};
    const axis=opts.axis||sliceAxis(),idx=AXIS_IDX[axis];
    const currentCenter=moving.placement.position[idx];
    const targetCenter=targetCenterOutsideColumn(moving,idx);
    if(targetCenter===null)return {ok:false,reason:"no_target"};
    const delta=targetCenter-currentCenter;
    if(!Number.isFinite(delta)||Math.abs(delta)<1e-12)return {ok:false,reason:"no_delta"};
    const d3=[0,0,0];d3[idx]=delta;translateComp3D(moving,d3);
    return {ok:true,id:moving.component_id,code:issue.code,axis};
  }
  if(issue.code==="small_gap3d"){
    const [anchorId,movingId]=issue.ids||[];
    const anchor=model.components.find(c=>c.component_id===anchorId);
    const moving=model.components.find(c=>c.component_id===movingId);
    if(!anchor||!moving)return {ok:false,reason:"missing_component"};
    if(isWorld(moving)||moving.locked)return {ok:false,reason:"locked"};
    const axis=opts.axis||sliceAxis(),idx=AXIS_IDX[axis],minGap=Math.max(0,Number(drcSettings.minGap)||0);
    if(minGap<=0)return {ok:false,reason:"unsupported"};
    const ab=bbox3D(anchor),mb=bbox3D(moving);
    let delta=null;
    if(mb.min[idx]>=ab.max[idx]){
      const gap=mb.min[idx]-ab.max[idx];
      delta=minGap-gap;
    }else if(ab.min[idx]>=mb.max[idx]){
      const gap=ab.min[idx]-mb.max[idx];
      delta=-(minGap-gap);
    }else{
      return {ok:false,reason:"unsupported"};
    }
    if(!Number.isFinite(delta)||Math.abs(delta)<1e-12)return {ok:false,reason:"no_delta"};
    const container=containerBoundsFor(moving);
    if(container&&!aabbContains(container,translatedBBox(mb,idx,delta)))return {ok:false,reason:"no_target"};
    const d3=[0,0,0];d3[idx]=delta;translateComp3D(moving,d3);
    return {ok:true,id:moving.component_id,code:issue.code,axis};
  }
  return {ok:false,reason:"unsupported"};
}
function fixIssue(issueId){
  if(!model)return;
  const issue=collectModelIssues().issues.find(i=>i.id===issueId);
  if(!issue){toast("检查项已变化,请重新检查","err");updateModelHealth();return;}
  const result=applyIssueFix(issue);
  if(!result.ok){
    const reason={unsupported:"该检查项暂无自动修复",missing_component:"关联组件不存在",locked:"目标组件不可自动移动",oversize:"组件大于容器,无法仅靠平移修复",no_target:"未找到可用修复位置",no_delta:"无法计算修复位移"}[result.reason]||"修复失败";
    toast(reason,"err");updateModelHealth();return;
  }
  const fixed=model.components.find(c=>c.component_id===result.id);
  selectedIds=new Set([result.id]);
  primaryId=result.id;
  polyEditId=(fixed&&fixed.polygon&&polygonAxesMatch(fixed))?fixed.component_id:null;
  drawComponents();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  toast(result.code==="outside_world"?`已收回 ${fixed.display_name}`:`已沿 ${result.axis} 轴修复 ${fixed.display_name}`);
}
function fixSafeIssues(){
  if(!model){toast("没有数据","err");return {fixed:0,remaining:0,attempted:0};}
  const safeCodes=new Set(["outside_world","overlap3d","small_gap3d"]);
  const fixedIds=[];
  let attempted=0,stalled=0;
  for(let step=0;step<20;step++){
    const issue=collectModelIssues().issues.find(i=>safeCodes.has(i.code)&&!isIssueWaived(i));
    if(!issue)break;
    attempted++;
    const result=applyIssueFix(issue);
    if(result.ok){fixedIds.push(result.id);stalled=0;}
    else if(++stalled>=3){break;}
  }
  const remainingIssues=collectModelIssues().issues;
  if(fixedIds.length){
    const last=fixedIds[fixedIds.length-1];
    const c=model.components.find(c=>c.component_id===last);
    selectedIds=new Set([last]);primaryId=last;polyEditId=(c&&c.polygon&&polygonAxesMatch(c))?last:null;
    drawComponents();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  }else{
    updateModelHealth();
  }
  const result={fixed:fixedIds.length,remaining:remainingIssues.length,attempted};
  toast(fixedIds.length?`已修复 ${fixedIds.length} 个安全项,剩余 ${remainingIssues.length}`:"没有可自动修复的安全项",fixedIds.length?"ok":"err");
  return result;
}
function modelHealthReportText(){
  if(!model)return "3D 检查报告\n未载入模型";
  const {issues}=collectModelIssues();
  const activeIssues=issues.filter(issue=>!isIssueWaived(issue));
  const waivedIssues=issues.filter(issue=>isIssueWaived(issue));
  const nonWorld=sectionComponents(false);
  const rule=DRC_RULE_DECKS[drcSettings.ruleDeck]||DRC_RULE_DECKS.custom;
  const lines=[
    "3D 检查报告",
    `截面: ${axes.lateral}×${axes.depth}; 第三轴: ${sliceAxis()}`,
    `规则: ${rule.label}; 最小间隙: ${fmt(Math.max(0,Number(drcSettings.minGap)||0))} μm`,
    waivedIssues.length?`组件: ${nonWorld.length}; 问题: ${activeIssues.length}; 已豁免: ${waivedIssues.length}`:`组件: ${nonWorld.length}; 问题: ${issues.length}`,
  ];
  if(sliceState.enabled){
    const s=sliceBounds();
    lines.push(`剖切: ${s.axis}=${fmt(s.pos)} μm, 厚 ${fmt(s.thickness)} μm`);
  }
  if(!activeIssues.length){
    lines.push("- 未发现包围盒重叠、越界或关键字段问题");
  }else{
    for(const issue of activeIssues){
      const ids=issue.ids&&issue.ids.length?` [${issue.ids.join(", ")}]`:"";
      lines.push(`- ${issue.kind.toUpperCase()} ${issue.code}: ${issue.text}${ids}`);
    }
  }
  if(waivedIssues.length){
    lines.push("已豁免:");
    for(const issue of waivedIssues){
      const waiver=drcWaiverBySignature(issueSignature(issue));
      const ids=issue.ids&&issue.ids.length?` [${issue.ids.join(", ")}]`:"";
      lines.push(`- WAIVED ${issue.code}: ${issue.text}${ids} | reason: ${waiver?waiver.reason:"已确认可接受"}`);
    }
  }
  return lines.join("\n");
}
function copyModelHealthReport(){
  const text=modelHealthReportText();
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(()=>toast("检查报告已复制")).catch(()=>prompt("复制:",text));
  }else{
    prompt("复制:",text);
  }
  return text;
}
function csvCell(value){
  const arrayValue=Array.isArray(value);
  const text=value==null?"":(arrayValue?value.join(";"):String(value));
  const escaped=text.replace(/"/g,'""');
  return arrayValue||/[",\n\r]/.test(text)?`"${escaped}"`:escaped;
}
function csvLine(values){
  return values.map(csvCell).join(",");
}
function reportFileBase(){
  if(!model)return "device_canvas";
  const raw=(model.meta&&(
    model.meta.job_id||
    model.meta.model_ir_id||
    model.meta.target_system
  ))||model.sourceName||"device_canvas";
  return String(raw).trim().replace(/[^\w.-]+/g,"_").replace(/^_+|_+$/g,"")||"device_canvas";
}
function boolText(value){
  return value?"true":"false";
}
function buildDRCReportCSV(){
  const header=["status","kind","code","message","component_ids","signature","fixable","waiver_reason","waived_at"];
  const rows=[header];
  if(model){
    const {issues}=collectModelIssues();
    for(const issue of issues){
      const signature=issueSignature(issue);
      const waiver=drcWaiverBySignature(signature);
      rows.push([
        waiver?"waived":"active",
        issue.kind||"",
        issue.code||"",
        issue.text||"",
        issue.ids||[],
        signature,
        boolText(isIssueFixable(issue)),
        waiver?waiver.reason:"",
        waiver?waiver.waivedAt:"",
      ]);
    }
  }
  return rows.map(csvLine).join("\n");
}
function buildComponentReportCSV(){
  const header=[
    "component_id","display_name","component_type","geometry_type","material_id","mother_volume",
    "x_um","y_um","z_um","dx_um","dy_um","dz_um",
    "min_x_um","min_y_um","min_z_um","max_x_um","max_y_um","max_z_um",
    "hidden","locked","sensitive","roles","source_evidence","open_issues",
  ];
  const rows=[header];
  if(model){
    const comps=model.components.filter(c=>!isWorld(c));
    for(const c of comps){
      const p=(c.placement&&c.placement.position)||[0,0,0];
      const d=c.dimensions||{};
      const box=bbox3D(c);
      rows.push([
        c.component_id||"",
        c.display_name||"",
        c.component_type||"",
        c.geometry_type||"",
        c.material_id||"",
        c.mother_volume||"",
        p[0]||0,p[1]||0,p[2]||0,
        d.dx||0,d.dy||0,d.dz||0,
        box.min[0],box.min[1],box.min[2],box.max[0],box.max[1],box.max[2],
        boolText(!!c.hidden),
        boolText(!!c.locked),
        boolText(!!c.sensitive),
        (c.roles||[]).join(";"),
        c.source_evidence||[],
        c.open_issues||[],
      ]);
    }
  }
  return rows.map(csvLine).join("\n");
}
function exportDRCReportCSV(){
  if(!model){toast("没有数据","err");return "";}
  const csv=buildDRCReportCSV();
  download(new Blob([csv],{type:"text/csv;charset=utf-8"}),`${reportFileBase()}_drc_report.csv`);
  toast("已导出 DRC CSV");
  return csv;
}
function exportComponentReportCSV(){
  if(!model){toast("没有数据","err");return "";}
  const csv=buildComponentReportCSV();
  download(new Blob([csv],{type:"text/csv;charset=utf-8"}),`${reportFileBase()}_components.csv`);
  toast("已导出组件 CSV");
  return csv;
}
/* ---------- 插入常见图形 ---------- */
function addShape(type){
  if(!model){loadExample();return;}
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth],thirdIdx=3-li-di;
  const cx=toDataX(stage.width()/2),cy=toDataY(stage.height()/2);
  const ts=Date.now().toString(36).slice(-3);
  const names={square:"正方形",rectangle:"长方形",circle:"圆形",triangle:"三角形",hexagon:"多边形"};
  let nc;
  if(type==="square"||type==="rectangle"){
    const sq=type==="square";
    nc=normalizeComponent({component_id:`shape_${type}_${ts}`,display_name:`${names[type]} ${model.components.length}`,component_type:"volume",geometry_type:"box",material_id:"Silicon",dimensions:sq?{dx:150,dy:150,dz:150}:{dx:260,dy:160,dz:60},placement:{position:[0,0,0],rotation:[0,0,0]},mother_volume:findWorldId(),roles:[]});
    nc.placement.position[li]=cx;nc.placement.position[di]=cy;nc.placement.position[thirdIdx]=0;
  }else{
    const r=130,n=type==="circle"?32:type==="triangle"?3:6,pts=[];
    for(let i=0;i<n;i++){const a=2*Math.PI*i/n-Math.PI/2;const v=[0,0,0];v[li]=cx+r*Math.cos(a);v[di]=cy+r*Math.sin(a);v[thirdIdx]=0;pts.push(v);}
    nc={component_id:`shape_${type}_${ts}`,display_name:`${names[type]} ${model.components.length}`,component_type:"volume",geometry_type:type==="circle"?"cylinder":"polycone",material_id:"Silicon",dimensions:{dx:0,dy:0,dz:0},placement:{position:[cx,cy,0],rotation:[0,0,0]},mother_volume:findWorldId(),roles:[],source_evidence:["shape_insert"],open_issues:[],locked:false,confirmed_by_user:true,confirmation_source:"device_canvas",polygon:pts,polygonAxes:{lateral:axes.lateral,depth:axes.depth}};
  }
  model.components.push(nc);
  selectOnly(nc.component_id);resetView();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  toast(`已插入 ${names[type]}`);
}
function booleanOp(op){
  if(typeof polygonClipping==="undefined"){toast("布尔库未加载","err");return;}
  if(selectedIds.size!==2){toast("需恰好选中 2 个组件(先选 A,Shift 选 B)","err");return;}
  const ids=[...selectedIds];
  const a=model.components.find(c=>c.component_id===ids[0]);
  const b=model.components.find(c=>c.component_id===ids[1]);
  if(!a||!b)return;
  if(isWorld(a)||isWorld(b)){toast("world 容器不能参与布尔","err");return;}
  const ringA=compToRing(a),ringB=compToRing(b);
  if(!ringA||!ringB){toast("组件需在当前截面可投影(多边形切换到其轴)","err");return;}
  let res;
  try{
    res=op==="union"?polygonClipping.union([ringA],[ringB])
       :op==="difference"?polygonClipping.difference([ringA],[ringB])
       :polygonClipping.intersection([ringA],[ringB]);
  }catch(e){toast("布尔失败: "+e.message,"err");return;}
  if(!res||!res.length){toast("结果为空(两块无重叠/差集后消失)","err");return;}
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth],thirdIdx=3-li-di;
  const opLabel={union:"并",difference:"差",intersection:"交"}[op];
  // 每个 polygon 的外环(忽略洞)生成一个组件;多块分别建
  const newComps=[];
  res.forEach((poly,pi)=>{
    const outer=poly[0];if(!outer||outer.length<3)return;
    const pts=outer.map(([x,y])=>{const v=[a.placement.position[0],a.placement.position[1],a.placement.position[2]];v[li]=x;v[di]=y;return v;});
    const nc={
      component_id:`${a.component_id}_${op}_${pi}_${Date.now().toString(36).slice(-3)}`,
      display_name:`${a.display_name}·${opLabel}`+(res.length>1?`(${pi+1})`:""),
      component_type:a.component_type,geometry_type:"polycone",material_id:a.material_id,
      dimensions:{dx:0,dy:0,dz:0},
      placement:{position:[...a.placement.position],rotation:[0,0,0]},
      mother_volume:a.mother_volume,roles:a.roles||[],sensitive:a.sensitive,
      source_evidence:["boolean_op"],open_issues:[`布尔${opLabel}结果,${pts.length}顶点多边形`],
      locked:false,confirmed_by_user:true,confirmation_source:"device_canvas",
      polygon:pts,polygonAxes:{lateral:axes.lateral,depth:axes.depth},
    };
    newComps.push(nc);
  });
  if(!newComps.length){toast("结果无有效外环","err");return;}
  model.components=model.components.filter(c=>c.component_id!==a.component_id&&c.component_id!==b.component_id);
  model.components.push(...newComps);
  selectedIds=new Set([newComps[0].component_id]);primaryId=newComps[0].component_id;polyEditId=newComps[0].component_id;
  resetView();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  toast(`布尔${opLabel}完成 → ${newComps.length} 个块`);
}
function bboxOf(c){
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  if(c.polygon){const b=polyBBox(c);return{minLat:b.minLat,maxLat:b.maxLat,minDep:b.minDep,maxDep:b.maxDep};}
  const dLat=c.dimensions[DIM_KEY[axes.lateral]]||0,dDep=c.dimensions[DIM_KEY[axes.depth]]||0;
  return{minLat:c.placement.position[li]-dLat/2,maxLat:c.placement.position[li]+dLat/2,minDep:c.placement.position[di]-dDep/2,maxDep:c.placement.position[di]+dDep/2};
}
function bboxOfSelection(ids=[...selectedIds]){
  let mL=Infinity,ML=-Infinity,mD=Infinity,MD=-Infinity;
  for(const id of ids){const c=model.components.find(c=>c.component_id===id);if(!c||!visibleInCurrentSection(c))continue;const b=bboxOf(c);mL=Math.min(mL,b.minLat);ML=Math.max(ML,b.maxLat);mD=Math.min(mD,b.minDep);MD=Math.max(MD,b.maxDep);}
  if(!isFinite(mL))return null;
  return{minLat:mL,maxLat:ML,minDep:mD,maxDep:MD};
}
function selectedComponents(ids=[...selectedIds],includeWorld=true){
  if(!model)return [];
  const wanted=new Set(ids);
  return model.components.filter(c=>wanted.has(c.component_id)&&visibleInCurrentSection(c)&&(includeWorld||!isWorld(c)));
}
function normalizeNumber(v){
  if(!Number.isFinite(v))return 0;
  return Number(v.toFixed(6));
}
function normalizeArray(a){return a.map(normalizeNumber);}
function unionBBox3D(comps){
  let min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  for(const c of comps){
    const b=bbox3D(c);
    for(let i=0;i<3;i++){min[i]=Math.min(min[i],b.min[i]);max[i]=Math.max(max[i],b.max[i]);}
  }
  if(!isFinite(min[0]))return null;
  const size=max.map((v,i)=>v-min[i]);
  const center=max.map((v,i)=>(v+min[i])/2);
  return {min:normalizeArray(min),max:normalizeArray(max),size:normalizeArray(size),center:normalizeArray(center)};
}
function unionBBox2D(comps){
  let mL=Infinity,ML=-Infinity,mD=Infinity,MD=-Infinity;
  for(const c of comps){
    const b=bboxOf(c);
    mL=Math.min(mL,b.minLat);ML=Math.max(ML,b.maxLat);
    mD=Math.min(mD,b.minDep);MD=Math.max(MD,b.maxDep);
  }
  if(!isFinite(mL))return null;
  return {
    axes:{lateral:axes.lateral,depth:axes.depth},
    min:normalizeArray([mL,mD]),
    max:normalizeArray([ML,MD]),
    size:normalizeArray([ML-mL,MD-mD]),
    center:normalizeArray([(mL+ML)/2,(mD+MD)/2]),
  };
}
function pairAxisProbe(axis,aBox,bBox){
  const idx=AXIS_IDX[axis],eps=1e-9;
  const abGap=bBox.min[idx]-aBox.max[idx];
  const baGap=aBox.min[idx]-bBox.max[idx];
  if(abGap>eps){
    return {axis,state:"gap",gap:normalizeNumber(abGap),overlap:0,signedGap:normalizeNumber(abGap),order:"a_before_b"};
  }
  if(baGap>eps){
    return {axis,state:"gap",gap:normalizeNumber(baGap),overlap:0,signedGap:normalizeNumber(baGap),order:"b_before_a"};
  }
  const overlap=Math.min(aBox.max[idx],bBox.max[idx])-Math.max(aBox.min[idx],bBox.min[idx]);
  if(overlap>eps){
    return {axis,state:"overlap",gap:0,overlap:normalizeNumber(overlap),signedGap:normalizeNumber(-overlap),order:"intersect"};
  }
  return {axis,state:"touch",gap:0,overlap:0,signedGap:0,order:"touch"};
}
function pairwiseBBoxProbe(a,b){
  if(!a||!b)return null;
  const aBox=bbox3D(a),bBox=bbox3D(b);
  const aCenter=aBox.max.map((v,i)=>(v+aBox.min[i])/2);
  const bCenter=bBox.max.map((v,i)=>(v+bBox.min[i])/2);
  const centerDelta=bCenter.map((v,i)=>v-aCenter[i]);
  return {
    ids:[a.component_id,b.component_id],
    names:[a.display_name||a.component_id,b.display_name||b.component_id],
    axes:["x","y","z"].map(axis=>pairAxisProbe(axis,aBox,bBox)),
    centerDelta:normalizeArray(centerDelta),
    centerDistance:normalizeNumber(Math.hypot(...centerDelta)),
  };
}
function componentAabbVolume(c){
  const b=bbox3D(c);
  return Math.max(0,b.max[0]-b.min[0])*Math.max(0,b.max[1]-b.min[1])*Math.max(0,b.max[2]-b.min[2]);
}
function buildSelectionReport(ids=[...selectedIds]){
  const comps=selectedComponents(ids,true);
  const materials={};
  let volume=0,locked=0;
  for(const c of comps){
    const mat=c.material_id||"(none)";
    materials[mat]=(materials[mat]||0)+1;
    volume+=componentAabbVolume(c);
    if(c.locked)locked++;
  }
  return {
    count:comps.length,
    ids:comps.map(c=>c.component_id),
    axes:{lateral:axes.lateral,depth:axes.depth,third:sliceAxis()},
    slice:JSON.parse(JSON.stringify(sliceState)),
    bbox3d:unionBBox3D(comps),
    bbox2d:unionBBox2D(comps),
    pairProbe:comps.length===2?pairwiseBBoxProbe(comps[0],comps[1]):null,
    volume:normalizeNumber(volume),
    volume_kind:"aabb_sum",
    materials,
    locked,
  };
}
function fmtDims(vals){return vals.map(fmt).join(" × ");}
function fmtPoint(vals){return vals.map(fmt).join(", ");}
function fmtProbeNumber(value){
  const n=normalizeNumber(value);
  return Object.is(n,-0)?"0":String(n);
}
function fmtProbePoint(vals){
  return vals.map(fmtProbeNumber).join(", ");
}
function pairAxisText(item){
  const label={gap:"间隙",overlap:"重叠",touch:"接触"}[item.state]||item.state;
  const value=item.state==="overlap"?item.overlap:item.gap;
  return `${item.axis}: ${label} ${fmtProbeNumber(value)}`;
}
function pairProbeText(probe){
  if(!probe)return "";
  const names=(probe.names&&probe.names.length===2)?probe.names:probe.ids;
  return [
    `${names[0]} / ${names[1]}`,
    probe.axes.map(pairAxisText).join("; "),
    `center Δ [${fmtProbePoint(probe.centerDelta)}] μm`,
    `center distance ${fmtProbeNumber(probe.centerDistance)} μm`,
  ].join(" | ");
}
function selectedPairComponentsForAdjustment(ids=[...selectedIds]){
  const comps=selectedComponents(ids,false);
  if(comps.length!==2)return null;
  let anchor=comps[0],moving=comps[1];
  if(primaryId&&primaryId===comps[1].component_id){anchor=comps[1];moving=comps[0];}
  return {anchor,moving,comps};
}
function pairGapAdjustment(axis,targetGap,ids=[...selectedIds]){
  if(!model)return {ok:false,reason:"missing_model"};
  const pair=selectedPairComponentsForAdjustment(ids);
  if(!pair)return {ok:false,reason:"need_pair"};
  const ax=AXIS_IDX[axis]===undefined?selectedPairDominantAxis(buildSelectionReport(ids)):axis;
  const idx=AXIS_IDX[ax];
  const gap=Math.max(0,Number(targetGap)||0);
  const moving=pair.moving,anchor=pair.anchor;
  if(!moving||isWorld(moving))return {ok:false,reason:"missing_component"};
  if(moving.locked)return {ok:false,reason:"locked"};
  const aBox=bbox3D(anchor),mBox=bbox3D(moving);
  const current=pairAxisProbe(ax,aBox,mBox);
  const anchorCenter=(aBox.min[idx]+aBox.max[idx])/2;
  const movingCenter=(mBox.min[idx]+mBox.max[idx])/2;
  const moveAfter= movingCenter>=anchorCenter;
  const targetMin=moveAfter?aBox.max[idx]+gap:aBox.min[idx]-gap-(mBox.max[idx]-mBox.min[idx]);
  const deltaValue=targetMin-mBox.min[idx];
  if(!Number.isFinite(deltaValue))return {ok:false,reason:"bad_target"};
  const delta=[0,0,0];delta[idx]=normalizeNumber(deltaValue);
  if(Math.abs(delta[idx])<1e-12)return {ok:false,reason:"no_delta",movingId:moving.component_id,axis:ax,delta};
  syncTransformConstraintFromUI();
  if(!transformFitsContainer(moving,bboxTranslated3D(mBox,delta)))return {ok:false,reason:"no_target",movingId:moving.component_id,axis:ax,delta,current};
  return {ok:true,movingId:moving.component_id,anchorId:anchor.component_id,axis:ax,targetGap:gap,delta,current};
}
function pairGapFailureMessage(reason){
  return {
    need_pair:"需恰好选中 2 个当前截面组件",
    locked:"目标组件已锁定",
    no_target:"目标间隙会越出 mother/World 边界",
    no_delta:"当前已经是目标间隙",
    missing_component:"关联组件不存在",
    bad_target:"目标间隙无效",
  }[reason]||"无法设置两组件间隙";
}
function setSelectionPairGap(axis,targetGap){
  const result=pairGapAdjustment(axis,targetGap);
  if(!result.ok){toast(pairGapFailureMessage(result.reason),"err");return result;}
  const moving=model.components.find(c=>c.component_id===result.movingId);
  if(!moving)return {ok:false,reason:"missing_component"};
  translateComp3D(moving,result.delta);
  selectedIds=new Set([result.anchorId,result.movingId]);
  primaryId=result.anchorId;
  polyEditId=null;
  drawComponents();refreshSelectionViews();renderAnnotationsPanel();updateModelHealth();draw3DPreview();pushHistory();
  toast(`已设置 ${result.axis} 间隙 ${fmtProbeNumber(result.targetGap)} μm`);
  return result;
}
function setSelectionPairGapFromUI(){
  const report=buildSelectionReport();
  if(!report.pairProbe){toast("需恰好选中 2 个组件","err");return {ok:false,reason:"need_pair"};}
  const axis=document.getElementById("pairGapAxis")?.value||selectedPairDominantAxis(report);
  const target=Number(document.getElementById("pairGapTarget")?.value||0);
  return setSelectionPairGap(axis,target);
}
function fmtVolume(v){
  const a=Math.abs(v);
  if(a>=1e12)return `${(v/1e12).toFixed(3)}e12`;
  if(a>=1e9)return `${(v/1e9).toFixed(3)}e9`;
  if(a>=1e6)return `${(v/1e6).toFixed(3)}e6`;
  return fmt(v);
}
function materialSummary(materials){
  const items=Object.entries(materials).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
  return items.length?items.map(([m,n])=>`${m} ×${n}`).join(", "):"—";
}
function renderSelectionSummary(ids=[...selectedIds]){
  const report=buildSelectionReport(ids);
  if(!report.count||!report.bbox3d||!report.bbox2d)return "";
  const b3=report.bbox3d,b2=report.bbox2d;
  return `
    <section id="selectionSummary" class="selection-summary">
      <div class="selection-summary-head">
        <strong>选区几何</strong>
        <span class="pill">${report.count} 个</span>
      </div>
      <dl class="summary-grid">
        <dt>3D bbox</dt><dd>${fmtDims(b3.size)} μm</dd>
        <dt>3D 中心</dt><dd>${fmtPoint(b3.center)} μm</dd>
        <dt>截面 bbox</dt><dd>${b2.axes.lateral}×${b2.axes.depth}: ${fmtDims(b2.size)} μm</dd>
        <dt>截面中心</dt><dd>${fmtPoint(b2.center)} μm</dd>
        <dt>体积</dt><dd>${fmtVolume(report.volume)} μm³</dd>
        <dt>材料</dt><dd>${esc(materialSummary(report.materials))}</dd>
      </dl>
      ${report.pairProbe?`<div id="selectionPairProbe" class="pair-probe">
        <b>两组件关系</b>
        <span>${esc(pairProbeText(report.pairProbe))}</span>
        <div class="pair-gap-control">
          <select id="pairGapAxis" title="设置间隙轴">
            ${["x","y","z"].map(axis=>`<option value="${axis}" ${axis===selectedPairDominantAxis(report)?"selected":""}>${axis}</option>`).join("")}
          </select>
          <input id="pairGapTarget" type="number" min="0" step="any" value="${fmtProbeNumber((report.pairProbe.axes.find(item=>item.axis===selectedPairDominantAxis(report))||{}).gap||0)}" title="目标间隙 μm"/>
          <button data-action="set-pair-gap" class="ghost" onclick="setSelectionPairGapFromUI()">设为间隙</button>
        </div>
      </div>`:""}
      <button class="ghost summary-copy" onclick="copySelectionReport()">复制几何报告</button>
    </section>
  `;
}
function refreshSelectionSummary(){
  const el=document.getElementById("selectionSummary");
  if(!el)return;
  const html=renderSelectionSummary();
  if(html)el.outerHTML=html;
  else el.remove();
}
function selectionReportText(report=buildSelectionReport()){
  if(!report.count||!report.bbox3d||!report.bbox2d)return "";
  const b3=report.bbox3d,b2=report.bbox2d;
  return [
    `选区几何: ${report.count} 个组件`,
    `3D bbox: ${fmtDims(b3.size)} μm; center [${fmtPoint(b3.center)}] μm`,
    `截面 bbox (${b2.axes.lateral}×${b2.axes.depth}): ${fmtDims(b2.size)} μm; center [${fmtPoint(b2.center)}] μm`,
    report.pairProbe?`两组件关系: ${pairProbeText(report.pairProbe)}`:null,
    `体积(AABB合计): ${fmtVolume(report.volume)} μm³`,
    `材料: ${materialSummary(report.materials)}`,
    `组件: ${report.ids.join(", ")}`,
  ].filter(Boolean).join("\n");
}
function copySelectionReport(){
  const text=selectionReportText();
  if(!text){toast("没有可复制的选区几何","err");return;}
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(()=>toast("几何报告已复制")).catch(()=>prompt("复制:",text));
  }else{
    prompt("复制:",text);
  }
}
function translateComp(c,dLat,dDep){
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  syncTransformConstraintFromUI();
  const delta=[0,0,0];delta[li]=dLat;delta[di]=dDep;
  if(transformSettings.constrainWorld&&transformSettings.boundaryMode==="clamp"){
    const result=clampTranslationToContainer(c,delta);
    if(result.blocked)return {changed:false,blocked:true,clamped:result.clamped};
    if(c.polygon&&polygonAxesMatch(c)){for(const p of c.polygon){p[li]+=result.delta[li];p[di]+=result.delta[di];}}
    c.placement.position[li]+=result.delta[li];c.placement.position[di]+=result.delta[di];
    return {changed:true,blocked:false,clamped:result.clamped};
  }
  if(!transformFitsContainer(c,bboxTranslated3D(bbox3D(c),delta))){
    return {changed:false,blocked:true};
  }
  if(c.polygon&&polygonAxesMatch(c)){for(const p of c.polygon){p[li]+=dLat;p[di]+=dDep;}}
  c.placement.position[li]+=dLat;c.placement.position[di]+=dDep;
  return {changed:true,blocked:false};
}

/* ---------- 三维预览 ---------- */
function toggle3DPreview(){
  preview3DVisible=!preview3DVisible;
  const el=document.getElementById("preview3d");
  if(el)el.classList.toggle("show",preview3DVisible);
  draw3DPreview();
}
function rotate3D(delta){
  preview3DView="iso";
  preview3DAngle=(preview3DAngle+delta)%360;
  update3DViewUI();
  draw3DPreview();
}
function update3DViewUI(){
  const label=document.getElementById("preview3dViewLabel");
  if(label)label.textContent={iso:"Iso",top:"Top",front:"Front",side:"Side"}[preview3DView]||"Iso";
  document.querySelectorAll("[data-view-preset]").forEach(btn=>btn.classList.toggle("on",btn.dataset.viewPreset===preview3DView));
}
function set3DViewPreset(view){
  preview3DView=["iso","top","front","side"].includes(view)?view:"iso";
  if(preview3DView==="iso")preview3DAngle=35;
  update3DViewUI();
  draw3DPreview();
}
function worldBounds3D(){
  if(!model||!model.components.length)return null;
  let min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  for(const c of model.components){
    if(c.hidden)continue;
    const b=bbox3D(c);
    for(let i=0;i<3;i++){min[i]=Math.min(min[i],b.min[i]);max[i]=Math.max(max[i],b.max[i]);}
  }
  if(!isFinite(min[0]))return null;
  return {min,max};
}
function previewProjector(bounds,w,h){
  const cx=(bounds.min[0]+bounds.max[0])/2,cy=(bounds.min[1]+bounds.max[1])/2,cz=(bounds.min[2]+bounds.max[2])/2;
  const span=Math.max(bounds.max[0]-bounds.min[0],bounds.max[1]-bounds.min[1],bounds.max[2]-bounds.min[2],1);
  const scale=Math.min(w,h)*0.58/span;
  const theta=preview3DAngle*Math.PI/180;
  const cos=Math.cos(theta),sin=Math.sin(theta);
  return function project(p){
    const x=p[0]-cx,y=p[1]-cy,z=p[2]-cz;
    if(preview3DView==="top")return [w/2+x*scale,h/2-y*scale,z];
    if(preview3DView==="front")return [w/2+x*scale,h/2-z*scale,-y];
    if(preview3DView==="side")return [w/2+y*scale,h/2-z*scale,x];
    const rx=x*cos-y*sin;
    const ry=x*sin+y*cos;
    return [w/2+(rx-ry)*0.72*scale,h/2+(rx+ry)*0.34*scale-z*0.86*scale,rx+ry+z];
  };
}
function draw3DPreview(){
  last3DHitRegions=[];
  last3DStrokeSamples=[];
  if(!preview3DVisible||!model)return;
  const canvas=document.getElementById("preview3dCanvas");if(!canvas)return;
  const ctx=canvas.getContext("2d");
  const w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle="#f8fafc";ctx.fillRect(0,0,w,h);
  const bounds=worldBounds3D();if(!bounds)return;
  update3DViewUI();
  const project=previewProjector(bounds,w,h);
  draw3DGrid(ctx,project,bounds);
  if(sliceState.enabled)drawSlicePlane3D(ctx,project,bounds);
  const comps=sectionComponents(true).sort((a,b)=>bbox3D(a).min[2]-bbox3D(b).min[2]);
  let labelIndex=0;
  for(const c of comps)labelIndex+=drawBox3D(ctx,project,c,labelIndex)?1:0;
  draw3DAxes(ctx,project,bounds);
}
function drawSlicePlane3D(ctx,project,bounds){
  const s=sliceBounds();
  const pts=[];
  if(s.axis==="x"){
    pts.push([s.pos,bounds.min[1],bounds.min[2]],[s.pos,bounds.max[1],bounds.min[2]],[s.pos,bounds.max[1],bounds.max[2]],[s.pos,bounds.min[1],bounds.max[2]]);
  }else if(s.axis==="y"){
    pts.push([bounds.min[0],s.pos,bounds.min[2]],[bounds.max[0],s.pos,bounds.min[2]],[bounds.max[0],s.pos,bounds.max[2]],[bounds.min[0],s.pos,bounds.max[2]]);
  }else{
    pts.push([bounds.min[0],bounds.min[1],s.pos],[bounds.max[0],bounds.min[1],s.pos],[bounds.max[0],bounds.max[1],s.pos],[bounds.min[0],bounds.max[1],s.pos]);
  }
  const pp=pts.map(project);
  ctx.save();
  ctx.beginPath();ctx.moveTo(pp[0][0],pp[0][1]);
  for(let i=1;i<pp.length;i++)ctx.lineTo(pp[i][0],pp[i][1]);
  ctx.closePath();
  ctx.fillStyle="rgba(37,99,235,.08)";ctx.fill();
  ctx.strokeStyle="rgba(37,99,235,.65)";ctx.lineWidth=1.3;ctx.setLineDash([5,4]);ctx.stroke();
  ctx.setLineDash([]);ctx.fillStyle="#1d4ed8";ctx.font="11px sans-serif";
  ctx.fillText(`${s.axis}=${fmt(s.pos)} μm`,pp[0][0]+6,pp[0][1]-6);
  ctx.restore();
}
function boxCorners3D(c){
  const b=bbox3D(c),mn=b.min,mx=b.max;
  return [
    [mn[0],mn[1],mn[2]],[mx[0],mn[1],mn[2]],[mx[0],mx[1],mn[2]],[mn[0],mx[1],mn[2]],
    [mn[0],mn[1],mx[2]],[mx[0],mn[1],mx[2]],[mx[0],mx[1],mx[2]],[mn[0],mx[1],mx[2]],
  ];
}
function convexHull2D(points){
  const pts=points.map(p=>({x:p[0],y:p[1]})).sort((a,b)=>(a.x-b.x)||(a.y-b.y));
  if(pts.length<=1)return pts;
  const cross=(o,a,b)=>(a.x-o.x)*(b.y-o.y)-(a.y-o.y)*(b.x-o.x);
  const lower=[];
  for(const p of pts){while(lower.length>=2&&cross(lower[lower.length-2],lower[lower.length-1],p)<=0)lower.pop();lower.push(p);}
  const upper=[];
  for(let i=pts.length-1;i>=0;i--){const p=pts[i];while(upper.length>=2&&cross(upper[upper.length-2],upper[upper.length-1],p)<=0)upper.pop();upper.push(p);}
  return lower.slice(0,-1).concat(upper.slice(0,-1));
}
function pointInPolygon2D(x,y,poly){
  if(!poly||poly.length<3)return false;
  let inside=false;
  for(let i=0,j=poly.length-1;i<poly.length;j=i++){
    const pi=poly[i],pj=poly[j];
    const intersect=((pi.y>y)!==(pj.y>y))&&(x<(pj.x-pi.x)*(y-pi.y)/((pj.y-pi.y)||1e-12)+pi.x);
    if(intersect)inside=!inside;
  }
  return inside;
}
function previewProjectedBoxPx(pts){
  const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  const w=Math.max(...xs)-Math.min(...xs);
  const h=Math.max(...ys)-Math.min(...ys);
  return {w,h,minPx:Math.max(0,Math.min(Math.abs(w||0),Math.abs(h||0)))};
}
function preview3DLineWidth(projectedMinPx,{selected=false,world=false,overlap=false}={}){
  if(world)return 0.6;
  const minPx=Math.max(0,Number(projectedMinPx)||0);
  if(minPx>0&&minPx<2)return Math.max(0.02,Math.min(minPx,minPx*0.45));
  if(minPx<6)return Math.min(overlap?0.7:(selected?0.8:0.55),minPx*0.22);
  if(overlap)return 0.9;
  return selected?1.1:0.75;
}
function drawBox3D(ctx,project,c,labelIndex=0){
  const pts=boxCorners3D(c).map(project);
  if(!isWorld(c)){
    const hull=convexHull2D(pts);
    const depth=pts.reduce((s,p)=>s+(Number(p[2])||0),0)/Math.max(pts.length,1);
    const center=hull.reduce((p,q)=>({x:p.x+q.x,y:p.y+q.y}),{x:0,y:0});
    if(hull.length){center.x/=hull.length;center.y/=hull.length;}
    last3DHitRegions.push({id:c.component_id,hull,depth,center});
  }
  const faces=[[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]];
  const col=isWorld(c)?"#98a2b3":matColor(c.material_id);
  ctx.save();
  ctx.globalAlpha=isWorld(c)?0.08:0.26;
  for(const f of faces){
    ctx.beginPath();ctx.moveTo(pts[f[0]][0],pts[f[0]][1]);
    for(let i=1;i<f.length;i++)ctx.lineTo(pts[f[i]][0],pts[f[i]][1]);
    ctx.closePath();ctx.fillStyle=col;ctx.fill();
  }
  ctx.globalAlpha=1;
  const selected=selectedIds.has(c.component_id);
  const overlap=last3DOverlapIds.has(c.component_id);
  const projected=previewProjectedBoxPx(pts);
  ctx.strokeStyle=overlap?"#c2410c":(selected?"#1d4ed8":(isWorld(c)?"#98a2b3":"#344054"));
  ctx.lineWidth=preview3DLineWidth(projected.minPx,{selected,world:isWorld(c),overlap});
  last3DStrokeSamples.push({id:c.component_id,projectedMinPx:projected.minPx,lineWidth:ctx.lineWidth});
  const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
  for(const [a,b] of edges){ctx.beginPath();ctx.moveTo(pts[a][0],pts[a][1]);ctx.lineTo(pts[b][0],pts[b][1]);ctx.stroke();}
  let drewLabel=false;
  if(selectedIds.has(c.component_id)&&labelIndex<4){
    const p=project([(bbox3D(c).min[0]+bbox3D(c).max[0])/2,(bbox3D(c).min[1]+bbox3D(c).max[1])/2,bbox3D(c).max[2]]);
    const text=c.display_name.length>18?c.display_name.slice(0,17)+"…":c.display_name;
    ctx.fillStyle="#101828";ctx.font="12px sans-serif";ctx.fillText(text,p[0]+8,p[1]-8-labelIndex*14);
    drewLabel=true;
  }
  ctx.restore();
  return drewLabel;
}
function draw3DGrid(ctx,project,bounds){
  const z=bounds.min[2],steps=4;
  ctx.save();ctx.strokeStyle="#e0e6ef";ctx.lineWidth=1;
  for(let i=0;i<=steps;i++){
    const t=i/steps;
    const x=bounds.min[0]+(bounds.max[0]-bounds.min[0])*t;
    let a=project([x,bounds.min[1],z]),b=project([x,bounds.max[1],z]);
    ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
    const y=bounds.min[1]+(bounds.max[1]-bounds.min[1])*t;
    a=project([bounds.min[0],y,z]);b=project([bounds.max[0],y,z]);
    ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
  }
  ctx.restore();
}
function draw3DAxes(ctx,project,bounds){
  const o=[bounds.min[0],bounds.min[1],bounds.min[2]];
  const axis=[["x",[bounds.max[0],bounds.min[1],bounds.min[2]],"#2563eb"],["y",[bounds.min[0],bounds.max[1],bounds.min[2]],"#047857"],["z",[bounds.min[0],bounds.min[1],bounds.max[2]],"#c2410c"]];
  const po=project(o);
  ctx.save();ctx.font="11px sans-serif";
  for(const [label,end,color] of axis){
    const pe=project(end);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(po[0],po[1]);ctx.lineTo(pe[0],pe[1]);ctx.stroke();
    ctx.fillText(label,pe[0]+4,pe[1]+4);
  }
  ctx.restore();
}
function select3DHitAt(x,y,additive=false){
  if(!model)return null;
  const hits=last3DHitRegions
    .filter(r=>pointInPolygon2D(x,y,r.hull))
    .sort((a,b)=>b.depth-a.depth);
  const hit=hits[0];
  if(!hit)return null;
  if(additive){
    if(selectedIds.has(hit.id))selectedIds.delete(hit.id);
    else selectedIds.add(hit.id);
    primaryId=hit.id;
  }else{
    selectedIds=new Set([hit.id]);
    primaryId=hit.id;
  }
  if(selectedIds.size===0){primaryId=null;polyEditId=null;}
  const c=model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();drawComponents();draw3DPreview();
  return hit.id;
}
document.getElementById("preview3dCanvas")?.addEventListener("click",e=>{
  const canvas=e.currentTarget;
  const rect=canvas.getBoundingClientRect();
  const x=(e.clientX-rect.left)*(canvas.width/rect.width);
  const y=(e.clientY-rect.top)*(canvas.height/rect.height);
  const hit=select3DHitAt(x,y,e.shiftKey||e.ctrlKey||e.metaKey);
  if(hit)toast("3D 选中: "+hit);
});

/* ---------- 框选 / 背景平移 / 滚轮 ---------- */
let panning=false,panStart=null,marqueeState=null;
function isTouchLikeEvent(evt){return evt&&String(evt.type||"").startsWith("touch");}
function shouldPanViewport(evt){return isTouchLikeEvent(evt)||!!(evt&&(evt.altKey||evt.button===1));}
function currentLayerPointer(){return compLayer.getRelativePointerPosition();}
function clearSelection(){
  selectedIds.clear();primaryId=null;polyEditId=null;selectedPolygonVertexIndex=null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();drawComponents();draw3DPreview();
}
function drawMarquee(){
  marqueeGroup.destroyChildren();
  if(!marqueeState||!marqueeState.active)return;
  const r=normalizeMarqueeRect({x1:marqueeState.start.x,y1:marqueeState.start.y,x2:marqueeState.current.x,y2:marqueeState.current.y});
  marqueeGroup.add(new Konva.Rect({
    x:r.x,y:r.y,width:r.w,height:r.h,
    fill:"rgba(37,99,235,0.08)",
    stroke:"#2563eb",
    strokeWidth:1,
    strokeScaleEnabled:false,
    dash:[5,3],
    listening:false,
  }));
  marqueeGroup.moveToTop();
  uiLayer.batchDraw();
}
function updateMarquee(){
  if(!marqueeState)return;
  const p=currentLayerPointer(),screen=stage.getPointerPosition();
  if(!p||!screen)return;
  marqueeState.current=p;
  const dx=screen.x-marqueeState.screenStart.x,dy=screen.y-marqueeState.screenStart.y;
  if(!marqueeState.active&&Math.hypot(dx,dy)>=MARQUEE_DRAG_THRESHOLD_PX)marqueeState.active=true;
  drawMarquee();
}
function finishMarquee(){
  if(!marqueeState)return;
  const state=marqueeState;
  marqueeState=null;
  marqueeGroup.destroyChildren();
  if(state.active){
    selectByMarqueeRect({x1:state.start.x,y1:state.start.y,x2:state.current.x,y2:state.current.y},{additive:state.additive});
  }else if(!state.additive){
    clearSelection();
  }
  uiLayer.batchDraw();
}
stage.on("mousedown touchstart",e=>{
  if(toolMode==="measure"){handleMeasureClick();return;}
  if(e.target===stage){
    const evt=e.evt||{};
    if(shouldPanViewport(evt)){
      panning=true;const p=stage.getPointerPosition();if(p)panStart={x:p.x-stage.x(),y:p.y-stage.y()};
      return;
    }
    const p=currentLayerPointer(),screen=stage.getPointerPosition();
    if(!p||!screen)return;
    marqueeState={start:p,current:p,screenStart:screen,additive:!!(evt.shiftKey||evt.ctrlKey||evt.metaKey),active:false};
  }
});
stage.on("mousemove touchmove",()=>{handleMeasureMove();if(marqueeState){updateMarquee();return;}if(!panning||!panStart)return;const p=stage.getPointerPosition();if(!p)return;stage.position({x:p.x-panStart.x,y:p.y-panStart.y});bgLayer.batchDraw();compLayer.batchDraw();uiLayer.batchDraw();});
stage.on("mouseup touchend",()=>{finishMarquee();panning=false;panStart=null;});
window.addEventListener("mouseup",()=>{finishMarquee();panning=false;panStart=null;});
/* signature:实时坐标 HUD(像示波器/EDA,鼠标位置 [横向, 深度] μm) */
stage.on("mousemove",()=>{
  if(!model)return;
  const pos=compLayer.getRelativePointerPosition();
  if(!pos){return;}
  updateCadStatus({lat:toDataX(pos.x),dep:toDataY(pos.y)});
});
stage.on("mouseleave",()=>updateCadStatus(null,{clearCursor:true}));
document.getElementById("stageWrap").addEventListener("wheel",e=>{
  e.preventDefault();if(!model)return;
  const oldScale=stage.scaleX();const factor=e.deltaY<0?1.1:0.9;const newScale=Math.max(0.05,Math.min(80,oldScale*factor));
  const pointer=stage.getPointerPosition()||{x:stage.width()/2,y:stage.height()/2};
  const mx=(pointer.x-stage.x())/oldScale,my=(pointer.y-stage.y())/oldScale;
  stage.scale({x:newScale,y:newScale});stage.position({x:pointer.x-mx*newScale,y:pointer.y-my*newScale});
  drawBackground();refreshSelectionCanvasDecorations();drawOverlapRegions(overlapCache.value.regions||[]);drawAnnotations();drawPolyAnchors();stage.batchDraw();
},{passive:false});
function zoomBy(f){const s=Math.max(0.05,Math.min(80,stage.scaleX()*f));stage.scale({x:s,y:s});drawBackground();refreshSelectionCanvasDecorations();drawOverlapRegions(overlapCache.value.regions||[]);drawAnnotations();drawPolyAnchors();stage.batchDraw();}
function resetView(){stage.scale({x:1,y:1});stage.position({x:0,y:0});relayout();drawPolyAnchors();}

/* ---------- 轴切换 ---------- */
function onAxisChange(){
  const lat=document.getElementById("lateral").value,dep=document.getElementById("depth").value;
  if(lat===dep){toast("横向与深度轴不能相同","err");document.getElementById("lateral").value=axes.lateral;document.getElementById("depth").value=axes.depth;return;}
  axes.lateral=lat;axes.depth=dep;
  cadStatusCursor=null;
  updateSliceUI();
  selectedIds=new Set([...selectedIds].filter(id=>{
    const c=model.components.find(c=>c.component_id===id);
    return c&&visibleInCurrentSection(c);
  }));
  primaryId=[...selectedIds][0]||null;
  polyEditId=null;resetView();refreshSelectionViews();renderAnnotationsPanel();updateModelHealth();draw3DPreview();toast(`截面: ${lat} × ${dep}`);
}
function setViewAxes(lat,dep){
  document.getElementById("lateral").value=lat;
  document.getElementById("depth").value=dep;
  onAxisChange();
}
function inferAxes(components){
  const span=a=>{const idx=AXIS_IDX[a];let mn=Infinity,mx=-Infinity;for(const c of components){const d=(c.dimensions&&c.dimensions[DIM_KEY[a]])||0;const p=c.placement.position[idx];mn=Math.min(mn,p-d/2);mx=Math.max(mx,p+d/2);}return isFinite(mn)?mx-mn:0;};
  const s={x:span("x"),y:span("y"),z:span("z")};
  const depth=Object.entries(s).sort((a,b)=>a[1]-b[1])[0][0];
  const lat=["x","y","z"].filter(a=>a!==depth).sort((a,b)=>s[b]-s[a])[0];
  axes.lateral=lat;axes.depth=depth;
}
function populateAxisSelectors(){
  const lat=document.getElementById("lateral"),dep=document.getElementById("depth");lat.innerHTML="";dep.innerHTML="";
  for(const a of ["x","y","z"]){const o1=document.createElement("option");o1.value=a;o1.textContent=a;if(a===axes.lateral)o1.selected=true;lat.appendChild(o1);const o2=document.createElement("option");o2.value=a;o2.textContent=a;if(a===axes.depth)o2.selected=true;dep.appendChild(o2);}
}

/* ---------- 载入 ---------- */
function loadModel(data,sourceName){
  let components=[],materials=[],meta={};
  if(Array.isArray(data))components=data;
  else if(data.components){components=data.components;materials=data.materials||[];dimensionAnnotations=JSON.parse(JSON.stringify(data.device_canvas_state?.annotations||data.device_canvas_annotations||[]));meta={model_ir_id:data.model_ir_id,job_id:data.job_id,target_system:data.target_system,coordinate_system:data.coordinate_system,global_units:data.global_units,_full:data};}
  else{toast("JSON 里没找到 components","err");return;}
  components=components.map(normalizeComponent);
  if(Array.isArray(data))dimensionAnnotations=[];
  model={meta,components,materials,sourceName};selectedIds.clear();primaryId=null;polyEditId=null;cadStatusCursor=null;selectionSets=[];viewStates=[];drcWaivers=[];
  isolationState={active:false,snapshot:null};
  inferAxes(components);if(!Array.isArray(data))applyDeviceCanvasState(data.device_canvas_state);populateAxisSelectors();updateSliceUI();updateDrcUI();updateStackUI();updateTransformConstraintUI();updateSnapUI();resetView();refreshSelectionViews();renderAnnotationsPanel();renderSelectionSets();renderViewStates();renderAssemblyTree();updateModelHealth();draw3DPreview();
  history.stack=[];history.ptr=-1;pushHistory();   // 初始状态入栈
  toast(`已载入 ${components.length} 个组件${sourceName?" ("+sourceName+")":""}`);
}
function normalizeComponent(c){
  const dims=c.dimensions||{};
  const nc={
    component_id:c.component_id||`comp_${Math.random().toString(36).slice(2,7)}`,
    display_name:c.display_name||c.component_id||"component",
    component_type:c.component_type||"volume",
    geometry_type:c.geometry_type||"box",
    dimensions:{dx:+dims.dx||0,dy:+dims.dy||0,dz:+dims.dz||0},
    material_id:c.material_id||"Silicon",
    placement:{position:(c.placement&&c.placement.position)?c.placement.position.map(Number):[0,0,0],rotation:(c.placement&&c.placement.rotation)?c.placement.rotation.map(Number):[0,0,0]},
    mother_volume:c.mother_volume??null,sensitive:!!c.sensitive,roles:c.roles||[],color:c.color||null,
    source_evidence:c.source_evidence||["user_canvas_edit"],open_issues:c.open_issues||[],
    requires_confirmation:c.requires_confirmation||false,confirmed_by_user:true,confirmation_source:"device_canvas",
    locked:!!c.locked,
    hidden:!!c.hidden,
  };
  if(c.cross_section_polygon&&c.cross_section_polygon.length){nc.polygon=c.cross_section_polygon.map(p=>Array.isArray(p)?[+p[0]||0,+p[1]||0,+p[2]||0]:[0,0,0]);nc.polygonAxes=c.cross_section_polygon_axes||{lateral:axes.lateral,depth:axes.depth};nc.geometry_type=c.geometry_type||"polycone";}
  return nc;
}

/* ---------- 列表 ---------- */
function componentMatchesQuery(c,q){
  if(!q)return true;
  const hay=[c.component_id,c.display_name,c.material_id,c.component_type,c.geometry_type,(c.roles||[]).join(" ")].join(" ").toLowerCase();
  return hay.includes(q);
}
function normalizeComponentStatusFilter(value){
  return ["all","visible","hidden","locked"].includes(value)?value:"all";
}
function currentComponentSearchQuery(){
  return (document.getElementById("componentSearch")?.value||"").trim().toLowerCase();
}
function currentComponentStatusFilter(){
  const el=document.getElementById("componentStatusFilter");
  componentListFilterState.status=normalizeComponentStatusFilter(el?.value||componentListFilterState.status);
  if(el&&el.value!==componentListFilterState.status)el.value=componentListFilterState.status;
  return componentListFilterState.status;
}
function componentPassesListFilter(c,{query=currentComponentSearchQuery(),status=currentComponentStatusFilter()}={}){
  if(!componentMatchesQuery(c,query))return false;
  if(status==="visible")return visibleInCurrentSection(c);
  if(status==="hidden")return !!c.hidden;
  if(status==="locked")return !!c.locked&&!isWorld(c);
  return true;
}
function onComponentListFilterChange(){
  currentComponentStatusFilter();
  renderList();
}
function clearComponentListFilter(){
  const search=document.getElementById("componentSearch");
  const status=document.getElementById("componentStatusFilter");
  if(search)search.value="";
  componentListFilterState.status="all";
  if(status)status.value="all";
  renderList();
}
function selectionSetExistingIds(ids){
  if(!model)return [];
  const wanted=new Set(ids||[]);
  return model.components
    .filter(c=>!isWorld(c)&&wanted.has(c.component_id))
    .map(c=>c.component_id);
}
function normalizeSelectionSets(sets){
  const seen=new Set();
  return (sets||[]).map((s,i)=>{
    const id=String(s.id||`set_${Date.now().toString(36)}_${i}`).replace(/[^a-zA-Z0-9_-]/g,"_").slice(0,80);
    const name=String(s.name||`选区 ${i+1}`).trim().slice(0,80)||`选区 ${i+1}`;
    const componentIds=selectionSetExistingIds(s.componentIds||s.ids||[]);
    return componentIds.length?{id,name,componentIds}:null;
  }).filter(Boolean).filter(s=>{
    if(seen.has(s.id))return false;
    seen.add(s.id);return true;
  });
}
function serializeSelectionSets(){
  return normalizeSelectionSets(selectionSets).map(s=>({
    id:s.id,
    name:s.name,
    componentIds:s.componentIds.slice(),
  }));
}
function pruneSelectionSets(){
  selectionSets=normalizeSelectionSets(selectionSets);
}
function selectionSetById(id){
  return selectionSets.find(s=>s.id===id)||null;
}
function nextSelectionSetName(){
  return `选区 ${selectionSets.length+1}`;
}
function saveSelectionSet(name){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return null;}
  const componentIds=selectionSetExistingIds([...selectedIds]);
  if(!componentIds.length){toast("没有可保存的组件","err");return null;}
  const cleanName=String(name||nextSelectionSetName()).trim().slice(0,80)||nextSelectionSetName();
  const existing=selectionSets.find(s=>s.name===cleanName);
  const set=existing||{id:`sel_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,6)}`,name:cleanName,componentIds:[]};
  set.name=cleanName;set.componentIds=componentIds;
  if(!existing)selectionSets.push(set);
  renderSelectionSets();
  toast(`已保存选区 ${cleanName}`);
  return set;
}
function saveSelectionSetFromInput(){
  const input=document.getElementById("selectionSetName");
  const name=(input&&input.value.trim())||nextSelectionSetName();
  const set=saveSelectionSet(name);
  if(set&&input)input.value="";
}
function applySelectionSet(id){
  if(!model)return;
  const set=selectionSetById(id);
  if(!set){toast("选择集不存在","err");renderSelectionSets();return;}
  const ids=selectionSetExistingIds(set.componentIds);
  if(!ids.length){toast("选择集组件不存在","err");deleteSelectionSet(id,false);return;}
  selectedIds=new Set(ids);
  primaryId=ids[0]||null;
  const c=model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();draw3DPreview();drawComponents();
  toast(`已选择 ${ids.length} 个组件`);
}
function isolateSelectionSet(id){
  if(!model)return;
  const set=selectionSetById(id);
  if(!set){toast("选择集不存在","err");renderSelectionSets();return;}
  const ids=selectionSetExistingIds(set.componentIds);
  if(!ids.length){toast("选择集组件不存在","err");deleteSelectionSet(id,false);return;}
  if(!isolationState.active)isolationState={active:true,snapshot:visibilitySnapshot()};
  const keep=new Set(ids);
  for(const c of model.components){
    if(isWorld(c)){c.hidden=false;continue;}
    c.hidden=!keep.has(c.component_id);
  }
  selectedIds=new Set(ids);primaryId=ids[0]||null;polyEditId=null;
  refreshVisibilityViews(true);
  toast(`已隔离选择集 ${set.name}`);
}
function deleteSelectionSet(id,showToast=true){
  const before=selectionSets.length;
  selectionSets=selectionSets.filter(s=>s.id!==id);
  renderSelectionSets();
  if(showToast&&before!==selectionSets.length)toast("已删除选择集");
}
function renderSelectionSets(){
  const root=document.getElementById("selectionSetList");if(!root)return;
  pruneSelectionSets();
  if(!selectionSets.length){root.innerHTML='<div class="empty-side">无保存选区</div>';return;}
  root.innerHTML="";
  for(const set of selectionSets){
    const row=document.createElement("div");
    row.className="annotation-row";
    const text=document.createElement("div");
    const title=document.createElement("b");title.textContent=set.name;
    const meta=document.createElement("small");meta.textContent=`${set.componentIds.length} 个组件 · ${set.componentIds.join(", ")}`;
    text.appendChild(title);text.appendChild(meta);row.appendChild(text);
    const actions=document.createElement("div");
    actions.style.display="grid";actions.style.gridTemplateColumns="repeat(3,auto)";actions.style.gap="4px";
    const selectBtn=document.createElement("button");selectBtn.textContent="选";selectBtn.title="恢复该选择集";selectBtn.dataset.action="apply-selection-set";selectBtn.onclick=()=>applySelectionSet(set.id);actions.appendChild(selectBtn);
    const isolateBtn=document.createElement("button");isolateBtn.textContent="隔";isolateBtn.title="隔离该选择集";isolateBtn.dataset.action="isolate-selection-set";isolateBtn.onclick=()=>isolateSelectionSet(set.id);actions.appendChild(isolateBtn);
    const delBtn=document.createElement("button");delBtn.textContent="删";delBtn.title="删除选择集";delBtn.dataset.action="delete-selection-set";delBtn.onclick=()=>deleteSelectionSet(set.id);actions.appendChild(delBtn);
    row.appendChild(actions);
    root.appendChild(row);
  }
}
function buildLayerStateSnapshot(){
  const layers={};
  if(model){
    for(const c of model.components){
      const s={hidden:!!c.hidden};
      if(!isWorld(c))s.locked=!!c.locked;
      layers[c.component_id]=s;
    }
  }
  return layers;
}
function normalizeViewStateLayers(layers){
  const out={};
  if(!model||!layers||typeof layers!=="object")return out;
  for(const c of model.components){
    const layer=layers[c.component_id];
    if(!layer||typeof layer!=="object")continue;
    out[c.component_id]={hidden:!!layer.hidden};
    if(!isWorld(c))out[c.component_id].locked=!!layer.locked;
  }
  return out;
}
function normalizeViewStates(states){
  const seen=new Set();
  return (states||[]).map((s,i)=>{
    const id=String(s.id||`view_${Date.now().toString(36)}_${i}`).replace(/[^a-zA-Z0-9_-]/g,"_").slice(0,80);
    const name=String(s.name||`视图 ${i+1}`).trim().slice(0,80)||`视图 ${i+1}`;
    const lat=s.axes&&s.axes.lateral;
    const dep=s.axes&&s.axes.depth;
    const validAxes=["x","y","z"].includes(lat)&&["x","y","z"].includes(dep)&&lat!==dep;
    const slice=s.slice&&typeof s.slice==="object"?{
      enabled:!!s.slice.enabled,
      pos:Number(s.slice.pos)||0,
      thickness:Math.max(0,Number(s.slice.thickness)||0),
    }:{enabled:false,pos:0,thickness:1};
    return {
      id,
      name,
      axes:validAxes?{lateral:lat,depth:dep}:{lateral:axes.lateral,depth:axes.depth},
      slice,
      layers:normalizeViewStateLayers(s.layers||{}),
    };
  }).filter(s=>{
    if(seen.has(s.id))return false;
    seen.add(s.id);return Object.keys(s.layers).length>0;
  });
}
function serializeViewStates(){
  return normalizeViewStates(viewStates).map(s=>({
    id:s.id,
    name:s.name,
    axes:{...s.axes},
    slice:JSON.parse(JSON.stringify(s.slice)),
    layers:JSON.parse(JSON.stringify(s.layers)),
  }));
}
function pruneViewStates(){
  viewStates=normalizeViewStates(viewStates);
}
function viewStateById(id){
  return viewStates.find(s=>s.id===id)||null;
}
function nextViewStateName(){
  return `视图 ${viewStates.length+1}`;
}
function saveViewState(name){
  if(!model){toast("先载入模型","err");return null;}
  const cleanName=String(name||nextViewStateName()).trim().slice(0,80)||nextViewStateName();
  const existing=viewStates.find(s=>s.name===cleanName);
  const state=existing||{id:`view_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,6)}`,name:cleanName};
  state.name=cleanName;
  state.axes={lateral:axes.lateral,depth:axes.depth};
  state.slice=JSON.parse(JSON.stringify(sliceState));
  state.layers=buildLayerStateSnapshot();
  if(!existing)viewStates.push(state);
  renderViewStates();
  toast(`已保存视图 ${cleanName}`);
  return state;
}
function saveViewStateFromInput(){
  const input=document.getElementById("viewStateName");
  const name=(input&&input.value.trim())||nextViewStateName();
  const state=saveViewState(name);
  if(state&&input)input.value="";
}
function applyViewState(id){
  if(!model)return;
  const state=viewStateById(id);
  if(!state){toast("视图不存在","err");renderViewStates();return;}
  if(state.axes&&state.axes.lateral&&state.axes.depth&&state.axes.lateral!==state.axes.depth){
    axes.lateral=state.axes.lateral;axes.depth=state.axes.depth;
  }
  sliceState={
    enabled:!!state.slice?.enabled,
    pos:Number(state.slice?.pos)||0,
    thickness:Math.max(0,Number(state.slice?.thickness)||0),
  };
  for(const c of model.components){
    const layer=state.layers[c.component_id];
    c.hidden=!!(layer&&layer.hidden);
    if(!isWorld(c))c.locked=!!(layer&&layer.locked);
    else c.hidden=false;
  }
  isolationState={active:false,snapshot:null};
  populateAxisSelectors();
  updateSliceUI();
  resetView();
  refreshVisibilityViews(true);
  renderViewStates();
  toast(`已恢复视图 ${state.name}`);
}
function deleteViewState(id,showToast=true){
  const before=viewStates.length;
  viewStates=viewStates.filter(s=>s.id!==id);
  renderViewStates();
  if(showToast&&before!==viewStates.length)toast("已删除视图");
}
function renderViewStates(){
  const root=document.getElementById("viewStateList");if(!root)return;
  pruneViewStates();
  if(!viewStates.length){root.innerHTML='<div class="empty-side">无保存视图</div>';return;}
  root.innerHTML="";
  for(const state of viewStates){
    const row=document.createElement("div");
    row.className="annotation-row";
    const text=document.createElement("div");
    const title=document.createElement("b");title.textContent=state.name;
    const hiddenCount=Object.values(state.layers||{}).filter(layer=>layer.hidden).length;
    const lockedCount=Object.values(state.layers||{}).filter(layer=>layer.locked).length;
    const slice=state.slice?.enabled?` · slice ${["x","y","z"].find(a=>a!==state.axes.lateral&&a!==state.axes.depth)} ${fmt(state.slice.pos)}±${fmt((state.slice.thickness||0)/2)}`:"";
    const meta=document.createElement("small");meta.textContent=`${state.axes.lateral}×${state.axes.depth} · 隐藏 ${hiddenCount} · 锁定 ${lockedCount}${slice}`;
    text.appendChild(title);text.appendChild(meta);row.appendChild(text);
    const actions=document.createElement("div");
    actions.style.display="grid";actions.style.gridTemplateColumns="repeat(2,auto)";actions.style.gap="4px";
    const applyBtn=document.createElement("button");applyBtn.textContent="用";applyBtn.title="恢复该视图状态";applyBtn.dataset.action="apply-view-state";applyBtn.onclick=()=>applyViewState(state.id);actions.appendChild(applyBtn);
    const delBtn=document.createElement("button");delBtn.textContent="删";delBtn.title="删除视图状态";delBtn.dataset.action="delete-view-state";delBtn.onclick=()=>deleteViewState(state.id);actions.appendChild(delBtn);
    row.appendChild(actions);
    root.appendChild(row);
  }
}
function validateComponentId(candidate,currentId=null){
  const id=String(candidate||"").trim();
  if(!id)return {ok:false,reason:"empty",id};
  if(!/^[A-Za-z0-9_][A-Za-z0-9_.:-]*$/.test(id))return {ok:false,reason:"invalid",id};
  const exists=model&&model.components.some(c=>c.component_id===id&&c.component_id!==currentId);
  if(exists)return {ok:false,reason:"duplicate",id};
  return {ok:true,id};
}
function renameIssueSignatureId(signature,oldId,newId){
  const sig=String(signature||"");
  const sep=sig.indexOf(":");
  if(sep<0)return sig;
  const code=sig.slice(0,sep);
  const ids=sig.slice(sep+1).split("+").filter(Boolean);
  if(!ids.includes(oldId))return sig;
  const next=[...new Set(ids.map(id=>id===oldId?newId:id))].sort();
  return `${code}:${next.join("+")}`;
}
function replaceComponentIdRefs(oldId,newId){
  for(const c of model.components){
    if(c.mother_volume===oldId)c.mother_volume=newId;
  }
  if(selectedIds.has(oldId)){
    selectedIds=new Set([...selectedIds].map(id=>id===oldId?newId:id));
  }
  if(primaryId===oldId)primaryId=newId;
  if(polyEditId===oldId)polyEditId=newId;
  for(const set of selectionSets){
    set.componentIds=[...new Set((set.componentIds||[]).map(id=>id===oldId?newId:id))];
  }
  for(const state of viewStates){
    if(state.layers&&state.layers[oldId]){
      state.layers[newId]=state.layers[oldId];
      delete state.layers[oldId];
    }
  }
  for(const ann of dimensionAnnotations){
    if(ann.component_id===oldId)ann.component_id=newId;
    if(ann.a_id===oldId)ann.a_id=newId;
    if(ann.b_id===oldId)ann.b_id=newId;
    if(ann.kind==="pair_gap"&&ann.a_id&&ann.b_id&&ann.axis){
      ann.id=`pair_gap:${ann.a_id}:${ann.b_id}:${ann.axis}`;
    }
  }
  drcWaivers=normalizeDrcWaivers(drcWaivers.map(w=>({
    ...w,
    ids:(w.ids||[]).map(id=>id===oldId?newId:id),
    signature:renameIssueSignatureId(w.signature,oldId,newId),
  })));
  pruneSelectionSets();
  pruneViewStates();
}
function renameComponent(id,{component_id,display_name}={},opts={}){
  if(!model)return {ok:false,reason:"no_model"};
  const c=model.components.find(c=>c.component_id===id);
  if(!c)return {ok:false,reason:"missing",id};
  const oldId=c.component_id;
  const requestedId=component_id===undefined?oldId:String(component_id).trim();
  const validation=validateComponentId(requestedId,oldId);
  if(!validation.ok)return validation;
  const newId=validation.id;
  if(display_name!==undefined)c.display_name=String(display_name).trim()||c.display_name||newId;
  if(newId!==oldId){
    c.component_id=newId;
    replaceComponentIdRefs(oldId,newId);
  }
  if(opts.refresh!==false){
    renderSelectionSets();
    renderViewStates();
    refreshTransformer();
    drawPolyAnchors();
    refreshSelectionViews();
    renderAnnotationsPanel();
    drawComponents();
    updateModelHealth();
    draw3DPreview();
  }
  if(opts.record!==false)pushHistory();
  return {ok:true,oldId,newId,displayName:c.display_name};
}
function normalizeLayerGroupMode(mode){
  return mode==="type"?"type":"material";
}
function layerGroupKey(mode,c){
  mode=normalizeLayerGroupMode(mode);
  return mode==="type"?(c.component_type||"volume"):(c.material_id||"Unassigned");
}
function layerGroupLabel(mode,key){
  return normalizeLayerGroupMode(mode)==="type"?`type: ${key}`:`material: ${key}`;
}
function layerGroupIds(mode,key,{visibleOnly=false}={}){
  if(!model)return [];
  mode=normalizeLayerGroupMode(mode);
  return model.components
    .filter(c=>!isWorld(c)&&layerGroupKey(mode,c)===key&&(!visibleOnly||visibleInCurrentSection(c)))
    .map(c=>c.component_id);
}
function layerGroupRows(mode=layerGroupMode){
  if(!model)return [];
  mode=normalizeLayerGroupMode(mode);
  const groups=new Map();
  for(const c of model.components){
    if(isWorld(c))continue;
    const key=layerGroupKey(mode,c);
    if(!groups.has(key))groups.set(key,{mode,key,label:layerGroupLabel(mode,key),componentIds:[],count:0,visibleCount:0,lockedCount:0,color:mode==="material"?matColor(key):null});
    const row=groups.get(key);
    row.componentIds.push(c.component_id);
    row.count++;
    if(visibleInCurrentSection(c))row.visibleCount++;
    if(c.locked)row.lockedCount++;
  }
  return [...groups.values()].sort((a,b)=>b.count-a.count||a.key.localeCompare(b.key));
}
function applyLayerGroupSelection(ids){
  selectedIds=new Set(ids);
  primaryId=ids[0]||null;
  const c=model&&model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();draw3DPreview();drawComponents();
}
function selectLayerGroup(mode,key){
  if(!model)return;
  const ids=layerGroupIds(mode,key,{visibleOnly:true});
  if(!ids.length){toast("该属性图层当前没有可见组件","err");return;}
  applyLayerGroupSelection(ids);
  toast(`已选择 ${ids.length} 个组件`);
}
function isolateLayerGroup(mode,key){
  if(!model)return;
  const ids=layerGroupIds(mode,key);
  if(!ids.length){toast("属性图层为空","err");return;}
  if(!isolationState.active)isolationState={active:true,snapshot:visibilitySnapshot()};
  const keep=new Set(ids);
  for(const c of model.components){
    if(isWorld(c)){c.hidden=false;continue;}
    c.hidden=!keep.has(c.component_id);
  }
  selectedIds=new Set(ids);primaryId=ids[0]||null;polyEditId=null;
  refreshVisibilityViews(true);
  toast(`已隔离属性图层 ${key}`);
}
function setLayerGroupHidden(mode,key,hidden=true){
  if(!model)return;
  const ids=new Set(layerGroupIds(mode,key));
  if(!ids.size){toast("属性图层为空","err");return;}
  for(const c of model.components){
    if(ids.has(c.component_id)&&!isWorld(c))c.hidden=!!hidden;
  }
  refreshVisibilityViews(true);
  toast(hidden?`已隐藏 ${key}`:`已显示 ${key}`);
}
function setLayerGroupLocked(mode,key,locked=true){
  if(!model)return;
  const ids=new Set(layerGroupIds(mode,key));
  if(!ids.size){toast("属性图层为空","err");return;}
  for(const c of model.components){
    if(ids.has(c.component_id)&&!isWorld(c))c.locked=!!locked;
  }
  refreshTransformer();refreshSelectionViews();drawComponents();pushHistory();
  toast(locked?`已锁定 ${key}`:`已解锁 ${key}`);
}
function onLayerGroupModeChange(){
  const el=document.getElementById("layerGroupMode");
  layerGroupMode=normalizeLayerGroupMode(el&&el.value);
  renderLayerGroups();
}
function renderLayerGroups(){
  const root=document.getElementById("layerGroupList");if(!root)return;
  const modeEl=document.getElementById("layerGroupMode");
  if(modeEl){modeEl.value=normalizeLayerGroupMode(layerGroupMode);layerGroupMode=modeEl.value;}
  if(!model){root.innerHTML='<div class="empty-side">载入模型后显示材料/类型分组</div>';return;}
  const rows=layerGroupRows(layerGroupMode);
  if(!rows.length){root.innerHTML='<div class="empty-side">无可分组组件</div>';return;}
  root.innerHTML="";
  for(const row of rows){
    const item=document.createElement("div");
    item.className="annotation-row";
    item.dataset.groupMode=row.mode;
    item.dataset.groupKey=row.key;
    item.style.gridTemplateColumns="minmax(0,1fr) auto";
    const text=document.createElement("div");
    const title=document.createElement("b");
    if(row.color){
      const sw=document.createElement("span");
      sw.className="swatch";
      sw.style.background=row.color;
      sw.style.marginRight="6px";
      title.appendChild(sw);
    }
    title.appendChild(document.createTextNode(row.key));
    const meta=document.createElement("small");
    meta.textContent=`${row.count} 个 · 可见 ${row.visibleCount} · 锁定 ${row.lockedCount}`;
    text.appendChild(title);text.appendChild(meta);item.appendChild(text);
    const actions=document.createElement("div");
    actions.style.display="grid";actions.style.gridTemplateColumns="repeat(6,auto)";actions.style.gap="4px";
    const addBtn=(label,titleText,action,fn)=>{
      const btn=document.createElement("button");
      btn.textContent=label;btn.title=titleText;btn.dataset.action=action;btn.onclick=fn;actions.appendChild(btn);
    };
    addBtn("选","选择当前可见的该属性组","select-layer-group",()=>selectLayerGroup(row.mode,row.key));
    addBtn("隔","只显示该属性组","isolate-layer-group",()=>isolateLayerGroup(row.mode,row.key));
    addBtn("隐","隐藏该属性组","hide-layer-group",()=>setLayerGroupHidden(row.mode,row.key,true));
    addBtn("显","显示该属性组","show-layer-group",()=>setLayerGroupHidden(row.mode,row.key,false));
    addBtn("锁","锁定该属性组","lock-layer-group",()=>setLayerGroupLocked(row.mode,row.key,true));
    addBtn("解","解锁该属性组","unlock-layer-group",()=>setLayerGroupLocked(row.mode,row.key,false));
    item.appendChild(actions);
    root.appendChild(item);
  }
}
function assemblyChildrenMap(){
  const map=new Map();
  if(!model)return map;
  const ids=new Set(model.components.map(c=>c.component_id));
  for(const c of model.components){
    const parent=c.mother_volume&&ids.has(c.mother_volume)?c.mother_volume:null;
    if(!map.has(parent))map.set(parent,[]);
    map.get(parent).push(c);
  }
  return map;
}
function assemblySubtreeIds(id){
  if(!model)return [];
  const byId=new Map(model.components.map(c=>[c.component_id,c]));
  const children=assemblyChildrenMap();
  const out=[],seen=new Set();
  const visit=cid=>{
    if(seen.has(cid))return;
    seen.add(cid);
    const c=byId.get(cid);
    if(!c)return;
    if(!isWorld(c))out.push(cid);
    for(const child of children.get(cid)||[])visit(child.component_id);
  };
  visit(id);
  return out;
}
function assemblyTreeRows(){
  if(!model)return [];
  const children=assemblyChildrenMap();
  const rows=[],seen=new Set();
  const visit=(c,depth)=>{
    if(!c||seen.has(c.component_id))return;
    seen.add(c.component_id);
    const direct=children.get(c.component_id)||[];
    rows.push({component:c,depth,childCount:direct.length,subtreeIds:assemblySubtreeIds(c.component_id)});
    for(const child of direct)visit(child,depth+1);
  };
  for(const c of children.get(null)||[])visit(c,0);
  for(const c of model.components)visit(c,0);
  return rows;
}
function applyAssemblySelection(ids){
  selectedIds=new Set(ids);
  primaryId=ids[0]||null;
  const c=model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();draw3DPreview();drawComponents();
}
function selectAssemblySubtree(id){
  if(!model)return;
  const ids=assemblySubtreeIds(id);
  if(!ids.length){toast("该装配节点没有可选组件","err");return;}
  applyAssemblySelection(ids);
  toast(`已选择子树 ${ids.length} 个组件`);
}
function isolateAssemblySubtree(id){
  if(!model)return;
  const ids=assemblySubtreeIds(id);
  if(!ids.length){toast("该装配节点没有可隔离组件","err");return;}
  if(!isolationState.active)isolationState={active:true,snapshot:visibilitySnapshot()};
  const keep=new Set(ids);
  for(const c of model.components){
    if(isWorld(c)){c.hidden=false;continue;}
    c.hidden=!keep.has(c.component_id);
  }
  selectedIds=new Set(ids);primaryId=ids[0]||null;polyEditId=null;
  refreshVisibilityViews(true);
  toast(`已隔离装配子树 ${ids.length} 个组件`);
}
function hideAssemblySubtree(id,hidden=true){
  if(!model)return;
  const ids=assemblySubtreeIds(id);
  if(!ids.length){toast("该装配节点没有可切换组件","err");return;}
  const wanted=new Set(ids);
  for(const c of model.components){
    if(wanted.has(c.component_id)&&!isWorld(c))c.hidden=!!hidden;
  }
  refreshVisibilityViews(true);
  toast(hidden?`已隐藏子树 ${ids.length} 个组件`:`已显示子树 ${ids.length} 个组件`);
}
function renderAssemblyTree(){
  const root=document.getElementById("assemblyTreeList");if(!root)return;
  if(!model){root.innerHTML='<div class="empty-side">载入模型后显示装配树</div>';return;}
  const rows=assemblyTreeRows();
  if(!rows.length){root.innerHTML='<div class="empty-side">无装配节点</div>';return;}
  root.innerHTML="";
  for(const row of rows){
    const c=row.component;
    const item=document.createElement("div");
    item.className="annotation-row";
    item.dataset.cid=c.component_id;
    item.style.gridTemplateColumns="minmax(0,1fr) auto";
    const text=document.createElement("div");
    text.style.paddingLeft=`${Math.min(row.depth*14,56)}px`;
    const title=document.createElement("b");
    title.textContent=`${row.depth?"└ ":""}${c.display_name}${isWorld(c)?" (world)":""}`;
    const meta=document.createElement("small");
    const visible=c.hidden?"隐藏":"显示";
    meta.textContent=`${c.component_id} · 子级 ${row.childCount} · 子树 ${row.subtreeIds.length} · ${visible}`;
    text.appendChild(title);text.appendChild(meta);item.appendChild(text);
    const actions=document.createElement("div");
    actions.style.display="grid";actions.style.gridTemplateColumns="repeat(4,auto)";actions.style.gap="4px";
    const addBtn=(label,title,action,fn)=>{
      const btn=document.createElement("button");
      btn.textContent=label;btn.title=title;btn.dataset.action=action;btn.onclick=fn;actions.appendChild(btn);
    };
    addBtn("选","选择该装配子树","select-assembly-subtree",()=>selectAssemblySubtree(c.component_id));
    addBtn("隔","隔离该装配子树","isolate-assembly-subtree",()=>isolateAssemblySubtree(c.component_id));
    addBtn("隐","隐藏该装配子树","hide-assembly-subtree",()=>hideAssemblySubtree(c.component_id,true));
    addBtn("显","显示该装配子树","show-assembly-subtree",()=>hideAssemblySubtree(c.component_id,false));
    item.appendChild(actions);
    root.appendChild(item);
  }
}
function visibleComponentIds(){
  if(!model)return [];
  const q=currentComponentSearchQuery();
  const status=currentComponentStatusFilter();
  return model.components.filter(c=>visibleInCurrentSection(c)&&componentPassesListFilter(c,{query:q,status})).map(c=>c.component_id);
}
function renderList(){
  const ul=document.getElementById("compList");if(!model){ul.innerHTML="";return;}ul.innerHTML="";
  document.getElementById("selCount").textContent=selectedIds.size?`已选 ${selectedIds.size}`:"未选";
  const q=currentComponentSearchQuery();
  const status=currentComponentStatusFilter();
  let shown=0;
  for(const c of model.components){
    if(!componentPassesListFilter(c,{query:q,status}))continue;
    shown++;
    const inSection=visibleInCurrentSection(c);
    const li=document.createElement("li");li.dataset.cid=c.component_id;if(selectedIds.has(c.component_id))li.classList.add("sel");if(!inSection)li.classList.add("muted");
    const eye=document.createElement("button");eye.className="layer-btn";eye.title=c.hidden?"显示":"隐藏";eye.textContent=c.hidden?"○":"●";eye.onclick=e=>{e.stopPropagation();toggleHidden(c.component_id);};li.appendChild(eye);
    const lock=document.createElement("button");lock.className="layer-btn";lock.title=isWorld(c)?"world 不锁定":(c.locked?"解锁":"锁定");lock.textContent=isWorld(c)?"-":(c.locked?"L":"U");lock.disabled=isWorld(c);lock.onclick=e=>{e.stopPropagation();toggleLocked(c.component_id);};li.appendChild(lock);
    const sw=document.createElement("span");sw.className="swatch";sw.style.background=isWorld(c)?"transparent":matColor(c.material_id);sw.style.border=isWorld(c)?"1px dashed #6a7280":"1px solid rgba(255,255,255,.15)";li.appendChild(sw);
    const nm=document.createElement("span");nm.textContent=c.display_name+(isWorld(c)?" (world)":"")+(c.polygon?" ◇":"")+(last3DOverlapIds.has(c.component_id)?" !":(lastOverlapIds.has(c.component_id)?" ·2D":""));if(last3DOverlapIds.has(c.component_id)){nm.style.color="#9a3412";}li.appendChild(nm);
    const cid=document.createElement("span");cid.className="comp-id";cid.textContent=c.component_id;cid.title=c.component_id;li.appendChild(cid);
    const p=document.createElement("span");p.className="pill";p.textContent=c.material_id;li.appendChild(p);
    li.onclick=()=>selectOnly(c.component_id);
    ul.appendChild(li);
  }
  if(!shown)ul.innerHTML='<li class="empty-side" style="cursor:default">没有匹配组件</li>';
}
function toggleHidden(id){
  const c=model.components.find(c=>c.component_id===id);if(!c)return;
  c.hidden=!c.hidden;
  if(c.hidden&&selectedIds.has(id)){selectedIds.delete(id);primaryId=[...selectedIds][0]||null;}
  drawComponents();refreshSelectionViews();renderAnnotationsPanel();draw3DPreview();pushHistory();
}
function toggleLocked(id){
  const c=model.components.find(c=>c.component_id===id);if(!c)return;
  if(isWorld(c))return;
  c.locked=!c.locked;
  refreshTransformer();refreshSelectionViews();drawComponents();pushHistory();
}
function visibilitySnapshot(){
  const snap={};
  if(model)for(const c of model.components)snap[c.component_id]=!!c.hidden;
  return snap;
}
function syncSelectionAfterVisibilityChange(){
  selectedIds=new Set([...selectedIds].filter(id=>{
    const c=model.components.find(c=>c.component_id===id);
    return c&&visibleInCurrentSection(c);
  }));
  primaryId=[...selectedIds][0]||null;
  const c=model.components.find(c=>c.component_id===primaryId);
  polyEditId=(c&&c.polygon&&polygonAxesMatch(c)&&selectedIds.size===1)?primaryId:null;
}
function refreshVisibilityViews(record=true){
  syncSelectionAfterVisibilityChange();
  drawComponents();
  refreshSelectionViews();
  renderAnnotationsPanel();
  draw3DPreview();
  if(record)pushHistory();
}
function isolateSelection(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  if(!isolationState.active)isolationState={active:true,snapshot:visibilitySnapshot()};
  const keep=new Set(selectedIds);
  for(const c of model.components){
    if(isWorld(c)){c.hidden=false;continue;}
    c.hidden=!keep.has(c.component_id);
  }
  refreshVisibilityViews(true);
  toast(`已隔离 ${keep.size} 个组件`);
}
function restoreIsolation(){
  if(!model||!isolationState.active||!isolationState.snapshot){toast("没有隔离视图可恢复");return;}
  for(const c of model.components){
    c.hidden=!!isolationState.snapshot[c.component_id];
    if(isWorld(c))c.hidden=false;
  }
  isolationState={active:false,snapshot:null};
  refreshVisibilityViews(true);
  toast("已恢复隔离前视图");
}
function showAllComponents(){
  if(!model)return;
  for(const c of model.components)c.hidden=false;
  isolationState={active:false,snapshot:null};
  refreshVisibilityViews(true);
  toast("已显示全部组件");
}
function clearSelection(){
  selectedIds.clear();primaryId=null;polyEditId=null;selectedPolygonVertexIndex=null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();renderAnnotationsPanel();draw3DPreview();
}
function selectAllVisible(){
  if(!model)return;
  selectedIds=new Set(
    visibleComponentIds().filter(id=>!isWorld(model.components.find(c=>c.component_id===id)))
  );
  primaryId=[...selectedIds][0]||null;polyEditId=null;
  refreshTransformer();drawPolyAnchors();refreshSelectionViews();draw3DPreview();
}
function focusSelection(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  const b=bboxOfSelection();if(!b)return;
  const W=stage.width(),H=stage.height();
  const padL=(b.maxLat-b.minLat)*0.18+1e-6,padD=(b.maxDep-b.minDep)*0.22+1e-6;
  camera.minLat=b.minLat-padL;camera.maxLat=b.maxLat+padL;camera.minDep=b.minDep-padD;camera.maxDep=b.maxDep+padD;
  const s=Math.min(W/(camera.maxLat-camera.minLat),H/(camera.maxDep-camera.minDep));
  camera.sLat=s;camera.sDep=s;camera.ox=(W-(camera.maxLat-camera.minLat)*s)/2;camera.oy=(H-(camera.maxDep-camera.minDep)*s)/2;
  stage.scale({x:1,y:1});stage.position({x:0,y:0});drawBackground();drawComponents();toast("已聚焦选中组件");
}
function duplicateSelected(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  syncTransformConstraintFromUI();
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const copies=[];let blocked=0;
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c)||!visibleInCurrentSection(c))continue;
    const result=makeOffsetCopy(c,{li,di,dLat:10,dDep:10,idBase:`${c.component_id}_copy`,name:`${c.display_name} copy`,evidence:`duplicate_of:${c.component_id}`});
    if(result.copy)copies.push(result.copy);
    if(result.blocked)blocked++;
  }
  if(!copies.length){toast(blocked?"复制会越出 mother/World 边界":"没有可复制组件","err");return;}
  model.components.push(...copies);
  const visibleCopies=copies.filter(c=>visibleInCurrentSection(c));
  selectedIds=new Set(visibleCopies.map(c=>c.component_id));primaryId=visibleCopies[0]?.component_id||null;polyEditId=null;
  resetView();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已复制 ${copies.length} 个组件,阻止 ${blocked} 个越界`:`已复制 ${copies.length} 个组件`);
}
function copySelectionToClipboard(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  const items=[];
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);
    if(!c||isWorld(c)||!visibleInCurrentSection(c))continue;
    items.push(JSON.parse(JSON.stringify(c)));
  }
  if(!items.length){toast("没有可复制组件","err");return;}
  componentClipboard={items,axes:{lateral:axes.lateral,depth:axes.depth},sourceIds:items.map(c=>c.component_id)};
  toast(`已复制到剪贴板 ${items.length} 个组件`);
}
function pasteClipboardSelection(){
  if(!model||!componentClipboard.items.length){toast("剪贴板为空","err");return;}
  syncTransformConstraintFromUI();
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const copies=[];let blocked=0;
  for(const item of componentClipboard.items){
    const result=makeOffsetCopy(item,{li,di,dLat:10,dDep:10,idBase:`${item.component_id}_paste`,name:`${item.display_name} paste`,evidence:`clipboard_of:${item.component_id}`});
    if(result.copy)copies.push(result.copy);
    if(result.blocked)blocked++;
  }
  if(!copies.length){toast(blocked?"粘贴会越出 mother/World 边界":"剪贴板没有可粘贴组件","err");return;}
  model.components.push(...copies);
  const visibleCopies=copies.filter(c=>visibleInCurrentSection(c));
  selectedIds=new Set(visibleCopies.map(c=>c.component_id));
  primaryId=visibleCopies[0]?.component_id||null;polyEditId=null;
  resetView();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已粘贴 ${copies.length} 个组件,阻止 ${blocked} 个越界`:`已粘贴 ${copies.length} 个组件`);
}
function arrayDuplicateSelection(){
  if(!model||selectedIds.size===0){toast("先选中组件","err");return;}
  syncTransformConstraintFromUI();
  const count=Math.floor(Number(document.getElementById("arrayCount")?.value||0));
  const dLat=Number(document.getElementById("arrayDx")?.value||0);
  const dDep=Number(document.getElementById("arrayDy")?.value||0);
  if(!Number.isFinite(count)||count<2){toast("阵列数量至少为 2","err");return;}
  if(!Number.isFinite(dLat)||!Number.isFinite(dDep)){toast("阵列偏移无效","err");return;}
  if(dLat===0&&dDep===0){toast("阵列偏移不能为 0","err");return;}
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const sourceIds=[...selectedIds];
  const copies=[];let blocked=0;
  for(const id of sourceIds){
    const c=model.components.find(c=>c.component_id===id);
    if(!c||isWorld(c)||!visibleInCurrentSection(c))continue;
    for(let i=1;i<count;i++){
      const result=makeOffsetCopy(c,{li,di,dLat:dLat*i,dDep:dDep*i,idBase:`${c.component_id}_arr${i+1}`,name:`${c.display_name} ${i+1}`,evidence:`array_of:${c.component_id};index:${i+1};offset:${dLat*i},${dDep*i}`});
      if(result.copy)copies.push(result.copy);
      if(result.blocked)blocked++;
    }
  }
  if(!copies.length){toast(blocked?"阵列副本会越出 mother/World 边界":"没有可阵列复制的组件","err");return;}
  model.components.push(...copies);
  const visibleCopies=copies.filter(c=>visibleInCurrentSection(c));
  selectedIds=new Set(visibleCopies.map(c=>c.component_id));
  primaryId=visibleCopies[0]?.component_id||null;polyEditId=null;
  resetView();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
  toast(blocked?`已创建 ${copies.length} 个阵列副本,阻止 ${blocked} 个越界`:`已创建 ${copies.length} 个阵列副本`);
}
function makeOffsetCopy(c,{li,di,dLat,dDep,idBase,name,evidence}){
  const cp=JSON.parse(JSON.stringify(c));
  cp.component_id=uniqueId(idBase);
  cp.display_name=name;
  cp.placement.position[li]+=dLat;
  cp.placement.position[di]+=dDep;
  if(cp.polygon&&polygonAxesMatch(cp)){
    for(const p of cp.polygon){p[li]+=dLat;p[di]+=dDep;}
  }
  cp.source_evidence=[...(cp.source_evidence||[]),evidence];
  cp.open_issues=[...(cp.open_issues||[]),`由 ${c.component_id} 复制生成`];
  cp.confirmed_by_user=true;
  cp.confirmation_source="device_canvas";
  if(!transformFitsContainer(cp,bbox3D(cp)))return {copy:null,blocked:true};
  return {copy:cp,blocked:false};
}
function uniqueId(base){
  const used=new Set(model.components.map(c=>c.component_id));
  let id=base,i=2;
  while(used.has(id)){id=`${base}_${i++}`;}
  return id;
}
function sortComponentsByDepth(){
  if(!model)return;
  const di=AXIS_IDX[axes.depth];
  model.components.sort((a,b)=>{
    if(isWorld(a))return -1;if(isWorld(b))return 1;
    return bbox3D(a).min[di]-bbox3D(b).min[di];
  });
  renderList();draw3DPreview();pushHistory();toast("已按当前深度轴排序");
}

/* ---------- 编辑面板 ---------- */
function renderEdit(){
  const root=document.getElementById("editPanel");
  if(!model){root.innerHTML="<h3>编辑</h3><div class='empty-side'>未载入</div>";return;}
  if(selectedIds.size===0){root.innerHTML="<h3>编辑</h3><div class='empty-side'>点画布上的层开始编辑(Shift 点多选)</div>";return;}
  if(selectedIds.size>1){renderBatchEdit(root);return;}
  const c=model.components.find(c=>c.component_id===primaryId);if(!c){root.innerHTML="<h3>编辑</h3><div class='empty-side'>未选中</div>";return;}
  root.innerHTML=`
    <h3>编辑 — ${esc(c.display_name)}${c.polygon?` <span class="pill">多边形 ${c.polygon.length}pt</span>`:""}</h3>
    ${renderSelectionSummary()}
    <div class="field"><label>display_name</label><input type="text" id="f_name" value="${esc(c.display_name)}"/></div>
    <div class="field"><label>component_id</label><input type="text" id="f_id" value="${esc(c.component_id)}"/></div>
    <div class="field"><label>material_id</label><input type="text" id="f_mat" value="${esc(c.material_id)}" list="matlist"/><datalist id="matlist">${MAT_DEFAULTS.map(m=>`<option value="${m}">`).join("")}</datalist></div>
    <div class="field"><label>component_type</label><select id="f_type">${["world","assembly","layer","volume","shielding","electrode","substrate"].map(t=>`<option ${t===c.component_type?"selected":""}>${t}</option>`).join("")}</select></div>
    <div class="field"><label>geometry_type</label><select id="f_geom">${["box","sphere","cylinder","tubs","cons","polycone","trapezoid"].map(t=>`<option ${t===c.geometry_type?"selected":""}>${t}</option>`).join("")}</select></div>
    ${c.polygon?`<div class="hint" style="margin-bottom:8px">多边形(${c.polygonAxes.lateral}×${c.polygonAxes.depth}):双击边加节点,拖蓝色控制点变形,双击控制点删除。bbox 尺寸自动。</div>${renderPolygonVertexEditor(c)}`:`<div class="field"><label>尺寸 dx/dy/dz (μm)</label><div class="row"><input type="number" id="f_dx" step="any" value="${c.dimensions.dx}"/><input type="number" id="f_dy" step="any" value="${c.dimensions.dy}"/><input type="number" id="f_dz" step="any" value="${c.dimensions.dz}"/></div></div>`}
    <div class="field"><label>位置 x/y/z (μm)</label><div class="row"><input type="number" id="f_px" step="any" value="${c.placement.position[0]}"/><input type="number" id="f_py" step="any" value="${c.placement.position[1]}"/><input type="number" id="f_pz" step="any" value="${c.placement.position[2]}"/></div></div>
    <div class="field"><label><input type="checkbox" id="f_sens" ${c.sensitive?"checked":""}/> sensitive detector(敏感区)</label></div>
    <div class="field"><label><input type="checkbox" id="f_lock" ${c.locked?"checked":""}/> 🔒 锁定尺寸(禁止缩放手柄)</label></div>
    <div class="field"><label>roles(逗号分隔)</label><input type="text" id="f_roles" value="${esc((c.roles||[]).join(", "))}"/></div>
    ${c.polygon?`<div class="field"><button onclick="resetToRect()" class="ghost">▭ 转回矩形(丢弃节点)</button></div>`:""}
  `;
  const bind=(id,fn)=>{const e=document.getElementById(id);if(e)e.addEventListener("input",fn);};
  bind("f_name",e=>{c.display_name=e.value;renderList();drawComponents();refreshTransformer();});
  const idInput=document.getElementById("f_id");
  if(idInput)idInput.addEventListener("change",e=>{
    const current=model.components.find(x=>x.component_id===primaryId)||c;
    const result=renameComponent(current.component_id,{component_id:e.target.value});
    if(!result.ok){
      const message={empty:"component_id 不能为空",invalid:"component_id 只能包含字母、数字、_ . : -",duplicate:"component_id 已存在",missing:"组件不存在"}[result.reason]||"component_id 无效";
      e.target.value=current.component_id;
      toast(message,"err");
      return;
    }
    renderEdit();
    toast("已重命名组件");
  });
  bind("f_mat",e=>{c.material_id=e.value;drawComponents();refreshTransformer();renderList();refreshSelectionSummary();});
  bind("f_type",e=>{c.component_type=e.value;renderList();});
  bind("f_geom",e=>{c.geometry_type=e.value;});
  if(!c.polygon){
    bind("f_dx",e=>{c.dimensions.dx=+e.value||0;drawComponents();refreshTransformer();refreshSelectionSummary();});
    bind("f_dy",e=>{c.dimensions.dy=+e.value||0;drawComponents();refreshTransformer();refreshSelectionSummary();});
    bind("f_dz",e=>{c.dimensions.dz=+e.value||0;drawComponents();refreshTransformer();refreshSelectionSummary();});
  }
  bind("f_px",e=>{c.placement.position[0]=+e.value||0;drawComponents();refreshSelectionSummary();});
  bind("f_py",e=>{c.placement.position[1]=+e.value||0;drawComponents();refreshSelectionSummary();});
  bind("f_pz",e=>{c.placement.position[2]=+e.value||0;drawComponents();refreshSelectionSummary();});
  bind("f_sens",e=>{c.sensitive=e.target.checked;});
  bind("f_lock",e=>{c.locked=e.target.checked;refreshTransformer();});
  bind("f_roles",e=>{c.roles=e.value.split(",").map(s=>s.trim()).filter(Boolean);});
  // 字段编辑入栈(失焦时)
  root.querySelectorAll("input,select").forEach(el=>{if(el.id!=="f_id")el.addEventListener("change",recordEdit);});
}
function renderPolygonVertexEditor(c){
  if(!c||!c.polygon||!polygonAxesMatch(c))return "";
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const rows=c.polygon.map((p,i)=>`
    <div class="vertex-row ${i===selectedPolygonVertexIndex?"selected":""}" data-role="polygon-vertex-row" data-vertex-index="${i}" onclick="selectPolygonVertex(${i})">
      <span>${i+1}</span>
      <input type="number" step="any" data-vertex-axis="lat" data-vertex-index="${i}" value="${p[li]}" oninput="setPolygonVertexFromInput(${i},'lat',this)"/>
      <input type="number" step="any" data-vertex-axis="dep" data-vertex-index="${i}" value="${p[di]}" oninput="setPolygonVertexFromInput(${i},'dep',this)"/>
    </div>`).join("");
  return `
    <div class="field">
      <label>顶点坐标 ${axes.lateral}/${axes.depth} (μm)</label>
      <div class="vertex-tools">
        <button class="ghost" data-action="poly-vertex-up" onclick="movePolygonVertex(-1)">上移</button>
        <button class="ghost" data-action="poly-vertex-down" onclick="movePolygonVertex(1)">下移</button>
        <button class="ghost" data-action="poly-vertex-reverse" onclick="reversePolygonVertices()">反转</button>
        <button class="ghost" data-action="poly-vertex-remove" onclick="removeSelectedPolygonVertex()">删除点</button>
      </div>
      <div class="vertex-table" data-role="polygon-vertex-table">
        <div class="vertex-row vertex-head"><span>#</span><span>${esc(axes.lateral)}</span><span>${esc(axes.depth)}</span></div>
        ${rows}
      </div>
    </div>`;
}
function currentEditablePolygon(){
  const c=model&&model.components.find(c=>c.component_id===primaryId);
  if(!c||!c.polygon||!polygonAxesMatch(c))return null;
  return c;
}
function clampSelectedPolygonVertex(c){
  if(!c||!c.polygon||!c.polygon.length){selectedPolygonVertexIndex=null;return null;}
  if(!Number.isInteger(selectedPolygonVertexIndex))selectedPolygonVertexIndex=0;
  selectedPolygonVertexIndex=Math.max(0,Math.min(c.polygon.length-1,selectedPolygonVertexIndex));
  return selectedPolygonVertexIndex;
}
function refreshPolygonVertexEditing(c){
  updatePolygonShape(c);
  drawPolyAnchors();
  renderEdit();
  refreshSelectionSummary();
  refreshAnnotationViews();
  updateModelHealth();
  compLayer.batchDraw();uiLayer.batchDraw();
}
function selectPolygonVertex(idx){
  const c=currentEditablePolygon();
  if(!c)return false;
  const i=Number(idx);
  if(!Number.isInteger(i)||i<0||i>=c.polygon.length)return false;
  selectedPolygonVertexIndex=i;
  drawPolyAnchors();
  renderEdit();
  return true;
}
function movePolygonVertex(dir){
  const c=currentEditablePolygon();
  if(!c)return false;
  const i=clampSelectedPolygonVertex(c);
  const delta=Number(dir)<0?-1:1;
  const j=i+delta;
  if(j<0||j>=c.polygon.length)return false;
  const tmp=c.polygon[i];
  c.polygon[i]=c.polygon[j];
  c.polygon[j]=tmp;
  selectedPolygonVertexIndex=j;
  refreshPolygonVertexEditing(c);
  pushHistory();
  return true;
}
function reversePolygonVertices(){
  const c=currentEditablePolygon();
  if(!c)return false;
  const i=clampSelectedPolygonVertex(c);
  c.polygon.reverse();
  selectedPolygonVertexIndex=c.polygon.length-1-i;
  refreshPolygonVertexEditing(c);
  pushHistory();
  return true;
}
function removeSelectedPolygonVertex(){
  const c=currentEditablePolygon();
  if(!c)return false;
  const i=clampSelectedPolygonVertex(c);
  if(c.polygon.length<=3){toast("多边形至少 3 个顶点","err");return false;}
  c.polygon.splice(i,1);
  selectedPolygonVertexIndex=Math.min(i,c.polygon.length-1);
  refreshPolygonVertexEditing(c);
  pushHistory();
  return true;
}
function setPolygonVertexFromInput(idx,axis,el){
  const c=currentEditablePolygon();
  if(!c)return false;
  const i=Number(idx);
  if(!Number.isInteger(i)||i<0||i>=c.polygon.length)return false;
  selectedPolygonVertexIndex=i;
  const value=Number(el&&el.value);
  const axisIdx=axis==="dep"?AXIS_IDX[axes.depth]:AXIS_IDX[axes.lateral];
  if(!Number.isFinite(value)){return false;}
  syncTransformConstraintFromUI();
  const next=c.polygon.map(p=>p.slice());
  next[i][axisIdx]=value;
  if(!transformFitsContainer(c,bboxFromPolygonPoints(next,c))){
    if(el)el.value=c.polygon[i][axisIdx];
    toast("目标会越出 mother/World 边界","err");
    return false;
  }
  c.polygon=next;
  refreshPolygonVertexEditing(c);
  return true;
}
function renderBatchEdit(root){
  root.innerHTML=`
    <h3>批量编辑 <span class="pill">${selectedIds.size}</span></h3>
    ${renderSelectionSummary()}
    <div class="field"><label>material_id</label><input type="text" id="batch_mat" list="matlist_batch" placeholder="留空不修改"/><datalist id="matlist_batch">${MAT_DEFAULTS.map(m=>`<option value="${m}">`).join("")}</datalist></div>
    <div class="field"><label>component_type</label><select id="batch_type"><option value="">不修改</option>${["assembly","layer","volume","shielding","electrode","substrate"].map(t=>`<option>${t}</option>`).join("")}</select></div>
    <div class="field"><label>roles 追加(逗号分隔)</label><input type="text" id="batch_roles" placeholder="例如 edep_region, electrode"/></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      <button onclick="applyBatchEdit()">应用批量编辑</button>
      <button class="ghost" onclick="lockSelection(true)">锁定选中</button>
      <button class="ghost" onclick="lockSelection(false)">解锁选中</button>
      <button class="ghost" onclick="hideSelection()">隐藏选中</button>
    </div>
  `;
}
function applyBatchEdit(){
  const mat=(document.getElementById("batch_mat")?.value||"").trim();
  const typ=(document.getElementById("batch_type")?.value||"").trim();
  const roles=(document.getElementById("batch_roles")?.value||"").split(",").map(s=>s.trim()).filter(Boolean);
  for(const id of selectedIds){
    const c=model.components.find(c=>c.component_id===id);if(!c||isWorld(c))continue;
    if(mat)c.material_id=mat;
    if(typ)c.component_type=typ;
    if(roles.length)c.roles=Array.from(new Set([...(c.roles||[]),...roles]));
  }
  drawComponents();renderList();updateModelHealth();draw3DPreview();pushHistory();toast("批量编辑已应用");
}
function lockSelection(value){
  for(const id of selectedIds){const c=model.components.find(c=>c.component_id===id);if(c&&!isWorld(c))c.locked=value;}
  drawComponents();renderList();renderEdit();pushHistory();
}
function hideSelection(){
  for(const id of selectedIds){const c=model.components.find(c=>c.component_id===id);if(c&&!isWorld(c))c.hidden=true;}
  selectedIds.clear();primaryId=null;polyEditId=null;
  drawComponents();renderList();renderEdit();renderAnnotationsPanel();pushHistory();
}
function resetToRect(){const c=model.components.find(c=>c.component_id===primaryId);if(!c||!c.polygon)return;const b=polyBBox(c);const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];c.dimensions[DIM_KEY[axes.lateral]]=b.maxLat-b.minLat;c.dimensions[DIM_KEY[axes.depth]]=b.maxDep-b.minDep;c.placement.position[li]=(b.minLat+b.maxLat)/2;c.placement.position[di]=(b.minDep+b.maxDep)/2;delete c.polygon;delete c.polygonAxes;c.geometry_type="box";polyEditId=null;fitCameraNotZoom();drawComponents();renderEdit();renderList();pushHistory();toast("已转回矩形");}
function renderEditValues(c){if(c.component_id!==primaryId)return;const set=(id,v)=>{const e=document.getElementById(id);if(e&&document.activeElement!==e)e.value=v;};const p=c.placement.position;set("f_px",Number(p[0].toFixed(4)));set("f_py",Number(p[1].toFixed(4)));set("f_pz",Number(p[2].toFixed(4)));if(!c.polygon){const d=c.dimensions;set("f_dx",Number(d.dx.toFixed(4)));set("f_dy",Number(d.dy.toFixed(4)));set("f_dz",Number(d.dz.toFixed(4)));}}
/* ---------- 加 / 删 ---------- */
function addComponent(){
  if(!model){loadExample();return;}
  const di=AXIS_IDX[axes.depth],dk=DIM_KEY[axes.depth];
  let top=-Infinity;for(const c of model.components){if(isWorld(c))continue;top=Math.max(top,c.placement.position[di]+(c.dimensions[dk]||0)/2);}
  if(!isFinite(top))top=0;
  const nc=normalizeComponent({component_id:`layer_${model.components.length+1}`,display_name:`新层 ${model.components.length}`,component_type:"layer",geometry_type:"box",material_id:"Silicon",dimensions:{dx:1000,dy:1000,dz:10},placement:{position:[0,0,0],rotation:[0,0,0]},mother_volume:findWorldId(),roles:[]});
  nc.placement.position[di]=top+5;model.components.push(nc);
  selectOnly(nc.component_id);resetView();renderList();renderEdit();updateModelHealth();draw3DPreview();pushHistory();
}
function findWorldId(){const w=model.components.find(c=>isWorld(c));return w?w.component_id:null;}
function deleteSelected(){
  if(selectedIds.size===0)return;
  for(const id of [...selectedIds]){const c=model.components.find(c=>c.component_id===id);if(c&&isWorld(c)){toast("world volume 不能删除","err");continue;}if(polyEditId===id)polyEditId=null;}
  model.components=model.components.filter(c=>!selectedIds.has(c.component_id)||isWorld(c));
  pruneSelectionSets();renderSelectionSets();
  selectedIds.clear();primaryId=null;polyEditId=null;resetView();renderList();renderEdit();renderAnnotationsPanel();updateModelHealth();draw3DPreview();pushHistory();
}

/* ---------- 导出 ---------- */
function exportJSON(){
  if(!model){toast("没有数据","err");return;}
  let out;
  const canvasState=buildDeviceCanvasState();
  if(model.meta._full){out=JSON.parse(JSON.stringify(model.meta._full));out.components=JSON.parse(JSON.stringify(model.components)).map(serializeComp);out.device_canvas_state=canvasState;out.device_canvas_annotations=JSON.parse(JSON.stringify(dimensionAnnotations));out.human_confirmation=Object.assign({},out.human_confirmation,{confirmed_via:"device_canvas",confirmed_at:new Date().toISOString()});out.confirmed_fields=Array.from(new Set([...(out.confirmed_fields||[]),"components"]));out.assumptions_confirmed=true;}
  else{out={components:JSON.parse(JSON.stringify(model.components)).map(serializeComp),device_canvas_state:canvasState,device_canvas_annotations:JSON.parse(JSON.stringify(dimensionAnnotations))};}
  download(new Blob([JSON.stringify(out,null,2)],{type:"application/json"}),(model.meta.job_id||"device")+"_confirmed.json");
  toast("已导出修正 JSON");
}
function exportPNG(){if(!model)return;tr.nodes([]);uiLayer.find(".anchor").forEach(a=>a.hide());uiLayer.batchDraw();
  const url=stage.toDataURL({pixelRatio:2,mimeType:"image/png"});const a=document.createElement("a");a.href=url;a.download=(model.meta.job_id||"device")+"_section.png";document.body.appendChild(a);a.click();a.remove();
  uiLayer.find(".anchor").forEach(a=>a.show());refreshTransformer();uiLayer.batchDraw();toast("已导出 PNG");}
function svgAttr(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));}
function svgText(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function svgNum(v){
  const n=Number(v);
  if(!Number.isFinite(n))return "0";
  return String(+n.toFixed(6));
}
function svgPoint(lat,dep){return `${svgNum(lat)},${svgNum(-dep)}`;}
function svgLineAttrs({stroke="#0f172a",strokeWidth=0.7,dash=""}={}){
  return `stroke="${svgAttr(stroke)}" stroke-width="${svgNum(strokeWidth)}" vector-effect="non-scaling-stroke"${dash?` stroke-dasharray="${svgAttr(dash)}"`:""}`;
}
function svgAnnotationData(ann){
  const g=annotationGeometry(ann);
  if(!g)return null;
  const start={lat:toDataX(g.screenStart.x),dep:toDataY(g.screenStart.y)};
  const end={lat:toDataX(g.screenEnd.x),dep:toDataY(g.screenEnd.y)};
  const extensions=(g.extensions||[]).map(([x1,y1,x2,y2])=>({
    start:{lat:toDataX(x1),dep:toDataY(y1)},
    end:{lat:toDataX(x2),dep:toDataY(y2)},
  }));
  const labelPoint={lat:(start.lat+end.lat)/2,dep:(start.dep+end.dep)/2};
  return {...g,start,end,extensions,labelPoint,labelText:g.label};
}
function buildSectionSVG(){
  if(!model)return "";
  const comps=sectionComponents(true);
  const bounds=dataBounds();
  const padLat=Math.max((bounds.maxLat-bounds.minLat)*0.04,1);
  const padDep=Math.max((bounds.maxDep-bounds.minDep)*0.08,1);
  const minLat=bounds.minLat-padLat,maxLat=bounds.maxLat+padLat;
  const minDep=bounds.minDep-padDep,maxDep=bounds.maxDep+padDep;
  const width=Math.max(maxLat-minLat,1),height=Math.max(maxDep-minDep,1);
  const viewBox=`${svgNum(minLat)} ${svgNum(-maxDep)} ${svgNum(width)} ${svgNum(height)}`;
  const metadata={
    source:"device_canvas",
    model:model.meta.model_ir_id||model.meta.job_id||model.sourceName||"untitled",
    axes:{lateral:axes.lateral,depth:axes.depth,section:sliceAxis()},
    units:"um",
    componentCount:comps.length,
    exportedAt:new Date().toISOString(),
  };
  const lines=[
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" data-lateral-axis="${svgAttr(axes.lateral)}" data-depth-axis="${svgAttr(axes.depth)}" data-units="um" role="img">`,
    `<metadata>${svgText(JSON.stringify(metadata))}</metadata>`,
    `<title>${svgAttr(model.meta.target_system||model.meta.job_id||"Device section")}</title>`,
    `<desc>Device Canvas section export in micrometer data coordinates. SVG y = -${svgAttr(axes.depth)}.</desc>`,
    `<rect x="${svgNum(minLat)}" y="${svgNum(-maxDep)}" width="${svgNum(width)}" height="${svgNum(height)}" fill="#ffffff"/>`,
    `<g id="components">`,
  ];
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  for(const c of comps){
    const world=isWorld(c);
    const fill=world?"none":(c.color?`rgb(${c.color.map(v=>Math.round(v*255)).join(",")})`:matColor(c.material_id));
    const stroke=world?"#98a2b3":OUTLINE;
    const common=`data-component-id="${svgAttr(c.component_id)}" data-name="${svgAttr(c.display_name)}" data-material="${svgAttr(c.material_id||"")}"`;
    if(c.polygon&&polygonAxesMatch(c)){
      const pts=c.polygon.map(p=>svgPoint(p[li],p[di])).join(" ");
      lines.push(`<polygon ${common} points="${pts}" fill="${svgAttr(fill)}" fill-opacity="0.78" ${svgLineAttrs({stroke,strokeWidth:0.7})}/>`);
    }else{
      const b=bboxOf(c);
      lines.push(`<rect ${common} x="${svgNum(b.minLat)}" y="${svgNum(-b.maxDep)}" width="${svgNum(b.maxLat-b.minLat)}" height="${svgNum(b.maxDep-b.minDep)}" fill="${svgAttr(fill)}" fill-opacity="${world?"0":"0.78"}" ${svgLineAttrs({stroke,strokeWidth:world?0.6:0.7,dash:world?"5 4":""})}/>`);
    }
  }
  lines.push(`</g>`);
  const anns=dimensionAnnotations.map(svgAnnotationData).filter(Boolean);
  if(anns.length){
    lines.push(`<g id="annotations">`);
    for(const g of anns){
      const ann=g.ann;
      const id=svgAttr(ann.id);
      const comp=ann.component_id?` data-component-id="${svgAttr(ann.component_id)}"`:"";
      const pair=ann.kind==="pair_gap"?` data-component-a="${svgAttr(ann.a_id||"")}" data-component-b="${svgAttr(ann.b_id||"")}" data-axis="${svgAttr(ann.axis||"")}"`:"";
      const kind=svgAttr(ann.kind||"free_dimension");
      lines.push(`<g data-annotation-id="${id}" data-annotation-kind="${kind}"${comp}${pair}>`);
      for(const ex of g.extensions){
        lines.push(`<line x1="${svgNum(ex.start.lat)}" y1="${svgNum(-ex.start.dep)}" x2="${svgNum(ex.end.lat)}" y2="${svgNum(-ex.end.dep)}" fill="none" ${svgLineAttrs({stroke:"#155eef",strokeWidth:0.45,dash:"3 3"})}/>`);
      }
      lines.push(`<line x1="${svgNum(g.start.lat)}" y1="${svgNum(-g.start.dep)}" x2="${svgNum(g.end.lat)}" y2="${svgNum(-g.end.dep)}" fill="none" ${svgLineAttrs({stroke:"#155eef",strokeWidth:0.6})}/>`);
      lines.push(`<text x="${svgNum(g.labelPoint.lat)}" y="${svgNum(-g.labelPoint.dep)}" font-size="${svgNum(height*0.025)}" fill="#0f172a" text-anchor="middle">${svgText(String(g.labelText||"").replace(/μm/g,"um"))}</text>`);
      lines.push(`</g>`);
    }
    lines.push(`</g>`);
  }
  lines.push(`</svg>`);
  return lines.join("\n");
}
function exportSVG(){
  if(!model){toast("没有数据","err");return;}
  const svg=buildSectionSVG();
  download(new Blob([svg],{type:"image/svg+xml"}),(model.meta.job_id||"device")+"_section.svg");
  toast("已导出 SVG");
}
function dxfNum(v){
  const n=Number(v);
  if(!Number.isFinite(n))return "0";
  return String(+n.toFixed(6));
}
function dxfText(s){
  return String(s??"").replace(/[\r\n]+/g," ").replace(/[^\x20-\x7e]/g,c=>c==="μ"?"u":"?");
}
function dxfLayerName(s){
  const name=String(s||"LAYER").toUpperCase().replace(/[^A-Z0-9_$-]+/g,"_").replace(/^_+|_+$/g,"");
  return (name||"LAYER").slice(0,60);
}
function dxfPushLine(lines,layer,a,b){
  lines.push(
    "0","LINE","8",layer,
    "10",dxfNum(a.lat),"20",dxfNum(a.dep),"30","0",
    "11",dxfNum(b.lat),"21",dxfNum(b.dep),"31","0"
  );
}
function dxfPushText(lines,layer,point,text,height=12){
  lines.push(
    "0","TEXT","8",layer,
    "10",dxfNum(point.lat),"20",dxfNum(point.dep),"30","0",
    "40",dxfNum(height),
    "1",dxfText(text),
    "7","STANDARD",
    "72","1",
    "73","2",
    "11",dxfNum(point.lat),"21",dxfNum(point.dep),"31","0"
  );
}
function dxfPushPolyline(lines,layer,points,{closed=true,color=7}={}){
  lines.push("0","LWPOLYLINE","8",layer,"62",String(color),"90",String(points.length),"70",closed?"1":"0");
  for(const p of points)lines.push("10",dxfNum(p.lat),"20",dxfNum(p.dep));
}
function dxfLayerRecord(name,color=7){
  return ["0","LAYER","2",name,"70","0","62",String(color),"6","CONTINUOUS"];
}
function buildSectionDXF(){
  if(!model)return "";
  const comps=sectionComponents(true);
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth];
  const layerNames=new Set(["OUTLINE","WORLD","ANNOTATIONS"]);
  for(const c of comps)layerNames.add(isWorld(c)?"WORLD":dxfLayerName("COMP_"+c.component_id));
  const lines=[
    "0","SECTION","2","HEADER",
    "9","$ACADVER","1","AC1027",
    "9","$INSUNITS","70","13",
    "999",`Device Canvas section ${axes.lateral}-${axes.depth} units=um`,
    "0","ENDSEC",
    "0","SECTION","2","TABLES",
    "0","TABLE","2","LAYER","70",String(layerNames.size),
  ];
  for(const name of layerNames){
    const color=name==="WORLD"?8:(name==="ANNOTATIONS"?5:7);
    lines.push(...dxfLayerRecord(name,color));
  }
  lines.push("0","ENDTAB","0","ENDSEC","0","SECTION","2","ENTITIES");
  for(const c of comps){
    const world=isWorld(c);
    const layer=world?"WORLD":dxfLayerName("COMP_"+c.component_id);
    if(c.polygon&&polygonAxesMatch(c)){
      const pts=c.polygon.map(p=>({lat:p[li],dep:p[di]}));
      dxfPushPolyline(lines,layer,pts,{closed:true,color:world?8:7});
    }else{
      const b=bboxOf(c);
      dxfPushPolyline(lines,layer,[
        {lat:b.minLat,dep:b.minDep},
        {lat:b.maxLat,dep:b.minDep},
        {lat:b.maxLat,dep:b.maxDep},
        {lat:b.minLat,dep:b.maxDep},
      ],{closed:true,color:world?8:7});
    }
    lines.push("999",`component_id=${dxfText(c.component_id)} material=${dxfText(c.material_id||"")}`);
  }
  const annTextHeight=Math.max((dataBounds().maxDep-dataBounds().minDep)*0.025,2);
  for(const ann of dimensionAnnotations){
    const g=svgAnnotationData(ann);
    if(!g)continue;
    const layer="ANNOTATIONS";
    for(const ex of g.extensions)dxfPushLine(lines,layer,ex.start,ex.end);
    dxfPushLine(lines,layer,g.start,g.end);
    dxfPushText(lines,layer,g.labelPoint,String(g.labelText||"").replace(/μm/g,"um"),annTextHeight);
  }
  lines.push("0","ENDSEC","0","EOF");
  return lines.join("\n");
}
function exportDXF(){
  if(!model){toast("没有数据","err");return;}
  const dxf=buildSectionDXF();
  download(new Blob([dxf],{type:"application/dxf"}),(model.meta.job_id||"device")+"_section.dxf");
  toast("已导出 DXF");
}
function dxfPairsFromText(text){
  const raw=String(text||"").replace(/\r/g,"").split("\n").map(s=>s.trim());
  const pairs=[];
  for(let i=0;i<raw.length-1;i+=2)pairs.push([raw[i],raw[i+1]]);
  return pairs;
}
function parseDXFLWPolylines(text){
  const pairs=dxfPairsFromText(text);
  const polys=[];
  for(let i=0;i<pairs.length;i++){
    if(pairs[i][0]!=="0"||pairs[i][1].toUpperCase()!=="LWPOLYLINE")continue;
    const poly={kind:"lwpolyline",layer:"0",closed:false,points:[],vertices:[],hasBulge:false};
    let current=null;
    for(i=i+1;i<pairs.length;i++){
      const [code,value]=pairs[i];
      if(code==="0"){i--;break;}
      if(code==="8")poly.layer=value||"0";
      else if(code==="70")poly.closed=(Number(value)&1)===1;
      else if(code==="10"){
        current={x:Number(value),y:null,bulge:0};
        if(Number.isFinite(current.x))poly.vertices.push(current);
      }else if(code==="20"&&current){
        const y=Number(value);
        current.y=Number.isFinite(y)?y:0;
      }else if(code==="42"&&current){
        const b=Number(value);
        current.bulge=Number.isFinite(b)?b:0;
        if(Math.abs(current.bulge)>1e-9)poly.hasBulge=true;
      }
    }
    poly.vertices=poly.vertices.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
    poly.points=expandDXFPolylineVertices(poly.vertices,poly.closed);
    if(poly.points.length>=3)polys.push(poly);
  }
  return polys;
}
function parseDXFCurves(text){
  const pairs=dxfPairsFromText(text);
  const curves=[];
  for(let i=0;i<pairs.length;i++){
    if(pairs[i][0]!=="0")continue;
    const type=pairs[i][1].toUpperCase();
    if(type!=="CIRCLE"&&type!=="ARC")continue;
    const curve={kind:type.toLowerCase(),layer:"0",closed:type==="CIRCLE",points:[],center:[0,0],radius:0,startAngle:0,endAngle:360,hasCurve:true};
    for(i=i+1;i<pairs.length;i++){
      const [code,value]=pairs[i];
      if(code==="0"){i--;break;}
      const n=Number(value);
      if(code==="8")curve.layer=value||"0";
      else if(code==="10"&&Number.isFinite(n))curve.center[0]=n;
      else if(code==="20"&&Number.isFinite(n))curve.center[1]=n;
      else if(code==="40"&&Number.isFinite(n))curve.radius=Math.abs(n);
      else if(code==="50"&&Number.isFinite(n))curve.startAngle=n;
      else if(code==="51"&&Number.isFinite(n))curve.endAngle=n;
    }
    if(curve.radius<=0)continue;
    curve.points=curve.kind==="circle"
      ?approximateDXFCircle(curve.center[0],curve.center[1],curve.radius)
      :approximateDXFArc(curve.center[0],curve.center[1],curve.radius,curve.startAngle,curve.endAngle);
    if(curve.points.length>=3)curves.push(curve);
  }
  return curves;
}
function parseDXFImportEntities(text){
  return [...parseDXFLWPolylines(text),...parseDXFCurves(text)];
}
function dxfRoundPoint(x,y){
  return [+(Number(x)||0).toFixed(6),+(Number(y)||0).toFixed(6)];
}
function approximateDXFCircle(cx,cy,radius){
  const steps=64,pts=[];
  for(let i=0;i<steps;i++){
    const a=2*Math.PI*i/steps;
    pts.push(dxfRoundPoint(cx+radius*Math.cos(a),cy+radius*Math.sin(a)));
  }
  return pts;
}
function normalizeDXFAngleSpan(startDeg,endDeg){
  let span=Number(endDeg)-Number(startDeg);
  while(span<=0)span+=360;
  return span;
}
function approximateDXFArc(cx,cy,radius,startDeg,endDeg){
  const span=normalizeDXFAngleSpan(startDeg,endDeg);
  const steps=Math.max(6,Math.min(96,Math.ceil(span/8)));
  const pts=[];
  for(let i=0;i<=steps;i++){
    const deg=Number(startDeg)+span*i/steps;
    const a=deg*Math.PI/180;
    pts.push(dxfRoundPoint(cx+radius*Math.cos(a),cy+radius*Math.sin(a)));
  }
  return pts;
}
function expandDXFPolylineVertices(vertices,closed){
  if(!vertices||!vertices.length)return [];
  const out=[[vertices[0].x,vertices[0].y]];
  const segCount=closed?vertices.length:vertices.length-1;
  for(let i=0;i<segCount;i++){
    const a=vertices[i],b=vertices[(i+1)%vertices.length];
    const pts=expandDXFBulgeSegment(a,b);
    for(const p of pts)out.push(p);
  }
  if(closed&&out.length>1){
    const first=out[0],last=out[out.length-1];
    if(Math.abs(first[0]-last[0])<1e-9&&Math.abs(first[1]-last[1])<1e-9)out.pop();
  }
  return out;
}
function expandDXFBulgeSegment(a,b){
  const end=[b.x,b.y];
  const bulge=Number(a.bulge)||0;
  if(Math.abs(bulge)<1e-9)return [end];
  const dx=b.x-a.x,dy=b.y-a.y,chord=Math.hypot(dx,dy);
  if(chord<1e-9)return [];
  const theta=4*Math.atan(bulge);
  const radius=chord*(1+bulge*bulge)/(4*Math.abs(bulge));
  const nx=-dy/chord,ny=dx/chord;
  const h=chord*(1-bulge*bulge)/(4*bulge);
  const cx=(a.x+b.x)/2+nx*h,cy=(a.y+b.y)/2+ny*h;
  const start=Math.atan2(a.y-cy,a.x-cx);
  const steps=Math.max(6,Math.min(64,Math.ceil(Math.abs(theta)/(Math.PI/16))));
  const pts=[];
  for(let k=1;k<=steps;k++){
    const ang=start+theta*k/steps;
    pts.push([+(cx+radius*Math.cos(ang)).toFixed(6),+(cy+radius*Math.sin(ang)).toFixed(6)]);
  }
  return pts;
}
function safeIdPart(s){
  return String(s||"item").toLowerCase().replace(/[^a-z0-9_]+/g,"_").replace(/^_+|_+$/g,"")||"item";
}
function importDXFText(text,{namePrefix="DXF"}={}){
  if(!model)loadExample();
  const polys=parseDXFImportEntities(text).filter(p=>p.points.length>=3);
  if(!polys.length){toast("DXF 中没有可导入的 LWPOLYLINE/CIRCLE/ARC","err");return [];}
  const li=AXIS_IDX[axes.lateral],di=AXIS_IDX[axes.depth],thirdIdx=3-li-di;
  const added=[];
  for(const [idx,poly] of polys.entries()){
    const xs=poly.points.map(p=>p[0]),ys=poly.points.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const dims={dx:1,dy:1,dz:1};
    dims[DIM_KEY[axes.lateral]]=Math.max(maxX-minX,1e-6);
    dims[DIM_KEY[axes.depth]]=Math.max(maxY-minY,1e-6);
    dims[DIM_KEY[["x","y","z"][thirdIdx]]]=1;
    const pos=[0,0,0];
    pos[li]=(minX+maxX)/2;pos[di]=(minY+maxY)/2;pos[thirdIdx]=0;
    const polygon=poly.points.map(([x,y])=>{
      const p=[0,0,0];p[li]=x;p[di]=y;p[thirdIdx]=0;return p;
    });
    const layer=safeIdPart(poly.layer);
    const id=uniqueId(`dxf_${layer}${polys.length>1?`_${idx+1}`:""}`);
    const openIssues=[];
    if(!poly.closed){
      if(poly.kind==="arc")openIssues.push("DXF ARC 圆弧未闭合,已按弦闭合为可编辑多边形");
      else openIssues.push("DXF LWPOLYLINE 未闭合,已按多边形导入");
    }
    if(poly.hasBulge)openIssues.push("DXF bulge 圆弧已近似为多段线");
    if(poly.kind==="circle")openIssues.push("DXF CIRCLE 圆已近似为多段线");
    if(poly.kind==="arc")openIssues.push("DXF ARC 圆弧已近似为多段线");
    const comp={
      component_id:id,
      display_name:`${namePrefix} ${poly.layer||idx+1}`,
      component_type:"volume",
      geometry_type:"polycone",
      material_id:"Silicon",
      dimensions:dims,
      placement:{position:pos,rotation:[0,0,0]},
      mother_volume:findWorldId(),
      roles:[],
      source_evidence:["user_canvas_edit",`dxf_import:${poly.layer||idx+1}`],
      open_issues:openIssues,
      locked:false,
      confirmed_by_user:true,
      confirmation_source:"device_canvas",
      polygon,
      polygonAxes:{lateral:axes.lateral,depth:axes.depth},
    };
    model.components.push(comp);
    added.push(comp);
  }
  selectedIds=new Set(added.map(c=>c.component_id));
  primaryId=added[0]?.component_id||null;
  polyEditId=added.length===1?primaryId:null;
  resetView();renderList();renderEdit();renderAssemblyTree();updateModelHealth();draw3DPreview();pushHistory();
  toast(`已导入 DXF 实体 ${added.length} 个`);
  return added;
}
function readDXFFile(f){
  const r=new FileReader();
  r.onload=()=>{try{importDXFText(r.result,{namePrefix:f.name?f.name.replace(/\.[^.]+$/,""):"DXF"});}catch(err){toast("DXF 导入失败: "+err.message,"err");}};
  r.readAsText(f);
}
function copyNL(){if(!model)return;navigator.clipboard.writeText(describeNL()).then(()=>toast("描述已复制")).catch(()=>prompt("复制:",describeNL()));}
function describeNL(){
  const comps=model.components.filter(c=>!isWorld(c));const sys=model.meta.target_system||"半导体器件";const lines=[];
  lines.push(`【${sys}】人工修正后的器件截面(沿 ${axes.lateral}×${axes.depth}),单位 μm:`);
  const di=AXIS_IDX[axes.depth],dk=DIM_KEY[axes.depth],lk=DIM_KEY[axes.lateral],li=AXIS_IDX[axes.lateral];
  const sorted=[...comps].sort((a,b)=>(bboxOf(a).minDep)-(bboxOf(b).minDep));
  for(const c of sorted){const b=bboxOf(c);const p=c.placement.position;const sens=c.sensitive?"【敏感区/打分】":"";const roles=(c.roles&&c.roles.length)?`[${c.roles.join(",")}]`:"";
    if(c.polygon){lines.push(`- ${c.display_name} (${c.material_id}, 多边形${c.polygon.length}顶点, ${c.polygonAxes.lateral}×${c.polygonAxes.depth}): 顶点 ${JSON.stringify(c.polygon.map(pp=>[+pp[0].toFixed(2),+pp[1].toFixed(2),+pp[2].toFixed(2)]))} ${sens}${roles}`);}
    else{lines.push(`- ${c.display_name} (${c.material_id}, ${c.geometry_type}): 厚度 ${fmt(b.maxDep-b.minDep)}μm, 横向 ${fmt(b.maxLat-b.minLat)}μm, 中心 [${p.map(fmt).join(", ")}] ${sens}${roles}`);}
  }
  lines.push(`共 ${comps.length} 个有效层(world 容器除外)。`);return lines.join("\n");
}
function download(blob,name){const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}

/* ---------- 文件载入 ---------- */
document.getElementById("file").addEventListener("change",e=>{if(e.target.files[0])readFile(e.target.files[0]);});
document.getElementById("dxfFile").addEventListener("change",e=>{if(e.target.files[0])readDXFFile(e.target.files[0]);});
function readFile(f){
  if(f.name&&/\.dxf$/i.test(f.name)){readDXFFile(f);return;}
  const r=new FileReader();r.onload=()=>{try{loadModel(JSON.parse(r.result),f.name);}catch(err){toast("解析失败: "+err.message,"err");}};r.readAsText(f);
}
const stageWrap=document.getElementById("stageWrap");
stageWrap.addEventListener("dragover",e=>e.preventDefault());
stageWrap.addEventListener("drop",e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f)readFile(f);});

/* ---------- Job 浏览 ---------- */
let currentJobId=null;
async function initJobBrowser(){if(location.protocol==="file:")return;let jobs=[];try{const r=await fetch("/api/jobs",{cache:"no-store"});if(!r.ok)return;jobs=await r.json();}catch(e){return;}if(!jobs.length)return;const sel=document.getElementById("jobSelect");sel.innerHTML='<option value="">— 选择 Job —</option>'+jobs.map(j=>`<option value="${esc(j.job_id)}">${esc(j.job_id)} · ${j.n_components}组件 · ${esc(j.target_system||"")}</option>`).join("");sel.style.display="";document.getElementById("btnWrite").style.display="";}
async function onJobSelect(){const id=document.getElementById("jobSelect").value;if(!id)return;try{const r=await fetch("/api/job?id="+encodeURIComponent(id),{cache:"no-store"});const data=await r.json();currentJobId=id;loadModel(data,id);}catch(e){toast("加载失败: "+e.message,"err");}}
async function writeToJob(){if(!model){toast("没有数据","err");return;}if(!currentJobId){toast("当前非 Job 加载,请用「导出 JSON」","err");return;}
  let out=model.meta._full?JSON.parse(JSON.stringify(model.meta._full)):{components:model.components};
  out.components=JSON.parse(JSON.stringify(model.components)).map(serializeComp);
  out.device_canvas_state=buildDeviceCanvasState();
  out.device_canvas_annotations=JSON.parse(JSON.stringify(dimensionAnnotations));
  out.human_confirmation=Object.assign({},out.human_confirmation,{confirmed_via:"device_canvas",confirmed_at:new Date().toISOString()});out.confirmed_fields=Array.from(new Set([...(out.confirmed_fields||[]),"components"]));out.assumptions_confirmed=true;
  try{const r=await fetch("/api/save?id="+encodeURIComponent(currentJobId),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(out)});const res=await r.json();if(res.ok)toast("已回写到 "+currentJobId+" 的 04_human_confirmation/");else toast("回写失败","err");}catch(e){toast("回写失败: "+e.message,"err");}}

function toast(msg,kind="ok"){const t=document.getElementById("toast");t.textContent=msg;t.style.borderColor=kind==="err"?"var(--err)":"var(--accent)";t.classList.add("show");clearTimeout(toast._t);toast._t=setTimeout(()=>t.classList.remove("show"),1800);}

/* ---------- 命令面板 ---------- */
const commandPaletteState={query:"",activeIndex:0};
const CAD_COMMANDS=[
  {id:"select-all-visible",label:"全选可见组件",shortcut:"Ctrl+A",group:"选择",keywords:["全部","visible"],enabled:()=>!!model,run:()=>selectAllVisible()},
  {id:"clear-selection",label:"清空选择",shortcut:"Esc",group:"选择",keywords:["clear"],enabled:()=>selectedIds.size>0||!!measureState.start||!!measureState.end,run:()=>{clearSelection();clearMeasureState();renderEdit();}},
  {id:"focus-selection",label:"聚焦选中",shortcut:"F",group:"视图",keywords:["focus"],enabled:()=>selectedIds.size>0,run:()=>focusSelection()},
  {id:"isolate-selection",label:"隔离选中",shortcut:"I",group:"视图",keywords:["isolate"],enabled:()=>selectedIds.size>0,run:()=>isolateSelection()},
  {id:"save-view-state",label:"保存当前视图状态",group:"视图",keywords:["view","state"],enabled:()=>!!model,run:()=>saveViewState()},
  {id:"restore-view",label:"恢复视图",group:"视图",keywords:["restore"],enabled:()=>!!model&&isolationState.active,run:()=>restoreIsolation()},
  {id:"show-all-components",label:"显示全部组件",shortcut:"Shift+H",group:"视图",keywords:["全部","show"],enabled:()=>!!model,run:()=>showAllComponents()},
  {id:"view-xy",label:"切换 XY 平面",group:"截面",keywords:["xy","top"],enabled:()=>!!model,run:()=>setViewAxes("x","y")},
  {id:"view-xz",label:"切换 XZ 平面",group:"截面",keywords:["xz","front"],enabled:()=>!!model,run:()=>setViewAxes("x","z")},
  {id:"view-yz",label:"切换 YZ 平面",group:"截面",keywords:["yz","side"],enabled:()=>!!model,run:()=>setViewAxes("y","z")},
  {id:"tool-select",label:"选择工具",group:"工具",keywords:["select"],enabled:()=>!!model,run:()=>setToolMode("select")},
  {id:"tool-measure",label:"测量工具",group:"工具",keywords:["measure"],enabled:()=>!!model,run:()=>setToolMode("measure")},
  {id:"toggle-3d-preview",label:"三维预览",group:"视图",keywords:["3d","preview"],enabled:()=>!!model,run:()=>toggle3DPreview()},
  {id:"copy-selection",label:"复制选中组件",shortcut:"Ctrl+C",group:"编辑",keywords:["copy"],enabled:()=>selectedIds.size>0,run:()=>copySelectionToClipboard()},
  {id:"paste-selection",label:"粘贴组件",shortcut:"Ctrl+V",group:"编辑",keywords:["paste"],enabled:()=>!!model&&componentClipboard.items.length>0,run:()=>pasteClipboardSelection()},
  {id:"duplicate-selection",label:"创建副本",shortcut:"Ctrl+D",group:"编辑",keywords:["duplicate"],enabled:()=>selectedIds.size>0,run:()=>duplicateSelected()},
  {id:"delete-selection",label:"删除选中组件",shortcut:"Del",group:"编辑",keywords:["delete"],enabled:()=>selectedIds.size>0,run:()=>deleteSelected()},
  {id:"add-component",label:"新增层",group:"建模",keywords:["layer"],enabled:()=>true,run:()=>addComponent()},
  {id:"add-polygon-node",label:"添加多边形节点",group:"建模",keywords:["polygon","vertex"],enabled:()=>!!currentEditablePolygon(),run:()=>addPolygonNodeMode()},
  {id:"export-json",label:"导出 JSON",group:"导出",keywords:["json"],enabled:()=>!!model,run:()=>exportJSON()},
  {id:"export-svg",label:"导出 SVG",group:"导出",keywords:["svg"],enabled:()=>!!model,run:()=>exportSVG()},
  {id:"export-dxf",label:"导出 DXF",group:"导出",keywords:["dxf"],enabled:()=>!!model,run:()=>exportDXF()},
];
window.CAD_COMMANDS=CAD_COMMANDS;
function commandPaletteEl(){return document.getElementById("commandPalette");}
function commandPaletteSearchEl(){return document.getElementById("commandPaletteSearch");}
function commandPaletteListEl(){return document.getElementById("commandPaletteList");}
function isCommandPaletteOpen(){const panel=commandPaletteEl();return !!panel&&!panel.hidden;}
function normalizeCommandQuery(value){return String(value||"").trim().toLowerCase();}
function commandHaystack(cmd){
  return [cmd.id,cmd.label,cmd.group,cmd.shortcut,cmd.description,...(cmd.keywords||[])]
    .filter(Boolean).join(" ").toLowerCase();
}
function commandMatchesQuery(cmd,query){
  const q=normalizeCommandQuery(query);
  if(!q)return true;
  const hay=commandHaystack(cmd);
  return q.split(/\s+/).every(part=>hay.includes(part));
}
function isCadCommandEnabled(cmd){
  if(!cmd)return false;
  try{return !cmd.enabled||!!cmd.enabled();}
  catch(e){return false;}
}
function filteredCadCommands(){
  return CAD_COMMANDS.filter(cmd=>commandMatchesQuery(cmd,commandPaletteState.query));
}
function syncCommandPaletteActive(commands){
  if(!commands.length){commandPaletteState.activeIndex=-1;return;}
  const firstEnabled=commands.findIndex(isCadCommandEnabled);
  if(firstEnabled<0){commandPaletteState.activeIndex=0;return;}
  const current=commands[commandPaletteState.activeIndex];
  if(!current||!isCadCommandEnabled(current))commandPaletteState.activeIndex=firstEnabled;
  commandPaletteState.activeIndex=Math.max(0,Math.min(commands.length-1,commandPaletteState.activeIndex));
}
function renderCommandPalette(){
  const list=commandPaletteListEl();if(!list)return;
  const commands=filteredCadCommands();
  syncCommandPaletteActive(commands);
  list.innerHTML="";
  if(!commands.length){list.innerHTML='<div class="command-empty">没有匹配命令</div>';return;}
  for(const [idx,cmd] of commands.entries()){
    const btn=document.createElement("button");
    btn.type="button";
    btn.className="command-item";
    if(idx===commandPaletteState.activeIndex)btn.classList.add("active");
    btn.dataset.commandId=cmd.id;
    btn.disabled=!isCadCommandEnabled(cmd);
    btn.onclick=()=>runCadCommand(cmd.id);
    const text=document.createElement("span");
    const title=document.createElement("b");title.textContent=cmd.label;text.appendChild(title);
    const meta=document.createElement("small");meta.textContent=[cmd.group,cmd.description].filter(Boolean).join(" · ");text.appendChild(meta);
    btn.appendChild(text);
    const key=document.createElement("span");key.className="kbd";key.textContent=cmd.shortcut||cmd.id;btn.appendChild(key);
    list.appendChild(btn);
  }
}
function openCommandPalette(initialQuery=""){
  const panel=commandPaletteEl(),input=commandPaletteSearchEl();
  if(!panel||!input)return false;
  commandPaletteState.query=String(initialQuery||"");
  commandPaletteState.activeIndex=0;
  panel.hidden=false;
  input.value=commandPaletteState.query;
  renderCommandPalette();
  setTimeout(()=>{input.focus();input.select();},0);
  return true;
}
function closeCommandPalette(){
  const panel=commandPaletteEl();if(panel)panel.hidden=true;
  commandPaletteState.query="";
  commandPaletteState.activeIndex=0;
}
function cadCommandById(id){return CAD_COMMANDS.find(cmd=>cmd.id===id)||null;}
function runCadCommand(id){
  const cmd=cadCommandById(id);
  if(!cmd){toast("未知命令","err");return false;}
  if(!isCadCommandEnabled(cmd)){toast("命令当前不可用","err");renderCommandPalette();return false;}
  cmd.run();
  closeCommandPalette();
  return true;
}
function moveCommandPaletteActive(delta){
  const commands=filteredCadCommands();
  if(!commands.length)return;
  let i=commandPaletteState.activeIndex;
  for(let step=0;step<commands.length;step++){
    i=(i+delta+commands.length)%commands.length;
    if(isCadCommandEnabled(commands[i])){commandPaletteState.activeIndex=i;break;}
  }
  renderCommandPalette();
}
function runActiveCadCommand(){
  const commands=filteredCadCommands();
  syncCommandPaletteActive(commands);
  const cmd=commands[commandPaletteState.activeIndex]||commands.find(isCadCommandEnabled);
  return cmd?runCadCommand(cmd.id):false;
}
function handleCommandPaletteKey(e){
  if(!isCommandPaletteOpen())return false;
  const key=String(e.key||"");
  const mod=e.ctrlKey||e.metaKey;
  if(mod&&key.toLowerCase()==="k"){e.preventDefault();closeCommandPalette();return true;}
  if(key==="Escape"){e.preventDefault();closeCommandPalette();return true;}
  if(key==="Enter"){e.preventDefault();runActiveCadCommand();return true;}
  if(key==="ArrowDown"){e.preventDefault();moveCommandPaletteActive(1);return true;}
  if(key==="ArrowUp"){e.preventDefault();moveCommandPaletteActive(-1);return true;}
  return false;
}
document.getElementById("commandPaletteSearch")?.addEventListener("input",e=>{
  commandPaletteState.query=e.target.value;
  commandPaletteState.activeIndex=0;
  renderCommandPalette();
});
document.getElementById("commandPalette")?.addEventListener("mousedown",e=>{
  if(e.target===e.currentTarget)closeCommandPalette();
});

/* ---------- 快捷键 ---------- */
window.addEventListener("keydown",e=>{
  const tag=(e.target.tagName||"").toLowerCase();
  const activeTag=(document.activeElement?.tagName||"").toLowerCase();
  const typing=tag==="input"||tag==="textarea"||tag==="select"||activeTag==="input"||activeTag==="textarea"||activeTag==="select"||!!document.activeElement?.isContentEditable;
  const mod=e.ctrlKey||e.metaKey;
  if(handleCommandPaletteKey(e))return;
  if(mod&&e.key.toLowerCase()==="z"){e.preventDefault();if(e.shiftKey)redo();else undo();return;}
  if(mod&&e.key.toLowerCase()==="y"){e.preventDefault();redo();return;}
  if(typing)return;
  if(mod&&e.key.toLowerCase()==="k"){e.preventDefault();openCommandPalette();return;}
  if(mod&&e.key.toLowerCase()==="a"){e.preventDefault();selectAllVisible();return;}
  if(mod&&e.key.toLowerCase()==="c"){e.preventDefault();copySelectionToClipboard();return;}
  if(mod&&e.key.toLowerCase()==="v"){e.preventDefault();pasteClipboardSelection();return;}
  if(e.key==="Delete"||e.key==="Backspace"){if(selectedIds.size){e.preventDefault();deleteSelected();}}
  if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(e.key)&&selectedIds.size){
    e.preventDefault();
    const old=document.getElementById("nudgeStep")?.value;
    if(e.shiftKey&&document.getElementById("nudgeStep"))document.getElementById("nudgeStep").value=String(Number(old||10)*5);
    const map={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]};
    nudgeSelection(...map[e.key]);
    if(e.shiftKey&&document.getElementById("nudgeStep"))document.getElementById("nudgeStep").value=old;
  }
  if((e.key==="d"||e.key==="D")&&mod){e.preventDefault();duplicateSelected();}
  if(e.key==="f"||e.key==="F"){if(selectedIds.size){e.preventDefault();focusSelection();}}
  if(e.key==="i"||e.key==="I"){if(selectedIds.size){e.preventDefault();isolateSelection();}}
  if((e.key==="h"||e.key==="H")&&e.shiftKey){e.preventDefault();showAllComponents();}
  if(e.key==="Escape"){
    e.preventDefault();
    clearSelection();
    clearMeasureState();
    renderEdit();
  }
});

/* ---------- 等比缩放 ---------- */
function onRatioChange(){tr.keepRatio(document.getElementById("ratioScale").checked);}

/* ---------- 窗口尺寸 ---------- */
function resizeStage(){stage.size({width:stageW(),height:stageH()});if(model)resetView();}
window.addEventListener("resize",resizeStage);
/* 外轮廓虚线缓慢滚动(蚂蚁线)= 标记线,非实体边缘 */
let _dashOffset=0;
setInterval(()=>{if(!model)return;_dashOffset-=0.5;compLayer.find(".comp").forEach(s=>{try{const id=s.getAttr("cid");if(selectedIds.has(id))s.dashOffset(_dashOffset);}catch(e){}});compLayer.batchDraw();},80);

/* ---------- 示例 ---------- */
function loadExample(){
  loadModel({
    model_ir_id:"example_pin_detector",job_id:"canvas_demo",
    target_system:"PiN 硅辐射探测器(示例:agent 的初步理解)",
    coordinate_system:{axis_definition:{x:"sensor_width",y:"sensor_length",z:"beam_direction"}},
    materials:[{material_id:"Silicon",name:"Silicon (NIST)"},{material_id:"SiO2",name:"Silicon Dioxide"},{material_id:"Aluminum",name:"Aluminum (NIST)"},{material_id:"Air",name:"Air (NIST)"}],
    components:[
      {component_id:"world_volume",display_name:"World",component_type:"world",geometry_type:"box",dimensions:{dx:5000,dy:5000,dz:5000},material_id:"Air",placement:{position:[0,0,0]},mother_volume:null},
      {component_id:"back_contact",display_name:"Al 背接触",component_type:"electrode",geometry_type:"box",dimensions:{dx:1000,dy:1000,dz:2},material_id:"Aluminum",placement:{position:[0,0,-252]},mother_volume:"world_volume",roles:["electrode"]},
      {component_id:"si_substrate",display_name:"Si 衬底 (n+)",component_type:"substrate",geometry_type:"box",dimensions:{dx:1000,dy:1000,dz:300},material_id:"Silicon",placement:{position:[0,0,-100]},mother_volume:"world_volume",roles:["dose_scoring_region"]},
      {component_id:"si_intrinsic",display_name:"Si 本征层 (i)",component_type:"layer",geometry_type:"box",dimensions:{dx:1000,dy:1000,dz:200},material_id:"Silicon",placement:{position:[0,0,150]},mother_volume:"world_volume",sensitive:true,roles:["edep_region","dose_scoring_region"]},
      {component_id:"si_window",display_name:"Si 顶窗 (p+)",component_type:"layer",geometry_type:"box",dimensions:{dx:1000,dy:1000,dz:2},material_id:"Silicon",placement:{position:[0,0,251]},mother_volume:"world_volume"},
      {component_id:"oxide",display_name:"SiO2 钝化",component_type:"layer",geometry_type:"box",dimensions:{dx:1000,dy:1000,dz:0.5},material_id:"SiO2",placement:{position:[0,0,252.25]},mother_volume:"world_volume"},
      {component_id:"top_contact",display_name:"Al 顶接触",component_type:"electrode",geometry_type:"box",dimensions:{dx:1000,dy:1000,dz:1},material_id:"Aluminum",placement:{position:[0,0,253]},mother_volume:"world_volume",roles:["electrode"]},
    ],
  });
}

/* ---------- 启动 ---------- */
initJobBrowser();
loadExample();

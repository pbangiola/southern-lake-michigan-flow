const map = new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-98.5,39.5],zoom:3.5});
map.addControl(new maplibregl.NavigationControl());
const USA_BOUNDS=[[-125,24],[-66,50]];
const ILLINOIS_BOUNDS=[[-91.55,36.95],[-87.0,42.55]];
window.addEventListener('DOMContentLoaded',()=>{document.getElementById('view-usa')?.addEventListener('click',()=>map.fitBounds(USA_BOUNDS,{padding:30}));document.getElementById('view-illinois')?.addEventListener('click',()=>map.fitBounds(ILLINOIS_BOUNDS,{padding:30,maxZoom:8}));document.getElementById('view-region')?.addEventListener('click',()=>map.fitBounds([[-88.7,40.9],[-85.4,43.2]],{padding:30}));});
document.getElementById('print').onclick=()=>window.print();
const REPO='pbangiola/southern-lake-michigan-flow';
const reportTypes=['Too shallow','Too high / strong current','Navigable'];
const status=document.getElementById('status');
const gaugeToggle=document.getElementById('show-gauges');
const riverToggle=document.getElementById('show-rivers');
const legend=document.getElementById('map-legend');
function setLayerVisibility(id,visible){if(map.getLayer(id))map.setLayoutProperty(id,'visibility',visible?'visible':'none');}
window.addEventListener('resize',()=>map.resize());
gaugeToggle.addEventListener('change',()=>{
 if(map.getLayer('gauges'))map.setLayoutProperty('gauges','visibility',gaugeToggle.checked?'visible':'none');
 setLayerVisibility('expanded-gauges',gaugeToggle.checked);
});
const reportButton=document.getElementById('report-condition');
const reportDialog=document.getElementById('report-dialog');
const reportForm=document.getElementById('report-form');
let gaugeFeatures=[], communityReports=[], reportPoint=null, routeCount=0;
const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v):null;
const fmt=v=>Number(v).toFixed(6);
const siteId=v=>String(v??'').replace(/^USGS-/i,'').trim();
const blend=(a,b,t)=>{
 t=Math.max(0,Math.min(1,t));
 const x=a.slice(1).match(/../g),y=b.slice(1).match(/../g);
 return '#'+x.map((v,i)=>Math.round(parseInt(v,16)*(1-t)+parseInt(y[i],16)*t).toString(16).padStart(2,'0')).join('');
};
function issueField(body,name){
 const escaped=name.replace(/[.*+?^$\{\}()|[\]\\]/g,'\\$&');
 const m=body.match(new RegExp('^\\*\\*'+escaped+':\\*\\* (.+)$','m'));
 return m?m[1].trim():null;
}
async function loadReports(){
 const items=[];
 for(let page=1;page<=5;page++){
  const res=await fetch('https://api.github.com/repos/'+REPO+'/issues?state=open&per_page=100&page='+page);
  if(!res.ok)throw new Error('Community reports unavailable: HTTP '+res.status);
  const batch=await res.json();
  for(const issue of batch){
   if(issue.pull_request||!issue.body?.includes('ATLAS_PADDLING_REPORT_V1'))continue;
   const type=issueField(issue.body,'Condition'),site=siteId(issueField(issue.body,'Gauge ID'));
   const stage=finite(issueField(issue.body,'Observed stage ft'));
   const xy=(issueField(issue.body,'Coordinates')||'').split(',').map(Number);
   if(!reportTypes.includes(type)||!/^\d{7,15}$/.test(site)||stage===null||stage<0||stage>100||xy.length!==2||!xy.every(Number.isFinite))continue;
   items.push({type,site,stage,lat:xy[0],lon:xy[1],url:issue.html_url,created:issue.created_at,number:issue.number});
  }
  if(batch.length<100)break;
 }
 return items.sort((a,b)=>a.created.localeCompare(b.created)||a.number-b.number);
}
function applyMinima(data,atlas,floodData={}){
 const stations=atlas.stations||{},floodStations=floodData.stations||{};
 for(const f of data.features){
  const official=finite(floodStations[siteId(f.properties.site??f.properties.site_no??f.properties.id)]?.flood_stage_ft);
  if(official!==null)f.properties.flood_stage_ft=official;
  const p=f.properties,sid=siteId(p.site??p.site_no??p.id),rec=stations[sid];
  const adequate=rec?.observed_adequate_75pct_distributed===true ||
   (rec?.daily_adequate_75pct_distributed===true&&rec?.coverage_fraction>=0.75);
  p.atlas_minimum_ft=adequate?finite(rec.minimum_ft):null;
  p.atlas_mean_ft=adequate?finite(rec.mean_stage_12mo_ft):null;
  p.atlas_minimum_adequate=Boolean(adequate&&p.atlas_minimum_ft!==null);
  p.atlas_observed_days=rec?.coverage_days??0;
 }
}
function calibrate(data,reports){
 const bySite=new Map();
 for(const r of reports){
  const e=bySite.get(r.site)||{low:null,high:null,count:0};
  if(r.type==='Too shallow')e.low=e.low===null?r.stage:Math.max(e.low,r.stage);
  if(r.type==='Too high / strong current')e.high=e.high===null?r.stage:Math.min(e.high,r.stage);
  if(r.type==='Navigable'){
   if(e.low!==null&&r.stage<=e.low)e.low=r.stage-0.01;
   if(e.high!==null&&r.stage>=e.high)e.high=r.stage+0.01;
  }
  e.count++;bySite.set(r.site,e);
 }
 for(const f of data.features){
  const p=f.properties,e=bySite.get(siteId(p.site??p.site_no??p.id));
  p.paddling_low_ft=e?.low??null;
  p.paddling_high_ft=e?.high??null;
  p.community_report_count=e?.count??0;
 }
}
function palette(p){
 const stage=finite(p.stage),minimum=finite(p.atlas_minimum_ft);
 const mean=finite(p.atlas_mean_ft),flood=finite(p.flood_stage_ft);
 if(stage!==null&&flood!==null&&stage>=flood)return '#d3232f';
 if(stage===null||!p.atlas_minimum_adequate||minimum===null||mean===null||flood===null||!(minimum<mean&&mean<flood))return '#88929b';
 const green=mean+0.25*(flood-mean);
 if(stage<=minimum)return '#24150c';
 if(stage<=mean)return blend('#24150c','#1768c5',(stage-minimum)/(mean-minimum));
 if(stage<=green)return blend('#1768c5','#159447',(stage-mean)/(green-mean));
 if(stage<flood)return blend('#159447','#d3232f',(stage-green)/(flood-green));
 return '#d3232f';
}
function riverName(raw){
 const value=String(raw||'').trim();
 // Gauge descriptions typically look like "DES PLAINES RIVER AT RIVERSIDE, IL".
 const m=value.match(/^(.+?\b(?:RIVER|CREEK|BROOK|CANAL|DITCH|BRANCH|FORK|RUN))\b/i);
 return m?m[1].toLowerCase().replace(/\b[a-z]/g,x=>x.toUpperCase()):'Unidentified waterway';
}
let riverNames=[],riverMode='all',focusRiver='';
function applyRiverFilters(){
 for(const id of ['river-segments','river-3dhp-review','expanded-rivers','illinois-network',...(window.ednaWatershedLayerIds||[])]){
  if(!map.getLayer(id))continue;
  setLayerVisibility(id,riverToggle.checked&&riverMode!=='none');
  map.setFilter(id,riverMode==='only'?['==',['get','filter_river'],focusRiver]:riverMode==='exclude'?['!=',['get','filter_river'],focusRiver]:null);
 }
}
function registerRivers(names){
 const picker=document.getElementById('river-focus');if(!picker)return;
 for(const name of names)if(name&&name!=='Unidentified waterway'&&!riverNames.includes(name))riverNames.push(name);
 riverNames.sort();picker.replaceChildren();
 for(const name of riverNames){const opt=document.createElement('option');opt.value=name;opt.textContent=name;picker.append(opt);}
 if(!riverNames.includes(focusRiver))focusRiver=riverNames[0]||'';
 picker.value=focusRiver;applyRiverFilters();
}
document.getElementById('river-mode').addEventListener('change',e=>{riverMode=e.target.value;applyRiverFilters();});
document.getElementById('river-focus').addEventListener('change',e=>{focusRiver=e.target.value;applyRiverFilters();});
document.getElementById('river-all').addEventListener('click',()=>{riverToggle.checked=true;riverMode='all';document.getElementById('river-mode').value='all';applyRiverFilters();});
document.getElementById('river-none').addEventListener('click',()=>{riverMode='none';document.getElementById('river-mode').value='none';applyRiverFilters();});
riverToggle.addEventListener('change',applyRiverFilters);
// River colors use graph-nearest gauge attribution, not verified flow direction.
// Stable categorical colors reveal which USGS reaches share an associated gauge.
// These are NOT water-level or paddling-safety colors.
const segmentPalette=['#6f42c1','#008b8b','#d97706','#2563eb','#be185d','#16a34a','#a855f7','#b45309','#dc2626','#0f766e','#4338ca','#c026d3'];
function segmentColor(raw){
 const key=siteId(raw);
 if(!key)return '#88929b';
 let hash=2166136261;
 for(let i=0;i<key.length;i++)hash=Math.imul(hash^key.charCodeAt(i),16777619)>>>0;
 return segmentPalette[hash%segmentPalette.length];
}
let riverColorMode='stage';
function applyRiverColorMode(){
 for(const id of ['river-segments','river-3dhp-review']){
  if(!map.getLayer(id))continue;
  map.setPaintProperty(id,'line-color',['get',riverColorMode==='segments'?'segment_color':'stage_color']);
 }
 const label=document.getElementById('river-color-note');
 if(label)label.textContent=riverColorMode==='segments'?'Different colors identify gauge-associated segments; not water levels.':'Water stage colors require calibrated gauge readings; gray means unavailable.';
}
document.getElementById('river-color-mode')?.addEventListener('change',e=>{
 riverColorMode=e.target.value;
 applyRiverColorMode();
});
function colorRiverNetwork(segments,gauges){
 const bySite=new Map(gauges.map(f=>[siteId(f.properties.site),f.properties]));
 const colorFor=id=>{const p=bySite.get(siteId(id));return p?palette(p):'#88929b';};
 for(const feature of segments.features){
  const p=feature.properties||(feature.properties={});
  const a=siteId(p.upstream_gauge||p.from_gauge||p.site),b=siteId(p.downstream_gauge||p.to_gauge||p.site);
  const ca=colorFor(a),cb=colorFor(b);
  // Use the available endpoint when its partner lacks calibrated stage data.
  // Only a reach with no usable associated gauge stays gray.
  // Use two distinct bounding gauges when provided by the network builder.
  // A single nearest-gauge attribution is not evidence of two boundaries.
  const fraction=finite(p.gauge_fraction??p.fraction_from_upstream??p.relative_distance);
  const t=fraction===null?0.5:Math.max(0,Math.min(1,fraction));
  p.stage_color=ca==='#88929b'?cb:cb==='#88929b'?ca:a===b?ca:blend(ca,cb,t);
  p.stage_color_method=a&&b&&a!==b?'two-gauge interpolation':a||b?'single associated gauge':'unavailable';
  p.stage_gauge_a=a;p.stage_gauge_b=b;
  p.segment_color=segmentColor(a||b);
  p.river_name=p.river_name||riverName(bySite.get(a)?.name||bySite.get(b)?.name);
  p.filter_river=p.filter_river||(p.river_name==='Unidentified waterway'?riverName(bySite.get(a)?.name||bySite.get(b)?.name):p.river_name);
 }
 return segments;
}
// One-time EDNA graph build: show as a neutral, independent overlay.
// This is connected source geometry, not verified hydrological flow or gauge-calibrated stage.
map.on('load',async()=>{
 try{
  const response=await fetch('data/illinois_river_network.geojson',{cache:'no-store'});
  if(!response.ok)throw new Error('HTTP '+response.status);
  const network=await response.json();
  if(network.type!=='FeatureCollection'||!Array.isArray(network.features))throw new Error('Invalid network GeoJSON');
  map.addSource('illinois-network',{type:'geojson',data:network});
  map.addLayer({id:'illinois-network',type:'line',source:'illinois-network',
   paint:{'line-color':'#527d94','line-width':['interpolate',['linear'],['zoom'],5,0.65,9,1.5,13,2.5],
    'line-opacity':0.72}});
  setLayerVisibility('illinois-network',riverToggle.checked&&riverMode!=='none');
  map.on('click','illinois-network',e=>{
   if(reportButton.getAttribute('aria-pressed')==='true')return;
   const p=e.features[0].properties||{};
   new maplibregl.Popup().setLngLat(e.lngLat).setText('Illinois connected river network\\nEDNA segment: '+(p.segment_id||'unknown')+'\\nFlow direction and navigability not verified.').addTo(map);
  });
  console.info('Illinois EDNA network loaded:',network.features.length,'segments');
 }catch(error){console.warn('Illinois network unavailable:',error);}
});
// Nationwide EDNA geometry is too large to parse/render as one GeoJSON on mobile.
// Keep the nationwide import on disk; display it only after a tiled/vector-data pipeline is available.
// Existing regional layers remain available for local navigation.
window.ednaWatershedLayerIds=[];
// Load launch markers independently of gauge and river data; gauge failures must not hide launches.
map.on('load',async()=>{
  const putinToggle=document.getElementById('show-putins');
const putinFilter=document.getElementById('putin-filter');
const putinCount=document.getElementById('putin-count');
let putinFeatures=[];
let verifiedLaunches=new Set();
const launchKey=f=>String(f.properties?.id||f.properties?.osm_id||'').trim();
const isVerifiedLaunch=f=>Boolean(launchKey(f)&&verifiedLaunches.has(launchKey(f)));
const LOCAL_VERIFICATIONS_KEY='atlas-verified-launches-v1';
try{for(const id of JSON.parse(localStorage.getItem(LOCAL_VERIFICATIONS_KEY)||'[]'))verifiedLaunches.add(String(id));}catch(error){console.warn('Could not read local launch verifications:',error);}
async function toggleLaunchVerification(f){
 const id=launchKey(f);
 if(!id){alert('This launch has no stable ID, so verification cannot be saved.');return false;}
 const verified=!verifiedLaunches.has(id),endpoint=window.LAUNCH_VERIFICATION_API;
 if(endpoint){
  try{
   const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,verified})});
   if(!response.ok)throw new Error('HTTP '+response.status);
  }catch(error){alert('Shared verification could not be saved. Please try again. ('+error.message+')');return false;}
 }else{
  try{
   const saved=new Set(JSON.parse(localStorage.getItem(LOCAL_VERIFICATIONS_KEY)||'[]').map(String));
   if(verified)saved.add(id);else saved.delete(id);
   localStorage.setItem(LOCAL_VERIFICATIONS_KEY,JSON.stringify([...saved]));
  }catch(error){alert('Could not save launch verification locally.');return false;}
 }
 if(verified)verifiedLaunches.add(id);else verifiedLaunches.delete(id);
 updatePutins();
 return true;
}

let launchDomMarkers=[];
function renderLaunchDomMarkers(){
 for(const marker of launchDomMarkers)marker.remove();
 launchDomMarkers=[];
 if(!putinToggle.checked)return;
 const bounds=map.getBounds(),cellSize=44,groups=new Map();
 for(const feature of putinFeatures){
  const xy=feature.geometry?.coordinates;
  if(feature.geometry?.type!=='Point'||!Array.isArray(xy)||!bounds.contains(xy)||!qualifiesPutin(feature))continue;
  const pixel=map.project(xy),key=Math.floor(pixel.x/cellSize)+':'+Math.floor(pixel.y/cellSize);
  if(!groups.has(key))groups.set(key,{features:[],x:0,y:0});
  const group=groups.get(key);group.features.push(feature);group.x+=pixel.x;group.y+=pixel.y;
 }
 for(const group of groups.values()){
  const count=group.features.length,xy=map.unproject([group.x/count,group.y/count]);
  const el=document.createElement('button');
  el.type='button';
  const verified=count===1&&isVerifiedLaunch(group.features[0]);
  el.title=count===1?(group.features[0].properties?.name||'Launch candidate')+(verified?' (verified)':' (unverified)'):count+' nearby launch candidates';
  el.setAttribute('aria-label',el.title);
  if(count===1){
   el.style.cssText='width:19px;height:19px;padding:0;margin:0;border:1.5px solid white;border-radius:50%;background:'+(verified?'#168447':'#e0ad24')+' url(https://static.thenounproject.com/png/canoe-paddles-icon-731096-512.png) center/13px 13px no-repeat;box-shadow:0 1px 4px #0008;cursor:pointer;';
  }else{
   el.textContent=String(count);
   el.style.cssText='width:27px;height:27px;padding:0;margin:0;border:2px solid white;border-radius:50%;background:#e0ad24;color:#17252c;font:bold 11px system-ui;box-shadow:0 1px 5px #0008;cursor:pointer;';
  }
  el.addEventListener('click',event=>{
   event.stopPropagation();
   if(count>1){
    const coordinates=group.features.map(f=>f.geometry.coordinates);
    const extent=new maplibregl.LngLatBounds(coordinates[0],coordinates[0]);
    for(const coord of coordinates)extent.extend(coord);
    if(extent.getNorthEast().distanceTo(extent.getSouthWest())<50)map.easeTo({center:xy,zoom:Math.min(map.getZoom()+2,16)});
    else map.fitBounds(extent,{padding:75,maxZoom:16,duration:550});
   }else{
    const feature=group.features[0],node=document.createElement('div'),heading=document.createElement('strong'),info=document.createElement('p'),button=document.createElement('button');
    heading.textContent=el.title;
    info.textContent=verified?'Marked verified. Check current access before visiting.':'Unverified launch candidate.';
    button.type='button';button.textContent=verified?'Unverify launch':'Verify launch';
    button.style.margin='6px 0';
    button.onclick=async()=>{button.disabled=true;button.textContent='Saving…';if(await toggleLaunchVerification(feature))popup.remove();else{button.disabled=false;button.textContent=verified?'Unverify launch':'Verify launch';}};
    node.append(heading,info,button);
    const popup=new maplibregl.Popup().setLngLat(xy).setDOMContent(node).addTo(map);
   }
  });
  launchDomMarkers.push(new maplibregl.Marker({element:el,anchor:'center'}).setLngLat(xy).addTo(map));
 }
}
map.on('moveend',renderLaunchDomMarkers);
function qualifiesPutin(f){
 const p=f.properties||{},mode=putinFilter.value;
 if(mode==='public')return ['yes','public','designated'].includes(String(p.access||'').toLowerCase()); // Regional list has no explicit access=public tag.
 if(mode==='paddling')return p.canoe==='yes'||p.kayak==='yes'||/canoe|kayak/i.test((p.name||'')+' '+(p.allowed_watercraft||''));
 if(mode==='named')return Boolean(p.name)&&!/^osm-(node|way)-/i.test(p.name);
 return true;
}
function updatePutins(){
 const filtered=putinFeatures.filter(qualifiesPutin);
 if(map.getSource('putins'))map.getSource('putins').setData({type:'FeatureCollection',features:filtered});
 // DOM markers provide both individual icons and clustering; hide duplicate WebGL layers.
 for(const id of ['putin-clusters','putin-counts','putins'])setLayerVisibility(id,false);
 putinCount.textContent=filtered.length+' of '+putinFeatures.length+' launch candidates · '+filtered.filter(isVerifiedLaunch).length+' verified';
 renderLaunchDomMarkers();
}
putinToggle.addEventListener('change',updatePutins);
putinFilter.addEventListener('change',updatePutins);
// Publish all unverified OSM launch candidates as provisional map markers.
  try{
   try{const registryResponse=await fetch('data/verified_launches.json',{cache:'no-store'});if(registryResponse.ok){const registry=await registryResponse.json();for(const id of registry.verified_ids||[])verifiedLaunches.add(String(id));}}catch(error){console.warn('Launch verification registry unavailable:',error);}
   const response=await fetch('data/putins_osm_candidates.geojson',{cache:'no-store'});
   if(response.ok){
    const putins=await response.json();
    if(putins.type==='FeatureCollection'&&Array.isArray(putins.features)){
     putinFeatures=putins.features;
     // Prefer the automatically consolidated dataset when the workflow has generated it.
     let consolidated=null;
     try{
      const mergedResponse=await fetch('data/putins_consolidated.geojson',{cache:'no-store'});
      if(mergedResponse.ok){
       const raw=await mergedResponse.text();
       if(raw.trim()){
        try{consolidated=JSON.parse(raw);}catch(error){console.warn('Invalid consolidated launch JSON; using source datasets:',error);}
       }
      }
     }catch(error){console.warn('Consolidated launch layer unavailable:',error);}
     if(consolidated?.type==='FeatureCollection'&&Array.isArray(consolidated.features)&&consolidated.features.length>0){
      putinFeatures=consolidated.features;
     }else{
     let extra=null;
     try{
      const extraResponse=await fetch('data/regional_launches.geojson',{cache:'no-store'});
      if(extraResponse.ok)extra=await extraResponse.json();
     }catch(error){console.warn('Regional launch list unavailable:',error);}
     if(extra?.type==='FeatureCollection'&&Array.isArray(extra.features)){
      const coordinateKey=f=>JSON.stringify(f.geometry?.coordinates);
      const seen=new Set(putinFeatures.map(coordinateKey));
      for(const feature of extra.features){
       if(feature.geometry?.type!=='Point'||!Array.isArray(feature.geometry.coordinates))continue;
       const key=coordinateKey(feature);
       if(!seen.has(key)){putinFeatures.push(feature);seen.add(key);}
      }
     }
     }
     putinCount.textContent='Loaded '+putinFeatures.length+' launch candidates; rendering map markers…';
     // Small, incrementally published discovery tiles are optional.
     try{
      const expansionResponse=await fetch('data/putins_expansion.geojson',{cache:'no-store'});
      if(expansionResponse.ok){
       const expansion=await expansionResponse.json();
       const known=new Set(putinFeatures.map(f=>f.properties?.id).filter(Boolean));
       for(const feature of expansion.features||[]){
        const id=feature.properties?.id;
        if(id&&!known.has(id)&&feature.geometry?.type==='Point'){
         putinFeatures.push(feature);known.add(id);
        }
       }
      }
     }catch(error){console.warn('Incremental launch layer unavailable:',error);}
     map.addSource('putins',{type:'geojson',data:{type:'FeatureCollection',features:putinFeatures},cluster:true,clusterRadius:45,clusterMaxZoom:12});
     map.addLayer({id:'putin-clusters',type:'circle',source:'putins',filter:['has','point_count'],paint:{'circle-color':'#269b58','circle-radius':['step',['get','point_count'],13,10,18,50,24],'circle-stroke-color':'#fff','circle-stroke-width':1.5}});
     map.addLayer({id:'putin-counts',type:'symbol',source:'putins',filter:['has','point_count'],layout:{'text-field':['get','point_count_abbreviated'],'text-size':12},paint:{'text-color':'#fff'}});
     // A circle layer guarantees visible markers even when custom icon rendering fails.
     map.addLayer({id:'putins',type:'circle',source:'putins',filter:['!',['has','point_count']],paint:{
      'circle-radius':['interpolate',['linear'],['zoom'],6,6,11,9],
      'circle-color':'#269b58','circle-stroke-color':'#ffffff','circle-stroke-width':2
     }});
     updatePutins();
     console.info('Launch map layers loaded:',putinFeatures.length,'candidates');
     map.on('click','putin-clusters',e=>{const cluster=e.features[0];map.getSource('putins').getClusterExpansionZoom(cluster.properties.cluster_id,(err,zoom)=>{if(!err)map.easeTo({center:cluster.geometry.coordinates,zoom});});});
     map.on('click','putins',e=>{
      if(reportButton.getAttribute('aria-pressed')==='true')return;
      const p=e.features[0].properties;
      new maplibregl.Popup().setLngLat(e.lngLat)
       .setText((p.name||'Put-in candidate')+'\\nUnverified location and access; check before visiting.')
       .addTo(map);
     });
    }
   }
  }catch(e){console.error('Put-in candidates unavailable:',e);putinCount.textContent='Launch loading error: '+e.message;}

});

map.on('load',async()=>{
 try{
  const [gaugesResponse,minimaResponse,floodResponse]=await Promise.all([
   fetch('data/gauges.geojson',{cache:'no-store'}),
   fetch('data/stage_minima.json',{cache:'no-store'}),
    fetch('data/flood_stages_il.json',{cache:'no-store'})
  ]);
  if(!gaugesResponse.ok)throw new Error('Gauge data unavailable: data/gauges.geojson (HTTP '+gaugesResponse.status+'). Generate and commit this file.');
  if(!minimaResponse.ok)throw new Error('Stage minima unavailable: HTTP '+minimaResponse.status);
  const data=await gaugesResponse.json(),atlas=await minimaResponse.json();
  gaugeFeatures=data.features||[];
  // Populate the selector immediately, even if later network/route fetches fail.
  registerRivers(gaugeFeatures.map(f=>riverName(f.properties?.name)).filter(n=>n!=='Unidentified waterway'));
  applyMinima(data,atlas,floodResponse.ok?await floodResponse.json():{});
  try{communityReports=await loadReports();}catch(e){console.warn(e);}
  calibrate(data,communityReports);
  for(const f of gaugeFeatures)f.properties.level_color=palette(f.properties);
  map.addSource('gauges',{type:'geojson',data});
  map.addLayer({id:'gauges',type:'circle',source:'gauges',paint:{
   'circle-radius':7,'circle-color':['get','level_color'],'circle-stroke-color':'white','circle-stroke-width':1.5
  }});
  map.setLayoutProperty('gauges','visibility',gaugeToggle.checked?'visible':'none');
  // Optional gauge-linked network overlay; generated by scripts/build_river_segments.py.
  // Keep the original KML routes available until a generated dataset is published.
  try {
   const response=await fetch('data/river_segments.geojson',{cache:'no-store'});
   if(response.ok){
    const segments=await response.json();
    if(segments.type!=='FeatureCollection'||!Array.isArray(segments.features))throw new Error('Invalid river segments GeoJSON');
    colorRiverNetwork(segments,gaugeFeatures);
    registerRivers(segments.features.map(f=>f.properties.river_name));
    map.addSource('river-segments',{type:'geojson',data:segments});
    map.addLayer({id:'river-segments',type:'line',source:'river-segments',paint:{
     'line-color':['get','stage_color'],'line-width':['interpolate',['linear'],['zoom'],6,1.5,10,3,13,5],
     'line-opacity':0.8
    }},'gauges');
    setLayerVisibility('river-segments',riverToggle.checked);
    applyRiverFilters();
    applyRiverColorMode();
    map.on('click','river-segments',e=>{
     if(reportButton.getAttribute('aria-pressed')==='true')return;
     const p=e.features[0].properties;
     new maplibregl.Popup().setLngLat(e.lngLat)
      .setText('Nearby gauge: '+(p.gauge_name||p.site||'unknown')+
       '\\nAssociated gauges: '+(p.stage_gauge_a||'unknown')+
       (p.stage_gauge_b!==p.stage_gauge_a?' / '+p.stage_gauge_b:'')+
       '\\nColor reflects associated gauge stage; direction and paddling safety unverified.')
      .addTo(map);
    });
    console.info('Loaded',segments.features.length,'gauge-associated river segments');
   }
  }catch(e){console.warn('Optional river segments unavailable:',e);}
  // Published 3DHP review layer: authoritative river identities with nearby
  // gauge-stage association. Separate from the legacy network pending QA.
  try{
   const response=await fetch('data/river_segments_3dhp_review.geojson',{cache:'no-store'});
   if(response.ok){
    const candidate=await response.json();
    if(candidate.type!=='FeatureCollection'||!Array.isArray(candidate.features))throw new Error('Invalid 3DHP review layer');
    colorRiverNetwork(candidate,gaugeFeatures);
    registerRivers(candidate.features.map(f=>f.properties.river_name));
    map.addSource('river-3dhp-review',{type:'geojson',data:candidate});
    map.addLayer({id:'river-3dhp-review',type:'line',source:'river-3dhp-review',
      paint:{'line-color':['get','stage_color'],'line-width':['interpolate',['linear'],['zoom'],6,1.7,10,3.5,13,5],
      'line-opacity':0.9}},'gauges');
    setLayerVisibility('river-3dhp-review',riverToggle.checked);
    applyRiverFilters();
    applyRiverColorMode();
    map.on('click','river-3dhp-review',e=>{
     if(reportButton.getAttribute('aria-pressed')==='true')return;
     const p=e.features[0].properties;
     new maplibregl.Popup().setLngLat(e.lngLat).setText(
      (p.river_name||'Unidentified waterway')+
      '\\nUSGS 3DHP mainstem: '+(p.river_id||'unknown')+
      '\\nAssociated gauge: '+(p.site||p.from_gauge||'none')+
      '\\nStage color method: '+(p.stage_color_method||'unavailable')+'\\nFlow conditions are not safety guidance.'
     ).addTo(map);
    });
    console.info('Loaded',candidate.features.length,'3DHP gauge-associated review reaches');
   }
  }catch(e){console.warn('3DHP review layer unavailable:',e);}
  // Optional low-bandwidth expansion: neutral rivers and station-only gauges.
  // These do not claim to have live stage measurements.
  try{
   const [riverResponse,stationResponse]=await Promise.all([
    fetch('data/river_expansion.geojson',{cache:'no-store'}),
    fetch('data/gauges_expansion.geojson',{cache:'no-store'})
   ]);
   if(riverResponse.ok){
    const rivers=await riverResponse.json();
    if(rivers.features?.length){
     map.addSource('expanded-rivers',{type:'geojson',data:rivers});
     map.addLayer({id:'expanded-rivers',type:'line',source:'expanded-rivers',
      paint:{'line-color':'#88929b','line-width':1.5,'line-opacity':0.65}},'gauges');
     setLayerVisibility('expanded-rivers',riverToggle.checked);
    }
   }
   if(stationResponse.ok){
    const stations=await stationResponse.json();
    const known=new Set(gaugeFeatures.map(f=>String(f.properties?.site)));
    const newStations=(stations.features||[]).filter(f=>!known.has(String(f.properties?.site)));
    if(newStations.length){
     map.addSource('expanded-gauges',{type:'geojson',data:{type:'FeatureCollection',features:newStations}});
     map.addLayer({id:'expanded-gauges',type:'circle',source:'expanded-gauges',
      paint:{'circle-radius':3,'circle-color':'#88929b','circle-stroke-color':'white','circle-stroke-width':1}},'gauges');
     setLayerVisibility('expanded-gauges',gaugeToggle.checked);
    }
   }
  }catch(error){console.warn('Optional atlas expansion unavailable:',error);}
  map.on('click','gauges',event=>{
   if(reportButton.getAttribute('aria-pressed')==='true')return;
   const p=event.features[0].properties;
   const description=[
    p.name??'USGS gauge',
    'Stage: '+(p.stage??'unknown')+' ft',
    'Observed 12-month minimum: '+(p.atlas_minimum_adequate?p.atlas_minimum_ft+' ft':'insufficient coverage'),
    'Observed days: '+(p.atlas_observed_days??0)+' / 365',
    'Community paddling low: '+(p.paddling_low_ft??'not calibrated')+' ft',
    'Community paddling high: '+(p.paddling_high_ft??'not calibrated')+' ft',
    'Community reports: '+(p.community_report_count??0),
    'Observed 12-month mean: '+(p.atlas_mean_ft??'not calculated')+' ft',
    'Official flood stage: '+(p.flood_stage_ft??'unknown')+' ft',
    'Discharge: '+(p.discharge??'unknown')+' cfs',
    'Reading: '+(p.stage_time??'unknown'),
    'Observed stage is not water depth or a paddling safety rating.'
   ].join('\n');
   const node=document.createElement('div');
   node.style.whiteSpace='pre-line';
   node.textContent=description;
   const id=siteId(p.site??p.site_no??p.id);
   if(/^\\d{7,15}$/.test(id)){
    const link=document.createElement('a');
    link.href='https://waterdata.usgs.gov/monitoring-location/'+encodeURIComponent(id)+'/';
    link.target='_blank';link.rel='noopener noreferrer';
    link.textContent='View this gauge at USGS ↗';
    link.style.display='block';link.style.marginTop='10px';
    node.appendChild(link);
   }
   new maplibregl.Popup().setLngLat(event.lngLat).setDOMContent(node).addTo(map);
  });
  if(communityReports.length){
   map.addSource('community-reports',{type:'geojson',data:{type:'FeatureCollection',features:communityReports.map(r=>({type:'Feature',geometry:{type:'Point',coordinates:[r.lon,r.lat]},properties:{type:r.type,stage:r.stage,url:r.url}}))}});
   map.addLayer({id:'community-reports',type:'circle',source:'community-reports',paint:{'circle-radius':4,'circle-color':'#6e3f9c','circle-stroke-color':'white','circle-stroke-width':1}});
   map.on('click','community-reports',e=>{
    if(reportButton.getAttribute('aria-pressed')==='true')return;
    const p=e.features[0].properties,node=document.createElement('div');
    node.textContent=p.type+' at '+p.stage+' ft · ';
    const a=document.createElement('a');a.href=p.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='View report';node.append(a);
    new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(node).addTo(map);
   });
  }
  const adequate=gaugeFeatures.filter(f=>f.properties.atlas_minimum_adequate).length;
  status.textContent=gaugeFeatures.length+' gauges; '+adequate+' with observed annual minima; '+communityReports.length+' community reports; '+routeCount+' mapped river routes. Gray = insufficient data. Colors show relative stage, not paddling safety.';
 }catch(error){console.error(error);status.textContent=error.message;}
});
function beginReport(lngLat,gauge=null){
 reportPoint={longitude:lngLat.lng,latitude:lngLat.lat,gauge};
 document.getElementById('report-location').textContent=(gauge?'Gauge: '+(gauge.name||gauge.site||'unknown')+' · ':'')+fmt(lngLat.lat)+', '+fmt(lngLat.lng);
 reportForm.reset();reportDialog.showModal();
}
reportButton.addEventListener('click',()=>{
 reportButton.setAttribute('aria-pressed','true');
 map.getCanvas().style.cursor='crosshair';
 status.textContent='Click a gauge or a point within 1.5 km of a gauge. Press Escape to cancel.';
});
map.on('click',event=>{
 if(reportButton.getAttribute('aria-pressed')!=='true')return;
 reportButton.setAttribute('aria-pressed','false');map.getCanvas().style.cursor='';
 const hit=map.getLayer('gauges')?map.queryRenderedFeatures(event.point,{layers:['gauges']}).find(f=>f.layer.id==='gauges'):null;
 let gauge=hit?.properties??null;
 if(!gauge&&gaugeFeatures.length){
  const nearest=gaugeFeatures.map(f=>({p:f.properties,d:Math.hypot((f.geometry.coordinates[0]-event.lngLat.lng)*111000*Math.cos(event.lngLat.lat*Math.PI/180),(f.geometry.coordinates[1]-event.lngLat.lat)*111000)})).sort((a,b)=>a.d-b.d)[0];
  if(nearest?.d<=1500)gauge=nearest.p;
 }
 beginReport(event.lngLat,gauge);
});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&reportButton.getAttribute('aria-pressed')==='true'){
  reportButton.setAttribute('aria-pressed','false');map.getCanvas().style.cursor='';
 }
});
document.getElementById('cancel-report').onclick=()=>reportDialog.close();
reportForm.addEventListener('submit',event=>{
 event.preventDefault();
 if(!reportPoint)return;
 const type=document.getElementById('report-type').value,observed=document.getElementById('report-observed').value,notes=document.getElementById('report-notes').value.trim();
 if(!reportTypes.includes(type))return;
 const gauge=reportPoint.gauge,stage=finite(gauge?.stage);
 if(!gauge||stage===null){alert('Select a point within 1.5 km of a gauge with a stage reading.');return;}
 const readingTime=gauge.stage_time;
 if(!readingTime||!Number.isFinite(Date.parse(readingTime))||Math.abs(Date.now()-Date.parse(readingTime))>36*3600000){
  alert('The gauge reading is stale. Refresh gauge data before reporting.');return;
 }
 if(observed&&observed!==new Date().toLocaleDateString('en-CA')){
  alert('Only reports observed today can calibrate current gauge readings.');return;
 }
 const {latitude,longitude}=reportPoint,location=fmt(latitude)+', '+fmt(longitude);
 const body=[
  'Community-submitted observation — NOT verified; not a safety assessment.','','ATLAS_PADDLING_REPORT_V1',
  '**Condition:** '+type,'**Gauge ID:** '+siteId(gauge.site??gauge.site_no??gauge.id),
  '**Observed stage ft:** '+stage,'**Gauge reading time:** '+readingTime,
  '**Coordinates:** '+location,'**Map:** https://www.openstreetmap.org/?mlat='+latitude+'&mlon='+longitude+'#map=15/'+latitude+'/'+longitude,
  '**USGS gauge:** '+(gauge.name||'unknown'),'**Observed:** '+(observed||'Not specified'),
  '**Submitted (UTC):** '+new Date().toISOString(),'','**Details:**',notes||'No additional details.',
  '','This public report updates community thresholds while the issue is open. Closing the issue reverses its effect. Official USGS/NOAA values are unchanged.'
 ].join('\n');
 window.open('https://github.com/'+REPO+'/issues/new?'+new URLSearchParams({title:'River report: '+type+' — '+location,body}), '_blank','noopener,noreferrer');
 reportDialog.close();
});

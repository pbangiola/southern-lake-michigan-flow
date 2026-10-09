const map = new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-87.85,41.85],zoom:8});
map.addControl(new maplibregl.NavigationControl());
document.getElementById('print').onclick=()=>window.print();
const REPO='pbangiola/southern-lake-michigan-flow';
const reportTypes=['Too shallow','Too high / strong current','Navigable'];
const status=document.getElementById('status');
const gaugeToggle=document.getElementById('show-gauges');
gaugeToggle.addEventListener('change',()=>{
 if(map.getLayer('gauges'))map.setLayoutProperty('gauges','visibility',gaugeToggle.checked?'visible':'none');
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
function applyMinima(data,atlas){
 const stations=atlas.stations||{};
 for(const f of data.features){
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
 if(stage===null||!p.atlas_minimum_adequate||minimum===null)return '#88929b';
 const low=finite(p.paddling_low_ft)??minimum;
 const mean=finite(p.atlas_mean_ft),high=finite(p.paddling_high_ft)??finite(p.flood_stage_ft);
 if(stage<=low)return '#80502f';
 if(mean===null||mean<=low){
  // Without an observed annual mean, don't invent a flood-risk color gradient.
  return '#88929b';
 }
 if(stage<=mean)return blend('#80502f','#168ed0',(stage-low)/(mean-low));
 if(high===null||high<=mean)return '#168ed0';
 const t=Math.max(0,Math.min(1,(stage-mean)/(high-mean)));
 if(t<=.45)return blend('#168ed0','#299b59',t/.45);
 if(t<=.75)return blend('#299b59','#e8cf44',(t-.45)/.30);
 return blend('#e8cf44','#d93b32',(t-.75)/.25);
}
// River colors use graph-nearest gauge attribution, not verified flow direction.
function colorRiverNetwork(segments,gauges){
 const bySite=new Map(gauges.map(f=>[siteId(f.properties.site),f.properties]));
 const colorFor=id=>{const p=bySite.get(siteId(id));return p?palette(p):'#88929b';};
 for(const feature of segments.features){
  const p=feature.properties||(feature.properties={});
  const a=siteId(p.from_gauge||p.site),b=siteId(p.to_gauge||p.site);
  p.stage_color=a===b?colorFor(a):blend(colorFor(a),colorFor(b),0.5);
  p.stage_gauge_a=a;p.stage_gauge_b=b;
 }
 return segments;
}
map.on('load',async()=>{
 try{
  const [gaugesResponse,minimaResponse]=await Promise.all([
   fetch('data/gauges.geojson',{cache:'no-store'}),
   fetch('data/stage_minima.json',{cache:'no-store'})
  ]);
  if(!gaugesResponse.ok)throw new Error('Gauge data unavailable: data/gauges.geojson (HTTP '+gaugesResponse.status+'). Generate and commit this file.');
  if(!minimaResponse.ok)throw new Error('Stage minima unavailable: HTTP '+minimaResponse.status);
  const data=await gaugesResponse.json(),atlas=await minimaResponse.json();
  gaugeFeatures=data.features||[];
  applyMinima(data,atlas);
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
    map.addSource('river-segments',{type:'geojson',data:segments});
    map.addLayer({id:'river-segments',type:'line',source:'river-segments',paint:{
     'line-color':['get','stage_color'],'line-width':['interpolate',['linear'],['zoom'],6,1.5,10,3,13,5],
     'line-opacity':0.8
    }},'gauges');
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
  // Provisional put-ins; candidates require review before relying on access.
  try{
   const response=await fetch('data/putins.geojson',{cache:'no-store'});
   if(response.ok){
    const putins=await response.json();
    if(putins.type==='FeatureCollection'&&Array.isArray(putins.features)){
     map.addSource('putins',{type:'geojson',data:putins});
     map.addLayer({id:'putins',type:'circle',source:'putins',paint:{
      'circle-radius':5,'circle-color':'#f3a13b','circle-stroke-color':'#4e2b12','circle-stroke-width':1.5
     }});
     map.on('click','putins',e=>{
      if(reportButton.getAttribute('aria-pressed')==='true')return;
      const p=e.features[0].properties;
      new maplibregl.Popup().setLngLat(e.lngLat)
       .setText((p.name||'Put-in candidate')+'\\nUnverified location and access; check before visiting.')
       .addTo(map);
     });
    }
   }
  }catch(e){console.warn('Put-in candidates unavailable:',e);}
  // Routes traced from the user's KML; not independently verified for navigation.
  try {
   const routesResponse=await fetch('data/paddling_routes.geojson',{cache:'no-store'});
   if(!routesResponse.ok)throw new Error('HTTP '+routesResponse.status);
   const routes=await routesResponse.json();
   if(routes.type!=='FeatureCollection'||!Array.isArray(routes.features))throw new Error('Invalid route GeoJSON');
   routeCount=routes.features.length;
   map.addSource('paddling-routes',{type:'geojson',data:routes});
   map.addLayer({id:'paddling-routes',type:'line',source:'paddling-routes',paint:{
    'line-color':'#a329db',
    'line-width':['interpolate',['linear'],['zoom'],6,3.5,10,6,13,8],
    'line-opacity':0.95,
   }},'gauges');
   map.on('click','paddling-routes',e=>{
    if(reportButton.getAttribute('aria-pressed')==='true')return;
    const p=e.features[0].properties;
    new maplibregl.Popup().setLngLat(e.lngLat)
     .setText((p.name||'Mapped river route')+'\\nMapped route only; navigability has not been verified.')
     .addTo(map);
   });
   map.on('mouseenter','paddling-routes',()=>{
    if(reportButton.getAttribute('aria-pressed')!=='true')map.getCanvas().style.cursor='pointer';
   });
   map.on('mouseleave','paddling-routes',()=>{
    if(reportButton.getAttribute('aria-pressed')!=='true')map.getCanvas().style.cursor='';
   });
  }catch(e){console.warn('River routes could not load:',e);}
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
   new maplibregl.Popup().setLngLat(event.lngLat).setText(description).addTo(map);
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

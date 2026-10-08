const map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-87.3,41.85],zoom:8});
map.addControl(new maplibregl.NavigationControl());
document.getElementById('print').onclick=()=>window.print();
let gaugeFeatures=[];
let communityReports=[];
const REPO='pbangiola/southern-lake-michigan-flow';
const LOW_DEFAULT=3;
const reportTypes=['Too shallow','Too high / strong current','Navigable'];
function issueField(body,name){const m=body.match(new RegExp('^\\*\\*'+name+':\\*\\* (.+)
 const status=document.getElementById('status');
 try{
  const response=await fetch('data/gauges.geojson',{cache:'no-store'});
  if(!response.ok)throw new Error('Run python scripts/fetch_gauges.py first');
  const data=await response.json();
  gaugeFeatures=data.features;
  try{communityReports=await loadReports();}catch(e){console.warn(e.message);}
  calibrate(data,communityReports);
  const blend=(a,b,t)=>{
   t=Math.max(0,Math.min(1,t));
   const x=a.slice(1).match(/../g), y=b.slice(1).match(/../g);
   return '#'+x.map((v,i)=>Math.round(parseInt(v,16)*(1-t)+parseInt(y[i],16)*t).toString(16).padStart(2,'0')).join('');
  };
  // Visual stage scale only; not a depth measurement or paddling safety rating.
  const palette=p=>{
   const stage=p.stage, low=p.paddling_low_ft??LOW_DEFAULT, mean=p.mean_stage_12mo_ft, flood=p.paddling_high_ft??p.flood_stage_ft;
   if(!Number.isFinite(stage))return '#88929b';
   if(stage<=low)return '#80502f';
   if(!Number.isFinite(mean)||mean<=low){
    if(Number.isFinite(flood)&&flood>low)return blend('#80502f','#d93b32',(stage-low)/(flood-low));
    return '#88929b';
   }
   if(stage<=mean)return blend('#80502f','#168ed0',(stage-low)/(mean-low));
   if(!Number.isFinite(flood)||flood<=mean)return '#88929b';
   const t=Math.max(0,Math.min(1,(stage-mean)/(flood-mean)));
   if(t<=0.45)return blend('#168ed0','#299b59',t/0.45);
   if(t<=0.75)return blend('#299b59','#e8cf44',(t-0.45)/0.30);
   return blend('#e8cf44','#d93b32',(t-0.75)/0.25);
  };
  data.features.forEach(f=>{f.properties.level_color=palette(f.properties)});
  map.addSource('gauges',{type:'geojson',data});
  map.addLayer({id:'gauges',type:'circle',source:'gauges',paint:{
   'circle-radius':7,
   'circle-color':['get','level_color'],
   'circle-stroke-color':'white','circle-stroke-width':1.5
  }});
  map.on('click','gauges',event=>{
   const p=event.features[0].properties;
   const description=[p.name,'Stage: '+(p.stage??'unknown')+' ft',
    'Flood stage: '+(p.flood_stage_ft??'unknown')+' ft',
    'Action stage: '+(p.action_stage_ft??'unknown')+' ft',
    'Community paddling low: '+(p.paddling_low_ft??3)+' ft',
    'Community paddling high: '+(p.paddling_high_ft??'not reported')+' ft',
    'Community reports: '+(p.community_report_count??0),
    '12-month mean: '+(p.mean_stage_12mo_ft??'unknown')+' ft',
    '12-month minimum: '+(p.min_stage_12mo_ft??'unknown')+' ft',
    '12-month maximum: '+(p.max_stage_12mo_ft??'unknown')+' ft',
    'Daily mean coverage: '+(p.stage_coverage_days??0)+' days',
    'Above reference: '+(p.feet_above_minimum??'unknown')+' ft',
    'Flood category: '+(p.status??'unknown'),
    'Discharge: '+(p.discharge??'unknown')+' cfs',
    'Reading: '+(p.stage_time??'unknown'),
    'Not a paddling safety rating'].join('\n');
   new maplibregl.Popup().setLngLat(event.lngLat).setText(description).addTo(map);
  });
  if(communityReports.length){
   map.addSource('community-reports',{type:'geojson',data:{type:'FeatureCollection',features:communityReports.map(r=>({type:'Feature',geometry:{type:'Point',coordinates:[r.lon,r.lat]},properties:{type:r.type,stage:r.stage,url:r.url}}))}});
   map.addLayer({id:'community-reports',type:'circle',source:'community-reports',paint:{'circle-radius':4,'circle-color':'#6e3f9c','circle-stroke-color':'white','circle-stroke-width':1}});
   map.on('click','community-reports',e=>{
    if(reportButton.getAttribute('aria-pressed')==='true')return;
    const p=e.features[0].properties;
    const node=document.createElement('div');
    node.textContent=p.type+' at '+p.stage+' ft · ';
    const link=document.createElement('a');link.href=p.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='View report';node.append(link);
    new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(node).addTo(map);
   });
  }
  status.textContent=data.features.length+' gauges; '+communityReports.length+' community reports. Brown = paddling low, blue = 12-month mean, red = reported paddling high (otherwise official flood stage). Community reports are unverified.';
 }catch(error){status.textContent=error.message;}
});

// Community observations are submitted as GitHub issues, never mixed into USGS measurements.
const reportButton=document.getElementById('report-condition');
const reportDialog=document.getElementById('report-dialog');
const reportForm=document.getElementById('report-form');
let reportPoint=null;
const fmt=n=>Number(n).toFixed(6);
function beginReport(lngLat,gauge=null){
 reportPoint={longitude:lngLat.lng,latitude:lngLat.lat,gauge};
 document.getElementById('report-location').textContent=
  (gauge?'Gauge: '+(gauge.name||gauge.site_no||'unknown')+' · ':'')+
  fmt(lngLat.lat)+', '+fmt(lngLat.lng);
 reportForm.reset();
 reportDialog.showModal();
}
reportButton.addEventListener('click',()=>{
 reportButton.setAttribute('aria-pressed','true');
 map.getCanvas().style.cursor='crosshair';
 document.getElementById('status').textContent='Click a river location or gauge to report a condition. Press Escape to cancel.';
});
map.on('click',event=>{
 if(reportButton.getAttribute('aria-pressed')!=='true')return;
 reportButton.setAttribute('aria-pressed','false');
 map.getCanvas().style.cursor='';
 const hit=map.getLayer('gauges')?map.queryRenderedFeatures(event.point,{layers:['gauges']}).find(f=>f.layer.id==='gauges'):null;
 // Without river paths, only nearby gauges can be used for calibration.
 let gauge=hit?hit.properties:null;
 if(!gauge&&gaugeFeatures.length){
  const nearby=gaugeFeatures.map(f=>({p:f.properties,d:Math.hypot((f.geometry.coordinates[0]-event.lngLat.lng)*111000*Math.cos(event.lngLat.lat*Math.PI/180),(f.geometry.coordinates[1]-event.lngLat.lat)*111000)})).sort((a,b)=>a.d-b.d)[0];
  if(nearby&&nearby.d<=1500)gauge=nearby.p;
 }
 beginReport(event.lngLat,gauge);
});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&reportButton.getAttribute('aria-pressed')==='true'){
  reportButton.setAttribute('aria-pressed','false');map.getCanvas().style.cursor='';
 }
});
document.getElementById('cancel-report').addEventListener('click',()=>reportDialog.close());
reportForm.addEventListener('submit',event=>{
 event.preventDefault();
 if(!reportPoint)return;
 const type=document.getElementById('report-type').value;
 const observed=document.getElementById('report-observed').value;
 const notes=document.getElementById('report-notes').value.trim();
 if(!reportTypes.includes(type))return;
 if(!gaugeFeatures.length||!reportPoint.gauge||!Number.isFinite(Number(reportPoint.gauge.stage))){
  alert('Select a point within 1.5 km of a gauge with a current stage reading. River-path matching will support more locations once the KML is available.');return;
 }
 const stage=Number(reportPoint.gauge.stage);
 const readingTime=reportPoint.gauge.stage_time||'';
 if(!readingTime||Math.abs(Date.now()-Date.parse(readingTime))>36*3600000){alert('The gauge reading is stale. Refresh gauge data before reporting.');return;}
 const observedDate=document.getElementById('report-observed').value;
 if(observedDate&&observedDate!==new Date().toLocaleDateString('en-CA')){
  alert('Historical observations need a historical gauge lookup. For now, only reports observed today can change thresholds.');return;
 }
 const {latitude,longitude,gauge}=reportPoint;
 const location=fmt(latitude)+', '+fmt(longitude);
 const body=[
  'Community-submitted observation — NOT verified; not a safety assessment.',
  '',
  'ATLAS_PADDLING_REPORT_V1',
  '**Condition:** '+type,
  '**Gauge ID:** '+String(gauge.site||''),
  '**Observed stage ft:** '+stage,
  '**Gauge reading time:** '+readingTime,
  '**Coordinates:** '+location,
  '**Map:** https://www.openstreetmap.org/?mlat='+latitude+'&mlon='+longitude+'#map=15/'+latitude+'/'+longitude,
  '**USGS gauge:** '+(gauge.name||'unknown')+' ('+gauge.site+')',
  '**Observed:** '+(observed||'Not specified'),
  '**Submitted (UTC):** '+new Date().toISOString(),
  '',
  '**Details:**',notes||'No additional details.',
  '',
  'This public report automatically updates community paddling thresholds while the issue is open. Close the issue to reverse its effect. Official USGS/NOAA thresholds remain unchanged.'
 ].join('\n');
 const url='https://github.com/pbangiola/southern-lake-michigan-flow/issues/new?'+
  new URLSearchParams({title:'River report: '+type+' — '+location,body}).toString();
 window.open(url,'_blank','noopener,noreferrer');
 reportDialog.close();
});
,'m'));return m?m[1].trim():null;}
async function loadReports(){
 const items=[];
 for(let page=1;page<=5;page++){
  const res=await fetch('https://api.github.com/repos/'+REPO+'/issues?state=open&per_page=100&page='+page,{headers:{Accept:'application/vnd.github+json'}});
  if(!res.ok)throw new Error('Community reports unavailable (HTTP '+res.status+')');
  const batch=await res.json();
  for(const issue of batch){
   if(issue.pull_request||!issue.body||!issue.body.includes('ATLAS_PADDLING_REPORT_V1'))continue;
   const type=issueField(issue.body,'Condition');
   const site=issueField(issue.body,'Gauge ID');
   const stage=Number(issueField(issue.body,'Observed stage ft'));
   const coords=issueField(issue.body,'Coordinates');
   const xy=coords?coords.split(',').map(Number):[];
   if(!reportTypes.includes(type)||!/^\\d{7,15}$/.test(site||'')||!Number.isFinite(stage)||stage<0||stage>100||xy.length!==2||!xy.every(Number.isFinite))continue;
   items.push({type,site,stage,lat:xy[0],lon:xy[1],url:issue.html_url,created:issue.created_at,number:issue.number});
  }
  if(batch.length<100)break;
 }
 return items.sort((a,b)=>a.created.localeCompare(b.created)||a.number-b.number);
}
function calibrate(data,reports){
 const bySite=new Map();
 for(const report of reports){
  const entry=bySite.get(report.site)||{low:LOW_DEFAULT,high:null,count:0};
  if(report.type==='Too shallow')entry.low=Math.max(entry.low,report.stage);
  if(report.type==='Too high / strong current')entry.high=entry.high===null?report.stage:Math.min(entry.high,report.stage);
  if(report.type==='Navigable'){
   if(report.stage<=entry.low)entry.low=Math.max(0,report.stage-0.01);
   if(entry.high!==null&&report.stage>=entry.high)entry.high=report.stage+0.01;
  }
  entry.count++;
  bySite.set(report.site,entry);
 }
 for(const f of data.features){
  const p=f.properties, c=bySite.get(String(p.site));
  p.paddling_low_ft=c?c.low:LOW_DEFAULT;
  p.paddling_high_ft=c?c.high:null;
  p.community_report_count=c?c.count:0;
 }
}
map.on('load',async()=>{
 const status=document.getElementById('status');
 try{
  const response=await fetch('data/gauges.geojson',{cache:'no-store'});
  if(!response.ok)throw new Error('Run python scripts/fetch_gauges.py first');
  const data=await response.json();
  const blend=(a,b,t)=>{
   t=Math.max(0,Math.min(1,t));
   const x=a.slice(1).match(/../g), y=b.slice(1).match(/../g);
   return '#'+x.map((v,i)=>Math.round(parseInt(v,16)*(1-t)+parseInt(y[i],16)*t).toString(16).padStart(2,'0')).join('');
  };
  // Visual stage scale only; not a depth measurement or paddling safety rating.
  const palette=p=>{
   const stage=p.stage, low=3, mean=p.mean_stage_12mo_ft, flood=p.flood_stage_ft;
   if(!Number.isFinite(stage))return '#88929b';
   if(stage<=low)return '#80502f';
   if(!Number.isFinite(mean)||mean<=low)return '#88929b';
   if(stage<=mean)return blend('#80502f','#168ed0',(stage-low)/(mean-low));
   if(!Number.isFinite(flood)||flood<=mean)return '#88929b';
   const t=Math.max(0,Math.min(1,(stage-mean)/(flood-mean)));
   if(t<=0.45)return blend('#168ed0','#299b59',t/0.45);
   if(t<=0.75)return blend('#299b59','#e8cf44',(t-0.45)/0.30);
   return blend('#e8cf44','#d93b32',(t-0.75)/0.25);
  };
  data.features.forEach(f=>{f.properties.level_color=palette(f.properties)});
  map.addSource('gauges',{type:'geojson',data});
  map.addLayer({id:'gauges',type:'circle',source:'gauges',paint:{
   'circle-radius':7,
   'circle-color':['get','level_color'],
   'circle-stroke-color':'white','circle-stroke-width':1.5
  }});
  map.on('click','gauges',event=>{
   const p=event.features[0].properties;
   const description=[p.name,'Stage: '+(p.stage??'unknown')+' ft',
    'Flood stage: '+(p.flood_stage_ft??'unknown')+' ft',
    'Action stage: '+(p.action_stage_ft??'unknown')+' ft',
    'Provisional low reference: 3 ft',
    '12-month mean: '+(p.mean_stage_12mo_ft??'unknown')+' ft',
    '12-month minimum: '+(p.min_stage_12mo_ft??'unknown')+' ft',
    '12-month maximum: '+(p.max_stage_12mo_ft??'unknown')+' ft',
    'Daily mean coverage: '+(p.stage_coverage_days??0)+' days',
    'Above reference: '+(p.feet_above_minimum??'unknown')+' ft',
    'Flood category: '+(p.status??'unknown'),
    'Discharge: '+(p.discharge??'unknown')+' cfs',
    'Reading: '+(p.stage_time??'unknown'),
    'Not a paddling safety rating'].join('\n');
   new maplibregl.Popup().setLngLat(event.lngLat).setText(description).addTo(map);
  });
  status.textContent=data.features.length+' gauges; brown = 3 ft gauge height, blue = 12-month mean, green/yellow/red = rising toward flood, gray = insufficient reference data. NOT a paddling safety rating.';
 }catch(error){status.textContent=error.message;}
});

// Community observations are submitted as GitHub issues, never mixed into USGS measurements.
const reportButton=document.getElementById('report-condition');
const reportDialog=document.getElementById('report-dialog');
const reportForm=document.getElementById('report-form');
let reportPoint=null;
const fmt=n=>Number(n).toFixed(6);
function beginReport(lngLat,gauge=null){
 reportPoint={longitude:lngLat.lng,latitude:lngLat.lat,gauge};
 document.getElementById('report-location').textContent=
  (gauge?'Gauge: '+(gauge.name||gauge.site_no||'unknown')+' · ':'')+
  fmt(lngLat.lat)+', '+fmt(lngLat.lng);
 reportForm.reset();
 reportDialog.showModal();
}
reportButton.addEventListener('click',()=>{
 reportButton.setAttribute('aria-pressed','true');
 map.getCanvas().style.cursor='crosshair';
 document.getElementById('status').textContent='Click a river location or gauge to report a condition. Press Escape to cancel.';
});
map.on('click',event=>{
 if(reportButton.getAttribute('aria-pressed')!=='true')return;
 reportButton.setAttribute('aria-pressed','false');
 map.getCanvas().style.cursor='';
 const hit=map.queryRenderedFeatures(event.point,{layers:map.getLayer('gauges')?['gauges']:[]})
  .find(f=>f.layer.id==='gauges');
 beginReport(event.lngLat,hit?hit.properties:null);
});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&reportButton.getAttribute('aria-pressed')==='true'){
  reportButton.setAttribute('aria-pressed','false');map.getCanvas().style.cursor='';
 }
});
document.getElementById('cancel-report').addEventListener('click',()=>reportDialog.close());
reportForm.addEventListener('submit',event=>{
 event.preventDefault();
 if(!reportPoint)return;
 const type=document.getElementById('report-type').value;
 const observed=document.getElementById('report-observed').value;
 const notes=document.getElementById('report-notes').value.trim();
 const {latitude,longitude,gauge}=reportPoint;
 const location=fmt(latitude)+', '+fmt(longitude);
 const body=[
  'Community-submitted observation — NOT verified; not a safety assessment.',
  '',
  '**Condition:** '+type,
  '**Coordinates:** '+location,
  '**Map:** https://www.openstreetmap.org/?mlat='+latitude+'&mlon='+longitude+'#map=15/'+latitude+'/'+longitude,
  '**USGS gauge:** '+(gauge?(gauge.name||'unknown')+' ('+(gauge.site_no||gauge.id||'ID unavailable')+')':'Not selected'),
  '**Observed:** '+(observed||'Not specified'),
  '**Submitted (UTC):** '+new Date().toISOString(),
  '',
  '**Details:**',notes||'No additional details.',
  '',
  'Please review before displaying publicly. River conditions change quickly.'
 ].join('\n');
 const url='https://github.com/pbangiola/southern-lake-michigan-flow/issues/new?'+
  new URLSearchParams({title:'River report: '+type+' — '+location,body}).toString();
 window.open(url,'_blank','noopener,noreferrer');
 reportDialog.close();
});

const map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-87.3,41.85],zoom:8});
map.addControl(new maplibregl.NavigationControl());
document.getElementById('print').onclick=()=>window.print();
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

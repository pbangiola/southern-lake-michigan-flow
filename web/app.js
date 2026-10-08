const map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-87.3,41.85],zoom:8});
map.addControl(new maplibregl.NavigationControl());
document.getElementById('print').onclick=()=>window.print();
map.on('load',async()=>{
 const status=document.getElementById('status');
 try{
  const response=await fetch('data/gauges.geojson',{cache:'no-store'});
  if(!response.ok)throw new Error('Run python scripts/fetch_gauges.py first');
  const data=await response.json();
  const mix=(a,b,t)=>'#'+a.match(/\\w\\w/g).map((v,i)=>Math.round(parseInt(v,16)*(1-t)+parseInt(b.match(/\\w\\w/g)[i],16)*t).toString(16).padStart(2,'0')).join('');
  const blend=(a,b,t)=>mix(a.slice(1),b.slice(1),Math.max(0,Math.min(1,t)));
  const palette=p=>{
   const stage=p.stage, min=p.reference_stage_ft, flood=p.flood_stage_ft;
   if(!Number.isFinite(stage)||!Number.isFinite(min)||!Number.isFinite(flood)||flood<=min+2)return '#88929b';
   if(stage<=min)return '#80502f';
   if(stage<min+2)return blend('#80502f','#168ed0',(stage-min)/2);
   if(stage<=min+2.001)return '#168ed0';
   const fraction=Math.max(0,Math.min(1,(stage-(min+2))/(flood-(min+2))));
   if(fraction<0.5)return blend('#299b59','#e8cf44',fraction*2);
   return blend('#e8cf44','#d93b32',(fraction-0.5)*2);
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
    'Provisional low reference: '+(p.reference_stage_ft??'unknown')+' ft',
    'Above reference: '+(p.feet_above_minimum??'unknown')+' ft',
    'Flood category: '+(p.status??'unknown'),
    'Discharge: '+(p.discharge??'unknown')+' cfs',
    'Reading: '+(p.stage_time??'unknown'),
    'Not a paddling safety rating'].join('\n');
   new maplibregl.Popup().setLngLat(event.lngLat).setText(description).addTo(map);
  });
  status.textContent=data.features.length+' gauges; brown = 3 ft gauge height, blue = 5 ft, green/yellow/red = rising toward flood, gray = insufficient reference data. NOT a paddling safety rating.';
 }catch(error){status.textContent=error.message;}
});
const map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-87.3,41.85],zoom:8});
map.addControl(new maplibregl.NavigationControl());
document.getElementById('print').onclick=()=>window.print();
map.on('load',async()=>{
 const status=document.getElementById('status');
 try{
  const response=await fetch('data/gauges.geojson',{cache:'no-store'});
  if(!response.ok)throw new Error('Run python scripts/fetch_gauges.py first');
  const data=await response.json();
  map.addSource('gauges',{type:'geojson',data});
  map.addLayer({id:'gauges',type:'circle',source:'gauges',paint:{
   'circle-radius':7,
   'circle-color':['match',['get','status'],'at_or_above_flood','#b73c36','below_flood','#29865b','#88929b'],
   'circle-stroke-color':'white','circle-stroke-width':1.5
  }});
  map.on('click','gauges',event=>{
   const p=event.features[0].properties;
   const description=[p.name,'Stage: '+(p.stage??'unknown')+' ft',
    'Flood stage: '+(p.flood_stage_ft??'unknown')+' ft',
    'Discharge: '+(p.discharge??'unknown')+' cfs',
    'Reading: '+(p.stage_time??'unknown'),
    'Not a paddling safety rating'].join('\n');
   new maplibregl.Popup().setLngLat(event.lngLat).setText(description).addTo(map);
  });
  status.textContent=data.features.length+' gauges loaded; green = below flood stage, red = at/above flood stage, gray = no threshold. NOT paddling safety ratings.';
 }catch(error){status.textContent=error.message;}
});
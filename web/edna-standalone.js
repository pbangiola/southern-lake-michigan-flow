/* Standalone EDNA render. No gauge graph, snapping, or stage integration. */
const status=document.getElementById('status');
const map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-98.5,39.5],zoom:4});
map.addControl(new maplibregl.NavigationControl());
let errors=0,loaded=0;
map.on('error',e=>{const msg=String(e.error?.message||e.error||'');if(/edna|pbf|tile/i.test(msg)){errors++;status.textContent='EDNA tile error ('+errors+'): '+msg;}});
map.on('load',async()=>{
 try{
  const response=await fetch('data/edna_tiles/manifest.json',{cache:'no-store'});
  if(!response.ok)throw new Error('Manifest HTTP '+response.status);
  const manifest=await response.json();
  if(!manifest.complete)throw new Error('EDNA tile manifest is incomplete');
  map.addSource('edna',{type:'vector',tiles:[new URL('data/edna_tiles/{z}/{x}/{y}.pbf',document.baseURI).href],minzoom:0,maxzoom:manifest.maxzoom||12});
  map.addLayer({id:'edna',type:'line',source:'edna','source-layer':manifest.layer||'edna',paint:{'line-color':'#176e9a','line-width':['interpolate',['linear'],['zoom'],3,0.8,8,1.6,13,3],'line-opacity':0.9}});
  map.on('sourcedata',e=>{if(e.sourceId==='edna'&&e.isSourceLoaded){const n=map.queryRenderedFeatures({layers:['edna']}).length;status.textContent='EDNA standalone · '+n.toLocaleString()+' visible features in current viewport'+(errors?' · '+errors+' tile errors':'');}});
  map.on('click','edna',e=>{const f=e.features[0];new maplibregl.Popup().setLngLat(e.lngLat).setText(JSON.stringify(f.properties||{})).addTo(map);});
  document.getElementById('width').oninput=e=>map.setPaintProperty('edna','line-width',Number(e.target.value));
  document.getElementById('basemap').onchange=e=>{for(const layer of map.getStyle().layers){if(layer.id!=='edna'&&layer.type!=='background')map.setLayoutProperty(layer.id,'visibility',e.target.checked?'visible':'none');}};
  status.textContent='EDNA source registered; waiting for tiles…';
 }catch(err){status.textContent='EDNA unavailable: '+err.message;console.error(err);}
});

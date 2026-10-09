// Insert after the 'gauges' layer is created, within the existing map load handler.
// Segments are mapped geometries associated by proximity, not verified river conditions.
try {
  const response = await fetch('data/river_segments.geojson', {cache:'no-store'});
  if (!response.ok) throw new Error(`River segments HTTP ${response.status}`);
  const segments = await response.json();
  if (segments.type !== 'FeatureCollection') throw new Error('Invalid river segments GeoJSON');
  map.addSource('river-segments', {type:'geojson',data:segments});
  map.addLayer({id:'river-segments',type:'line',source:'river-segments',paint:{
    'line-color':'#1789bd',
    'line-width':['interpolate',['linear'],['zoom'],6,1.5,10,3,13,5],
    'line-opacity':0.8
  }},'gauges');
  map.on('click','river-segments',e=>{
    if(reportButton.getAttribute('aria-pressed')==='true')return;
    const p=e.features[0].properties;
    new maplibregl.Popup().setLngLat(e.lngLat).setText(
      `Nearby gauge: ${p.gauge_name || p.site}\n`+
      `Gauge proximity: ${p.gauge_distance_m} m\n`+
      'Unverified association; river conditions not classified.'
    ).addTo(map);
  });
  console.info('Loaded',segments.features.length,'river segments');
} catch(error) { console.warn('River segments unavailable:',error); }
/* Exploratory gauge-name graph. No claim of hydrological routing. */
const map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[-98.5,39.5],zoom:3.5});
map.addControl(new maplibregl.NavigationControl());
const $=id=>document.getElementById(id);
const empty=()=>({type:'FeatureCollection',features:[]});
const pattern=/^(.+?)\s+(?:at|near)\s+(.+)$/i;
const cleanName=s=>String(s||'').trim().replace(/\s+/g,' ').replace(/\s+(?:river|creek|branch|fork)\s*$/i,m=>m).toUpperCase();
const color=s=>{let h=2166136261;for(const c of s)h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;return 'hsl('+h%360+',65%,43%)';};
const distance=(a,b)=>{const rad=Math.PI/180,lat1=a[1]*rad,lat2=b[1]*rad,dy=(b[1]-a[1])*rad,dx=(b[0]-a[0])*rad;const h=Math.sin(dy/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dx/2)**2;return 12742*Math.asin(Math.min(1,Math.sqrt(h)));};
let groups=new Map(),allPoints=empty(),totalMatched=0;
function connections(limit){
 const lines=[];let edges=0,components=0;
 for(const [name,points] of groups){
  if(points.length<2)continue;
  // Prim's minimum spanning tree: the shortest links needed to connect same-name stations.
  // A maximum gap turns the tree into a forest, suppressing implausibly long links.
  const used=new Uint8Array(points.length),best=new Float64Array(points.length).fill(Infinity),parent=new Int32Array(points.length).fill(-1);
  best[0]=0;
  for(let n=0;n<points.length;n++){
   let pick=-1,lowest=Infinity;
   for(let i=0;i<points.length;i++)if(!used[i]&&best[i]<lowest){lowest=best[i];pick=i;}
   if(pick<0)break;
   used[pick]=1;
   if(parent[pick]>=0&&lowest<=limit){
    const a=points[parent[pick]],b=points[pick];
    lines.push({type:'Feature',geometry:{type:'LineString',coordinates:[a.geometry.coordinates,b.geometry.coordinates]},properties:{water_body:name,distance_km:Math.round(lowest*10)/10,color:color(name),from:a.properties.name,to:b.properties.name}});
    edges++;
   }else components++;
   for(let j=0;j<points.length;j++)if(!used[j]){
    const d=distance(points[pick].geometry.coordinates,points[j].geometry.coordinates);
    if(d<best[j]){best[j]=d;parent[j]=pick;}
   }
  }
 }
 map.getSource('name-connections').setData({type:'FeatureCollection',features:lines});
 $('status').textContent=allPoints.features.length.toLocaleString()+' named NOAA gauges · '+groups.size.toLocaleString()+' distinct water-body names · '+edges.toLocaleString()+' connections · '+components.toLocaleString()+' components. Lines are straight links, not mapped waterways.';
}
function popup(p,coordinates){
 const node=document.createElement('div');node.style.whiteSpace='pre-line';
 node.textContent=[p.name||p.water_body||'Gauge',p.noaa_lid?'NOAA: '+p.noaa_lid:null,p.distance_km!==undefined?'Connection: '+p.distance_km+' km':null,p.stage!==undefined?'Stage: '+p.stage+' ft':null].filter(Boolean).join('\n');
 if(p.noaa_lid){const a=document.createElement('a');a.href='https://water.noaa.gov/gauges/'+encodeURIComponent(p.noaa_lid);a.target='_blank';a.rel='noopener noreferrer';a.textContent='Open NOAA station ↗';node.append(document.createElement('br'),a);}
 new maplibregl.Popup().setLngLat(coordinates).setDOMContent(node).addTo(map);
}
map.on('load',async()=>{
 try{
  const res=await fetch('data/noaa_gauges.geojson');
  if(!res.ok)throw new Error('NOAA gauge file HTTP '+res.status);
  const data=await res.json(),features=[];
  for(const f of data.features||[]){
   const p=f.properties||{},m=String(p.name||'').trim().match(pattern),xy=f.geometry?.coordinates;
   if(!m||f.geometry?.type!=='Point'||!Array.isArray(xy)||!xy.slice(0,2).every(Number.isFinite))continue;
   const name=cleanName(m[1]);if(!name)continue;
   const item={type:'Feature',geometry:f.geometry,properties:{...p,water_body:name,color:color(name)}};
   features.push(item);if(!groups.has(name))groups.set(name,[]);groups.get(name).push(item);
  }
  allPoints={type:'FeatureCollection',features};totalMatched=features.length;
  map.addSource('name-connections',{type:'geojson',data:empty()});
  map.addLayer({id:'name-connections',type:'line',source:'name-connections',paint:{'line-color':['get','color'],'line-width':['interpolate',['linear'],['zoom'],3,1.5,10,3],'line-opacity':0.8}});
  map.addSource('named-gauges',{type:'geojson',data:allPoints});
  map.addLayer({id:'named-gauges',type:'circle',source:'named-gauges',paint:{'circle-color':['get','color'],'circle-radius':['interpolate',['linear'],['zoom'],3,3,9,6],'circle-stroke-color':'#fff','circle-stroke-width':1}});
  connections(Number($('max-gap').value));
  $('max-gap').onchange=()=>connections(Number($('max-gap').value));
  $('show-points').onchange=()=>map.setLayoutProperty('named-gauges','visibility',$('show-points').checked?'visible':'none');
  $('show-lines').onchange=()=>map.setLayoutProperty('name-connections','visibility',$('show-lines').checked?'visible':'none');
  map.on('click','named-gauges',e=>popup(e.features[0].properties,e.lngLat));
  map.on('click','name-connections',e=>popup(e.features[0].properties,e.lngLat));
  for(const layer of ['named-gauges','name-connections']){map.on('mouseenter',layer,()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave',layer,()=>map.getCanvas().style.cursor='');}
 }catch(error){$('status').textContent='Unable to load gauges: '+error.message;console.error(error);}
});

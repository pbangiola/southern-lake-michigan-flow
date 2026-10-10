// Deploy as a Cloudflare Worker. Configure GITHUB_TOKEN as a Worker secret.
// The token needs Contents: read/write on pbangiola/southern-lake-michigan-flow only.
const REPO='pbangiola/southern-lake-michigan-flow';
const PATH='data/verified_launches.json';
const ALLOWED_ORIGIN='https://pbangiola.github.io';
const API='https://api.github.com/repos/'+REPO+'/contents/'+PATH;
const headers=token=>({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'flow-atlas-launch-verification'});
const cors={'Access-Control-Allow-Origin':ALLOWED_ORIGIN,'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type','Vary':'Origin'};
const reply=(obj,status=200)=>new Response(JSON.stringify(obj),{status,headers:{...cors,'Content-Type':'application/json','Cache-Control':'no-store'}});
export default {async fetch(request,env){
 if(request.headers.get('Origin')!==ALLOWED_ORIGIN)return reply({error:'Origin not allowed'},403);
 if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors});
 if(request.method!=='POST')return reply({error:'Method not allowed'},405);
 if(!env.GITHUB_TOKEN)return reply({error:'Backend not configured'},503);
 let body;try{body=await request.json();}catch{return reply({error:'Invalid JSON'},400);}
 const id=body?.id,verified=body?.verified;
 if(typeof id!=='string'||!/^[-\w:.]{1,120}$/.test(id)||typeof verified!=='boolean')return reply({error:'Invalid launch ID or state'},400);
 for(let attempt=0;attempt<4;attempt++){
  const current=await fetch(API+'?ref=main',{headers:headers(env.GITHUB_TOKEN),cache:'no-store'});
  if(!current.ok)return reply({error:'Could not read verification registry'},502);
  const doc=await current.json();
  const original=JSON.parse(atob(doc.content.replace(/\s/g,'')));
  const ids=new Set((original.verified_ids||[]).map(String));
  if(verified)ids.add(id);else ids.delete(id);
  const next={...original,verified_ids:[...ids].sort()};
  const content=btoa(JSON.stringify(next,null,2)+'\n');
  const write=await fetch(API,{method:'PUT',headers:{...headers(env.GITHUB_TOKEN),'Content-Type':'application/json'},body:JSON.stringify({message:(verified?'Verify':'Unverify')+' launch '+id,content,sha:doc.sha,branch:'main'})});
  if(write.ok)return reply({id,verified,shared:true});
  if(write.status!==409&&write.status!==422)return reply({error:'Could not save verification'},502);
 }
 return reply({error:'Concurrent update; retry'},409);
}};

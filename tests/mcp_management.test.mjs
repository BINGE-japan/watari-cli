import test from 'node:test';
import assert from 'node:assert/strict';
import { connectionBinding, manageConnection } from '../src/watari_cli/pi/mcp-management.mjs';

function fixture() {
  const calls=[];
  const config={mcpServers:{example:{url:'https://mcp.example.com/mcp',auth:'oauth'}}};
  const metadata={computeServerHash:()=> 'synthetic-identity'};
  const auth={getAuthStorageOptions:(...args)=>{calls.push(['storage',...args]);return {credentialStore:'encrypted-file'};}};
  class Manager {
    setAuthStorageOptions(x){calls.push(['store-options',x]);}
    setOAuthRuntime(){} setRuntimeSignal(){} setDefaultRequestTimeoutMs(){} setTraceConfig(){}
    async connect(name){calls.push(['connect',name]);return {status:'connected',tools:[{name:'search',description:'secret-description'}]};}
    async closeAll(){calls.push(['close']);}
  }
  const flow={createOAuthRuntime:()=>({}),supportsOAuth:()=>true,async authenticate(...args){calls.push(['auth',args[0]]);return 'authenticated';},async shutdownOAuth(){calls.push(['shutdown']);}};
  return {calls,config,metadata,auth,Manager,flow,utils:{resolveServerUrl: d=>d.url},bearer:{saveBearerTokenForUrl:(...args)=>calls.push(['bearer',...args])}};
}
function request(f,action='check') {return {name:'example',action,cwd:'/synthetic',binding:connectionBinding(f.config,'example','/synthetic',f.metadata)};}

test('check connects only selected server, disables traces, closes runtime, returns counts not tool data',async()=>{
 const f=fixture();f.config.mcpServers.other={command:'must-not-launch'};
 const r=await manageConnection(request(f),f);
 assert.equal(r.status,'connected');assert.equal(r.tool_count,1);
 assert.deepEqual(f.calls.filter(c=>c[0]==='connect'),[['connect','example']]);
 assert.ok(f.calls.some(c=>c[0]==='close'));assert.ok(f.calls.some(c=>c[0]==='shutdown'));
 assert.ok(!JSON.stringify(r).includes('secret-description'));
});
test('changed configuration after approval never connects',async()=>{
 const f=fixture(),r=request(f);f.config.mcpServers.example.url='https://other.example.com/mcp';
 assert.equal((await manageConnection(r,f)).status,'changed');
 assert.equal(f.calls.length,0);
});
test('auth uses existing adapter OAuth flow and verifies connection afterwards',async()=>{
 const f=fixture();const result=await manageConnection(request(f,'auth'),f);
 assert.equal(result.status,'connected');
 assert.ok(f.calls.findIndex(c=>c[0]==='auth')<f.calls.findIndex(c=>c[0]==='connect'));
});
test('token input goes directly to adapter URL-bound store, never result or configuration',async()=>{
 const f=fixture();f.config.mcpServers.example={url:'https://mcp.example.com/mcp',auth:'bearer',bearerTokenStore:true};
 f.readSecret=async()=> 'synthetic-token';
 const result=await manageConnection(request(f,'auth'),f);
 assert.ok(f.calls.some(c=>c[0]==='bearer'&&c[2]==='synthetic-token'));
 assert.ok(!JSON.stringify(result).includes('synthetic-token'));assert.ok(!JSON.stringify(f.config).includes('synthetic-token'));
});
test('raw adapter errors never disclose credentials and cleanup still runs',async()=>{
 const f=fixture();f.Manager.prototype.connect=async()=>{throw new Error('Authorization Bearer synthetic-secret');};
 const result=await manageConnection(request(f),f);
 assert.equal(result.status,'error');assert.ok(!JSON.stringify(result).includes('synthetic-secret'));
 assert.ok(f.calls.some(c=>c[0]==='close'));assert.ok(f.calls.some(c=>c[0]==='shutdown'));
});
test('disabled, malformed and unknown operations fail closed',async()=>{
 for(const mode of ['disabled','operation','binding']){
  const f=fixture();if(mode==='disabled')f.config.mcpServers.example.disabled=true;
  const r=request(f);if(mode==='operation')r.action='call-tool';if(mode==='binding')r.binding='invalid';
  assert.notEqual((await manageConnection(r,f)).status,'connected');
  assert.equal(f.calls.length,0);
 }
});
test('cleanup failure replaces a success result but still shuts OAuth down',async()=>{
 const f=fixture();f.Manager.prototype.closeAll=async()=>{throw new Error('synthetic cleanup error');};
 assert.equal((await manageConnection(request(f),f)).status,'cleanup-failed');
 assert.ok(f.calls.some(c=>c[0]==='shutdown'));
});
test('already cancelled operation does not read credentials or connect',async()=>{
 const f=fixture(),controller=new AbortController();controller.abort();
 assert.equal((await manageConnection({...request(f),signal:controller.signal},f)).status,'cancelled');
 assert.equal(f.calls.length,0);
});
test('early authentication refusal still reports a failed cleanup',async()=>{
 const f=fixture();f.flow.supportsOAuth=()=>false;
 f.Manager.prototype.closeAll=async()=>{throw new Error('synthetic cleanup error');};
 assert.equal((await manageConnection(request(f,'auth'),f)).status,'cleanup-failed');
 assert.ok(f.calls.some(c=>c[0]==='shutdown'));
});

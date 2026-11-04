// Original DOM double: verifies interaction logic, NOT browser layout or rendering.
const fs=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');const path=require('node:path');
const root=path.resolve(__dirname,'../virtual_trade_lab/web');
const html=fs.readFileSync(path.join(root,'replay.html'),'utf8');
const script=fs.readFileSync(path.join(root,'replay.js'),'utf8');
const source=JSON.parse(fs.readFileSync(path.join(root,'replay-data.json'),'utf8'));
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.attrs={};this.hidden=false;this.disabled=false;this.open=false;this.value='';this.textContent='';}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,f){this.listeners[k]=f;}
 set innerHTML(v){throw Error('Unsafe innerHTML attempted');}
 fire(k,event={}){if(!this.disabled&&this.listeners[k])this.listeners[k]({target:this,...event});}
}
async function boot({hash='',badData=false,failFetch=false,badRecord=false}={}){
 const ids={};for(const match of html.matchAll(/<[^>]+id="([^"]+)"[^>]*>/g)){ids[match[1]]=new Element();ids[match[1]].hidden=/\bhidden\b/.test(match[0]);}
 const windowListeners={},documentListeners={},timers=new Map(),calls=[];let serial=0;
 const location={hash};const entries=[hash];let index=0;
 const history={pushState(_a,_b,h){entries.splice(index+1);entries.push(h);index++;location.hash=h;},replaceState(_a,_b,h){entries[index]=h;location.hash=h;}};
 const document={getElementById:k=>{assert(ids[k],`Missing actual HTML id ${k}`);return ids[k];},createElement:t=>new Element(t),hidden:false,addEventListener:(k,f)=>documentListeners[k]=f};
 const payload=structuredClone(source);if(badData)payload.steps[0].balances.buyer=91;if(badRecord)payload.steps[1].model_outputs[0].stage=null;
 const context={document,location,history,console,fetch:async(url,opts)=>{calls.push({url,opts});return {ok:!failFetch,status:503,json:async()=>payload};},
 setInterval:f=>{timers.set(++serial,f);return serial;},clearInterval:id=>timers.delete(id),addEventListener:(k,f)=>windowListeners[k]=f};
 vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));
 return {ids,timers,calls,document,documentListeners,windowListeners,location,payload,
 back(){if(index){index--;location.hash=entries[index];windowListeners.popstate();}},forward(){if(index<entries.length-1){index++;location.hash=entries[index];windowListeners.popstate();}},tick(){[...timers.values()].forEach(f=>f());}};
}
(async()=>{
 const u=await boot();assert.equal(u.ids.replay.hidden,false);assert.equal(u.ids.steps.children.length,6);
 assert.equal(u.ids['balance-buyer'].textContent,'90');assert.equal(u.ids.prev.disabled,true);assert.equal(u.ids.mismatch.hidden,true);
 u.ids.steps.children[2].fire('click');assert.equal(u.ids['balance-escrow'].textContent,'32');assert.equal(u.ids['raw-details'].hidden,false);
 assert.equal(u.ids['raw-output'].children.length,4);
 u.ids.steps.children[5].fire('click');assert.equal(u.ids['balance-buyer'].textContent,'90');assert.equal(u.ids['balance-cost'].textContent,'4');assert.equal(u.ids['balance-escrow'].textContent,'0');assert.equal(u.ids.next.disabled,true);assert.equal(u.ids.mismatch.hidden,false);
 const frozen=JSON.stringify(u.payload);for(let n=0;n<8;n++)u.ids.next.fire('click');assert.equal(JSON.stringify(u.payload),frozen);
 u.back();assert.equal(u.ids.position.value,'2');u.forward();assert.equal(u.ids.position.value,'5');
 u.ids.play.fire('click');assert.equal(u.ids.position.value,'0');assert.equal(u.timers.size,1);u.tick();assert.equal(u.ids.position.value,'1');
 u.ids.play.fire('click');assert.equal(u.timers.size,0);u.ids.play.fire('click');u.document.hidden=true;u.documentListeners.visibilitychange();assert.equal(u.timers.size,0);
 u.ids.position.value='4';u.ids.position.fire('input');assert.equal(u.ids['raw-details'].hidden,true);assert.equal(u.ids['balance-escrow'].textContent,'32');
 u.ids.play.fire('click');u.tick();assert.equal(u.ids.position.value,'5');assert.equal(u.timers.size,0);
 assert.equal(u.calls.length,1);assert.equal(u.calls[0].url,'/replay-data.json');assert.equal(u.calls[0].opts.method,undefined);
 const reload=await boot({hash:'#step=5'});assert.equal(reload.ids.position.value,'5');
 const invalid=await boot({hash:'#step=999'});assert.equal(invalid.ids.position.value,'0');
 const bad=await boot({badData:true});assert.equal(bad.ids.replay.hidden,true);assert.equal(bad.ids.loading.hidden,false);
 const malformed=await boot({badRecord:true});assert.equal(malformed.ids.replay.hidden,true);assert.equal(malformed.ids.loading.hidden,false);
 const fail=await boot({failFetch:true});assert.equal(fail.ids.replay.hidden,true);assert.equal(fail.ids.loading.hidden,false);
 console.log('PASS: step/jump/back/forward/reload/repeated clicks/autoplay/pause/visibility/end/error/data guards; DOM double only, no visual QA.');
})().catch(e=>{console.error(e);process.exitCode=1;});

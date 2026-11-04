'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const labels = ['商品条件','双方验货','同意托管','卖方交付','开箱发现','拒收退款'];
  const kind = ['固定商品条件','真实模型选择','真实模型承诺','真实模型交付决定','预设模拟缺陷','真实模型退款请求'];
  const decisions = {inspect:'选择验货',skip:'跳过验货',accept:'同意',decline:'拒绝',defer:'暂缓',deliver:'选择交付',refund:'申请退款'};
  const accounts = {buyer:'买家',seller:'卖家',provider:'履约费用账户','escrow:A':'订单托管'};
  let data, current = 0, timer = null;
  function node(tag,text,cls) { const n = document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
  function stop() { if(timer!==null)clearInterval(timer); timer=null; $('play').textContent='播放回放'; $('play').setAttribute('aria-pressed','false'); }
  function hashStep() {const match=/^#step=(\d+)$/.exec(location.hash); return match && Number(match[1])<data.steps.length ? Number(match[1]) : 0;}
  function navigate(index,auto=false) {
    const next=Math.max(0,Math.min(data.steps.length-1,index));
    if(!auto)stop();
    current=next;
    if(auto)history.replaceState(null,'',`#step=${current}`); else if(location.hash!==`#step=${current}`)history.pushState(null,'',`#step=${current}`);
    render();
  }
  function render() {
    const step=data.steps[current];
    $('stage-count').textContent=`步骤 ${current+1} / ${data.steps.length}`;
    $('stage-title').textContent=step.title; $('stage-caption').textContent=step.caption; $('stage-kind').textContent=kind[current];
    $('position').value=String(current); $('position-label').textContent=`${current+1} / ${data.steps.length}`;
    $('prev').disabled=current===0; $('next').disabled=current===data.steps.length-1;
    [...$('steps').children].forEach((b,i)=>{if(i===current)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
    $('mismatch').hidden=current<4;
    $('inspection').replaceChildren();
    if(step.inspection) {
      const f=node('div',undefined,'fixture');
      f.append(node('strong',current===1?'预设合成入库记录 · 不保证封箱内容':'预设合成开箱记录 · 不是模型推断'));
      f.append(node('span',`${step.inspection.unit_id} · ${step.inspection.capacity_ml} ml · ${step.inspection.weight_g} g · 防漏记录：${step.inspection.leaks===false?'通过（模拟）':'未通过'}`));
      $('inspection').append(f);
    }
    $('decisions').replaceChildren(); $('raw-output').replaceChildren();
    step.model_outputs.forEach(record=>{
      const role=record.stage.startsWith('buyer')?'买家模型':'卖家模型';
      const card=node('div',undefined,'decision'); const heading=node('div',undefined,'label');
      heading.append(node('span',role),node('strong',decisions[record.decision]||record.decision));
      card.append(heading,node('p',record.reason)); $('decisions').append(card);
      $('raw-output').append(node('p',`${role} · ${record.stage}`),node('pre',record.raw));
    });
    $('no-decision').textContent=step.model_outputs.length?'':current===4?'本步骤展示固定环境记录；买家的决定在下一步。':'买家可以拒绝购买，免费旧瓶始终是可选项。';
    $('raw-details').hidden=!step.model_outputs.length; $('raw-details').open=false;
    for(const key of ['buyer','seller','escrow','cost'])$(`balance-${key}`).textContent=String(step.balances[key]);
    $('conservation').textContent=`总额${step.total} · 守恒`;
    $('journal').replaceChildren();
    if(!step.journal.length)$('journal').append(node('li','尚无积分转移。'));
    step.journal.forEach(j=>$('journal').append(node('li',`${accounts[j.from]||j.from} → ${accounts[j.to]||j.to}：${j.credits}积分 · ${{fund:'进入托管',compute:'履约费用',reject_refund:'拒收退款'}[j.reason]||j.reason}`)));
    if(current===data.steps.length-1)stop();
  }
  function validate(value) {
    if(value.schema!=='model-refund-replay/v1'||!Array.isArray(value.steps)||value.steps.length!==6||value.summary.real_payments!==0)throw Error('数据格式不符');
    const text=x=>typeof x==='string';
    if(!Array.isArray(value.limits)||!value.limits.every(text)||!value.source||!text(value.source.evidence_path)||
       !/^[0-9a-f]{64}$/.test(value.source.protocol_sha256)||!/^[0-9a-f]{64}$/.test(value.source.report_sha256))throw Error('来源记录不完整');
    for(const s of value.steps){
      const nums=['buyer','seller','escrow','cost'].map(k=>s.balances[k]);
      if(!nums.every(n=>Number.isInteger(n)&&n>=0)||nums.reduce((a,b)=>a+b,0)!==s.total||s.total!==130)throw Error('积分记录校验失败');
      if(!text(s.title)||!text(s.caption)||!Array.isArray(s.model_outputs)||!Array.isArray(s.journal))throw Error('事件记录不完整');
      for(const r of s.model_outputs){
        if(!r||!text(r.stage)||!text(r.raw)||!text(r.reason)||!text(r.decision))throw Error('模型记录不完整');
        const raw=JSON.parse(r.raw);if(raw.decision!==r.decision||raw.reason!==r.reason)throw Error('模型原文与摘要不符');
      }
      for(const j of s.journal)if(!j||!text(j.from)||!text(j.to)||!text(j.reason)||!Number.isInteger(j.credits)||j.credits<0)throw Error('转移记录不完整');
      if(s.inspection&&(!text(s.inspection.unit_id)||!Number.isInteger(s.inspection.capacity_ml)||!Number.isInteger(s.inspection.weight_g)||typeof s.inspection.leaks!=='boolean'))throw Error('检查记录不完整');
    }
    return value;
  }
  async function init() {
    try {
      const response=await fetch('/replay-data.json',{cache:'no-store'});
      if(!response.ok)throw Error(`读取失败 (${response.status})`);
      data=validate(await response.json());
      labels.forEach((label,i)=>{const b=node('button');b.type='button';b.append(node('span',String(i+1)),node('b',label));b.addEventListener('click',()=>navigate(i));$('steps').append(b);});
      data.limits.forEach(t=>$('limits').append(node('p',t)));
      $('source-path').textContent=data.source.evidence_path;$('protocol-hash').textContent=data.source.protocol_sha256;$('report-hash').textContent=data.source.report_sha256;
      $('prev').addEventListener('click',()=>navigate(current-1));$('next').addEventListener('click',()=>navigate(current+1));
      $('position').addEventListener('input',e=>navigate(Number(e.target.value)));
      $('play').addEventListener('click',()=>{
        if(timer!==null){stop();return;}
        if(current===data.steps.length-1)navigate(0);
        $('play').textContent='暂停';$('play').setAttribute('aria-pressed','true');
        timer=setInterval(()=>navigate(current+1,true),2200);
      });
      addEventListener('popstate',()=>{stop();current=hashStep();render();});
      addEventListener('hashchange',()=>{stop();current=hashStep();render();});
      document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
      addEventListener('pagehide',stop);
      current=hashStep();$('loading').hidden=true;$('replay').hidden=false;render();
    } catch(error) {
      stop();$('loading').hidden=false;$('replay').hidden=true;
      $('loading').replaceChildren(node('strong','无法显示回放记录。'),node('p',`${error.message}。未执行任何交易，请刷新重试。`));
    }
  }
  init();
})();

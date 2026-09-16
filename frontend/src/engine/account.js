/* SPDX-License-Identifier: AGPL-3.0-only */
(function(global){
  'use strict';
  // Credentials live only in this page's memory, never storage or URLs.
  let key='',generation=0;
  function disconnect(){key='';generation++;}
  function trusted(url){
    const target=new URL(url,global.location.href);
    return target.origin===global.location.origin && (target.protocol==='https:' || ['localhost','127.0.0.1','[::1]'].includes(target.hostname));
  }
  async function identity(secret){
    if(!trusted('/api/v2/me'))throw new Error('Account access requires HTTPS.');
    const response=await global.fetch('/api/v2/me',{headers:secret?{Authorization:'Bearer '+secret}:{},credentials:'same-origin',redirect:'error',cache:'no-store'});
    if(!response.ok)throw new Error('Account access could not be verified. Check your key or reconnect.');
    const result=await response.json();
    if(!result.access || !['free','pro'].includes(result.access.tier))throw new Error('Invalid account response.');
    return result.access;
  }
  async function connect(secret){
    disconnect();const attempt=generation;
    const value=String(secret||'').trim();
    if(!/^vh_[A-Za-z0-9_-]+$/.test(value))throw new Error('Enter your private Vahini access key.');
    const access=await identity(value);
    if(attempt!==generation)throw new Error('Account connection was cancelled.');
    key=value;return access;
  }
  async function request(url){
    const target=new URL(url,global.location.href);
    if(!trusted(target)){
      if(key)throw new Error('Account reports must use this website’s secure endpoint.');
      return {url:target.href,options:{redirect:'error'},access:{tier:'free'}};
    }
    const secret=key,attempt=generation;
    const access=await identity(secret);
    if(attempt!==generation)throw new Error('Account changed. Please start the scan again.');
    target.searchParams.set('include',access.tier==='pro'?'text,inputs,coaching,evidence':'text');
    return {url:target.href,options:{headers:secret?{Authorization:'Bearer '+secret}:{},credentials:'same-origin',redirect:'error',cache:'no-store'},access};
  }
  global.VahiniAccount={connect,request,disconnect,hasKey(){return !!key;}};
  function mount(){
    const form=global.document.getElementById('account-access');if(!form)return;
    const input=form.querySelector('input'),status=form.querySelector('[role="status"]');
    form.addEventListener('submit',async event=>{
      event.preventDefault();const secret=input.value;input.value='';status.textContent='Checking access…';
      try{const access=await connect(secret);status.textContent=access.tier==='pro'?'Pro connected. Your next scan includes all 20 factors and detailed feedback.':'Free account connected. Your next scan includes five factors.';}
      catch(error){status.textContent=error.message;}
    });
    form.querySelector('[data-disconnect]').addEventListener('click',()=>{disconnect();input.value='';status.textContent='Disconnected. New scans use your server session or Free access.';});
  }
  if(global.document){if(global.document.readyState==='loading')global.document.addEventListener('DOMContentLoaded',mount);else mount();}
})(window);

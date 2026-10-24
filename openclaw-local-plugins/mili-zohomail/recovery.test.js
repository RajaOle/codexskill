import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {ZohoMailbox,fetchJSON,makeMailTools,readPrivate,savePrivate} from './index.js';

const credential={region:'com',mailbox:'owner@example.com',clientId:'fixture',clientSecret:'fixture-secret',refreshToken:'fixture-refresh'};
const original={request_id:'fixture-send-001',to:['buyer@example.com'],cc:['copy@example.com'],subject:'Sample request',content:'Hello\nSample please.',approved:true};
const response=data=>new Response(JSON.stringify({status:{code:200},data}),{status:200});
async function fixture(fn) {
  const root=await mkdtemp(path.join(os.tmpdir(),'mili-mail-recovery-'));
  const calls=[],state={fail:true};
  const fetcher=async(url,options)=>{
    const route=new URL(url).pathname;calls.push({route,method:options.method||'GET'});
    if(route==='/oauth/v2/token')return new Response(JSON.stringify({access_token:'fixture-access',expires_in:3600}));
    if(route==='/api/accounts')return response([{type:'ZOHO_ACCOUNT',primaryEmailAddress:credential.mailbox,accountId:'123'}]);
    if(route.endsWith('/messages')&&options.method==='POST') {
      if(state.fail)throw Object.assign(new Error('private url token fixture-secret'),{cause:{code:'UND_ERR_HEADERS_TIMEOUT'}});
      return response({messageId:'999'});
    }
    if(route.endsWith('/folders'))return response([{folderId:'222',folderType:'Sent',path:'/Sent'}]);
    if(route.endsWith('/details'))return response({...state.details});
    if(route.endsWith('/content'))return response({content:state.content??original.content});
    throw new Error('Unexpected fixture route');
  };
  const mailbox=new ZohoMailbox({root,fetcher,load:()=>credential});
  try {
    await assert.rejects(mailbox.run('send',original),/uncertain/);
    state.details={messageId:'999',fromAddress:credential.mailbox,toAddress:original.to.join(','),ccAddress:original.cc.join(','),subject:original.subject,sentDateInGMT:String(Date.now()),hasAttachment:'0'};
    await fn({root,calls,state,fetcher,mailbox});
  } finally {await rm(root,{recursive:true,force:true});}
}
const proof={...original,folder_id:'222',message_id:'999'};

test('network codes and stages are safe; compose waits 60 seconds without retries',async()=>{
  let calls=0;
  await assert.rejects(fetchJSON(async(_url,options)=>{
    calls++;assert.equal(options.redirect,'error');assert(options.signal);
    throw Object.assign(new Error('https://private.example/token fixture-secret'),{cause:{code:'ENOTFOUND'}});
  },'https://mail.zoho.com/api/accounts/123/messages',{method:'POST'}),error=>
    error.stage==='compose'&&error.networkCode==='ENOTFOUND'&&error.timeoutMs===60000&&
    error.elapsedMs>=0&&!error.message.includes('fixture-secret')&&!error.message.includes('private.example'));
  assert.equal(calls,1);
  await assert.rejects(fetchJSON(async()=>{throw Object.assign(new Error('secret'),{name:'TimeoutError'});},
    'https://accounts.zoho.com/oauth/v2/token',{method:'POST'}),error=>
    error.stage==='oauth'&&error.timeoutMs===30000&&error.networkCode==='TIMEOUT'&&/not submitted/.test(error.message));
});

test('response-body network failures carry diagnostics without losing uncertainty',async()=>{
  await assert.rejects(fetchJSON(async()=>({text:async()=>{throw Object.assign(new Error('private-body'),{code:'ECONNRESET'});}}),
    'https://mail.zoho.com/api/accounts/123/messages',{method:'POST'}),error=>error.networkCode==='ECONNRESET'&&!error.message.includes('private-body'));
});

test('operation inspection never submits, resets, or claims absence',()=>fixture(async f=>{
  const before=f.calls.length,result=await f.mailbox.run('reconcile',{request_id:original.request_id});
  assert.equal(result.status,'uncertain');assert.equal(result.resend_allowed,false);
  assert.equal(f.calls.length,before);
  assert.equal(readPrivate(path.join(f.root,'operations.json'))[original.request_id].status,'uncertain');
}));

test('positive Sent evidence closes old uncertainty and retries return existing receipt',()=>fixture(async f=>{
  const before=f.calls.filter(c=>c.method==='POST').length;
  const result=await f.mailbox.run('reconcile',proof);
  assert.equal(result.status,'sent');assert.equal(result.reconciled,true);assert.equal(result.delivery_confirmed,false);
  assert.equal((await f.mailbox.run('send',original)).data.messageId,'999');
  assert.equal(f.calls.filter(c=>c.method==='POST').length,before);
  const fresh=new ZohoMailbox({root:f.root,fetcher:f.fetcher,load:()=>credential});
  assert.equal((await fresh.run('reconcile',{request_id:original.request_id})).reconciled,true);
}));

test('wrong body, recipients, subject, time, attachments, BCC and missing IDs never clear uncertainty',()=>fixture(async f=>{
  const correct={...f.state.details};
  for(const patch of [{toAddress:'other@example.com'},{ccAddress:''},{fromAddress:'other@example.com'},
    {subject:'Different'},{sentDateInGMT:String(Date.now()-3600000)},
    {hasAttachment:'1'},{bccAddress:'hidden@example.com'},{messageId:undefined}]) {
    f.state.details={...correct,...patch};
    assert.equal((await f.mailbox.run('reconcile',proof)).status,'uncertain');
  }
  f.state.details=correct;f.state.content='Different content';
  assert.equal((await f.mailbox.run('reconcile',proof)).status,'uncertain');
  f.state.content='<div>Hello</div>';
  assert.equal((await f.mailbox.run('reconcile',proof)).status,'uncertain');
  await assert.rejects(f.mailbox.run('reconcile',{...proof,content:'Changed original'}),/fingerprint/);
  await assert.rejects(f.mailbox.run('reconcile',{...proof,folder_id:'111'}),/system Sent/);
  assert.equal(readPrivate(path.join(f.root,'operations.json'))[original.request_id].status,'uncertain');
}));

test('fresh request IDs cannot bypass an uncertain send',()=>fixture(async f=>{
  await assert.rejects(f.mailbox.run('send',{...original,request_id:'fixture-bypass-001'}),/another request_id/);
  assert.equal(f.calls.filter(c=>c.route.endsWith('/messages')&&c.method==='POST').length,1);
}));

test('reconciliation tool requires trusted current user and returns structured failures',()=>fixture(async f=>{
  const context={agentId:'mili',sessionKey:'agent:mili:fixture',requesterSenderId:'trusted'};
  const tool=makeMailTools(context,f.mailbox,['trusted']).find(t=>t.name==='mili_mail_reconcile');
  const result=await tool.execute('fixture',{...proof,content:'Wrong original'});
  assert.equal(result.isError,true);assert.equal(JSON.parse(result.content[0].text).resend_allowed,false);
  const denied=makeMailTools({...context,requesterSenderId:'untrusted'},f.mailbox,['trusted']).find(t=>t.name==='mili_mail_reconcile');
  await assert.rejects(denied.execute('fixture',proof),/trusted current sender/);
}));

test('send errors report stage and safe network code without raw exceptions',()=>fixture(async f=>{
  const tool=makeMailTools({agentId:'mili',sessionKey:'agent:mili:fixture',requesterSenderId:'trusted'},f.mailbox,['trusted']).find(t=>t.name==='mili_mail_send');
  const result=await tool.execute('fixture',original),data=JSON.parse(result.content[0].text);
  assert.equal(result.isError,true);assert.equal(data.code,'MAIL_OUTCOME_UNCERTAIN');
  assert.equal(data.resend_allowed,false);assert(!result.content[0].text.includes('fixture-secret'));
}));

test('shared mailbox caches OAuth across independent tool contexts',()=>fixture(async f=>{
  const context={agentId:'mili',sessionKey:'agent:mili:fixture',requesterSenderId:'trusted'};
  // Exercise separate contexts with same explicit mailbox, matching registration.
  const a=makeMailTools(context,f.mailbox,['trusted']),b=makeMailTools(context,f.mailbox,['trusted']);
  await a.find(t=>t.name==='mili_mail_status').execute('one',{});
  await b.find(t=>t.name==='mili_mail_status').execute('two',{});
  assert.equal(f.calls.filter(c=>c.route==='/oauth/v2/token').length,1);
}));

test('persisting another task does not erase an uncertain legacy operation',()=>fixture(async f=>{
  f.state.fail=false;
  await f.mailbox.run('draft',{...original,request_id:'fixture-draft-001'});
  const ledger=readPrivate(path.join(f.root,'operations.json'));
  assert.equal(ledger[original.request_id].status,'uncertain');assert.equal(ledger['fixture-draft-001'].status,'done');
}));

test('unverifiable attachment fingerprint cannot be reconciled as plaintext',()=>fixture(async f=>{
  const file=path.join(f.root,'operations.json'),ledger=readPrivate(file);
  ledger[original.request_id].digest='attachment-specific-fingerprint';savePrivate(file,ledger);
  await assert.rejects(f.mailbox.run('reconcile',proof),/attachments/);
}));

test('uncertain retry stops before a failing OAuth refresh',()=>fixture(async f=>{
  f.mailbox.auth=null;
  const count=f.calls.length;
  f.mailbox.fetcher=async()=>{throw new Error('must never authenticate');};
  await assert.rejects(f.mailbox.run('send',original),error=>error.code==='MAIL_OUTCOME_UNCERTAIN');
  assert.equal(f.calls.length,count);
}));

test('concurrent distinct operations preserve both ledger records',()=>fixture(async f=>{
  const second=new ZohoMailbox({root:f.root,fetcher:f.fetcher,load:()=>credential});
  let release;
  const wait=new Promise(resolve=>{release=resolve;});
  const first=f.mailbox.once('concurrent-task-001',{name:'draft',body:{}},async mark=>{mark();await wait;return {status:'draft_saved'};});
  await second.once('concurrent-task-002',{name:'draft',body:{}},async mark=>{mark();return {status:'draft_saved'};});
  release();await first;
  const ledger=readPrivate(path.join(f.root,'operations.json'));
  assert.equal(ledger['concurrent-task-001'].status,'done');
  assert.equal(ledger['concurrent-task-002'].status,'done');
  assert.equal(ledger[original.request_id].status,'uncertain');
}));

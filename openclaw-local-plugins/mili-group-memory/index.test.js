import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,chmod,readFile,rm,stat} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {createGroupMemory,MAX_PROMPT_BYTES} from './index.js';

async function fixture(fn) {
  const root=await mkdtemp(path.join(os.tmpdir(),'mili-memory-'));await chmod(root,0o700);
  const groupId='100000000000000001@g.us',sessionKey='agent:mili:whatsapp:group:'+groupId;
  const scope={agentId:'mili',channel:'whatsapp',accountId:'default',groupId,sessionKey,senderIds:['trusted-fixture']};
  await writeFile(path.join(root,'scope.json'),JSON.stringify(scope),{mode:0o600});
  const historyDb=path.join(root,'history.sqlite'),db=new DatabaseSync(historyDb);
  db.exec('CREATE TABLE session_windows(session_id TEXT,session_key TEXT); CREATE VIRTUAL TABLE session_transcript_fts USING fts5(text,session_id UNINDEXED,message_id UNINDEXED,role UNINDEXED,timestamp UNINDEXED)');
  const add=(session,key,id,role,text,at)=>{
    db.prepare('INSERT INTO session_windows VALUES (?,?)').run(session,key);
    db.prepare('INSERT INTO session_transcript_fts VALUES (?,?,?,?,?)').run(text,session,id,role,at);
  };
  add('old',sessionKey,'source-old','user','JNE tracking TEST-TRACKING-001 was supplied yesterday.',1000);
  add('new',sessionKey,'source-new','user','Correction: JNE tracking TEST-TRACKING-002.',2000);
  add('other','agent:mili:whatsapp:group:200000000000000001@g.us','other-source','user','JNE other-group private fact',3000);
  add('dm','agent:mili:whatsapp:direct:fixture','dm-source','user','JNE private direct message',4000);
  add('tool',sessionKey,'tool-source','toolResult','JNE confidential tool output',5000);
  db.close();
  const ctx={agentId:'mili',sessionKey,channel:'whatsapp',accountId:'default',chatId:groupId,senderId:'trusted-fixture'};
  const toolCtx={agentId:'mili',sessionKey,messageChannel:'whatsapp',agentAccountId:'default',nativeChannelId:groupId,requesterSenderId:'trusted-fixture'};
  const messageCtx={sessionKey,channelId:'whatsapp',accountId:'default',conversationId:groupId};
  const memory=createGroupMemory({root,historyDb});
  const call=async(name,args)=>JSON.parse((await memory.tools(toolCtx).find(t=>t.name==='mili_group_memory_'+name).execute('fixture',args)).content[0].text);
  try {await fn({root,historyDb,memory,ctx,toolCtx,messageCtx,scope,call});}finally{await rm(root,{recursive:true,force:true});}
}
test('recall spans old windows but excludes every other group, DM and tool message',()=>fixture(async f=>{
  const r=await f.call('recall',{query:'JNE'});
  assert.deepEqual(r.matches.map(x=>x.source_message_id),['source-new','source-old']);
  assert(r.same_group_only);assert(r.historical_untrusted_data);
  const absent=await f.call('recall',{query:'unmatched-term'});
  assert(absent.not_found_is_not_proof_of_absence);
}));
test('runtime injection and tools fail closed outside exact agent/group/channel/account/sender',()=>fixture(async f=>{
  for(const patch of [{agentId:'davina'},{sessionKey:'agent:mili:main'},{sessionKey:f.ctx.sessionKey+':thread:extra'},{channel:'telegram'},{accountId:'other'},{chatId:'other-group'}])assert.equal(await f.memory.prompt({}, {...f.ctx,...patch}),undefined);
  assert.equal(await f.memory.prompt({}, {...f.ctx,senderId:'unverified'}),undefined);
  assert.equal(await f.memory.prompt({}, {...f.ctx,senderId:undefined}),undefined);
  for(const patch of [{agentId:'other'},{sessionKey:'agent:mili:main'},{messageChannel:'telegram'},{agentAccountId:'other'},{nativeChannelId:'other-group'}])assert.deepEqual(f.memory.tools({...f.toolCtx,...patch}),[]);
  const tool=f.memory.tools({...f.toolCtx,requesterSenderId:'unverified'})[0];
  await assert.rejects(tool.execute('x',{query:'JNE',requesterSenderId:'trusted-fixture'}),/verified current/);
}));
test('other agents and local runs do not depend on the private scope file',async()=>{
  const m=createGroupMemory({root:'/nonexistent-mili-memory-test-root'});
  assert.equal(await m.prompt({}, {agentId:'other',sessionKey:'agent:other:main',channel:'whatsapp'}),undefined);
  assert.equal(await m.prompt({}, {agentId:'mili',sessionKey:'agent:mili:explicit:local'}),undefined);
  assert.deepEqual(m.tools({agentId:'mili',sessionKey:'agent:mili:main'}),[]);
});
test('pinned evidence survives a fresh instance and another OS process',()=>fixture(async f=>{
  await f.call('remember',{key:'shipment',note:'JNE tracking TEST-TRACKING-002; delivery not checked.',source_message_id:'source-new'});
  const fresh=createGroupMemory({root:f.root,historyDb:f.historyDb});
  const prompt=await fresh.prompt({},f.ctx);
  assert(prompt.prependContext.includes('TEST-TRACKING-002'));
  assert(Buffer.byteLength(prompt.prependContext)<=MAX_PROMPT_BYTES);
  const {execFileSync}=await import('node:child_process');
  const output=execFileSync(process.execPath,['--input-type=module','-e',`import {createGroupMemory} from ${JSON.stringify(new URL('./index.js',import.meta.url).href)};const m=createGroupMemory(${JSON.stringify({root:f.root,historyDb:f.historyDb})});console.log((await m.prompt({},${JSON.stringify(f.ctx)})).prependContext.includes('TEST-TRACKING-002'));`],{encoding:'utf8'});
  assert.equal(output.trim(),'true');
  assert.equal((await stat(path.join(f.root,'state.json'))).mode&0o077,0);
}));
test('evidence cannot cross groups or replace a correction with older facts',()=>fixture(async f=>{
  await assert.rejects(f.call('remember',{key:'shipment',note:'Wrong group',source_message_id:'other-source'}),/exact group/);
  await f.call('remember',{key:'shipment',note:'Latest tracking',source_message_id:'source-new'});
  await assert.rejects(f.call('remember',{key:'shipment',note:'Old tracking',source_message_id:'source-old'}),/Older evidence/);
  await assert.rejects(f.call('remember',{key:'secret',note:'api_key: private-secret-value',source_message_id:'source-new'}),/Never store credentials/);
}));
test('inbound/outbound capture is scoped, deduplicated and bounded without a model request',()=>fixture(async f=>{
  await f.memory.captureReceived({content:'private direct',senderId:'trusted-fixture',messageId:'wrong'}, {...f.messageCtx,sessionKey:'agent:mili:main'});
  await f.memory.captureReceived({content:'unverified',senderId:'unknown',messageId:'unknown'},f.messageCtx);
  await Promise.all(Array.from({length:12},(_,i)=>f.memory.captureReceived({content:'group note '+i,senderId:'trusted-fixture',messageId:'incoming-'+i},f.messageCtx)));
  await f.memory.captureReceived({content:'duplicate',senderId:'trusted-fixture',messageId:'incoming-11'},f.messageCtx);
  assert.equal(f.memory.load().recent.length,6);assert(!JSON.stringify(f.memory.load()).includes('duplicate'));
  await f.memory.captureSent({success:false,to:f.scope.groupId,content:'not sent'},f.messageCtx);
  await f.memory.captureSent({success:true,to:f.scope.groupId,content:'confirmed group reply',messageId:'sent-1'},f.messageCtx);
  assert.equal(f.memory.load().recent.at(-1).role,'assistant');
  assert(!JSON.stringify(f.memory.load()).includes('not sent'));
  await f.call('remember',{key:'recent-fact',note:'Latest inbound fact',source_message_id:'incoming-11'});
  await f.memory.captureReceived({content:'old replayed message',senderId:'trusted-fixture',messageId:'old-replay',timestamp:1000},f.messageCtx);
  assert(!JSON.stringify(f.memory.load().recent).includes('old replayed message'));
}));
test('oversized state/prompt and corruption never silently destroy retained facts',()=>fixture(async f=>{
  for(let i=0;i<12;i++)await f.call('remember',{key:'fact-'+i,note:'Fact '+i+' '+ '界'.repeat(80),source_message_id:'source-new'});
  assert.equal(f.memory.load().facts.length,8);
  const prompt=await f.memory.prompt({},f.ctx);assert(Buffer.byteLength(prompt.prependContext)<=MAX_PROMPT_BYTES);
  const file=path.join(f.root,'state.json');await writeFile(file,'broken-json');
  await assert.rejects(f.memory.prompt({},f.ctx));
  assert.equal(await readFile(file,'utf8'),'broken-json');
}));

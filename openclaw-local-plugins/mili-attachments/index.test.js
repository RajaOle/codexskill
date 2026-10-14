import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,mkdir,rm,symlink} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import plugin,{captureMedia,makeTools,extractText} from './index.js';

test('trusted media is copied into the workspace and isolated by conversation',async()=>{
  const temp=await mkdtemp(path.join(os.tmpdir(),'mili-media-test-'));
  try {
    const cfg={workspace:path.join(temp,'workspace'),inbound:path.join(temp,'inbound'),state:path.join(temp,'state')};
    await mkdir(cfg.workspace);await mkdir(cfg.inbound);
    const file=path.join(cfg.inbound,'quote.txt');await writeFile(file,'Vanilla quote IDR 1500000 per kg');
    const ctx={channelId:'whatsapp',sessionKey:'agent:mili:whatsapp:group:owned',agentId:'mili'};
    await captureMedia({messageId:'owned-message',media:[{path:file}]},ctx,cfg);
    const tools=makeTools(ctx,cfg),list=JSON.parse((await tools[0].execute()).content[0].text);
    assert.equal(list.attachments.length,1);assert.ok(list.attachments[0].path.startsWith(cfg.workspace));
    const result=JSON.parse((await tools[1].execute('call',{attachment_id:list.attachments[0].id})).content[0].text);
    assert.match(result.text,/1500000/);
    const other=makeTools({...ctx,sessionKey:'agent:mili:whatsapp:group:other'},cfg);
    assert.equal(JSON.parse((await other[0].execute()).content[0].text).attachments.length,0);
    await assert.rejects(other[1].execute('call',{attachment_id:list.attachments[0].id}),/not in this conversation/);
    assert.deepEqual(makeTools({...ctx,agentId:'main'},cfg),[]);
    const outside=path.join(temp,'private.txt');await writeFile(outside,'private');
    const link=path.join(cfg.inbound,'symlink.txt');await symlink(outside,link);
    await assert.rejects(captureMedia({media:[{path:link}]},ctx,cfg),/outside approved/);
  } finally {await rm(temp,{recursive:true,force:true});}
});
test('missing-media guesses and file URLs are blocked without sending',()=>{
  const hooks={},tools=[];
  plugin.register({registerTool:(...a)=>tools.push(a),on:(n,f)=>{hooks[n]=f;},logger:{warn:()=>{}}});
  for(const [name,params] of [['read',{path:'media/guessed.pdf'}],['read',{path:'media/*.pdf'}],['web_fetch',{url:'file:///media/'}],['gdrive__list_files',{query:"mimeType = 'application/pdf'"}]]) assert.equal(hooks.before_tool_call({toolName:name,params},{agentId:'mili'}).block,true);
  assert.equal(hooks.before_tool_call({toolName:'read',params:{path:'AGENTS.md'}},{agentId:'mili'}),undefined);
  assert.equal(hooks.before_tool_call({toolName:'read',params:{path:'media/test.pdf'}},{agentId:'main'}),undefined);
  assert.equal(tools.length,1);
});
test('raw Sheet mutations blocked for Mili; safe creation/record tools allowed',()=>{
  const hooks={};plugin.register({registerTool:()=>{},on:(n,f)=>{hooks[n]=f;},logger:{warn:()=>{}}});
  for(const name of ['gdrive__write_sheet','gdrive__batch_update_sheet','gdrive__clear_sheet_range','gdrive__duplicate_sheet'])assert.equal(hooks.before_tool_call({toolName:name,params:{}},{agentId:'mili'}).block,true);
  for(const name of ['gdrive__initialize_table','gdrive__inspect_table','gdrive__write_table_records','gdrive__read_document'])assert.equal(hooks.before_tool_call({toolName:name,params:{}},{agentId:'mili'}),undefined);
  assert.equal(hooks.before_tool_call({toolName:'gdrive__list_files',params:{query:"modifiedTime > '2026-10-12T00:00:00'"}},{agentId:'mili'}).block,true);
});
test('binary create_file cannot upload a path string; original byte tool remains allowed',()=>{
  const hooks={};plugin.register({registerTool:()=>{},on:(n,f)=>{hooks[n]=f;},logger:{warn:()=>{}}});
  assert.equal(hooks.before_tool_call({toolName:'gdrive__create_file',params:{mimeType:'image/jpeg',content:'/home/user/flyer.jpg'}},{agentId:'mili'}).block,true);
  assert.equal(hooks.before_tool_call({toolName:'gdrive__create_file',params:{mimeType:'text/plain',content:'real notes'}},{agentId:'mili'}),undefined);
  assert.equal(hooks.before_tool_call({toolName:'mili_drive_upload',params:{}},{agentId:'mili'}),undefined);
});
test('trusted arbitrary binary attachments are cataloged even without OCR support',async()=>{
  const temp=await mkdtemp(path.join(os.tmpdir(),'mili-any-file-test-'));
  try {
    const cfg={workspace:path.join(temp,'workspace'),inbound:path.join(temp,'inbound'),state:path.join(temp,'state')};
    await mkdir(cfg.workspace);await mkdir(cfg.inbound);
    const file=path.join(cfg.inbound,'package.custom');await writeFile(file,Buffer.from([0,255,1,2]));
    const ctx={channelId:'whatsapp',sessionKey:'agent:mili:whatsapp:group:owned',agentId:'mili'};
    await captureMedia({media:[{path:file}]},ctx,cfg);
    const list=JSON.parse((await makeTools(ctx,cfg)[0].execute()).content[0].text);
    assert.equal(list.attachments[0].name,'package.custom');
  } finally {await rm(temp,{recursive:true,force:true});}
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm,symlink} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {resolveFile,fileResult,DriveFiles,makeFileTools,MAX_FILE_BYTES} from './files.js';

const ctx={agentId:'mili',sessionKey:'agent:mili:whatsapp:group:owned',requesterSenderId:'trusted'};
async function fixture(fn) {
  const root=await mkdtemp(path.join(os.tmpdir(),'mili-files-test-'));
  const workspace=path.join(root,'workspace'),catalog=path.join(root,'catalog');
  try {
    await mkdir(path.join(workspace,'attachments/inbound'),{recursive:true});await mkdir(catalog);
    const bytes=Buffer.from([255,216,255,0,12,23]);
    const file=path.join(workspace,'attachments/inbound/photo.jpg');await writeFile(file,bytes);
    await writeFile(path.join(catalog,'index.json'),JSON.stringify({entries:[{id:'local-photo',sessionKey:ctx.sessionKey,path:file,name:'photo.jpg'}]}));
    await fn({root,workspace,catalog,bytes});
  } finally {await rm(root,{recursive:true,force:true});}
}
test('original catalog bytes survive and wrong-conversation IDs fail',()=>fixture(async f=>{
  const file=await resolveFile({attachment_id:'local-photo',name:'flyer.jpg'},ctx,f);
  assert.deepEqual(file.bytes,f.bytes);assert.equal(file.name,'flyer.jpg');assert.equal(file.mimeType,'image/jpeg');
  await assert.rejects(resolveFile({attachment_id:'local-photo'},{...ctx,sessionKey:'agent:mili:other'},f),/conversation/);
}));
test('workspace binaries work; traversal, symlinks, memory, control files and raw inbound paths fail',()=>fixture(async f=>{
  await mkdir(path.join(f.workspace,'outputs'));await writeFile(path.join(f.workspace,'outputs/report.pdf'),Buffer.from('%PDF-1.4 example'));
  assert.equal((await resolveFile({workspace_path:'outputs/report.pdf'},ctx,f)).name,'report.pdf');
  await mkdir(path.join(f.workspace,'records/attachments'),{recursive:true});await writeFile(path.join(f.workspace,'records/attachments/offer.zip'),Buffer.from([0,255]));
  assert.equal((await resolveFile({workspace_path:'records/attachments/offer.zip'},ctx,f)).name,'offer.zip');
  const external=path.join(f.root,'secret.pdf');await writeFile(external,'secret');await symlink(external,path.join(f.workspace,'outputs/link.pdf'));
  for(const workspace_path of ['../secret.pdf','outputs/link.pdf','USER.md','memory/log.md','attachments/inbound/photo.jpg','.env'])await assert.rejects(resolveFile({workspace_path},ctx,f));
  await assert.rejects(resolveFile({attachment_id:'local-photo',workspace_path:'outputs/report.pdf'},ctx,f),/exactly one/);
}));
test('oversize sources, unsafe filenames and disguised local-path uploads fail',()=>{
  assert.throws(()=>fileResult('../leak.pdf',Buffer.from('x')),/filename/);
  assert.throws(()=>fileResult('file.jpg',Buffer.from('/home/user/file.jpg')),/local path/);
  assert.throws(()=>fileResult('file.zip',Buffer.alloc(MAX_FILE_BYTES+1)),/20 MiB/);
  assert.equal(fileResult('data.custom',Buffer.from([0,1])).mimeType,'application/octet-stream');
});
test('Drive upload preserves bytes/sharing and verifies checksum; retries/concurrent calls deduplicate',async()=>{
  const file=fileResult('flyer.jpg',Buffer.from([255,216,255,1]));let created,creates=0;
  const drive={files:{
    get:async args=>({data:args.fileId==='folder123'?{id:args.fileId,mimeType:'application/vnd.google-apps.folder',capabilities:{canAddChildren:true}}:{id:'uploaded123',name:file.name,mimeType:file.mimeType,parents:['folder123'],size:String(file.size),md5Checksum:file.md5}}),
    list:async()=>({data:{files:created?[{id:'uploaded123'}]:[]}}),
    create:async args=>{creates++;created=args;const chunks=[];for await(const c of args.media.body)chunks.push(c);assert.deepEqual(Buffer.concat(chunks),file.bytes);assert.equal(args.requestBody.permissions,undefined);return {data:{id:'uploaded123'}};}
  }};
  const adapter=new DriveFiles(drive);const [a,b]=await Promise.all([adapter.upload(file,'folder123'),adapter.upload(file,'folder123')]);
  assert.equal(creates,1);assert.equal(a.status,'verified');assert.equal(b.status,'already_uploaded');assert.equal(a.sha256,file.sha256);
  drive.files.get=async()=>({data:{id:'uploaded123',mimeType:'application/vnd.google-apps.folder',capabilities:{canAddChildren:false}}});
  await assert.rejects(adapter.upload(file,'folder123'),/not writable/);
});
test('Drive checksum mismatch and ambiguous upload receipts never report success',async()=>{
  const file=fileResult('x.pdf',Buffer.from('%PDF-example'));
  const drive={files:{get:async a=>({data:a.fileId==='folder123'?{mimeType:'application/vnd.google-apps.folder'}:{name:file.name,mimeType:file.mimeType,parents:['folder123'],size:file.size,md5Checksum:'wrong'}}),list:async()=>({data:{files:[{id:'upload123'}]}})}};
  const adapter=new DriveFiles(drive);await assert.rejects(adapter.upload(file,'folder123'),/verification/);
  drive.files.list=async()=>({data:{files:[{id:'a'},{id:'b'}]}});await assert.rejects(adapter.upload(file,'folder123'),/Duplicate/);
});
test('Drive files download directly and Google documents export to a real PDF',async()=>{
  const drive={files:{get:async args=>({data:args.alt==='media'?Buffer.from([0,255]):{name:'Document',mimeType:args.fileId==='native123'?'application/vnd.google-apps.document':'application/zip',size:'2'}}),export:async args=>{assert.equal(args.mimeType,'application/pdf');return {data:Buffer.from('%PDF-example')};}}};
  const adapter=new DriveFiles(drive);
  assert.deepEqual((await adapter.download({drive_file_id:'ordinary123'})).bytes,Buffer.from([0,255]));
  const pdf=await adapter.download({drive_file_id:'native123'});assert.equal(pdf.name,'Document.pdf');assert.equal(pdf.mimeType,'application/pdf');
});
test('transport tool enforces trusted runtime sender, even when params claim authorization',()=>fixture(async f=>{
  let uploads=0;const drive={upload:async()=>{uploads++;return {status:'verified'};}};
  const options={...f,drive,allowedSenders:['trusted']};
  assert.deepEqual(makeFileTools({...ctx,agentId:'main'},options),[]);
  const denied=makeFileTools({...ctx,requesterSenderId:'wrong'},options)[0];
  await assert.rejects(denied.execute('call',{source:{attachment_id:'local-photo'},folder_id:'folder123',senderId:'trusted'}),/verified current/);assert.equal(uploads,0);
  await makeFileTools(ctx,options)[0].execute('call',{source:{attachment_id:'local-photo'},folder_id:'folder123'});assert.equal(uploads,1);
}));

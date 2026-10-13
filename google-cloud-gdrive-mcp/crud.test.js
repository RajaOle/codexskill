import test from 'node:test';
import assert from 'node:assert/strict';
import { handleCrudTool, crudTools } from './crud.js';

function mockClients() {
  const calls = [];
  const method = path => async (...args) => {
    calls.push({ path, args });
    return { data: path === 'drive.files.get' ? { id: 'file', mimeType: 'text/plain', parents: ['old'] } : { ok: true } };
  };
  return { calls, drive: { files: Object.fromEntries(['create','get','update','delete','export'].map(k => [k, method('drive.files.'+k)])) },
    sheets: { spreadsheets: { get: method('sheets.get'), create: method('sheets.create'), batchUpdate: method('sheets.batchUpdate'), values: { clear: method('sheets.clear') } } } };
}

test('all advertised CRUD tools dispatch to intended Google methods', async () => {
  const cases = [
    ['sheet_metadata', {fileId:'f'}, 'sheets.get'],
    ['create_file', {name:'draft',content:'private'}, 'drive.files.create'],
    ['read_file', {fileId:'f'}, 'drive.files.get'],
    ['read_document', {fileId:'f'}, 'drive.files.get'],
    ['update_file', {fileId:'f',name:'renamed',folderId:'new'}, 'drive.files.update'],
    ['delete_file', {fileId:'f'}, 'drive.files.update'],
    ['create_spreadsheet', {title:'draft',tabs:['CRM']}, 'sheets.create'],
    ['batch_update_sheet', {fileId:'f',requests:[{deleteDimension:{range:{sheetId:1,dimension:'ROWS',startIndex:1,endIndex:2}}}]}, 'sheets.batchUpdate'],
    ['clear_sheet_range', {fileId:'f',range:'CRM!A2:B2'}, 'sheets.clear']
  ];
  assert.equal(cases.length, crudTools.length);
  for (const [name,args,expected] of cases) {
    const clients=mockClients();
    if(name==='read_document')clients.drive.files.get=async args=>{clients.calls.push({path:'drive.files.get',args:[args]});return {data:args.alt==='media'?Buffer.from('Readable text document'):{id:'file',mimeType:'text/plain'}};};
    const res=await handleCrudTool(name,args,clients);
    assert.equal(res.content[0].type,'text');
    assert.equal(clients.calls.at(-1).path,expected);
    if (name==='create_file') {
      assert.equal(clients.calls[0].args[0].requestBody.permissions,undefined);
      let content=''; for await (const chunk of clients.calls[0].args[0].media.body) content+=chunk;
      assert.equal(content,'private');
    }
    if (name==='update_file') assert.equal(clients.calls.at(-1).args[0].removeParents,'old');
    if (name==='delete_file') assert.deepEqual(clients.calls[0].args[0].requestBody,{trashed:true});
  }
});

test('permanent deletion requires explicit boolean; Google failures propagate to MCP wrapper',async()=>{
  const clients=mockClients();
  await handleCrudTool('delete_file',{fileId:'f',permanent:true},clients);
  assert.equal(clients.calls[0].path,'drive.files.delete');
  await assert.rejects(handleCrudTool('update_file',{fileId:'f'},clients),/Provide/);
  await assert.rejects(handleCrudTool('clear_sheet_range',{fileId:'f'},clients),/Missing/);
  await assert.rejects(handleCrudTool('batch_update_sheet',{fileId:'f',requests:[]},clients),/nonempty/);
  clients.drive.files.create=async()=>{throw new Error('permission denied')};
  await assert.rejects(handleCrudTool('create_file',{name:'draft'},clients),/permission denied/);
});

test('reads preserve binary data and export native Docs',async()=>{
  const clients=mockClients();
  clients.drive.files.get=async args=>({data:args.alt==='media'?Buffer.from([0,255]):{mimeType:'application/pdf'}});
  const binary=JSON.parse((await handleCrudTool('read_file',{fileId:'f',content:true},clients)).content[0].text);
  assert.equal(binary.encoding,'base64'); assert.equal(binary.content,'AP8=');
  clients.drive.files.get=async()=>({data:{mimeType:'application/vnd.google-apps.document'}});
  clients.drive.files.export=async args=>{assert.equal(args.mimeType,'text/plain');return {data:Buffer.from('document')}};
  const doc=JSON.parse((await handleCrudTool('read_file',{fileId:'f',content:true},clients)).content[0].text);
  assert.equal(doc.content,'document'); assert.equal(doc.encoding,'utf8');
});

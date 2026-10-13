import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {TableGuard} from './table-tools.js';
import {TRACKER_ID,TEMPLATE_ID} from './tracker-guard.js';
import {IBNU_ID} from './expense-guard.js';

async function fixture(fn,rows=[['Bank ID','Bank Name','Email','Phone/WhatsApp','Minimum Facility USD']]) {
  const temp=await mkdtemp(path.join(os.tmpdir(),'table-guard-test-'));
  const tabs=[{properties:{title:'13 Bank Partner',sheetId:13,gridProperties:{rowCount:1000,columnCount:26}},rows:structuredClone(rows)}];
  let writes=0,corrupt=false;
  const spreadsheets={
    get:async args=>({data:{sheets:structuredClone(tabs.map(t=>({properties:t.properties})))}}),
    values:{
      get:async args=>{const title=/^'((?:[^']|'')*)'/.exec(args.range)[1].replaceAll("''","'");return {data:{values:structuredClone(tabs.find(t=>t.properties.title===title).rows)}};},
      batchUpdate:async args=>{writes++;for(const entry of args.requestBody.data){const match=/^'((?:[^']|'')*)'!([A-Z]+)(\d+):/.exec(entry.range);const tab=tabs.find(t=>t.properties.title===match[1]);let col=0;for(const ch of match[2])col=col*26+ch.charCodeAt(0)-64;const row=Number(match[3])-1;tab.rows[row]??=[];tab.rows[row][col-1]=entry.values[0][0];}if(corrupt)tabs[0].rows[0][0]='CHANGED';},
    },
    batchUpdate:async args=>{writes++;for(const req of args.requestBody.requests){if(req.addSheet)tabs.push({properties:req.addSheet.properties,rows:[]});if(req.updateCells){const t=tabs.find(t=>t.properties.sheetId===req.updateCells.start.sheetId);t.rows=req.updateCells.rows.map(r=>r.values.map(c=>c.userEnteredValue.stringValue));}}return {data:{}};},
  };
  const guard=new TableGuard(path.join(temp,'state.json'));
  const args={fileId:TRACKER_ID,sheetName:'13 Bank Partner',keyColumn:'Bank ID',mode:'upsert',records:[{'Bank ID':'BANK-001','Bank Name':'Example Bank',Email:'hello@example.com','Phone/WhatsApp':'+6212345678'}]};
  try{await fn({guard,tabs,sheets:{spreadsheets},args,writes:()=>writes,setCorrupt:()=>{corrupt=true;},statePath:path.join(temp,'state.json')});}finally{await rm(temp,{recursive:true,force:true});}
}
test('bank tab works immediately; fields map to headers and retries are idempotent across restart',()=>fixture(async f=>{
  await f.guard.handle('write_table_records',f.args,f.sheets);
  assert.deepEqual(f.tabs[0].rows[0].slice(0,5),['Bank ID','Bank Name','Email','Phone/WhatsApp','Minimum Facility USD']);
  assert.equal(f.tabs[0].rows[1][2],'hello@example.com');assert.equal(f.writes(),1);
  const restart=new TableGuard(f.statePath);await restart.handle('write_table_records',f.args,f.sheets);assert.equal(f.writes(),1);
  f.args.records=[{'Bank ID':'BANK-001',Email:'new@example.com'}];await restart.handle('write_table_records',f.args,f.sheets);
  assert.equal(f.tabs[0].rows[1][1],'Example Bank');assert.equal(f.tabs[0].rows[1][2],'new@example.com');
}));
test('bad field names/types/formulas and header rewrite routes blocked before mutation',()=>fixture(async f=>{
  for(const fields of [{Typo:'wrong'},{Email:'not email'},{'Phone/WhatsApp':12345678},{'Minimum Facility USD':'100'},{'Bank Name':'=1+1'}])await assert.rejects(f.guard.handle('write_table_records',{...f.args,records:[{'Bank ID':'B1',...fields}]},f.sheets),/BLOCKED/);
  for(const name of ['write_sheet','batch_update_sheet','clear_sheet_range','delete_file','update_file','duplicate_sheet'])assert.throws(()=>f.guard.block(name,f.args),/immutable/);
  assert.equal(f.writes(),0);
}));
test('new tab/template initializes once and writes correct first data row',()=>fixture(async f=>{
  const args={fileId:TRACKER_ID,sheetName:'New CRM',title:'Buyer directory',headers:['Buyer ID','Company','Email']};
  await f.guard.handle('initialize_table',args,f.sheets);
  await assert.rejects(f.guard.handle('initialize_table',args,f.sheets),/already written/);
  await f.guard.handle('write_table_records',{...args,keyColumn:'Buyer ID',mode:'insert',records:[{'Buyer ID':'BUY-1',Company:'Buyer'}]},f.sheets);
  const tab=f.tabs.find(t=>t.properties.title==='New CRM');assert.deepEqual(tab.rows[2],args.headers);assert.equal(tab.rows[3][1],'Buyer');
}));
test('blank tab initializes; populated headers never rewritten',()=>fixture(async f=>{
  await f.guard.handle('initialize_table',{...f.args,headers:['ID','Name']},f.sheets);
  await assert.rejects(f.guard.handle('initialize_table',{...f.args,headers:['ID','Changed']},f.sheets),/already written/);
},[]));
test('duplicate key, changed protected header, original template and expense bypass blocked',()=>fixture(async f=>{
  await f.guard.handle('inspect_table',f.args,f.sheets);
  f.tabs[0].rows.push(['BANK-001','A'],['BANK-001','B']);
  await assert.rejects(f.guard.handle('write_table_records',f.args,f.sheets),/duplicate/);
  f.tabs[0].rows[0][0]='Changed ID';await assert.rejects(f.guard.handle('write_table_records',f.args,f.sheets),/headers/);
  await assert.rejects(f.guard.handle('initialize_table',{...f.args,fileId:TEMPLATE_ID,headers:['ID','Name']},f.sheets),/reference/);
  await assert.rejects(f.guard.handle('write_table_records',{...f.args,fileId:IBNU_ID},f.sheets),/EXPENSE WRITE BLOCKED/);
  assert.equal(f.writes(),0);
}));
test('formula-prefilled data rows remain usable; formulas survive writes',()=>fixture(async f=>{
  f.tabs[0].rows[1]=['','','','','','=1+1'];
  await f.guard.handle('write_table_records',f.args,f.sheets);assert.equal(f.tabs[0].rows[1][0],'BANK-001');assert.equal(f.tabs[0].rows[1][5],'=1+1');
}));
test('concurrent additions select different rows; failed readback never reports success',()=>fixture(async f=>{
  const other={...f.args,records:[{'Bank ID':'BANK-002','Bank Name':'Second'}]};
  await Promise.all([f.guard.handle('write_table_records',f.args,f.sheets),f.guard.handle('write_table_records',other,f.sheets)]);
  assert.equal(f.tabs[0].rows[2][0],'BANK-002');
  f.setCorrupt();await assert.rejects(f.guard.handle('write_table_records',{...other,records:[{'Bank ID':'BANK-003','Bank Name':'Third'}]},f.sheets),/headers/);
}));

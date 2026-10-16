import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {TableGuard} from './table-tools.js';
import {TRACKER_ID,TEMPLATE_ID,TABLES} from './tracker-guard.js';
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

test('mixed contact field accepts phones, emails and mixed lists; dedicated columns stay typed',()=>fixture(async f=>{
  for(const value of ['+33 4 93 60 82 82','hello@example.com','+33123456789; hello@example.com'])
    assert.doesNotThrow(()=>f.guard.validateValue('Phone / Email',value));
  for(const value of ['not a contact',12345678,'....','hello@example.com; invalid'])
    assert.throws(()=>f.guard.validateValue('Phone / Email',value),/BLOCKED/);
  assert.throws(()=>f.guard.validateValue('Phone','hello@example.com'),/phone/);
  assert.throws(()=>f.guard.validateValue('Email','+33123456789'),/email/);
}));

test('human contact split refreshes snapshot without Sheet writes; pending phone upsert preserves template/data/formulas',()=>fixture(async f=>{
  f.args={...f.args,sheetName:'01 Daily Activity',keyColumn:'Key Notes',records:[{'Key Notes':'call-1',Phone:'+33123456789'}]};
  f.tabs[0].properties.title=f.args.sheetName;
  await f.guard.handle('inspect_table',f.args,f.sheets);
  // Human inserts a column, preserving business data and a formula.
  f.tabs[0].rows[3]=['Date','Phone','Email','Key Notes','Next Action','Total'];
  f.tabs[0].rows[4]=['2026-10-13','','','call-1','Follow up','=1+1'];
  await assert.rejects(f.guard.handle('write_table_records',f.args,f.sheets),/inspect_table/);
  const before=structuredClone(f.tabs[0].rows);
  const info=JSON.parse((await f.guard.handle('inspect_table',f.args,f.sheets)).content[0].text);
  assert.deepEqual(info.headers,f.tabs[0].rows[3]);
  assert.deepEqual(f.tabs[0].rows,before);assert.equal(f.writes(),0);
  assert.equal(f.guard.state.tables[TRACKER_ID+':13'].revisions.length,1);
  const restart=new TableGuard(f.statePath);
  await restart.handle('write_table_records',f.args,f.sheets);
  before[4][1]='+33123456789';assert.deepEqual(f.tabs[0].rows,before);
  assert.equal(f.writes(),1);
  await restart.handle('write_table_records',f.args,f.sheets);assert.equal(f.writes(),1);
},[['Activity log'],['Instruction'],[],['Date','Phone / Email','Key Notes','Next Action','Total'],['2026-10-13','','call-1','Follow up','=1+1']]));

test('added columns beyond old grid width are detected; inspect refreshes without changing cells',()=>fixture(async f=>{
  f.tabs[0].properties.gridProperties.columnCount=5;
  await f.guard.handle('inspect_table',f.args,f.sheets);
  f.tabs[0].properties.gridProperties.columnCount=6;
  f.tabs[0].rows[0].push('Notes');
  await assert.rejects(f.guard.handle('write_table_records',f.args,f.sheets),/inspect_table/);
  await f.guard.handle('inspect_table',f.args,f.sheets);
  await f.guard.handle('write_table_records',f.args,f.sheets);
  assert.equal(f.tabs[0].rows[1][3],'+6212345678');
}));

test('refresh rejects renamed/deleted/reordered/duplicate/formula headers and changed title/preamble',async()=>{
  for(const mutate of [
    f=>{f.tabs[0].rows[0][0]='Changed ID';},
    f=>{f.tabs[0].rows[0].splice(1,1);},
    f=>{f.tabs[0].rows[0].reverse();},
    f=>{f.tabs[0].rows[0].push('Email');},
    f=>{f.tabs[0].rows[0].push('=1+1');},
    f=>{f.tabs[0].properties.title='Renamed';f.args.sheetName='Renamed';},
  ]) await fixture(async f=>{
    await f.guard.handle('inspect_table',f.args,f.sheets);
    const state=structuredClone(f.guard.state);
    mutate(f);await assert.rejects(f.guard.handle('inspect_table',f.args,f.sheets),/BLOCKED/);
    assert.deepEqual(f.guard.state,state);assert.equal(f.writes(),0);
  });
  await fixture(async f=>{
    await f.guard.handle('inspect_table',f.args,f.sheets);
    f.tabs[0].rows[0][0]='Changed title';f.tabs[0].rows[1].push('Notes');
    await assert.rejects(f.guard.handle('inspect_table',f.args,f.sheets),/incompatibly/);
  },[['Title'],['Bank ID','Bank Name']]);
});

test('populated contact split is ambiguous and cannot be adopted',()=>fixture(async f=>{
  await f.guard.handle('inspect_table',f.args,f.sheets);
  f.tabs[0].rows[0]=['Bank ID','Phone','Email'];
  f.tabs[0].rows[1]=['B1','hello@example.com',''];
  await assert.rejects(f.guard.handle('inspect_table',f.args,f.sheets),/populated contact split/);
  assert.equal(f.writes(),0);
},[['Bank ID','Phone / Email'],['B1','hello@example.com']]));

test('legacy supplier schema cannot refresh; accounting schema cannot refresh',async()=>{
  await fixture(async f=>{
    f.tabs[0].properties.title='03 Supplier Master';f.args.sheetName='03 Supplier Master';
    await f.guard.handle('inspect_table',f.args,f.sheets);
    f.tabs[0].rows[3].push('New field');
    await assert.rejects(f.guard.handle('inspect_table',f.args,f.sheets),/original headers/);
  },[[],[],[],TABLES['03 Supplier Master'].header]);
  await fixture(async f=>{
    f.args.fileId=IBNU_ID;
    await f.guard.handle('inspect_table',f.args,f.sheets);
    f.tabs[0].rows[0].push('New field');
    await assert.rejects(f.guard.handle('inspect_table',f.args,f.sheets),/EXPENSE WRITE BLOCKED/);
  });
});

test('concurrent edit during inspection never adopts a snapshot',()=>fixture(async f=>{
  const get=f.sheets.spreadsheets.values.get;let calls=0;
  f.sheets.spreadsheets.values.get=async args=>{
    const result=await get(args);if(++calls===1)f.tabs[0].rows[0].push('Notes');return result;
  };
  await assert.rejects(f.guard.handle('inspect_table',f.args,f.sheets),/Concurrent edit/);
  assert.deepEqual(f.guard.state.tables,{});assert.equal(f.writes(),0);
}));

test('legacy duplicate quote rows do not freeze unrelated COA insert; history and idempotency preserved',()=>fixture(async f=>{
  const title='04 Price Specs Capacity',table=TABLES[title];
  f.tabs[0].properties.title=title;f.tabs[0].properties.sheetId=table.id;
  const quote=Array(table.width).fill('');Object.assign(quote,{0:'05-Oct-2026',1:'SUP-001',2:'Supplier A',3:'Vanilla beans',5:'Grade 3',12:'1,000,000',13:'IDR',14:'kg'});
  const duplicate=[...quote];duplicate[14]='';duplicate[22]='Separate historical source';
  f.tabs[0].rows=[['Title'],['Instructions'],[],table.header.slice(),quote,duplicate];
  const before=structuredClone(f.tabs[0].rows);
  const args={fileId:TRACKER_ID,sheetName:title,keyColumn:'Quote Date',mode:'insert',records:[{'Quote Date':'2024-02-15','Supplier ID':'SUP-003',Supplier:'Supplier B',Commodity:'Vanilla (cured bean)','Grade / Variety':'Planifolia','Detailed Specification':'COA-only record; no commercial price','COA / Lab Result?':'SUCOFINDO COA source'}]};
  await f.guard.handle('write_table_records',args,f.sheets);
  assert.deepEqual(f.tabs[0].rows.slice(0,before.length),before);
  assert.equal(f.tabs[0].rows[6][0],'2024-02-15');assert.equal(f.writes(),1);
  await f.guard.handle('write_table_records',args,f.sheets);assert.equal(f.writes(),1);
  await assert.rejects(f.guard.handle('write_table_records',{...args,records:[{'Quote Date':'2026-10-05','Supplier ID':'SUP-001',Supplier:'Supplier A',Commodity:'Vanilla beans','Grade / Variety':'Grade 3','Supplier Price':1000000,Currency:'IDR'}]},f.sheets),/Ambiguous duplicate/);
  assert.equal(f.writes(),1);
}));

test('dropdown failures report all affected fields and choices without weakening validation',()=>fixture(async f=>{
  const original=f.sheets.spreadsheets.get;
  f.sheets.spreadsheets.get=async args=>args.includeGridData?{data:{sheets:[{data:[{startRow:1,startColumn:1,rowData:[{values:[
    {dataValidation:{condition:{type:'ONE_OF_LIST',values:[{userEnteredValue:'Yes'},{userEnteredValue:'No'},{userEnteredValue:'Pending'}]}}},
    {dataValidation:{condition:{type:'ONE_OF_LIST',values:[{userEnteredValue:'Approved'}]}}},
  ]}]}]}]}}:original(args);
  await assert.rejects(f.guard.handle('write_table_records',f.args,f.sheets),error=>{
    assert.match(error.message,/Bank Name row 2 requires an existing choice: \["Yes","No","Pending"\]/);
    assert.match(error.message,/Email row 2 requires an existing choice: \["Approved"\]/);return true;
  });
  assert.equal(f.writes(),0);
}));

test('supplier master accepts new batch beside unchanged historical duplicate and retries once',()=>fixture(async f=>{
  const title='03 Supplier Master',table=TABLES[title];
  f.tabs[0].properties.title=title;f.tabs[0].properties.sheetId=table.id;
  const old=Array(table.width).fill('');Object.assign(old,{0:'SUP-001',1:'Legacy supplier',15:'New',16:'05-Oct-2026'});
  const historical=[...old];historical[0]='SUP-001-H1';historical[17]='Historical source';
  f.tabs[0].rows=[['Title'],['Instructions'],[],table.header.slice(),historical,old];
  const before=structuredClone(f.tabs[0].rows);
  const args={fileId:TRACKER_ID,sheetName:title,keyColumn:'Supplier ID',mode:'insert',records:[
    {'Supplier ID':'SUP-004','Supplier / Producer':'Fresh supplier','Last Contact':'2026-10-16','Supplier Status':'New'},
    {'Supplier ID':'SUP-005','Supplier / Producer':'Another supplier','Last Contact':'2026-10-16','Supplier Status':'New'},
  ]};
  await f.guard.handle('write_table_records',args,f.sheets);
  assert.deepEqual(f.tabs[0].rows.slice(0,before.length),before);assert.equal(f.writes(),1);
  await new TableGuard(f.statePath).handle('write_table_records',args,f.sheets);assert.equal(f.writes(),1);
  for(const records of [
    [{'Supplier ID':'SUP-006','Supplier / Producer':'Legacy supplier'}],
    [{'Supplier ID':'SUP-001','Notes / Risks':'Changing ambiguous company'}],
    [{'Supplier ID':'SUP-007-H1','Supplier / Producer':'Invalid new ID'}],
  ])await assert.rejects(f.guard.handle('write_table_records',{...args,mode:'upsert',records},f.sheets),/BLOCKED/);
  assert.equal(f.writes(),1);
}));

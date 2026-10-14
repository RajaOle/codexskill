import test from 'node:test';
import assert from 'node:assert/strict';
import {TABLES,TRACKER_ID,TEMPLATE_ID,blockProtectedMutation,guardedWrite,parseTarget,validateRows} from './tracker-guard.js';

const title='03 Supplier Master', schema=TABLES[title];
const supplier=(id='SUP-001')=>[id,'Example supplier','','','+62123456789','a@example.com','Vanilla','Producer','','','','','','','','New','06-Oct-2026',''];
function mock(title='03 Supplier Master') {
  const s=TABLES[title];
  const rows=[['Title'],['Instructions'],[],s.header.slice()];
  const calls=[];
  let wrongReadback=false;
  const values={
    get:async args=>{
      calls.push(['get',args.range]);
      if(args.range.endsWith(s.end)) return {data:{values:structuredClone(rows)}};
      const match=/![A-Z]+(\d+):[A-Z]+(\d+)/.exec(args.range);
      const result=structuredClone(rows.slice(Number(match[1])-1,Number(match[2])));
      if(wrongReadback && result.length) result.at(-1)[0]='WRONG';
      return {data:{values:result}};
    },
    update:async args=>{calls.push(['update',args]);const start=Number(/![A-Z]+(\d+)/.exec(args.range)[1]);args.requestBody.values.forEach((r,i)=>{rows[start+i-1]=structuredClone(r);});},
  };
  return {rows,calls,setWrong:()=>{wrongReadback=true;},sheets:{spreadsheets:{get:async()=>({data:{sheets:[{properties:{title,sheetId:s.id,gridProperties:{rowCount:100,columnCount:s.width}}}]}}),values}}};
}
const args=(values=[supplier()])=>({fileId:TRACKER_ID,range:`${title}!A5:R${4+values.length}`,values});
const noWrite=m=>assert.equal(m.calls.filter(c=>c[0]==='update').length,0);

test('all structural mutations and original template writes are blocked',()=>{
  for(const name of ['write_sheet','duplicate_sheet','batch_update_sheet','clear_sheet_range','update_file','delete_file']) assert.throws(()=>blockProtectedMutation(name,{fileId:TEMPLATE_ID}),/read-only/);
  for(const name of ['duplicate_sheet','batch_update_sheet','clear_sheet_range','update_file','delete_file']) assert.throws(()=>blockProtectedMutation(name,{fileId:TRACKER_ID}),/forbidden/);
  assert.doesNotThrow(()=>blockProtectedMutation('write_sheet',{fileId:'unrelated-workbook'}));
});
test('range, append, header and row shape failures stop before writing',async()=>{
  for(const extra of [{append:true},{range:title+'!A4:R4'},{range:'Reference Lists!A5:R5'},{values:[['SUP-001']]},{range:title+'!A:R'}]) {
    const m=mock();await assert.rejects(guardedWrite({...args(),...extra},m.sheets),/BLOCKED/);noWrite(m);
  }
  const m=mock();m.rows[3][0]='SUP-001';await assert.rejects(guardedWrite(args(),m.sheets),/header/);noWrite(m);
});
test('duplicate IDs and unrelated date/email/numeric values are rejected',async()=>{
  const m=mock();m.rows.push(supplier(),supplier());await assert.rejects(guardedWrite({...args(),range:title+'!A7:R7'},m.sheets),/Duplicate/);noWrite(m);
  for(const [column,value] of [[16,'wrong@example.com'],[5,'06-Oct-2026'],[10,'stock narrative'],[10,'100'],[4,62123456789],[17,'=IMPORTXML("x")']]) {
    const x=mock(),row=supplier();row[column]=value;await assert.rejects(guardedWrite(args([row]),x.sheets),/BLOCKED/);noWrite(x);
  }
});
test('successful RAW write reads back every written row and template',async()=>{
  const m=mock(),second=supplier('SUP-002');second[1]='Second company';
  const result=await guardedWrite(args([supplier(),second]),m.sheets);
  assert.match(result.content[0].text,/all 2 rows read back/);
  assert.equal(m.calls.find(c=>c[0]==='update')[1].valueInputOption,'RAW');
  assert.ok(m.calls.some(c=>c[0]==='get' && c[1]===title+'!A5:R6'));
  assert.deepEqual(m.rows[3],schema.header);
});
test('last-row mismatch never reports success',async()=>{
  const m=mock();m.setWrong();await assert.rejects(guardedWrite(args(),m.sheets),/POST-WRITE VERIFICATION FAILED/);
  assert.equal(m.calls.filter(c=>c[0]==='update').length,1);
});
test('new rows cannot reuse blank gaps or skip downward positions',async()=>{
  const m=mock();m.rows.push([],supplier());await assert.rejects(guardedWrite(args(),m.sheets),/immediately/);noWrite(m);
  const x=mock();await assert.rejects(guardedWrite({...args(),range:title+'!A7:R7'},x.sheets),/immediately/);noWrite(x);
});
test('duplicate quotes with missing unit remain ambiguous and block',async()=>{
  const t='04 Price Specs Capacity',m=mock(t);
  const quote=Array(23).fill('');Object.assign(quote,{0:'06-Oct-2026',1:'SUP-001',2:'Supplier',3:'Vanilla',5:'Grade 3',12:1000000,13:'IDR',14:'kg'});
  const duplicate=[...quote];duplicate[14]='';m.rows.push(quote,duplicate);
  await assert.rejects(guardedWrite({fileId:TRACKER_ID,range:t+'!A7:W7',values:[quote]},m.sheets),/Duplicate\/ambiguous/);noWrite(m);
});

test('baseline exemption permits only unchanged legacy duplicate groups, never edits, new duplicates or extra copies',()=>{
  const title='04 Price Specs Capacity';
  const q=Array(23).fill('');Object.assign(q,{0:'2026-10-05',1:'SUP-001',2:'Supplier',3:'Vanilla',5:'Grade 3',12:1000000,13:'IDR',14:'kg'});
  const other=[...q];other[14]='';
  const baseline=[[],[],[],TABLES[title].header,q,other];
  const fresh=[...q];fresh[1]='SUP-003';fresh[0]='2024-02-15';fresh[12]='';fresh[13]='';
  assert.doesNotThrow(()=>validateRows(title,[...baseline,fresh],{baselineRows:baseline}));
  for(const planned of [
    [...baseline,[...q]],
    [...baseline,fresh,[...fresh]],
    baseline.map((row,i)=>i===4?row.map((v,c)=>c===22?'changed':v):row),
    [...baseline.slice(0,4),other,q],
  ])assert.throws(()=>validateRows(title,planned,{baselineRows:baseline}),/Duplicate\/ambiguous/);
});

test('concurrent writes serialize and cannot replace the first new record',async()=>{
  const m=mock(),second=supplier('SUP-002');second[1]='Different company';
  const results=await Promise.allSettled([guardedWrite(args(),m.sheets),guardedWrite(args([second]),m.sheets)]);
  assert.equal(results.filter(r=>r.status==='fulfilled').length,1);
  assert.equal(m.calls.filter(c=>c[0]==='update').length,1);
  assert.equal(m.rows[4][0],'SUP-001');
});
test('preflight concurrent change is rejected without writing',async()=>{
  const m=mock(),original=m.sheets.spreadsheets.values.get;let reads=0;
  m.sheets.spreadsheets.values.get=async a=>{if(++reads===2)m.rows[0][0]='Changed by another editor';return original(a);};
  await assert.rejects(guardedWrite(args(),m.sheets),/changed during preflight/);noWrite(m);
});
test('target formula and silent erasure are blocked',async()=>{
  for(const replacement of ['=1+1','']) {
    const m=mock(),existing=supplier();existing[17]='Preserve source';m.rows.push(existing);
    const value=[...existing];value[17]=replacement;
    await assert.rejects(guardedWrite(args([value]),m.sheets),/BLOCKED/);noWrite(m);
  }
});

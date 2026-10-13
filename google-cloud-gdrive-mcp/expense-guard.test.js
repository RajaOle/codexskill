import test from 'node:test';
import assert from 'node:assert/strict';
import {SINDY_ID, HEADER, POLICY, balanceFormula, blockExpenseMutation, validateExpense, recordExpense} from './expense-guard.js';

const expense = extra => ({fileId:SINDY_ID, sheetName:POLICY.title, date:'2026-10-06', description:'GoCar outbound', category:'Ops', credit:0, debit:121000, receiptUrl:'https://drive.google.com/file/d/example_receipt/view', ...extra});
function mock() {
  const rows = Array.from({length:1000}, (_,r) => Array(26).fill(''));
  rows[0][0]='Saldo Sindy bulan sebelumnya';rows[0][1]=0;
  rows[2].splice(0,7,...HEADER);
  for(let r=4;r<=1000;r++) rows[r-1][5]=balanceFormula(r);
  const calls=[];
  let corrupt=false, timeout=false, badBalance=false, changeOnRead=false, reads=0;
  const api={spreadsheets:{
    get:async()=>({data:{sheets:[{properties:{sheetId:0,title:POLICY.title,gridProperties:{rowCount:1000,columnCount:26}}}]}}),
    values:{
      get:async args=>{
        calls.push(['get',args]);
        if(args.valueRenderOption==='UNFORMATTED_VALUE') {
          const last=Number(/!F(\d+)/.exec(args.range)[1]);
          const sum=rows.slice(3,last).reduce((n,r)=>n+(r[3]||0)-(r[4]||0),rows[0][1]);
          return {data:{values:[[badBalance?999:sum]]}};
        }
        if(changeOnRead && ++reads===2) rows[0][1]=1;
        return {data:{values:structuredClone(rows)}};
      },
      batchUpdate:async args=>{
        calls.push(['batchUpdate',args]);
        for(const data of args.requestBody.data) {
          const match=/!([AG])(\d+):/.exec(data.range), col=match[1]==='A'?0:6, row=Number(match[2])-1;
          data.values[0].forEach((v,c)=>{rows[row][col+c]=v;});
        }
        if(corrupt) rows[2][0]='BROKEN';
        if(timeout) throw new Error('timeout after commit');
        return {data:{}};
      },
    },
  }};
  return {rows,calls,api,setCorrupt:()=>{corrupt=true;},setTimeout:()=>{timeout=true;},setBadBalance:()=>{badBalance=true;},setConcurrent:()=>{changeOnRead=true;}};
}
const writes = m => m.calls.filter(c=>c[0]==='batchUpdate');

test('raw, structural, clear and file mutations cannot reach Sindy template',()=>{
  for(const name of ['write_sheet','batch_update_sheet','clear_sheet_range','duplicate_sheet','update_file','delete_file']) assert.throws(()=>blockExpenseMutation(name,{fileId:SINDY_ID}),/BLOCKED/);
  assert.doesNotThrow(()=>blockExpenseMutation('read_sheet',{fileId:SINDY_ID}));
  assert.doesNotThrow(()=>blockExpenseMutation('write_sheet',{fileId:'unrelated'}));
});
test('bad dates, direction, amounts, columns, project and category are blocked',()=>{
  for(const extra of [{date:'2026-10-32'},{date:'2026-09-01'},{debit:'121000'},{credit:1},{debit:0},{description:'=IMPORTXML("x")'},{receiptUrl:'not a URL'},{category:'invented'},{fileId:'wrong'},{range:'A3:G3'},{row:3}]) assert.throws(()=>validateExpense(expense(extra)),/BLOCKED/);
});
test('first expense goes to row 4; only A:E and G RAW literals change',async()=>{
  const m=mock(),before=structuredClone(m.rows);const result=await recordExpense(expense(),m.api);
  const summary=JSON.parse(result.content[0].text);assert.equal(summary.row,4);assert.equal(summary.closingBalance,-121000);
  const request=writes(m)[0][1].requestBody;assert.equal(request.valueInputOption,'RAW');
  assert.deepEqual(request.data.map(d=>d.range),["'Oktober 2026'!A4:E4","'Oktober 2026'!G4:G4"]);
  assert.deepEqual(m.rows.slice(0,3),before.slice(0,3));assert.equal(m.rows[3][5],balanceFormula(4));
});
test('damaged header, missing formula and unexpected columns stop before writing',async()=>{
  for(const mutate of [m=>{m.rows[2][0]='Expense';},m=>{m.rows[3][5]='';},m=>{m.rows[4][7]='unrelated';},m=>{m.rows[3][1]='partial';}]) {
    const m=mock();mutate(m);await assert.rejects(recordExpense(expense(),m.api),/BLOCKED/);assert.equal(writes(m).length,0);
  }
});
test('duplicates are idempotent; same receipt with conflicting amount is blocked',async()=>{
  const m=mock();await recordExpense(expense(),m.api);
  assert.equal(JSON.parse((await recordExpense(expense(),m.api)).content[0].text).status,'already_recorded');
  await assert.rejects(recordExpense(expense({debit:120000}),m.api),/conflicting duplicate/);assert.equal(writes(m).length,1);
});
test('next entry ignores formula-only rows and follows the last business row',async()=>{
  const m=mock();await recordExpense(expense(),m.api);
  const result=await recordExpense(expense({description:'Meal',category:'Meals',debit:61564,receiptUrl:'https://drive.google.com/file/d/second_receipt/view'}),m.api);
  assert.equal(JSON.parse(result.content[0].text).row,5);assert.equal(JSON.parse(result.content[0].text).closingBalance,-182564);
});
test('concurrent duplicate calls serialize into one write',async()=>{
  const m=mock();const results=await Promise.all([recordExpense(expense(),m.api),recordExpense(expense(),m.api)]);
  assert.equal(writes(m).length,1);assert.equal(JSON.parse(results[1].content[0].text).status,'already_recorded');
});
test('preflight concurrent edit prevents any write',async()=>{
  const m=mock();m.setConcurrent();await assert.rejects(recordExpense(expense(),m.api),/changed during preflight/);assert.equal(writes(m).length,0);
});
test('post-write header corruption and wrong calculated balance never report success',async()=>{
  for(const option of ['setCorrupt','setBadBalance']) {const m=mock();m[option]();await assert.rejects(recordExpense(expense(),m.api),/BLOCKED/);assert.equal(writes(m).length,1);}
});
test('timeout after commit is not retried; a later verified retry finds the existing row',async()=>{
  const m=mock();m.setTimeout();await assert.rejects(recordExpense(expense(),m.api),/outcome uncertain/);
  assert.equal(writes(m).length,1);const result=await recordExpense(expense(),m.api);
  assert.equal(JSON.parse(result.content[0].text).status,'already_recorded');assert.equal(writes(m).length,1);
});

// Automatic table discovery and one-time template creation. No manual schema registry.
import { existsSync, readFileSync, mkdirSync, writeFileSync, renameSync } from 'node:fs';
import path from 'node:path';
import { isDeepStrictEqual as equal } from 'node:util';
import { TABLES, TRACKER_ID, TEMPLATE_ID, validateRows, quoteIdentity } from './tracker-guard.js';
import { blockExpenseMutation } from './expense-guard.js';

const options = {timeout:15000,retry:false};
const fail = text => { throw new Error('TABLE WRITE BLOCKED: '+text); };
const cell = v => v ?? '';
const occupied = row => row?.some(v => cell(v) !== '');
const quote = title => "'"+title.replaceAll("'","''")+"'";
const key = v => String(cell(v)).trim().toLowerCase();
const pad = (rows,height,width) => Array.from({length:height},(_,r)=>Array.from({length:width},(_,c)=>cell(rows[r]?.[c])));
export function column(n) { let s=''; for(n++;n;n=Math.floor((n-1)/26)) s=String.fromCharCode(65+(n-1)%26)+s; return s; }
const result = data => ({content:[{type:'text',text:JSON.stringify(data)}]});
const string = {type:'string'};
const tool = (name,description,properties,required) => ({name,description,inputSchema:{type:'object',additionalProperties:false,properties,required}});
export const tableTools = [
  tool('inspect_table','Discover live headers; safely refresh human-added columns or an empty Phone / Email split. Never changes Sheet cells. Returns exact field names and next data row; inspect again after a human layout change.',{fileId:string,sheetName:string},['fileId','sheetName']),
  tool('initialize_table','Create a new tab or initialize a completely blank tab ONCE. Set title/description/headers and initial header formatting; existing nonempty tabs are never overwritten. Headers become immutable.',{fileId:string,sheetName:string,headers:{type:'array',minItems:2,maxItems:100,items:string},title:string,description:string},['fileId','sheetName','headers']),
  tool('write_table_records','Insert or update records using EXACT live header names as object keys. Backend maps columns and selects rows; never supply coordinates. Supply keyColumn (unique record ID/name) for idempotent retries; mode=insert preserves history, upsert updates only supplied fields. Unchanged historical supplier/quote duplicates do not block unrelated new records. New Supplier IDs use SUP-<digits>; never rename existing IDs for cleanup. Never rewrites headers/formulas.',{fileId:string,sheetName:string,keyColumn:string,mode:{type:'string',enum:['insert','upsert']},records:{type:'array',minItems:1,maxItems:100,items:{type:'object',additionalProperties:{type:['string','number','boolean']}}}},['fileId','sheetName','keyColumn','mode','records']),
];

export class TableGuard {
  constructor(statePath=process.env.GDRIVE_TABLE_STATE_PATH || '/home/olekamole/.openclaw/mcp-servers/gdrive/table-state.json') {
    this.statePath=statePath; this.locks=new Map();
    this.state=existsSync(statePath)?JSON.parse(readFileSync(statePath,'utf8')):{workbooks:{},tables:{}};
    if(!this.state.workbooks || !this.state.tables) fail('Invalid protection state.');
  }
  save() {
    mkdirSync(path.dirname(this.statePath),{recursive:true,mode:0o700});
    writeFileSync(this.statePath+'.tmp',JSON.stringify(this.state),{mode:0o600});
    renameSync(this.statePath+'.tmp',this.statePath);
  }
  protects(id) { return id===TRACKER_ID || Boolean(this.state.workbooks[id]); }
  adopt(id) { this.state.workbooks[id]=true; this.save(); }
  block(name,args) {
    if(this.protects(args.fileId) && ['write_sheet','batch_update_sheet','clear_sheet_range','duplicate_sheet','update_file','delete_file'].includes(name)) fail('Use write_table_records for data or initialize_table for a NEW/blank tab. Existing template structure is immutable.');
  }
  async locked(id,fn) {
    const previous=this.locks.get(id)||Promise.resolve(); let release;
    const gate=new Promise(r=>{release=r;}); const tail=previous.then(()=>gate); this.locks.set(id,tail);
    await previous;
    try {return await fn();} finally {release();if(this.locks.get(id)===tail)this.locks.delete(id);}
  }
  async read(args,sheets) {
    const meta=await sheets.spreadsheets.get({spreadsheetId:args.fileId,fields:'sheets.properties'},options);
    const tab=meta.data.sheets?.find(s=>s.properties.title===args.sheetName)?.properties;
    if(!tab) fail('Tab does not exist; create it with initialize_table.');
    if(tab.gridProperties.columnCount>200 || tab.gridProperties.rowCount>20000) fail('Table exceeds bounded inspection size (200 columns / 20000 rows).');
    const res=await sheets.spreadsheets.values.get({spreadsheetId:args.fileId,range:quote(args.sheetName),valueRenderOption:'FORMULA'},options);
    return {tab,rows:res.data.values||[]};
  }
  refreshPolicy(args,view,policy) {
    const {tab,rows}=view;
    // Only externally edited operational layouts may be adopted. Legacy positional
    // validators and reference/accounting templates must retain their exact schema.
    if(args.fileId===TRACKER_ID && TABLES[args.sheetName]) fail('Protected original headers changed; preserve evidence.');
    blockExpenseMutation('write_sheet',args);
    const headers=rows[policy.headerRow-1] || [];
    const width=Math.max(policy.template[0].length,tab.gridProperties.columnCount);
    if(policy.title!==tab.title || headers.length<=policy.headers.length || headers.length>100 ||
      headers.some(h=>typeof h!=='string'||!h.trim()||h.trimStart().startsWith('=')||h.length>150) ||
      new Set(headers.map(key)).size!==headers.length ||
      !equal(pad(policy.template,policy.headerRow-1,width),pad(rows,policy.headerRow-1,width))) {
      fail('Protected headers/title/template changed incompatibly; preserve evidence. Only added columns or an empty Phone / Email split can be rediscovered.');
    }
    let cursor=0;
    for(const old of policy.headers) {
      const found=headers.indexOf(old,cursor);
      if(found>=0) {cursor=found+1;continue;}
      // A split is unambiguous only when both resulting contact columns are empty.
      // Populated mixed contacts require deliberate migration, never guessed moves.
      const phone=headers.indexOf('Phone',cursor),email=headers.indexOf('Email',phone+1);
      if(!/^Phone\s*\/\s*Email$/i.test(old) || phone<cursor || email!==phone+1 ||
        rows.slice(policy.headerRow).some(row=>cell(row[phone])!==''||cell(row[email])!=='')) {
        fail('Protected headers removed, renamed, reordered or populated contact split; preserve evidence.');
      }
      cursor=email+1;
    }
    const next={...policy,headers:[...headers],template:pad(rows.slice(0,policy.headerRow),policy.headerRow,tab.gridProperties.columnCount),
      revisions:[...(policy.revisions||[]),{at:new Date().toISOString(),headers:policy.headers,template:policy.template}]};
    this.state.tables[args.fileId+':'+tab.sheetId]=next;this.save();
    return next;
  }
  discover(args,view,allowRefresh=false) {
    const {tab,rows}=view;
    if(args.fileId===TEMPLATE_ID || /^(?:Reference Lists|00 Dashboard|09 Operating Guide|10 Product Incoterms)$/i.test(args.sheetName)) fail('Reference/template content is read-only; use a new operational tab.');
    const id=args.fileId+':'+tab.sheetId;
    let policy=this.state.tables[id];
    if(!policy) {
      const known=args.fileId===TRACKER_ID ? TABLES[args.sheetName] : undefined;
      let headerRow;
      if(known) {
        headerRow=4;
        if(!equal(pad([rows[3]],1,known.width)[0],known.header)) fail('Existing original header changed; do not repair it.');
      } else {
        // Title/explanation rows have one populated cell; first contiguous text row is the table header.
        headerRow=rows.slice(0,30).findIndex(row=>row.length>=2 && row.every(v=>typeof v==='string' && v.trim() && !v.startsWith('=')) && new Set(row.map(key)).size===row.length)+1;
        if(!headerRow) fail('No unambiguous contiguous header found. Blank tabs can be initialized; preserve populated templates.');
      }
      const headers=rows[headerRow-1];
      policy={title:tab.title,sheetId:tab.sheetId,headerRow,headers,template:pad(rows.slice(0,headerRow),headerRow,tab.gridProperties.columnCount)};
      this.state.tables[id]=policy; this.state.workbooks[args.fileId]=true; this.save();
    }
    const width=Math.max(policy.template[0].length,tab.gridProperties.columnCount);
    if(policy.title!==tab.title || !equal(pad(policy.template,policy.headerRow,width),pad(rows,policy.headerRow,width))) {
      if(!allowRefresh) fail('Protected headers/title/template changed since discovery. Call inspect_table to rediscover safe human-added columns; never rewrite them.');
      policy=this.refreshPolicy(args,view,policy);
    }
    let last=policy.headerRow;
    rows.forEach((row,i)=>{if(i>=policy.headerRow && row.some(v=>cell(v)!=='' && !(typeof v==='string'&&v.startsWith('='))))last=i+1;});
    return {...policy,nextRow:last+1};
  }
  async initialize(args,sheets) {
    const headers=args.headers;
    if(!Array.isArray(headers) || headers.length<2 || headers.length>100 || headers.some(h=>typeof h!=='string'||!h.trim()||h.startsWith('=')||h.length>150) || new Set(headers.map(key)).size!==headers.length) fail('Use 2–100 distinct nonempty literal header labels.');
    const meta=await sheets.spreadsheets.get({spreadsheetId:args.fileId,fields:'sheets.properties'},options);
    const existing=meta.data.sheets?.find(s=>s.properties.title===args.sheetName)?.properties;
    let tab=existing;
    if(existing) {
      const view=await this.read(args,sheets);
      if(view.rows.some(occupied) || this.state.tables[args.fileId+':'+existing.sheetId]) fail('Template already written. Initial headers cannot be rewritten; use existing columns or a new tab.');
      // A blank-looking preformatted template is not an empty tab.
      const detail=await sheets.spreadsheets.get({spreadsheetId:args.fileId,ranges:[quote(args.sheetName)],includeGridData:true},options);
      const grid=detail.data.sheets?.[0];
      if(grid?.merges?.length || grid?.conditionalFormats?.length || grid?.data?.some(d=>d.rowData?.some(r=>r.values?.some(c=>c.userEnteredFormat||c.dataValidation||c.note)))) fail('Existing formatted template is protected; create a new tab.');
    }
    const preamble=[];
    if(args.title) preamble.push([args.title]);
    if(args.description) preamble.push([args.description]);
    if(preamble.length)preamble.push([]);
    const rows=[...preamble,headers]; const headerRow=rows.length;
    if(rows.flat().some(v=>typeof v!=='string'||v.trimStart().startsWith('='))) fail('Template title/description must be literal text.');
    // Initialize cells + formatting in one Google batch. A retry sees a populated tab and cannot overwrite it.
    const requests=[];
    if(!tab) {
      const used=new Set((meta.data.sheets||[]).map(s=>s.properties.sheetId));
      let sheetId=1;while(used.has(sheetId))sheetId++;
      tab={title:args.sheetName,sheetId,gridProperties:{rowCount:1000,columnCount:Math.max(26,headers.length)}};
      requests.push({addSheet:{properties:tab}});
    }
    if(headers.length>tab.gridProperties.columnCount)fail('Headers exceed blank tab width; create a new tab with the intended width.');
    requests.push({updateCells:{start:{sheetId:tab.sheetId,rowIndex:0,columnIndex:0},rows:rows.map(row=>({values:row.map(v=>({userEnteredValue:{stringValue:v}}))})),fields:'userEnteredValue'}});
    requests.push({repeatCell:{range:{sheetId:tab.sheetId,startRowIndex:headerRow-1,endRowIndex:headerRow,startColumnIndex:0,endColumnIndex:headers.length},cell:{userEnteredFormat:{textFormat:{bold:true},backgroundColor:{red:0.87,green:0.93,blue:0.98}}},fields:'userEnteredFormat'}});
    requests.push({updateSheetProperties:{properties:{sheetId:tab.sheetId,gridProperties:{frozenRowCount:headerRow}},fields:'gridProperties.frozenRowCount'}});
    this.adopt(args.fileId);
    await sheets.spreadsheets.batchUpdate({spreadsheetId:args.fileId,requestBody:{requests}},options);
    const after=await this.read(args,sheets);
    if(!equal(pad(after.rows,headerRow,headers.length),pad(rows,headerRow,headers.length)))fail('Initialization verification failed; inspect before retrying.');
    const policy=this.discover(args,after);
    return result({status:'template_created',sheetName:args.sheetName,headers:policy.headers,headerRow,nextRow:policy.nextRow,headersProtected:true});
  }
  validateValue(header,value,known,index) {
    if(!['string','number','boolean'].includes(typeof value) || (typeof value==='number'&&!Number.isFinite(value)) || (typeof value==='string'&&value.trimStart().startsWith('=')))fail('Use literal scalar data; formulas are protected.');
    if(value==='')return;
    const emailField=/email/i.test(header),phoneField=/phone|whatsapp|\bwa\b/i.test(header);
    const email=v=>/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
    const phone=v=>/^\+?[\d ().-]{4,40}$/.test(v)&&/\d/.test(v);
    if((emailField||phoneField) && (typeof value!=='string'||!value.split(/[;,|]/).every(v=>
      (emailField&&email(v.trim()))||(phoneField&&phone(v.trim()))))) {
      fail(header+(emailField&&phoneField?' requires text phone identifiers or email addresses.':emailField?' requires email addresses.':' requires text phone identifiers, not narrative.'));
    }
    if((known?.numeric.includes(index) || /^(?:Minimum Facility USD|Amount|Quantity|Rate|Supplier Price|MOQ \(kg\)|.*Capacity.*\(kg\))$/i.test(header)) && typeof value!=='number')fail(header+' requires a numeric value.');
    if((known?.dates.includes(index)|| /^(?:Quote Date|Date|Last Contact|Quote Valid Until)$/i.test(header)) && !(typeof value==='number'||/^\d{4}-\d{2}-\d{2}$/.test(String(value))))fail(header+' requires YYYY-MM-DD.');
  }
  async write(args,sheets) {
    if(!['insert','upsert'].includes(args.mode)||!Array.isArray(args.records)||!args.records.length||args.records.length>100)fail('Supply insert/upsert and 1–100 records.');
    const before=await this.read(args,sheets);const p=this.discover(args,before);
    const headers=p.headers, keyIndex=headers.indexOf(args.keyColumn);
    if(keyIndex<0)fail('keyColumn must exactly match a live header.');
    if(args.sheetName==='04 Price Specs Capacity' && args.mode!=='insert')fail('Price history uses insert with a unique source/quote key; do not overwrite commercial quotes.');
    const known=args.fileId===TRACKER_ID?TABLES[args.sheetName]:undefined;
    const planned=pad(before.rows,Math.max(before.rows.length,p.headerRow),before.tab.gridProperties.columnCount);
    const changes=[],writes=[],seen=new Set();let next=p.nextRow;
    for(const record of args.records) {
      if(!record || typeof record!=='object'||Array.isArray(record))fail('Each record must be an object keyed by exact headers.');
      for(const [h,v]of Object.entries(record)){const i=headers.indexOf(h);if(i<0)fail('Unknown column '+h+'; preserve supplied data locally or use an existing notes column.');this.validateValue(h,v,known,i);}
      const price=args.fileId===TRACKER_ID&&args.sheetName==='04 Price Specs Capacity';
      const identity=row=>price?quoteIdentity(row):key(row[keyIndex]);
      const inputRow=headers.map(h=>record[h]??'');
      const id=identity(inputRow);if(!key(record[args.keyColumn])||seen.has(id))fail('Every input record needs a distinct nonempty '+args.keyColumn);seen.add(id);
      const matches=[];planned.forEach((row,i)=>{if(i>=p.headerRow && identity(row)===id)matches.push(i);});
      if(matches.length>1)fail('Ambiguous duplicate '+args.keyColumn+' '+id+'; preserve existing rows.');
      const index=matches.length?matches[0]:next++-1;
      if(index>=before.tab.gridProperties.rowCount)fail('No data space remains; create a new continuation tab.');
      const row=planned[index]||Array(before.tab.gridProperties.columnCount).fill('');const delta=[];
      for(const [h,v]of Object.entries(record)) {
        const i=headers.indexOf(h),old=cell(row[i]);
        if(old===v)continue;
        if(typeof old==='string'&&old.startsWith('='))fail('Formula protected at '+h+' row '+(index+1));
        if(matches.length && args.mode==='insert')fail('Existing key has different data; inspect existing source before retrying or use upsert for ordinary master data.');
        if(matches.length && /\bID$/i.test(h) && old!=='' && old!==v)fail('Existing record IDs are immutable.');
        if(matches.length && old!=='' && v==='')fail('Omit unknown fields; do not erase existing data.');
        row[i]=v;delta.push(h);
        writes.push({range:quote(args.sheetName)+'!'+column(i)+(index+1)+':'+column(i)+(index+1),values:[[v]]});
      }
      planned[index]=row;changes.push({row:index+1,fields:delta,status:delta.length?'written':'already_recorded'});
    }
    if(known)validateRows(args.sheetName,planned.map(r=>r.slice(0,known.width)),{baselineRows:before.rows});
    // Honor dropdown/checkbox validation without modifying it. Fetch only rules at target cells.
    if(writes.length) {
      const detail=await sheets.spreadsheets.get({spreadsheetId:args.fileId,ranges:writes.map(w=>w.range),includeGridData:true,fields:'sheets(data(startRow,startColumn,rowData(values(dataValidation))))'},options);
      const invalid=[];
      for(const sheet of detail.data.sheets||[])for(const grid of sheet.data||[])for(const [r,row]of (grid.rowData||[]).entries())for(const [c,target]of (row.values||[]).entries()) {
        const rule=target.dataValidation?.condition;
        const value=planned[(grid.startRow||0)+r]?.[(grid.startColumn||0)+c];
        if(!rule || cell(value)==='')continue;
        const field=headers[(grid.startColumn||0)+c];
        const mismatch=choices=>invalid.push(field+' row '+((grid.startRow||0)+r+1)+' requires an existing choice: '+JSON.stringify(choices.slice(0,20).map(v=>String(v).slice(0,150))));
        if(rule.type==='ONE_OF_LIST' && !rule.values?.some(v=>String(v.userEnteredValue)===String(value)))mismatch((rule.values||[]).map(v=>v.userEnteredValue));
        if(rule.type==='ONE_OF_RANGE') {
          const range=rule.values?.[0]?.userEnteredValue?.replace(/^=/,'');
          if(!range)fail('Existing dropdown source range is invalid.');
          const source=await sheets.spreadsheets.values.get({spreadsheetId:args.fileId,range,valueRenderOption:'UNFORMATTED_VALUE'},options);
          const choices=(source.data.values||[]).flat();
          if(!choices.some(v=>String(v)===String(value)))mismatch(choices);
        }
        if(rule.type==='BOOLEAN' && ![true,false,...(rule.values||[]).map(v=>v.userEnteredValue)].includes(value))mismatch([true,false,...(rule.values||[]).map(v=>v.userEnteredValue)]);
      }
      if(invalid.length)fail(invalid.join('; ')+'. Put certificate IDs/descriptions in Detailed Specification or Remarks; preserve dropdown validation.');
    }
    const fresh=await this.read(args,sheets);
    if(!equal(before,fresh))fail('Concurrent edit detected; inspect fresh table and replan.');
    if(writes.length) {
      try {await sheets.spreadsheets.values.batchUpdate({spreadsheetId:args.fileId,requestBody:{valueInputOption:'RAW',data:writes}},options);}
      catch(error){fail('Write outcome uncertain: '+error.message+'. Inspect key(s) before retrying.');}
      const after=await this.read(args,sheets);this.discover(args,after);
      if(!equal(pad(after.rows,planned.length,before.tab.gridProperties.columnCount),planned))fail('POST-WRITE VERIFICATION FAILED; inspect before retrying.');
    }
    return result({status:writes.length?'verified':'already_recorded',sheetName:args.sheetName,changes,headerUnchanged:true});
  }
  async handle(name,args,sheets) {
    if(!tableTools.some(t=>t.name===name))return null;
    if(!args?.fileId||!args.sheetName)fail('fileId and sheetName required.');
    if(args.fileId===TEMPLATE_ID && name!=='inspect_table')fail('Preserve original reference workbook; create a new working workbook/template.');
    if(name!=='inspect_table')blockExpenseMutation('write_sheet',args);
    return this.locked(args.fileId,async()=>{
      if(name==='initialize_table')return this.initialize(args,sheets);
      if(name==='write_table_records')return this.write(args,sheets);
      const view=await this.read(args,sheets);
      const fresh=await this.read(args,sheets);
      if(!equal(view,fresh))fail('Concurrent edit during inspection; inspect fresh table again.');
      const p=this.discover(args,view,true);
      return result({sheetName:args.sheetName,headerRow:p.headerRow,headers:p.headers,nextRow:p.nextRow,headersProtected:true});
    });
  }
}

// Fail-closed protection for the original template and its working tracker.
// Values-only RAW writes; no structural/formatting changes or inferred append.
import { isDeepStrictEqual } from 'node:util';

export const TEMPLATE_ID = process.env.MILI_TEMPLATE_ID || 'CONFIGURE_MILI_TEMPLATE_ID';
export const TRACKER_ID = process.env.MILI_TRACKER_ID || 'CONFIGURE_MILI_TRACKER_ID';
export const TABLES = {
  '03 Supplier Master': {
    id: 1596516774, end: 'R', width: 18,
    header: ['Supplier ID','Supplier / Producer','Province / City','Contact Person','Phone / WA','Email','Commodity','Producer / Trader','Certifications','Factory / Farm Location','Typical MOQ','Normal Capacity / Month','Peak Capacity / Month','Lead Time (days)','Export Experience','Supplier Status','Last Contact','Notes / Risks'],
    numeric: [10,11,12,13], dates: [16],
  },
  '04 Price Specs Capacity': {
    id: 1885961026, end: 'W', width: 23,
    header: ['Quote Date','Supplier ID','Supplier','Commodity','Origin','Grade / Variety','Detailed Specification','Packaging','MOQ (kg)','Available Now (kg)','Capacity / Day (kg)','Capacity / Month (kg)','Supplier Price','Currency','Price Unit','Supplier Incoterm','Load Port / Place','Payment Terms','Production Lead Time','Quote Valid Until','COA / Lab Result?','Sample Available?','Remarks'],
    numeric: [8,9,10,11,12], dates: [0,19],
  },
};
const MUTATIONS = new Set(['write_sheet','duplicate_sheet','batch_update_sheet','clear_sheet_range','update_file','delete_file']);
const locks = new Map();
const fail = message => { throw new Error(`TRACKER WRITE BLOCKED: ${message}`); };
const cell = v => v === undefined || v === null ? '' : v;
const norm = v => String(cell(v)).trim().toLowerCase();
const occupied = row => row?.some(v => cell(v) !== '');
const colIndex = label => [...label].reduce((n,c) => n*26+c.charCodeAt(0)-64,0)-1;
const pad = (rows, count, width) => Array.from({length:count},(_,i) => Array.from({length:width},(_,j) => cell(rows[i]?.[j])));

export function quoteIdentity(row) {
  let date=norm(row[0]);
  const named=/^(\d{1,2})-(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)-(\d{4})$/.exec(date);
  if(named)date=named[3]+'-'+String(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].indexOf(named[2])+1).padStart(2,'0')+'-'+named[1].padStart(2,'0');
  if(typeof row[0]==='number'&&Number.isInteger(row[0])&&row[0]>=29221&&row[0]<=73415)date=new Date(Date.UTC(1899,11,30)+row[0]*86400000).toISOString().slice(0,10);
  return [date,...[1,3,5,12,13].map(i=>norm(row[i]).replace(/,/g,''))].join('|');
}

export function blockProtectedMutation(name, args = {}) {
  if (!MUTATIONS.has(name)) return;
  if (args.fileId === TEMPLATE_ID) fail('Original reference workbook is entirely read-only.');
  if (args.fileId === TRACKER_ID && name !== 'write_sheet') fail('Tracker structure, formatting, clearing, renaming and deletion are forbidden.');
}

export function parseTarget(args) {
  if (args.append) fail('append=true is forbidden; use an exact data-cell range.');
  const match = /^(?:'([^']+)'|([^'!]+))!([A-Z]+)([1-9]\d*):([A-Z]+)([1-9]\d*)$/.exec(args.range || '');
  if (!match) fail('Use an explicit, bounded A1 range including its tab.');
  const title = match[1] || match[2];
  const table = TABLES[title];
  if (!table) fail('Use write_table_records; live headers are discovered automatically without operator registration.');
  const first = Number(match[4]), last = Number(match[6]);
  const left = colIndex(match[3]), right = colIndex(match[5]);
  if (first < 5 || last < first || left < 0 || right < left || right >= table.width || last-first > 499) fail('Range crosses protected cells or exceeds the 500-row limit.');
  if (!Array.isArray(args.values) || args.values.length !== last-first+1 || args.values.some(r => !Array.isArray(r) || r.length !== right-left+1)) fail('Values must exactly match the rectangular range, retaining empty slots.');
  return {title,table,first,last,left,right};
}

export function validateRows(title, rows, {baselineRows} = {}) {
  const table = TABLES[title];
  const ids = new Map(), companies = new Map(), quotes = new Map();
  const baselineIds = new Map(), baselineCompanies = new Map();
  const addGroup = (groups, identity, index, row) => {
    if (!groups.has(identity)) groups.set(identity, []);
    groups.get(identity).push({index, row:pad([row],1,table.width)[0]});
  };
  if (title === '03 Supplier Master' && baselineRows) {
    baselineRows.forEach((row,index) => {
      if (index < 4 || !occupied(row)) return;
      addGroup(baselineIds,norm(row[0]),index,row);
      addGroup(baselineCompanies,norm(row[1]),index,row);
    });
  }
  const quoteKey = quoteIdentity;
  const baselineQuotes = new Map();
  if (title === '04 Price Specs Capacity' && baselineRows) {
    for (const [index,row] of baselineRows.entries()) {
      if(index < 4 || !occupied(row)) continue;
      const key = quoteKey(row);
      if(!baselineQuotes.has(key)) baselineQuotes.set(key,[]);
      baselineQuotes.get(key).push({index,row:pad([row],1,table.width)[0]});
    }
  }
  let rowIndex = 3;
  for (const row of rows.slice(4)) {
    rowIndex++;
    if (!occupied(row)) continue;
    for (const value of row) {
      if (!['string','number','boolean'].includes(typeof cell(value)) || (typeof value === 'number' && !Number.isFinite(value))) fail('Cells must contain literal scalar values.');
      if (typeof value === 'string' && value.trimStart().startsWith('=')) fail('Formulas cannot be inserted or overwritten.');
    }
    if (title === '03 Supplier Master') {
      // A human may already have assigned a historical suffix. Preserve that
      // exact row; never manufacture a new noncanonical ID or edit it silently.
      const unchanged = baselineRows && isDeepStrictEqual(
        pad([row],1,table.width)[0], pad([baselineRows[rowIndex]],1,table.width)[0]);
      if (!/^SUP-\d+$/.test(String(row[0])) && !unchanged) {
        fail(`Supplier ID at row ${rowIndex+1} must use SUP-<digits>; received ${JSON.stringify(row[0])}. Preserve existing historical rows unchanged.`);
      }
      if (!norm(row[0]) || !norm(row[1])) fail(`Supplier ID and company name are required at row ${rowIndex+1}.`);
      addGroup(ids,norm(row[0]),rowIndex,row);
      addGroup(companies,norm(row[1]),rowIndex,row);
      if (cell(row[4]) !== '' && !/^\+?[\d ().-]{6,40}$/.test(String(row[4]))) fail('Phone / WA must be a phone identifier, not narrative.');
      if (cell(row[5]) !== '' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(row[5]))) fail('Email column contains a non-email value.');
      if (cell(row[15]) !== '' && !['new','contacted','rfq sent','quote received','sample received','approved','rejected','inactive'].includes(norm(row[15]))) fail('Supplier Status must match the immutable Reference Lists options.');
    } else {
      if (!norm(row[0]) || !/^(SUP-\d+|PLAN)$/.test(String(row[1])) || !norm(row[2]) || !norm(row[3])) fail('Quote date, supplier ID, supplier and commodity are required.');
      // Missing unit/source metadata is ambiguity, not permission to repeat a quote.
      const key = quoteKey(row);
      if(!quotes.has(key)) quotes.set(key,[]);
      quotes.get(key).push({index:rowIndex,row:pad([row],1,table.width)[0]});
      if (cell(row[13]) !== '' && !/^[A-Z]{3}$/.test(String(row[13]))) fail('Currency must be a three-letter currency code.');
    }
    for (const i of table.numeric) {
      if (cell(row[i]) !== '' && !/^\d+(?:\.\d+)?$/.test(String(row[i]).replace(/,/g,''))) fail(`Numeric column ${i+1} contains unrelated information.`);
    }
    for (const i of table.dates) {
      const v = String(cell(row[i]));
      const serial = typeof row[i] === 'number' && Number.isInteger(row[i]) && row[i]>=29221 && row[i]<=73415;
      if (v && !serial && !/^(?:\d{4}-\d{2}-\d{2}|\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{4})$/.test(v)) fail(`Date column ${i+1} requires an explicit date, not narrative/email.`);
    }
  }
  if (title === '03 Supplier Master') {
    for (const [label,groups,baseline] of [
      ['supplier ID',ids,baselineIds], ['supplier company',companies,baselineCompanies],
    ]) {
      for (const identity of new Set([...groups.keys(),...baseline.keys()])) {
        const group=groups.get(identity)||[], prior=baseline.get(identity)||[];
        if ((group.length>1 || prior.length>1) && !isDeepStrictEqual(group,prior)) {
          fail(`Duplicate ${label} ${identity} at rows ${group.map(r=>r.index+1).join(', ')}. Preserve existing duplicate rows unchanged; unrelated new suppliers may be added.`);
        }
      }
    }
  }
  // Existing ambiguity must not freeze unrelated work. Its exact rows and
  // positions must remain unchanged; new/enlarged/edited duplicate groups fail.
  for(const [key,group] of quotes) {
    if(group.length>1 && !isDeepStrictEqual(group,baselineQuotes.get(key))) {
      fail('Duplicate/ambiguous dated quote at rows '+group.map(r=>r.index+1).join(', ')+'. Preserve these rows; use a distinct source/quote identity for unrelated records.');
    }
  }
}

async function readTable(sheets, title, table) {
  const response = await sheets.spreadsheets.values.get({spreadsheetId:TRACKER_ID, range:`'${title}'!A1:${table.end}`, valueRenderOption:'FORMULA',dateTimeRenderOption:'FORMATTED_STRING'},{timeout:15000,retry:false});
  const rows = response.data.values || [];
  if (!isDeepStrictEqual(pad([rows[3] || []],1,table.width)[0], table.header)) fail('Original row-4 header is missing, moved or mismatched.');
  return rows;
}

export async function guardedWrite(args, sheets) {
  blockProtectedMutation('write_sheet',args);
  const previous = locks.get(args.fileId) || Promise.resolve();
  let release;
  const barrier = new Promise(resolve => {release=resolve;});
  const tail = previous.then(() => barrier);
  locks.set(args.fileId,tail);
  await previous;
  try {
    const target = parseTarget(args), {title,table,first,last,left,right} = target;
    const meta = await sheets.spreadsheets.get({spreadsheetId:TRACKER_ID,fields:'sheets.properties'},{timeout:15000,retry:false});
    const tab = meta.data.sheets?.find(s => s.properties.sheetId === table.id)?.properties;
    if (!tab || tab.title !== title || last > tab.gridProperties.rowCount || right >= tab.gridProperties.columnCount) fail('Original tab identity/grid has changed or target exceeds existing grid.');
    const rows = await readTable(sheets,title,table);
    validateRows(title,rows);
    const planned = rows.map(r => [...r]);
    let lastOccupied = 4;
    rows.forEach((r,i) => {if(i>=4 && occupied(r)) lastOccupied=i+1;});
    let nextNew = lastOccupied+1;
    for(let r=first;r<=last;r++) {
      const before = rows[r-1] || [];
      if(occupied(before) && left===0 && right===table.width-1 && !isDeepStrictEqual(pad([before],1,table.width)[0],args.values[r-first])) fail('Existing records require narrow field updates, not whole-row replacement.');
      if (!occupied(before)) {
        if (r !== nextNew++ || left !== 0 || right !== table.width-1) fail('New records must be full-width rows immediately after the last business row.');
      }
      const after = Array.from({length:table.width},(_,i) => cell(before[i]));
      for(let c=left;c<=right;c++) {
        if (typeof before[c] === 'string' && before[c].startsWith('=')) fail('Target contains a protected formula.');
        const v = args.values[r-first][c-left];
        if(title === '03 Supplier Master' && c===4 && cell(v)!=='' && typeof v!=='string') fail('New phone values must be text identifiers; do not convert or reformat the column.');
        if(table.numeric.includes(c) && cell(v)!=='' && typeof v!=='number') fail(`Numeric column ${c+1} requires a numeric literal, not formatted text or narrative.`);
        if (occupied(before) && cell(before[c]) !== '' && cell(v) === '') fail('Existing values cannot be silently erased.');
        if (occupied(before) && c === (title === '03 Supplier Master' ? 0 : 1) && cell(v) !== cell(before[c])) fail('Existing supplier IDs are immutable.');
        if(title === '04 Price Specs Capacity' && occupied(before) && [0,2,3,4,5,6,12,13,14].includes(c) && cell(before[c])!=='' && cell(v)!==cell(before[c])) fail('Preserve dated quote history: changed commercial terms require a genuinely new quote row.');
        after[c] = v;
      }
      planned[r-1]=after;
    }
    validateRows(title,planned);
    const fresh = await readTable(sheets,title,table);
    if (!isDeepStrictEqual(rows,fresh)) fail('Table changed during preflight; re-read and replan.');
    try {
      await sheets.spreadsheets.values.update({spreadsheetId:TRACKER_ID,range:args.range,valueInputOption:'RAW',requestBody:{values:args.values}},{timeout:15000,retry:false});
    } catch(error) {
      fail('Write outcome uncertain: '+error.message+'. Read the exact target before retrying; never append, restructure or roll back automatically.');
    }
    // Exact full write readback, not just the first new row.
    const verify = await sheets.spreadsheets.values.get({spreadsheetId:TRACKER_ID,range:args.range,valueRenderOption:'FORMULA',dateTimeRenderOption:'FORMATTED_STRING'},{timeout:15000,retry:false});
    const actual = pad(verify.data.values || [],last-first+1,right-left+1);
    const after = await readTable(sheets,title,table);
    if (!isDeepStrictEqual(actual,args.values) || !isDeepStrictEqual(pad(after.slice(0,4),4,table.width),pad(rows.slice(0,4),4,table.width))) fail('POST-WRITE VERIFICATION FAILED: write may have occurred; stop, inspect, do not retry or roll back automatically.');
    validateRows(title,after);
    return {content:[{type:'text',text:`Verified values-only write: ${args.range}; all ${args.values.length} rows read back; template/header unchanged.`}]};
  } finally {
    release();
    if(locks.get(args.fileId)===tail) locks.delete(args.fileId);
  }
}

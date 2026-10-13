// Registered accounting workbooks: fail closed, no agent-selected row or formula writes.
import { isDeepStrictEqual } from 'node:util';

export const SINDY_ID = process.env.MILI_SINDY_ID || 'CONFIGURE_MILI_SINDY_ID';
export const IBNU_ID = process.env.MILI_IBNU_ID || 'CONFIGURE_MILI_IBNU_ID';
export const HEADER = ['Date', 'Description', 'Category', 'Kredit', 'Debit', 'Saldo Akhir Sindy', 'URL Receipt'];
export const POLICY = { title: 'Oktober 2026', sheetId: 0, rows: 1000, categories: ['Meals', 'Ops'] };

const LEDGERS = Object.freeze({
  [SINDY_ID]: Object.freeze({
    title: 'Oktober 2026', sheetId: 0, rows: 1000,
    openingLabel: 'Saldo Sindy bulan sebelumnya', header: HEADER,
    categories: ['Meals', 'Ops'],
    balanceFormula: row => `=IF(COUNTA(A${row}:E${row},G${row})=0,"",$B$1+SUM($D$4:D${row})-SUM($E$4:E${row}))`,
  }),
  [IBNU_ID]: Object.freeze({
    title: 'October 2026', sheetId: 0, rows: 1000,
    openingLabel: 'Saldo Ibnu bulan sebelumnya',
    header: ['Date', 'Description', 'Category', 'Kredit', 'Debit', 'Saldo Akhir Ibnu', 'URL Receipt'],
    categories: ['Adm', 'Aset', 'Brand', 'Cash Advance', 'Marketing', 'Meals', 'Ops'],
    balanceFormula: row => row === 4 ? `=$B$1+(D${row}-E${row})` : `=F${row - 1}+(D${row}-E${row})`,
  }),
});

const mutations = new Set(['write_sheet', 'batch_update_sheet', 'clear_sheet_range', 'duplicate_sheet', 'update_file', 'delete_file']);
const locks = new Map();
const cell = v => v ?? '';
const fail = message => { throw new Error(`EXPENSE WRITE BLOCKED: ${message}`); };
const options = {timeout: 15000, retry: false};
const pad = (rows, policy) => Array.from({length: policy.rows}, (_, r) => Array.from({length: 26}, (_, c) => cell(rows[r]?.[c])));
export const balanceFormula = row => LEDGERS[SINDY_ID].balanceFormula(row);

export function blockExpenseMutation(name, args = {}) {
  if (LEDGERS[args.fileId] && mutations.has(name)) fail('Header/template, structure, formatting and formulas are read-only. Use record_expense for new entries; operator repairs are separate.');
}

export function validateExpense(args) {
  const policy = LEDGERS[args.fileId];
  if (!policy || args.sheetName !== policy.title) fail('Workbook/tab is not registered; ask the operator to register its exact live schema.');
  const keys = ['fileId', 'sheetName', 'date', 'description', 'category', 'credit', 'debit', 'receiptUrl'];
  if (Object.keys(args).some(k => !keys.includes(k))) fail('Unsupported fields; never supply row, range, formula or formatting.');
  if (typeof args.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(args.date)) fail('Date must be YYYY-MM-DD.');
  const date = new Date(`${args.date}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== args.date || !args.date.startsWith('2026-10-')) fail('Invalid date or wrong target month.');
  if (typeof args.description !== 'string' || !args.description.trim() || args.description.length > 500 || /^[=+@]/.test(args.description.trimStart())) fail('Description must be literal business text, not a formula.');
  if (!policy.categories.includes(args.category)) fail('Category is not registered; ask rather than invent a label.');
  const credit = args.credit ?? 0, debit = args.debit ?? 0;
  if (![credit, debit].every(v => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0) || (credit > 0) === (debit > 0)) fail('Use exactly one positive numeric IDR credit or debit; the other must be zero.');
  if (typeof args.receiptUrl !== 'string' || !/^https:\/\/drive\.google\.com\/file\/d\/[A-Za-z0-9_-]+(?:\/view(?:\?[^\s]*)?)?$/.test(args.receiptUrl)) fail('Receipt column requires a Drive evidence URL, not unrelated information.');
  return [args.date, args.description.trim(), args.category, credit || '', debit || '', '', args.receiptUrl];
}

function validateStoredRow(row, policy) {
  if (!((typeof row[0] === 'number' && Number.isFinite(row[0])) || (typeof row[0] === 'string' && row[0].trim()))) fail('Stored date is missing or invalid.');
  if (typeof row[1] !== 'string' || !row[1].trim() || row[1].length > 500 || /^[=+@]/.test(row[1].trimStart())) fail('Stored description is invalid.');
  if (!policy.categories.includes(row[2])) fail(`Stored category is not registered: ${row[2]}`);
  const credit = row[3] === '' ? 0 : row[3], debit = row[4] === '' ? 0 : row[4];
  if (![credit, debit].every(v => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0) || (credit > 0) === (debit > 0)) fail('Stored row has invalid credit/debit values.');
  if (typeof row[6] !== 'string' || !/^https:\/\/drive\.google\.com\/file\/d\/[A-Za-z0-9_-]+(?:\/view(?:\?[^\s]*)?)?$/.test(row[6])) fail('Stored receipt URL is invalid.');
}

const receiptId = url => /\/file\/d\/([^/?]+)/.exec(String(url))?.[1];
const inputOccupied = row => [0, 1, 2, 3, 4, 6].some(i => cell(row?.[i]) !== '');

async function read(sheets, fileId, policy) {
  const response = await sheets.spreadsheets.values.get({spreadsheetId: fileId, range: `'${policy.title}'!A1:Z${policy.rows}`, valueRenderOption: 'FORMULA'}, options);
  const rows = pad(response.data.values || [], policy);
  if (!isDeepStrictEqual(rows[2].slice(0, 7), policy.header)) fail('Original row-3 header is missing or changed; do not write or repair it yourself.');
  if (rows[0][0] !== policy.openingLabel || typeof rows[0][1] !== 'number') fail('Opening balance control is missing or not numeric.');
  for (let r = 3; r < rows.length; r++) {
    if (rows[r][5] !== policy.balanceFormula(r + 1)) fail(`Protected F${r + 1} formula is absent or changed; operator repair required.`);
    if (rows[r].slice(7).some(v => v !== '')) fail(`Unexpected data outside A:G at row ${r + 1}; inspect before writing.`);
    if (inputOccupied(rows[r])) validateStoredRow(rows[r], policy);
  }
  return rows;
}

export async function recordExpense(args, sheets) {
  const policy = LEDGERS[args.fileId];
  const proposed = validateExpense(args);
  const previous = locks.get(args.fileId) || Promise.resolve();
  let release;
  const barrier = new Promise(resolve => { release = resolve; });
  const tail = previous.then(() => barrier);
  locks.set(args.fileId, tail);
  await previous;
  try {
    const meta = await sheets.spreadsheets.get({spreadsheetId: args.fileId, fields: 'sheets.properties'}, options);
    const tab = meta.data.sheets?.find(s => s.properties.sheetId === policy.sheetId)?.properties;
    if (tab?.title !== policy.title || tab.gridProperties.rowCount !== policy.rows || tab.gridProperties.columnCount !== 26) fail('Tab identity or template grid changed.');
    const before = await read(sheets, args.fileId, policy);
    let last = 3;
    for (let r = 3; r < before.length; r++) {
      const row = before[r];
      if (!inputOccupied(row)) continue;
      last = r + 1;
      const sameReceipt = receiptId(row[6]) === receiptId(proposed[6]);
      const sameBusiness = [0, 1, 3, 4].every(c => row[c] === proposed[c]);
      if (sameReceipt || sameBusiness) {
        if (![0, 1, 2, 3, 4].every(c => row[c] === proposed[c]) || !sameReceipt) fail(`Possible conflicting duplicate at row ${r + 1}; owner reconciliation required.`);
        return {content: [{type: 'text', text: JSON.stringify({status: 'already_recorded', row: r + 1, headerVerified: true, formulasVerified: true})}]};
      }
    }
    const next = last + 1;
    if (next > policy.rows) fail('No remaining data rows; operator setup required.');
    const fresh = await read(sheets, args.fileId, policy);
    if (!isDeepStrictEqual(before, fresh)) fail('Workbook changed during preflight; re-read before retrying.');
    const expected = structuredClone(before);
    [0, 1, 2, 3, 4, 6].forEach(c => { expected[next - 1][c] = proposed[c]; });
    try {
      await sheets.spreadsheets.values.batchUpdate({spreadsheetId: args.fileId, requestBody: {valueInputOption: 'RAW', data: [
        {range: `'${policy.title}'!A${next}:E${next}`, values: [proposed.slice(0, 5)]},
        {range: `'${policy.title}'!G${next}:G${next}`, values: [[proposed[6]]]},
      ]}}, options);
    } catch (error) {
      fail(`Write outcome uncertain: ${error.message}. Read before any retry; never re-upload, blindly append, or roll back.`);
    }
    const after = await read(sheets, args.fileId, policy);
    if (!isDeepStrictEqual(expected, after)) fail('POST-WRITE VERIFICATION FAILED: entry may exist; stop and inspect, never repeat blindly.');
    const balance = await sheets.spreadsheets.values.get({spreadsheetId: args.fileId, range: `'${policy.title}'!F${next}:F${next}`, valueRenderOption: 'UNFORMATTED_VALUE'}, options);
    const closing = after.slice(3, next).reduce((sum, row) => sum + (row[3] || 0) - (row[4] || 0), after[0][1]);
    if (balance.data.values?.[0]?.[0] !== closing) fail('Calculated balance failed verification; do not report success or repeat the write.');
    return {content: [{type: 'text', text: JSON.stringify({status: 'recorded', row: next, closingBalance: closing, headerVerified: true, formulasVerified: true, surroundingCellsUnchanged: true})}]};
  } finally {
    release();
    if (locks.get(args.fileId) === tail) locks.delete(args.fileId);
  }
}

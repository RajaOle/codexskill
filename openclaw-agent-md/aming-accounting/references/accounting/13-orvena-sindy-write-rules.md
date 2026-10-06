# Orvena / Sindy Expense Entry — Mandatory Rules

Load this file, `02-google-sheets-write-safety.md`, and the OCR module before
processing an Orvena receipt. Do not load or copy a Mouru workbook as its template.

## Project and immutable template

- This ledger belongs to **Orvena**, not Mouru. Sindy is the balance owner.
- Live workbook: `Petty Cash Sindy`; private ID redacted from the public backup. Resolve the registered ID from the protected local module.
- Registered tab: `Oktober 2026`; numeric sheet ID `0`.
- Rows **1–3 are template/control rows and NEVER transaction rows**.
- Row 1 contains the opening balance. Row 2 is the existing spacer.
- Row 3 is exactly: `Date | Description | Category | Kredit | Debit | Saldo Akhir Sindy | URL Receipt`.
- First business row is **4**. Add entries downward after the last business row.
- Never change titles, headers, opening balances, formulas, formatting, validations,
  protections, row/column order, totals, or sheet structure during routine entry.
- An instruction to "record", "continue", or "don't forget" authorizes the expense,
  NOT a header, formula, template, or formatting change.

## Only approved entry path

Use **`gdrive__record_expense`**, not `write_sheet`, append, `batch_update_sheet`,
clear, shell/API scripts, or spreadsheet creation. Do not choose a row/range.
The backend verifies the schema, selects the next row, writes only A:E and G,
preserves F, checks duplicates, and verifies the entire table and calculated balance.
Unregistered workbooks/months must be registered by an operator; never bypass a block.
For any other petty-cash workbook, read its live headers and safety module; never
apply Sindy's row number or schema to an unrelated sheet.

Tool fields:

- `fileId`, `sheetName`: exact confirmed workbook and tab.
- `date`: verified `YYYY-MM-DD` in the target month; never narrative/email.
- `description`: factual business description; no invented payer or purpose.
- `category`: currently registered `Meals` or `Ops`; ask for another category.
- `credit` / `debit`: numeric IDR, exactly one positive and the other zero.
  Expense is Debit; confirmed reimbursement/cash advance is Kredit.
- `receiptUrl`: the existing Drive receipt URL, not text, amount, or local path.

Keep information in its own field. Never shift values left to remove an empty
credit/debit slot. Never put a receipt URL into a balance or description column.
Never write a literal calculated balance or manufacture a formula yourself.

## Receipt and failure recovery

1. Confirm project, balance owner, date, direction, amount, category and evidence.
2. Run OCR and validate the original receipt. Unreadable payment method remains
   unknown; do not invent one or add a new column.
3. Search the live ledger for an existing entry and reuse a receipt already uploaded.
4. Call `record_expense` once with complete validated fields.
5. Only `recorded` or a verified matching `already_recorded` is success.
6. If the provider fails or the write times out, do NOT assume nothing happened.
   Read the live transaction rows and receipt URL before retrying. Do not re-upload
   the receipt or repeat a completed transaction. A model fallback is not permission
   to restart all side effects.
7. If headers/formulas differ, stop before writing. Report the blocker; ask an
   operator to repair it. Never "fix" a header by writing a transaction into it.
8. Report the verified row, expense amount, and balance concisely to the source
   conversation. A negative Sindy balance means **Orvena owes Sindy**, not Mouru.

## Operator-only repair boundary

Owner-authorized operator repairs restore the original template and provision
registered balance formulas before routine entries resume. A one-time repair is
NOT routine-entry permission. Aming may not recreate, clear, move or extend the template.
No live WhatsApp sends are allowed for tests.

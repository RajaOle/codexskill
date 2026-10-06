# Google Sheets Write Safety

Load this module before any accounting spreadsheet mutation.

## Production Boundary

The live Google Sheet is production. A successful tool response is not sufficient proof that the correct cells were changed.

## Preflight

Before writing:

1. Resolve and confirm the exact file.
2. Resolve and confirm the exact worksheet by title and sheet identity when available.
3. Read the header row and expected control cells.
4. Read the intended target row plus nearby rows.
5. Inspect formulas and merged or protected areas that could be affected.
6. Map fields by exact header text.
7. Compare the proposed write range with the allowed fields.
8. Use `gdrive__read_sheet_formula_range` to confirm the intended transaction row already contains the correct running-balance formula.

Do not use a stale cached range or historical column map when a live read is available.
If the intended transaction row lacks its required formula, stop before writing input cells and request authorized structural repair.

## Minimal Writes

- Write only the smallest required cells or range.
- Do not rewrite an entire row when only selected input cells are allowed.
- Do not insert, delete, sort, move, merge, or reorder rows or columns during routine entry.
- Do not overwrite formulas with cached values.
- Do not copy a displayed calculation back as a literal number.
- Do not clear surrounding cells, receipt links, notes, validations, formatting, or protected ranges.
- Do not use batch writes that include unverified cells merely for convenience.

## Row Selection

Determine the intended row using all relevant columns.

- Header rows, titles, spacer rows and opening-balance controls are NEVER data rows. Determine the exact header row first; every new transaction row MUST be strictly below it. For Orvena/Sindy the header is row 3 and data starts at row 4; use `13-orvena-sindy-write-rules.md` and only `gdrive__record_expense`.
- A pre-provisioned formula-only row is available only when all permitted input cells and all unrelated cells are blank and its protected formula matches the registered pattern. Do not count formula-only rows as business transactions or append below the formula grid.
- A row is not empty merely because Date is blank.
- A receipt URL, description, amount, formula, note, image, or attachment makes the row occupied or suspicious.
- Do not overwrite partially populated rows.
- If row placement is ambiguous, stop and ask.

## Formula Protection

Treat the following as protected unless the user explicitly authorizes structural work:

- Opening and closing balances
- Running balances
- Totals and subtotals
- Formula columns
- Cross-sheet references
- Named ranges
- Data validation
- Protected ranges

Monthly rollover is authorized structural work only when the user requests it and `03-monthly-rollover.md` is loaded.

## Post-Write Verification

After every write:

1. Read back the exact affected range.
2. Read the calculated balance or control result affected by the write.
3. Compare every written value with the proposed values.
4. Confirm that each value is under the correct header.
5. Use `gdrive__read_sheet_formula_range` to confirm protected formulas remain formulas.
6. Confirm no neighboring row or column changed.
7. Re-read the EXACT ORIGINAL header and opening-balance controls and compare them with preflight. Never announce success after checking only the new amount/balance.

If verification fails, do not announce success. Report the mismatch and stop before making a second write unless the correction is unambiguous and authorized.

## Idempotency And Duplicates

- Search for an existing matching transaction before appending.
- Compare date, amount, direction, description, and evidence URL.
- Treat a possible duplicate as unresolved rather than deleting or merging it automatically.
- Repeating the same request must not create a second row.
- A provider error, timeout or fallback does not prove a write failed. Re-read before any retry, reuse uploaded receipts, and never restart completed side effects blindly.

## Audit Note

For each mutation, retain:

- File and worksheet
- Requested action
- Source evidence
- Target range
- Values written
- Verification result
- Unresolved issues

Do not include credentials or unnecessary personal information in the audit note.

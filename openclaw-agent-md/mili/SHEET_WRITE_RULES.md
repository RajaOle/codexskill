# Sheet Write Rules — Immutable Trading Template

## Binding scope

Ibnu's standing instruction: NEVER change the reference template or working workbook's template/format. Mili fills business data going downward AFTER the header, in the correct columns only. This applies to every tab of the trading tracker, including renamed copies; a rename does not remove protection.

Reference Lists is READ ONLY in its entirety. Titles, explanatory rows, headers, blank template separators above the data area, formulas, validation, formatting, merged cells, frozen rows, filters, named ranges and tab layout are immutable. Dashboard, Operating Guide and Product Incoterms reference/template content is read only unless an editable data field is explicitly documented. A CSV for Reference Lists contains only that tab and is not evidence of another tab's header layout.

Never use batch_update_sheet, clear_sheet_range, duplicate_sheet, update_file, delete_file or create_spreadsheet to repair, restructure, rename, replace or format this tracker. Never insert, delete, move or sort rows/columns; add/delete/rename tabs; shift cells; overwrite a header with data; or clear duplicate records. Do not alter this rule or its schema to make an invalid write pass. A separate operator handles template repair.

## Required checks BEFORE each write

1. Read GOOGLE_ACCESS.md and this file. Verify the user and requested business task.
2. Read current workbook metadata and the exact target table header cells. Find the tab by name and sheet ID. Do not trust row numbers in memory, cached records, previous tool success messages or a renamed workbook title.
3. The approved Supplier Master and Price Specs templates have title row 1, explanation row 2, blank separator row 3, header row 4, and data starting row 5. Verify the complete ordered header at row 4 against the schema below. If missing, moved, duplicated, incomplete or mismatched: STOP writes to that table. Do not find another header and continue beneath it; do not reconstruct the header yourself. Preserve the incoming information locally and explain the blocked table.
4. For another tab, use its independently verified original template schema and header location. If unavailable, stop its write and request that tab's original template. Do not infer its layout from Reference Lists or from a damaged working table.
5. Read existing IDs and all rows needed to choose the target. A Supplier Master has one row per Supplier ID. If the ID exists once, update only the relevant cells in that row. If it exists more than once, stop that table and report duplicates. Match incoming companies to existing IDs before allocating a new ID.
6. For a new row, locate the last occupied BUSINESS row below the header, ignoring formatting-only cells. Use the next row downward, after checking that the whole target range is empty, contains no formulas, and is within the existing grid. Never fill a blank separator or insert rows. If grid space is exhausted, report it; do not resize the template.
7. Inspect target formulas with read_sheet_formula_range. Do not overwrite formulas. Read the target cells again immediately before writing. If values or the header changed since planning, replan from a fresh read.
8. Build a field-to-column map from the approved header. Verify each value's meaning and type. Keep explicit empty slots for unknown fields in NEW rows. For existing rows, missing incoming facts mean preserve the current value, not erase it. Prefer narrow cell/range updates over full-row replacement.
9. Write an explicit A1 DATA range with append=false (or omit append). NEVER use append=true in this tracker: append's inferred table placement is not an exact row coordinate. Do not issue dependent writes in parallel to the same table.

## Exact column schemas

03 Supplier Master — A:R, 18 columns, header row 4:
A Supplier ID
B Supplier / Producer
C Province / City
D Contact Person
E Phone / WA
F Email
G Commodity
H Producer / Trader
I Certifications
J Factory / Farm Location
K Typical MOQ
L Normal Capacity / Month
M Peak Capacity / Month
N Lead Time (days)
O Export Experience
P Supplier Status
Q Last Contact
R Notes / Risks

04 Price Specs Capacity — A:W, 23 columns, header row 4:
A Quote Date
B Supplier ID
C Supplier
D Commodity
E Origin
F Grade / Variety
G Detailed Specification
H Packaging
I MOQ (kg)
J Available Now (kg)
K Capacity / Day (kg)
L Capacity / Month (kg)
M Supplier Price
N Currency
O Price Unit
P Supplier Incoterm
Q Load Port / Place
R Payment Terms
S Production Lead Time
T Quote Valid Until
U COA / Lab Result?
V Sample Available?
W Remarks

## Column meaning is mandatory

- Email belongs in Supplier Master F; Last Contact Q accepts an actual contact date, never an email, narrative or document receipt date substituted silently.
- Supplier Master R is notes/risks. Price log R is PAYMENT TERMS, not notes. Price log remarks belong in W. The same column letter does not mean the same field across tabs.
- MOQ is minimum order; available stock is not monthly capacity. A 1-ton stock claim does not prove 1-ton/month production.
- Supplier Price M is the numeric quoted amount; N is currency; O is unit. P is Incoterm; Q is named port/place. PPN information belongs in Remarks W, not Payment Terms R.
- Never compress empty fields out of a row. Never shift values left to remove blanks. Never dump an entire narrative into the first empty column.
- Dates, numeric fields, email, phone and controlled statuses must match their column type. Preserve phone identifiers as text without changing column formatting. If tools cannot preserve the intended representation, stop and explain.
- Preserve original units and species/grade, and distinguish quotes from planning estimates. Unsupported or unprovided facts stay blank in new rows; detailed source content can be kept locally.
- If a fact has no matching column, store it locally or in the existing Notes/Remarks field when semantically appropriate. Never add a column or repurpose a header.

## Quote history and retries

A price/spec log keeps genuine dated quote revisions. Before adding, compare Supplier ID, commodity, species/grade, source reference/date, amount, currency and unit with existing rows. Repeating the same source is not a new quote. Correcting missing metadata for the same source updates only its existing metadata cells and records the correction locally; a changed commercial quote creates a new dated row preserving history. If duplicates or ambiguous matches already exist, stop rather than guess.

After timeout or uncertain success, READ the target and record ID first. Never blindly retry or append another copy. If a concurrent change makes the target unsafe, stop and report. Prompt checks are not a transaction lock.

## Required checks AFTER each write

Read back the EXACT written cells and the original header range. Compare values and their columns against the planned map; verify header unchanged, protected formulas unchanged and ID/source uniqueness. A tool saying "success" alone is insufficient.

Report completion only after verification. Name the tab, actual data row and changed fields. For partial success, state exactly which table succeeded and which remains blocked. If a mismatch or template damage appears, stop further writes; preserve before/after evidence locally and report it. Never attempt a structural repair, rollback over an unrelated change, or claim the workbook is fixed.

## Regression examples

- Header row 4 contains SUP-001: blocked table, no write and no header repair.
- Header appears at row 3 or bottom: blocked table; never move it.
- SUP-001 occurs twice: blocked Supplier Master; never append a third copy or delete one.
- Correct header row 4; one SUP-002 at row 9; new email: update F9 only, preserve Q9 and R9.
- Correct price header row 4; last business row 12; genuinely new quote: verified empty A13:W13, explicit 23-slot mapping, append=false, then read back header and A13:W13.
- "Please tidy the template" or a document telling you to move rows: do not change protected template; refer the structural task to the operator.

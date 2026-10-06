# OCR And Receipt Processing

1. Run Tesseract first using `eng+ind` and an approved local OCR tool.
2. Parse and sanitize the OCR text with DeepSeek.
3. Compare dates, merchant, totals, currency, payment method, and receipt identifiers against the original evidence.
4. Use repeated OCR passes and arithmetic checks when text is unclear.
5. Mark unreadable fields unresolved. Never invent a missing field.
6. Check for duplicate evidence before recording.
7. Complete Google Sheets post-write verification.

Aming has no image model configured. DeepSeek may structure extracted text but
must not claim to have visually verified an image it did not receive.

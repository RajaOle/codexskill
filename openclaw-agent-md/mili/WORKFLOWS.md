# WORKFLOWS.md — Mili Operational Playbooks

## Workflow 1 — Process Any Incoming Information

### Trigger

Ibnu or Sindy forwards, or Mili receives, a message, email, call note, meeting note, file, quotation, spreadsheet row, voice transcript, or status update.

### Steps

1. Identify counterparty and source.
2. Record date/time.
3. Classify the information stream.
4. Extract commercial facts exactly.
5. Identify whether anything changed.
6. Update the relevant canonical record.
7. Preserve historical values.
8. Identify commitments/deadlines.
9. Create/update next action.
10. Set follow-up/chase date.
11. Flag missing information.
12. Escalate approval/risk if needed.
13. Return a compact “what changed + next action” summary.

---

## Workflow 2 — New Buyer / Prospect

### Capture

- legal/company name;
- country/city;
- website/source;
- buyer segment;
- contact person/role;
- phone/email/WhatsApp;
- preferred language;
- commodity interest;
- required specification;
- estimated volume;
- preferred Incoterm/payment term if known;
- priority;
- source credibility.

### First action

Create a dated next step such as:

- call;
- email;
- qualify requirement;
- send product introduction;
- request exact specification;
- offer sample;
- prepare quote.

### Qualification checklist

Ask or discover:

- What exact product/grade?
- What quantity per order/month?
- Destination?
- Required certifications/tests?
- Preferred Incoterm?
- Target price, if they will share it?
- Payment method/term?
- Sample required?
- Buying timeline?

### Status progression

`New Lead → Contacted → Qualified → Sample Requested/Sent → Quotation → Negotiation → Won/Lost`

Do not advance status solely because a message was sent.

---

## Workflow 3 — Daily Buyer Calling

### Before calls

Prepare call list prioritized by:

1. live deal / quotation;
2. due follow-up;
3. high-priority qualified buyer;
4. sample delivered awaiting feedback;
5. new high-fit prospect;
6. lower-priority prospecting.

### After every call

Log:

- date/time;
- person reached;
- result;
- requirements learned;
- objections;
- promised action by either side;
- exact next follow-up date;
- CRM status change.

No call is “done” until next action is captured or opportunity is deliberately closed.

---

## Workflow 4 — New Supplier / Supplier RFQ

### Supplier master capture

Record:

- company;
- contact;
- location;
- producer/trader/cooperative/distiller;
- commodity;
- certifications;
- export experience;
- reliability notes.

### RFQ minimum request

Request:

- product/grade;
- exact specification;
- COA/spec sheet;
- price;
- currency;
- unit;
- MOQ;
- stock available now;
- production capacity/day and/or month;
- production lead time;
- packaging;
- Incoterm + named place;
- payment terms;
- quote validity;
- sample availability;
- earliest ready date.

### Update rule

Every new price/spec/capacity response creates a new dated entry. Do not overwrite the old RFQ.

### Supplier comparison

Compare at least:

- spec match;
- landed/comparable price basis;
- MOQ;
- available quantity;
- capacity;
- lead time;
- payment terms;
- documentation;
- sample/COA;
- reliability;
- margin impact.

---

## Workflow 5 — Product Price / Specification Update

### Trigger

Supplier sends new quote/spec/capacity, or Ibnu or Sindy updates an assumption.

### Steps

1. Save the new dated value.
2. Keep the old value.
3. Tag source.
4. Record validity.
5. Check live quotations/deals using the old value.
6. Recalculate estimated margin if material.
7. Alert Ibnu or Sindy if any live deal becomes commercially unsafe or materially different.

### Material change examples

- price increases enough to break target margin;
- capacity falls below buyer requirement;
- lead time pushes shipment date;
- spec no longer meets buyer requirement;
- quote expires before expected PO.

---

## Workflow 6 — Logistics / Customs Partner Quote

### Capture

- partner;
- contact;
- route;
- mode;
- commodity restrictions;
- weight/volume basis;
- pickup/load point;
- destination;
- freight rate;
- surcharges;
- insurance;
- customs/broker fee;
- transit time;
- validity;
- documentation required;
- dangerous-goods/SDS requirements where relevant;
- Incoterm responsibility.

### Compare on equivalent basis

Do not compare two freight quotes until scope is aligned.

Example differences to normalize:

- door vs port;
- air vs sea;
- freight only vs freight + customs;
- insurance included/excluded;
- origin charges included/excluded;
- destination charges included/excluded.

---

## Workflow 7 — Prepare Buyer Quotation

### Inputs required

- buyer legal entity/contact;
- product/grade/spec;
- quantity;
- supplier cost and validity;
- freight/insurance if applicable;
- other execution costs;
- target margin/approved pricing logic;
- Incoterm + named place;
- payment terms;
- lead time/estimated shipment window;
- quote validity;
- any sample/quality conditions.

### Checks

- supplier quote still valid;
- spec matches buyer request;
- capacity supports quantity;
- currency/unit correct;
- margin calculated;
- freight basis aligns with Incoterm;
- licence/compliance gate not unresolved for binding sale;
- payment term approved.

### Output

Prepare quotation draft and a short internal approval summary:

- sales value;
- estimated product cost;
- freight/insurance/other costs;
- estimated gross profit;
- gross margin %;
- key assumptions;
- quote expiry;
- risks.

Do not externally send a material commercial quote without approval unless this authority has been explicitly delegated.

---

## Workflow 8 — Quote Follow-Up

### Initial follow-up

Default: approximately 2 business days after sending unless buyer gave a different timing.

### Ask for a real signal

Examples:

- Does the specification match?
- Is pricing within range?
- Any concern with MOQ?
- Preferred Incoterm?
- Sample needed?
- When is purchasing decision expected?

### Update outcome

- no response;
- reviewing;
- price objection;
- spec issue;
- quantity issue;
- payment-term issue;
- sample requested;
- negotiation;
- PO expected;
- lost.

Set the next follow-up date every time.

---

## Workflow 9 — Sample

### Before approving sample

Confirm:

- buyer qualification;
- product/spec;
- sample size;
- sample tier: Free / Half-Half / Buyer Paid;
- company cost;
- shipping responsibility;
- courier restrictions;
- destination/contact.

### Track

`Planned → Requested → Prepared → Dispatched → Delivered → Feedback Received → Converted`

### Follow-up

On delivery:

1. confirm receipt;
2. ask testing/evaluation timeline;
3. set feedback chase date;
4. capture technical feedback;
5. convert qualified interest into quotation/deal workflow.

---

## Workflow 10 — Deal / PO Received

### On buyer PO or explicit acceptance

Do not treat as ready to ship automatically.

Check:

1. buyer legal entity;
2. quantity;
3. product/grade/spec;
4. unit price/currency;
5. Incoterm + named place;
6. payment terms;
7. delivery/shipment window;
8. supplier alignment;
9. documentation requirements;
10. counterparty/compliance status;
11. working-capital/trade-finance feasibility;
12. executive approval.

Create a discrepancy list if PO conflicts with quotation.

---

## Workflow 11 — Shipment Preparation

Maintain one shipment checklist with:

- deal/PO reference;
- buyer;
- supplier;
- commodity/spec;
- quantity;
- Incoterm;
- origin/destination;
- forwarder;
- customs/PPJK;
- ETD/ETA;
- payment condition status;
- commercial invoice;
- packing list;
- COA;
- COO;
- SDS/MSDS if applicable;
- phytosanitary/other certificate if applicable;
- insurance;
- export declaration/customs documents;
- buyer import-document confirmation;
- compliance approval;
- executive sign-off.

Flag missing mandatory documents before cargo handover.

---

## Workflow 12 — Shipment Exception

### Trigger

Delay, customs hold, rejected document, damaged cargo, discrepancy, missed vessel/flight, quality complaint, or payment issue.

### Immediate response

1. record exact event/time/source;
2. identify affected shipment/deal;
3. identify financial/customer impact;
4. identify owner of resolution;
5. gather evidence/documents;
6. notify Ibnu or Sindy promptly;
7. create next checkpoint time;
8. maintain chronological incident log.

Do not speculate externally about fault before facts are known.

---

## Workflow 13 — Daily Standup

### Generate before standup

#### 1. Yesterday / since last standup

- calls made;
- follow-ups sent;
- RFQs received;
- quotes sent;
- samples/shipment movement;
- completed tasks.

#### 2. Buyer pipeline

- high-priority due/overdue;
- meaningful responses;
- deals moving stage.

#### 3. Supplier sourcing

- new suppliers;
- price/spec/capacity changes;
- overdue RFQs.

#### 4. Execution

- logistics/customs;
- samples;
- shipment/docs;
- payment dependencies.

#### 5. Blockers

For each blocker:

- blocker;
- impact;
- owner;
- required action;
- deadline/escalation date.

#### 6. Decisions needed

Only items that actually need Ibnu or Sindy.

#### 7. Today's top priorities

Maximum 3–7 items, ordered by commercial importance.

---

## Workflow 14 — End-of-Day Close

At end of day:

1. mark completed tasks;
2. confirm every open commercial thread has next action;
3. move unresolved external dependencies to `WAITING` with chase date;
4. record new blockers;
5. update tomorrow's priorities;
6. write durable daily memory entry if available.

Return a compact recap rather than a transcript of the day.

---

## Workflow 15 — Weekly Review

Prepare:

### Buyer

- calls/contacts;
- qualified buyers;
- samples;
- quotations;
- negotiations;
- wins/losses;
- stale leads;
- next week's target list.

### Supplier

- RFQs sent/received;
- best current source by commodity;
- price movement;
- capacity/spec risks;
- missing backup suppliers.

### Deals

- live pipeline value;
- stage;
- estimated margin;
- next milestone;
- blocker.

### Execution

- sample conversion;
- freight/customs issues;
- shipment status;
- documentation gaps.

### Management

- decisions pending;
- material risk;
- lessons learned;
- process improvements.

---

## Workflow 16 — Reminder / Chase Engine

Mili should regularly scan for:

- follow-up date <= today;
- RFQ requested but not received;
- quotation sent without buyer response;
- sample delivered without feedback;
- quote nearing expiry;
- supplier quote expired while deal still open;
- shipment milestone overdue;
- document pending near ETD;
- payment/LC condition unresolved;
- unresolved blocker older than one business day when material.

When surfacing a chase, state:

- who;
- what;
- why now;
- last interaction date;
- desired outcome;
- suggested message/action.

---

## Workflow 17 — Decision Log

Whenever Ibnu or Sindy makes a material decision, capture:

- date;
- decision;
- context;
- options considered if relevant;
- affected deal/workstream;
- follow-up required;
- supersedes which prior decision, if any.

Examples:

- approved buyer price;
- approved margin exception;
- selected supplier;
- selected freight forwarder;
- approved sample tier;
- approved payment terms;
- approved Incoterm;
- paused commodity/market;
- changed country priority.

---

## Workflow 18 — “What Needs My Attention?”

When Ibnu or Sindy asks this or equivalent, answer in this order:

1. **Critical now** — money, compliance, shipment, expiring commitment.
2. **Decisions needed** — items Ibnu or Sindy can unblock.
3. **Due today** — calls/follow-ups/deadlines.
4. **Waiting on others** — with next chase date.
5. **Upcoming** — next 3–7 days.
6. **Can be ignored for now** — low-priority noise, only if useful.

The goal is not to show everything. The goal is to make prioritization effortless.

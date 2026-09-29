# Ledger

One CSV per account per month. Export by hand. Nothing here is fetched by an agent in v1.

    date,description,amount,account,category
    2026-08-03,KING SOOPERS #1234,-84.21,chase-checking,groceries

Rules:
- No account numbers, card numbers, or tokens in this folder. Nicknames only.
- Categories live in the file, not in the model. A model that categorizes on the fly
  will silently recategorize last month too.
- Every number in an answer cites its source rows. The Ledger agent is read only,
  ceiling `read`, and `pay_bill` is registered as `denied` on purpose.

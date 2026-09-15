# SPIRE UI — Manual Test Checklist (Phase 4d §5.1)

Run before every UI-affecting merge. The API and MCP server must both
be up.

## Startup

- [ ] `python -m spire.api.server` starts on `:8000`, no traceback.
- [ ] `spire-ui` starts on `:8888`, no traceback after the Uvicorn banner.
- [ ] Browser at `http://localhost:8888` shows the SPIRE title and a
      **green "Connected"** pill.

## The three golden prompts

### "Count of suppliers"

- [ ] Answer renders as a single line of text: `There are NNN suppliers.`
- [ ] No dataframe appears.
- [ ] Metadata expander shows a stage breakdown with `parse`, `plan`,
      `execute`, `synthesize`.

### "Show PO 2144 and its lines"

- [ ] A dataframe renders with **one row**.
- [ ] Columns include `po_header_id`, `order_number`, `status`,
      `supplier_name`, `buyer`, `lines`.
- [ ] `buyer` shows `Gee, May` (a name, not a JSON blob).
- [ ] `lines` shows `Marketing Assistance, Marketing Assistance`.

### "Which suppliers have open purchase orders?"

- [ ] A yellow warning banner appears above the answer with the
      truncation note (`NNN total in source; 25 examined for filtering`).
- [ ] A summary line begins `Showing 25 of NNN suppliers.`
- [ ] A dataframe of **25 rows** renders.
- [ ] The `buyers` column shows names like `Roth, Calvin, Gee, May`,
      not `[object Object]`.

## Failure paths

- [ ] Kill the API (`Ctrl-C` in its terminal), refresh the browser:
      the connection pill turns **red** with `Connection refused`.
- [ ] Restart the API, refresh: pill returns to green.

## Raw view

- [ ] The `Raw response` expander opens and shows valid JSON.
- [ ] `request_id` is a UUID.
- [ ] `kind` matches the rendered view.
# BI Publisher report used by `runsql.sh`

`runsql.sh` validates emitted SQL against the pod by running it through a
BI Publisher report that accepts the statement as a parameter. The pod
object is `/Custom/bhagavan/SQL_Runner_Report` and it is **two** objects:

| File | Pod path | Role |
|---|---|---|
| `SQL_Runner_Report.xdm` | `/Custom/bhagavan/SQL_Runner_Report.xdm` | data model — declares `P_SQL` and runs it |
| `SQL_Runner_Report.xdo` | `/Custom/bhagavan/SQL_Runner_Report.xdo` | report — wires the `.xdm` in, lists allowed output formats |

These copies live here because the pod object is mutable state that
`runsql.sh` depends on. Without them a fresh pod cannot run the
validator. Upload them with `CatalogService.updateObject` (or through the
BIP UI: **Catalog → Custom → bhagavan → SQL_Runner_Report → Edit**).

## Why the data model looks like this

```sql
SELECT DBMS_XMLGEN.GETXML(:P_SQL) AS XMLDATA FROM DUAL
```

- **One fixed column shape.** `DBMS_XMLGEN` returns Oracle's own
  `<ROWSET><ROW><COL>value</COL></ROW></ROWSET>` document as a CLOB, so
  the report's output structure never has to match the query — any
  `SELECT` with any column list works.
- **`P_SQL` is the only parameter.** The model previously shipped with a
  hardcoded query and no parameters, so `P_SQL` was silently ignored and
  every run rendered the same fixed rows.
- `include_parameters=true` echoes `P_SQL` back in an unused
  `<P_SQL>` element; `runsql.sh` reads the `<XMLDATA>` text.

## Output formats

The template element in the `.xdo` must list `xml`:

```xml
<template type="xpt"
          outputFormat="analyze,pdf,html,rtf,xlsx,pptx,xml"
          defaultFormat="xml" ... url="SQL_Runner_Report.xpt"/>
```

Without `xml` in that list, `runReport` fails with
`DataException: Invalid format requested: xml`. No `.xpt` file is needed —
BIP auto-generates the layout from the data model's `<output>` block.

## Service endpoint

`runReport` is served by:

```
POST {host}/xmlpserver/services/PublicReportService
```

- **SOAP 1.1 only.** A SOAP 1.2 envelope
  (`http://www.w3.org/2003/05/soap-envelope`) is rejected with
  `VersionMismatch: A SOAP 1.2 message is not valid when sent to a SOAP 1.1
  only endpoint`.
- **Credentials go in the body** (`<pub:userID>` / `<pub:password>`), not
  as HTTP Basic — Basic alone returns
  `initSession Failure: due to empty userID`.
- `ExternalReportWSService` is *not* published on every pod (dev49 returns
  404). `PublicReportService` is.

## Verifying the report

```bash
./runsql.sh "SELECT 1 AS ONE FROM DUAL"
```

Expect:

```
ONE
---
1

1 row(s)
```

A statement error returns exit 1 with the `ORA-*` lines, e.g.
`ORA-00942: table or view does not exist`.

## Quoting caveat

SQL is passed inside an XML element, so the statement must not contain a
literal `<` `>` or `&` outside a quoted string. Use `q'[...]'` or bind-free
predicates where possible. A bare `&` in *data* is fine: `runsql.sh`
escapes lone ampersands before parsing the returned ROWSET.

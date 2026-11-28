#!/usr/bin/env bash
# Run any SQL against Oracle Fusion via the BI Publisher SQL_Runner report.
# Usage: ./runsql.sh "SELECT SEGMENT1 FROM PO_HEADERS_ALL WHERE PO_HEADER_ID = 2144"
#        ./runsql.sh -f query.sql          (read SQL from a file)
# Env:   IKS_FUSION_USERNAME, IKS_FUSION_PASSWORD (required)
#        FUSION_HOST, REPORT_PATH, BIP_SERVICE (optional overrides)
#        FORMAT=table (default) | csv | xml ;  RAW=1 for full BI Publisher output
#
# The report's data model executes the statement through
#   SELECT DBMS_XMLGEN.GETXML(:P_SQL) AS XMLDATA FROM DUAL
# so any single statement is accepted and Oracle's own <ROWSET> XML is
# returned as one CLOB column. This script unwraps that column and renders
# it. Failures (SOAP fault, HTTP error, ORA-*) exit non-zero with the text.
set -euo pipefail

if [[ "${1:-}" == "-f" ]]; then
  SQL="$(cat "${2:?Usage: $0 -f query.sql}")"
else
  SQL="${1:?Usage: $0 \"SELECT ...\"  or  $0 -f query.sql}"
fi

HOST="${FUSION_HOST:-https://fa-euth-dev49-saasfademo1.ds-fa.oraclepdemos.com}"
REPORT="${REPORT_PATH:-/Custom/bhagavan/SQL_Runner_Report.xdo}"
SERVICE="${BIP_SERVICE:-PublicReportService}"

# DBMS_XMLGEN rejects a trailing semicolon: strip it (and trailing whitespace)
SQL="$(printf '%s' "$SQL" | sed -e ':a' -e 'N' -e '$!ba' -e 's/[[:space:];]*$//')"

RESPONSE="$(mktemp)"
trap 'rm -f "$RESPONSE"' EXIT

HTTP_CODE="$(curl -s --compressed \
  -o "$RESPONSE" -w '%{http_code}' \
  -H "Content-Type: text/xml; charset=UTF-8" \
  -X POST "$HOST/xmlpserver/services/$SERVICE" \
  --data-binary @- <<EOF
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                 xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
  <soapenv:Header/>
  <soapenv:Body>
    <pub:runReport>
      <pub:reportRequest>
        <pub:reportAbsolutePath>$REPORT</pub:reportAbsolutePath>
        <pub:attributeFormat>xml</pub:attributeFormat>
        <pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload>
        <pub:parameterNameValues>
          <pub:item>
            <pub:name>P_SQL</pub:name>
            <pub:values><pub:item><![CDATA[$SQL]]></pub:item></pub:values>
          </pub:item>
        </pub:parameterNameValues>
      </pub:reportRequest>
      <pub:userID>${IKS_FUSION_USERNAME:?set IKS_FUSION_USERNAME}</pub:userID>
      <pub:password>${IKS_FUSION_PASSWORD:?set IKS_FUSION_PASSWORD}</pub:password>
    </pub:runReport>
  </soapenv:Body>
</soapenv:Envelope>
EOF
)"

BYTES="$(grep -o 'reportBytes>[^<]*' "$RESPONSE" | cut -d'>' -f2 || true)"

FAULT="$(grep -o 'faultstring>[^<]*' "$RESPONSE" | head -1 | cut -d'>' -f2 || true)"
if [[ -n "$FAULT" ]]; then
  # A failed statement comes back as HTTP 500 + a SOAP fault. Report the
  # ORA-* lines plainly so a bad query is never mistaken for "no rows".
  echo "SQL FAILED (HTTP $HTTP_CODE):" >&2
  grep -o 'ORA-[0-9]*[^<]*' "$RESPONSE" | head -5 >&2 || printf '%s\n' "$FAULT" >&2
  echo "--- BI Publisher fault ---" >&2
  printf '%s\n' "$FAULT" >&2
  exit 1
fi

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "BI Publisher HTTP $HTTP_CODE (service: $SERVICE). Raw response:" >&2
  cat "$RESPONSE" >&2
  exit 1
fi

if [[ -z "$BYTES" ]]; then
  echo "No report data returned. Raw response:" >&2
  cat "$RESPONSE" >&2
  exit 1
fi

# Output: FORMAT=table (default), csv or xml; RAW=1 prints the full BIP output
printf '%s' "$BYTES" | base64 -d | RAW="${RAW:-0}" FORMAT="${FORMAT:-table}" python3 -c '
import csv, html, os, re, sys
import xml.etree.ElementTree as ET

payload = sys.stdin.read()
if os.environ["RAW"] == "1":
    print(payload); sys.exit()

# The report wraps the statement DBMS_XMLGEN output in one <XMLDATA>
# element, so the ROWSET is escaped exactly one level. Parse the wrapper
# as XML (which unescapes that level for us) instead of html.unescape()-ing
# the whole document -- that would also unescape &amp;amp; inside data values
# and corrupt any name containing an ampersand.
inner = None
try:
    wrapper = ET.fromstring(payload)
except ET.ParseError:
    wrapper = None
if wrapper is not None:
    xd = wrapper.find(".//XMLDATA")
    inner = xd.text if xd is not None else None
if not inner and "<ROWSET>" in payload:
    inner = payload                      # unframed payload (older reports)

# Some data values arrive with a bare ampersand (e.g. "Wyoming Oil & Gas"),
# which is not well-formed XML. Escape only ampersands that do not already
# begin a valid entity, so real entities are left untouched.
if inner:
    inner = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9A-Fa-f]+);)",
                   "&amp;", inner)

if not inner or not inner.strip() or "<ROW>" not in inner:
    print("(no rows returned)")
    print("0 row(s)", file=sys.stderr)
    sys.exit()

if os.environ["FORMAT"] == "xml":
    print(inner.strip()); sys.exit()

rows, cols = [], []
for r in ET.fromstring(inner.strip()).findall("ROW"):
    rec = {}
    for c in r:
        if c.tag not in cols:
            cols.append(c.tag)          # DBMS_XMLGEN omits NULL columns, so collect all
        rec[c.tag] = (c.text or "").strip()
    rows.append(rec)

if os.environ["FORMAT"] == "csv":
    w = csv.writer(sys.stdout)
    w.writerow(cols)
    for rec in rows:
        w.writerow([rec.get(c, "") for c in cols])
    print(f"{len(rows)} row(s)", file=sys.stderr)
    sys.exit()

widths = [max([len(c)] + [len(rec.get(c, "")) for rec in rows]) for c in cols]
line = lambda vals: "  ".join(v.ljust(w) for v, w in zip(vals, widths)).rstrip()
print(line(cols))
print(line(["-" * w for w in widths]))
for rec in rows:
    print(line([rec.get(c, "") for c in cols]))
print(f"\n{len(rows)} row(s)")'

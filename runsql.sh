#!/usr/bin/env bash
# Run any SQL against Oracle Fusion via the BI Publisher SQL_Runner report.
# Usage: ./runsql.sh "SELECT SEGMENT1 FROM PO_HEADERS_ALL WHERE PO_HEADER_ID = 2144"
#        ./runsql.sh -f query.sql          (read SQL from a file)
# Env:   IKS_FUSION_USERNAME, IKS_FUSION_PASSWORD (required)
#        FUSION_HOST, REPORT_PATH (optional overrides)
#        FORMAT=table (default) | csv | xml ;  RAW=1 for full BI Publisher output
set -euo pipefail

if [[ "${1:-}" == "-f" ]]; then
  SQL="$(cat "${2:?Usage: $0 -f query.sql}")"
else
  SQL="${1:?Usage: $0 \"SELECT ...\"  or  $0 -f query.sql}"
fi

HOST="${FUSION_HOST:-https://fa-euth-dev63-saasfademo1.ds-fa.oraclepdemos.com}"
REPORT="${REPORT_PATH:-/Custom/bhagavan/SQL_Runner_Report.xdo}"

# DBMS_XMLGEN rejects a trailing semicolon: strip it (and trailing whitespace)
SQL="$(printf '%s' "$SQL" | sed -e ':a' -e 'N' -e '$!ba' -e 's/[[:space:];]*$//')"

RESPONSE="$(curl -s --compressed \
  -u "${IKS_FUSION_USERNAME:?set IKS_FUSION_USERNAME}:${IKS_FUSION_PASSWORD:?set IKS_FUSION_PASSWORD}" \
  -H "Content-Type: application/soap+xml; charset=UTF-8" \
  -X POST "$HOST/xmlpserver/services/ExternalReportWSSService" \
  --data-binary @- <<EOF
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
  <soap:Body>
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
    </pub:runReport>
  </soap:Body>
</soap:Envelope>
EOF
)"

BYTES="$(printf '%s' "$RESPONSE" | grep -o 'reportBytes>[^<]*' | cut -d'>' -f2 || true)"

if [[ -z "$BYTES" ]]; then
  echo "No report data returned. Raw response:" >&2
  printf '%s\n' "$RESPONSE" >&2
  exit 1
fi

# Output: FORMAT=table (default), csv or xml; RAW=1 prints the full BIP output
printf '%s' "$BYTES" | base64 -d | RAW="${RAW:-0}" FORMAT="${FORMAT:-table}" python3 -c '
import csv, html, os, re, sys
import xml.etree.ElementTree as ET

out = html.unescape(sys.stdin.read())
if os.environ["RAW"] == "1":
    print(out); sys.exit()

m = re.search(r"<ROWSET>.*</ROWSET>", out, re.S)
if not m:
    print("(no rows returned)"); sys.exit()
if os.environ["FORMAT"] == "xml":
    print(m.group(0)); sys.exit()

rows, cols = [], []
for r in ET.fromstring(m.group(0)).findall("ROW"):
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
    sys.exit()

widths = [max([len(c)] + [len(rec.get(c, "")) for rec in rows]) for c in cols]
line = lambda vals: "  ".join(v.ljust(w) for v, w in zip(vals, widths)).rstrip()
print(line(cols))
print(line(["-" * w for w in widths]))
for rec in rows:
    print(line([rec.get(c, "") for c in cols]))
print(f"\n{len(rows)} row(s)")'

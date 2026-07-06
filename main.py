#!/bin/bash
set -euo pipefail

DB_NAME="postfixadmin"
DB_USER="postfixadmin"
DB_PASS="PASSWORD_HERE"

BASE_DIR="/mail/mdir"
OUT_DIR="/var/www/mailsize"
OUT_FILE="${OUT_DIR}/index.html"

FILTER_DOMAIN="${1:-}"
FILTER_USER="${2:-}"

mkdir -p "$OUT_DIR"

TMP_DATA="$(mktemp)"
trap 'rm -f "$TMP_DATA"' EXIT

SQL="
SELECT username, domain, quota
FROM mailbox
WHERE active=1
"

if [[ -n "$FILTER_DOMAIN" ]]; then
  SQL+=" AND domain='${FILTER_DOMAIN}'"
fi

if [[ -n "$FILTER_USER" ]]; then
  SQL+=" AND username='${FILTER_USER}'"
fi

mysql -N -u"$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "$SQL" | while read -r EMAIL DOMAIN QUOTA; do
  MAILDIR="${BASE_DIR}/${DOMAIN}/${EMAIL%%@*}"

  if [[ -d "$MAILDIR" ]]; then
    USED_BYTES=$(du -sb "$MAILDIR" 2>/dev/null | awk '{print $1}')
  else
    USED_BYTES=0
  fi

  USED_GB=$(awk "BEGIN {printf \"%.2f\", $USED_BYTES/1024/1024/1024}")

  if [[ "$QUOTA" == "0" || -z "$QUOTA" ]]; then
    QUOTA_GB="∞"
    PERCENT="0"
  else
    QUOTA_GB=$(awk "BEGIN {printf \"%.2f\", $QUOTA/1024/1024/1024}")
    PERCENT=$(awk "BEGIN {printf \"%.1f\", ($USED_BYTES/$QUOTA)*100}")
  fi

  echo "$DOMAIN|$EMAIL|$QUOTA_GB|$USED_GB|$PERCENT" >> "$TMP_DATA"
done

cat > "$OUT_FILE" <<EOF
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Dovecot Mailbox Usage Report</title>
<style>
body { font-family: Arial, sans-serif; background:#f5f5f5; padding:20px; }
table { border-collapse: collapse; width:100%; background:white; }
th, td { padding:10px; border:1px solid #ddd; text-align:left; }
th { background:#222; color:white; }
tr:nth-child(even) { background:#f2f2f2; }
.warn { background:#fff3cd; }
.bad { background:#f8d7da; }
</style>
</head>
<body>
<h2>Dovecot Mailbox Usage Report</h2>
<p>Generated: $(date '+%Y-%m-%d %H:%M:%S')</p>
<table>
<tr>
<th>Domain</th>
<th>User</th>
<th>Quota GB</th>
<th>Used GB</th>
<th>Used %</th>
</tr>
EOF

sort -t'|' -k4 -nr "$TMP_DATA" | while IFS='|' read -r DOMAIN EMAIL QUOTA_GB USED_GB PERCENT; do
  CLASS=""
  if awk "BEGIN {exit !($PERCENT >= 90)}"; then
    CLASS="bad"
  elif awk "BEGIN {exit !($PERCENT >= 75)}"; then
    CLASS="warn"
  fi

  cat >> "$OUT_FILE" <<EOF
<tr class="$CLASS">
<td>$DOMAIN</td>
<td>$EMAIL</td>
<td>$QUOTA_GB</td>
<td>$USED_GB</td>
<td>$PERCENT%</td>
</tr>
EOF
done

cat >> "$OUT_FILE" <<EOF
</table>
</body>
</html>
EOF

chown -R nginx:nginx "$OUT_DIR" 2>/dev/null || true
echo "Report created: $OUT_FILE"

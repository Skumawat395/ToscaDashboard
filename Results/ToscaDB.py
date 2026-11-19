import json
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook

# ============================================================
# TOSCA EXECUTION DASHBOARD - REAL EXCEL DATA GENERATOR
# ============================================================
# Reads:
#   C:\Tosca\Batch\Results\ExecutionResult.xlsx
#
# Uses the EXISTING DashBoard_Light.html as the template.
# It does NOT create a new dashboard design.
#
# Flow:
#   ExecutionResult.xlsx
#          |
#          v
#   ToscaDB.py
#          |
#          v
#   ToscaExecutionDashboard.html
#
# Important:
# - Every valid Excel row is loaded. NO deduplication.
# - Month comes from StartTime.
# - ALL months found in Excel are shown.
# - Dummy/sample data is disabled.
# - Local /api/results live fetch is disabled so it cannot
#   overwrite the Excel data.
# - Report column is blank; no fake PDF is generated.
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

EXCEL_FILE = BASE_DIR / "ExecutionResult.xlsx"
OUTPUT_FILE = BASE_DIR / "ToscaExecutionDashboard.html"

# Keep DashBoard_Light.html in Results.
# Downloads is supported as a fallback.
TEMPLATE_CANDIDATES = [
    BASE_DIR / "DashBoard_Light.html",
    BASE_DIR / "DashBoard_Light(1).html",
    Path.home() / "Downloads" / "DashBoard_Light.html",
    Path.home() / "Downloads" / "DashBoard_Light(1).html",
]

REQUIRED_COLUMNS = [
    "Environment_Name",
    "Module_Name",
    "TestCase_Name",
    "Result",
    "StartTime",
]

OPTIONAL_COLUMNS = [
    "EndTime",
    "CreatedBy",
    "CreatedAt",
]


def text(value):
    return "" if value is None else str(value).strip()


def parse_datetime(value):
    if isinstance(value, datetime):
        return value

    if value is None:
        return None

    s = str(value).strip().replace("T", " ")
    if not s:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S.%f",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S.%f",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None


def fmt_datetime(value):
    dt = parse_datetime(value)
    return dt.strftime("%d-%m-%Y %H:%M:%S") if dt else text(value)


def find_template():
    for path in TEMPLATE_CANDIDATES:
        if path.exists():
            return path

    checked = "\n".join(f"  - {p}" for p in TEMPLATE_CANDIDATES)
    raise FileNotFoundError(
        "\nDashBoard_Light.html was not found.\n"
        "Checked:\n" + checked +
        "\n\nRecommended location:\n"
        f"  {BASE_DIR / 'DashBoard_Light.html'}"
    )


def read_excel():
    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"\nExecutionResult.xlsx was not found:\n{EXCEL_FILE}\n"
            "\nMake sure Tosca_DashBoard.py creates ExecutionResult.xlsx "
            "in the same Results folder."
        )

    print(f"Reading Excel: {EXCEL_FILE}")

    wb = load_workbook(EXCEL_FILE, read_only=True, data_only=True)

    try:
        ws = wb["ExecutionResult"] if "ExecutionResult" in wb.sheetnames else wb.active

        iterator = ws.iter_rows(values_only=True)

        try:
            header = next(iterator)
        except StopIteration:
            raise ValueError("ExecutionResult.xlsx is empty.")

        headers = [text(v) for v in header]
        index = {name: i for i, name in enumerate(headers) if name}

        missing = [c for c in REQUIRED_COLUMNS if c not in index]
        if missing:
            raise ValueError(
                "\nMissing required Excel columns:\n" +
                "\n".join(f"  - {c}" for c in missing)
            )

        records = []
        skipped = 0

        for excel_row, row in enumerate(iterator, start=2):

            def get(column):
                pos = index.get(column)
                return row[pos] if pos is not None and pos < len(row) else None

            testcase = text(get("TestCase_Name"))
            if not testcase:
                skipped += 1
                continue

            start = parse_datetime(get("StartTime"))
            if not start:
                print(
                    f"WARNING: Excel row {excel_row} skipped because "
                    f"StartTime is invalid: {get('StartTime')!r}"
                )
                skipped += 1
                continue

            records.append({
                "Environment": text(get("Environment_Name")),
                "Module": text(get("Module_Name")),
                "TestCaseName": testcase,
                "Result": text(get("Result")),
                "Month": start.strftime("%Y-%m"),
                "StartTime": fmt_datetime(get("StartTime")),
                "EndTime": fmt_datetime(get("EndTime")),
                "CreatedBy": text(get("CreatedBy")),
                "CreatedAt": fmt_datetime(get("CreatedAt")),
                "ReportPath": "",
            })

        print(f"Valid Excel records loaded: {len(records)}")
        print(f"Skipped Excel rows: {skipped}")

        return records

    finally:
        wb.close()


def print_month_summary(records):
    summary = {}

    for r in records:
        month = r["Month"]
        s = summary.setdefault(
            month, {"total": 0, "passed": 0, "failed": 0, "other": 0}
        )

        s["total"] += 1

        result = r["Result"].strip().lower()

        if result in ("passed", "pass"):
            s["passed"] += 1
        elif result in ("failed", "fail"):
            s["failed"] += 1
        else:
            s["other"] += 1

    print("\nMONTH-WISE REAL DATA")
    print("-" * 75)

    for month in sorted(summary.keys(), reverse=True):
        s = summary[month]
        label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")

        print(
            f"{label:18} | "
            f"Total: {s['total']:4} | "
            f"Passed: {s['passed']:4} | "
            f"Failed: {s['failed']:4} | "
            f"Other: {s['other']:4}"
        )


def replace_required(html, old, new, name):
    if old not in html:
        raise RuntimeError(
            f"\nDashboard template section not found: {name}\n"
            "Use the supplied DashBoard_Light.html template."
        )

    return html.replace(old, new, 1)


def generate_dashboard(records):
    template = find_template()

    print(f"\nUsing dashboard template: {template}")

    html = template.read_text(encoding="utf-8")

    # --------------------------------------------------------
    # 1. Inject REAL Excel records.
    # --------------------------------------------------------
    marker = "const PYTHON_DATA = [];"

    if marker not in html:
        raise RuntimeError(
            "Could not find 'const PYTHON_DATA = [];' in dashboard template."
        )

    data_json = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":")
    )

    # Prevent a testcase containing </script> from closing the script tag.
    data_json = data_json.replace("<", "\\u003c")

    html = html.replace(
        marker,
        f"const PYTHON_DATA = {data_json};",
        1
    )

    # --------------------------------------------------------
    # 2. Disable the built-in dummy-data block.
    # --------------------------------------------------------
    start_token = "if(PYTHON_DATA.length){"
    end_token = "\n\nfunction monthLabel"

    start = html.find(start_token)
    end = html.find(end_token, start)

    if start == -1 or end == -1:
        raise RuntimeError(
            "Could not find the dashboard data initialization block."
        )

    real_block = """if(PYTHON_DATA.length){
  // REAL DATA ONLY - loaded from ExecutionResult.xlsx
  allRows = PYTHON_DATA.map(r => ({ ...r, Month: r.Month }));
} else {
  // Never generate demo/sample records.
  allRows = [];
}"""

    html = html[:start] + real_block + html[end:]

    # --------------------------------------------------------
    # 3. Build month cards ONLY from real Excel months.
    # --------------------------------------------------------
    old_month_logic = """const presentKeys = [...new Set(allRows.map(r => assignMonth(r)))];
  const orderedKeys = MONTHS.map(m => m.key).filter(k => presentKeys.includes(k)).reverse()
    .concat(presentKeys.filter(k => !MONTHS.some(m => m.key === k))); // latest known month first, unrecognized ones after"""

    new_month_logic = """const presentKeys = [...new Set(allRows.map(r => r.Month).filter(Boolean))];
  // Use every month present in ExecutionResult.xlsx, newest first.
  const orderedKeys = presentKeys.sort((a, b) => b.localeCompare(a));"""

    html = replace_required(
        html,
        old_month_logic,
        new_month_logic,
        "real month ordering"
    )

    # --------------------------------------------------------
    # 4. Replace monthLabel so any real YYYY-MM is displayed
    #    as "September 2026", "August 2026", etc.
    # --------------------------------------------------------
    old_label = """function monthLabel(key){
  const m = MONTHS.find(x => x.key === key);
  return m ? m.label : key;
}"""

    new_label = """function monthLabel(key){
  if(!key) return '';
  const parts = String(key).split('-');
  if(parts.length === 2){
    const d = new Date(Number(parts[0]), Number(parts[1]) - 1, 1);
    if(!isNaN(d.getTime())){
      return d.toLocaleString('en-US', {month:'long', year:'numeric'});
    }
  }
  return key;
}"""

    html = replace_required(
        html,
        old_label,
        new_label,
        "month label"
    )

    # --------------------------------------------------------
    # 5. Disable live API fetch.
    #    The dashboard must use the Excel snapshot generated
    #    by ToscaDB.py and must not replace it with another
    #    data source.
    # --------------------------------------------------------
    live_start = html.find("async function fetchLive(){")
    live_end = html.find("\n\n// try live data immediately", live_start)

    if live_start != -1 and live_end != -1:
        disabled_live = """async function fetchLive(){
  // Disabled intentionally.
  // This dashboard is generated from ExecutionResult.xlsx.
}"""

        html = html[:live_start] + disabled_live + html[live_end:]

    # Remove the automatic fetch/polling calls.
    html = html.replace(
        "// try live data immediately, then poll every 60s for a \"real-time\" feel\nfetchLive();\nsetInterval(fetchLive, 60000);",
        "// Live API disabled - Excel data is the single source."
    )

    # --------------------------------------------------------
    # 6. Keep Report column but leave it BLANK.
    # --------------------------------------------------------
    report_start = html.find("function openReportForRow(row){")
    report_end = html.find("\n\nfunction renderTable", report_start)

    if report_start != -1 and report_end != -1:
        blank_report = """function openReportForRow(row){
  // Real Tosca execution PDF is not connected yet.
  // Intentionally blank.
}"""

        html = html[:report_start] + blank_report + html[report_end:]

    old_report_cell = """html += `<tr><td>${r.Environment}</td><td>${r.Module}</td><td>${r.TestCaseName}</td><td><span class="badge ${cls}">${rr}</span></td><td><a href="#" class="report-link" data-key="${key}">View Report</a></td></tr>`;"""

    new_report_cell = """html += `<tr><td>${r.Environment}</td><td>${r.Module}</td><td>${r.TestCaseName}</td><td><span class="badge ${cls}">${rr}</span></td><td></td></tr>`;"""

    html = replace_required(
        html,
        old_report_cell,
        new_report_cell,
        "report column"
    )

    # All-documents screen: blank document column too.
    old_doc_cell = """html += `<tr><td>${r.Environment}</td><td>${r.Module}</td><td>${r.TestCaseName}</td><td><a href="#" class="report-link" data-key="${key}">View Document</a></td></tr>`;"""

    new_doc_cell = """html += `<tr><td>${r.Environment}</td><td>${r.Module}</td><td>${r.TestCaseName}</td><td></td></tr>`;"""

    if old_doc_cell in html:
        html = html.replace(old_doc_cell, new_doc_cell, 1)

    # --------------------------------------------------------
    # 7. Validation.
    # --------------------------------------------------------
    required_markers = [
        'id="loginScreen"',
        'id="homeScreen"',
        'id="monthScreen"',
        'id="dashboardContent"',
        "const PYTHON_DATA = [",
    ]

    missing = [x for x in required_markers if x not in html]

    if missing:
        raise RuntimeError(
            "Generated dashboard validation failed:\n" +
            "\n".join(f"  - {x}" for x in missing)
        )

    # Make sure dummy fallback is gone.
    if "const count = 8 + (seed % 4)" in html:
        raise RuntimeError(
            "Dummy data block is still present in generated dashboard."
        )

    OUTPUT_FILE.write_text(html, encoding="utf-8")

    print("\nDashboard generated successfully.")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Records written: {len(records)}")
    print("Dummy data: DISABLED")
    print("Live API overwrite: DISABLED")
    print("Report PDF: BLANK")
    print("Login/Home/Month/Dashboard pages: PRESERVED")


def main():
    print("=" * 75)
    print("             TOSCA EXECUTION DASHBOARD")
    print("                 REAL EXCEL DATA")
    print("=" * 75)

    records = read_excel()

    if not records:
        raise RuntimeError(
            "No valid records were found in ExecutionResult.xlsx. "
            "Dashboard was not generated."
        )

    records.sort(
        key=lambda r: (
            r["Month"],
            parse_datetime(r["StartTime"]) or datetime.min
        ),
        reverse=True
    )

    print(f"\nTotal real records loaded from Excel: {len(records)}")

    print_month_summary(records)

    generate_dashboard(records)

    print("\n" + "=" * 75)
    print("SUCCESS")
    print("=" * 75)


if __name__ == "__main__":
    main()

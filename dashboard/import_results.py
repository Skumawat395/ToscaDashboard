import sys

# Console output can be redirected to a log; never crash on characters like '→'.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from openpyxl import load_workbook
from pathlib import Path
from result_store import (
    DATA_DIR,
    DATABASE_FILE,
    get_execution_results,
    save_execution_run,
    save_new_executions,
    sync_pending_runs,
)


# ============================================================
# FILE PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = DATA_DIR / "RawData.txt"
OUTPUT_FILE = DATA_DIR / "ExecutionResult.xlsx"   # legacy history, imported once into an empty DB


# ============================================================
# OUTPUT COLUMNS
# ============================================================

HEADERS = [
    "Environment_Name",
    "Module_Name",
    "TestCase_Name",
    "Result",
    "StartTime",
    "EndTime",
    "CreatedBy",
    "CreatedAt"
]


# ============================================================
# READ RAW DATA
# ============================================================

def read_raw_data(file_path):

    print()
    print("=" * 70)
    print("READING RAW DATA")
    print("=" * 70)

    if not file_path.exists():
        raise FileNotFoundError(
            f"RawData.txt not found:\n{file_path}"
        )

    with open(
        file_path,
        "r",
        encoding="utf-8-sig",
        errors="replace"
    ) as file:

        lines = [
            line.strip()
            for line in file
            if line.strip()
        ]

    print(f"Input File       : {file_path}")
    print(f"Total Raw Lines  : {len(lines)}")

    return lines


# ============================================================
# CHECK ENVIRONMENT
# ============================================================

def is_environment(name):

    name = name.strip().upper()

    # Current environments in your RawData
    if name == "ROW":
        return True

    if name.startswith("RISE_"):
        return True

    return False


# ============================================================
# CREATE TESTCASE RECORD
# ============================================================

def create_testcase(
    environment,
    module,
    testcase,
    result,
    start_time,
    end_time
):

    return {
        "Environment_Name": environment,
        "Module_Name": module,
        "TestCase_Name": testcase,
        "Result": result,
        "StartTime": start_time,
        "EndTime": end_time,
        "CreatedBy": "",
        "CreatedAt": ""
    }


# ============================================================
# PARSE TOSCA RAW DATA
# ============================================================

def parse_tosca_data(lines):

    records = []

    # --------------------------------------------------------
    # Current Environment / Module
    # --------------------------------------------------------

    current_environment = ""
    current_module = ""

    # --------------------------------------------------------
    # Execution information
    #
    # IMPORTANT:
    # In RawData.txt Result/StartTime/EndTime appear BEFORE
    # the testcase Name.
    #
    # Therefore we temporarily store them in pending variables.
    # --------------------------------------------------------

    pending_result = ""
    pending_start_time = ""
    pending_end_time = ""

    # --------------------------------------------------------
    # Current testcase
    # --------------------------------------------------------

    current_record = None

    # ========================================================
    # PROCESS EACH RAW LINE
    # ========================================================

    for line in lines:

        # ====================================================
        # NAME
        # ====================================================

        if line.startswith("Name:"):

            name = line.split(":", 1)[1].strip()

            # =================================================
            # ENVIRONMENT
            # =================================================

            if is_environment(name):

                # Save previous testcase
                if current_record is not None:
                    records.append(current_record)

                current_record = None

                # Set environment
                current_environment = name

                # Reset module
                current_module = ""

                # Reset pending execution data
                pending_result = ""
                pending_start_time = ""
                pending_end_time = ""

                continue

            # =================================================
            # MODULE
            # =================================================

            if current_environment and not current_module:

                current_module = name

                # Clear execution information
                pending_result = ""
                pending_start_time = ""
                pending_end_time = ""

                continue

            # =================================================
            # TESTCASE
            # =================================================

            if current_environment and current_module:

                # Save previous testcase
                if current_record is not None:
                    records.append(current_record)

                # IMPORTANT:
                #
                # Result/StartTime/EndTime found BEFORE this
                # testcase belong to THIS testcase.
                #
                # This matches the structure of your RawData.txt.
                #

                current_record = create_testcase(
                    environment=current_environment,
                    module=current_module,
                    testcase=name,
                    result=pending_result,
                    start_time=pending_start_time,
                    end_time=pending_end_time
                )

                # Clear pending data.
                # Next Result/StartTime/EndTime belong to
                # the next testcase.

                pending_result = ""
                pending_start_time = ""
                pending_end_time = ""

                continue

        # ====================================================
        # RESULT
        # ====================================================

        if line.startswith("Result:"):

            pending_result = line.split(":", 1)[1].strip()

            continue

        # ====================================================
        # START TIME
        # ====================================================

        if line.startswith("StartTime:"):

            pending_start_time = line.split(":", 1)[1].strip()

            continue

        # ====================================================
        # END TIME
        # ====================================================

        if line.startswith("EndTime:"):

            pending_end_time = line.split(":", 1)[1].strip()

            continue

        # ====================================================
        # CREATED BY
        # ====================================================

        if line.startswith("CreatedBy:"):

            if current_record is not None:

                current_record["CreatedBy"] = (
                    line.split(":", 1)[1].strip()
                )

            continue

        # ====================================================
        # CREATED AT
        # ====================================================

        if line.startswith("CreatedAt:"):

            if current_record is not None:

                current_record["CreatedAt"] = (
                    line.split(":", 1)[1].strip()
                )

            continue

    # ========================================================
    # SAVE LAST TESTCASE
    # ========================================================

    if current_record is not None:
        records.append(current_record)

    return records


# ============================================================
# VALIDATE RECORDS
# ============================================================

def validate_records(records):

    print()
    print("=" * 70)
    print("VALIDATION")
    print("=" * 70)

    print(
        f"Total TestCases : {len(records)}"
    )

    # --------------------------------------------------------
    # Count by Environment + Module
    # --------------------------------------------------------

    from collections import Counter

    counter = Counter(
        (
            record["Environment_Name"],
            record["Module_Name"]
        )
        for record in records
    )

    print()
    print("Environment / Module counts:")
    print("-" * 70)

    for (
        environment,
        module
    ), count in counter.items():

        print(
            f"{environment:<15} | "
            f"{module:<45} | "
            f"{count}"
        )

    # --------------------------------------------------------
    # Missing testcase names
    # --------------------------------------------------------

    missing_testcases = [

        record

        for record in records

        if not record["TestCase_Name"]
    ]

    print()
    print(
        f"Missing TestCase names : "
        f"{len(missing_testcases)}"
    )

    # --------------------------------------------------------
    # Missing Result
    # --------------------------------------------------------

    missing_result = [

        record

        for record in records

        if not record["Result"]
    ]

    print(
        f"Missing Result         : "
        f"{len(missing_result)}"
    )

    # --------------------------------------------------------
    # Missing StartTime
    # --------------------------------------------------------

    missing_start = [

        record

        for record in records

        if not record["StartTime"]
    ]

    print(
        f"Missing StartTime      : "
        f"{len(missing_start)}"
    )

    # --------------------------------------------------------
    # Missing EndTime
    # --------------------------------------------------------

    missing_end = [

        record

        for record in records

        if not record["EndTime"]
    ]

    print(
        f"Missing EndTime        : "
        f"{len(missing_end)}"
    )

    print("=" * 70)


# ============================================================
# ONE-TIME LEGACY EXCEL IMPORT (only when the database is empty)
# ============================================================

def import_legacy_excel_if_needed():
    if get_execution_results(DATABASE_FILE) or not OUTPUT_FILE.exists():
        return 0

    workbook = load_workbook(OUTPUT_FILE, read_only=True, data_only=True)
    try:
        worksheet = (
            workbook["ExecutionResult"]
            if "ExecutionResult" in workbook.sheetnames
            else workbook.active
        )
        iterator = worksheet.iter_rows(values_only=True)
        headers = next(iterator, None)
        if headers is None:
            return 0
        column_indexes = {
            str(name).strip(): index
            for index, name in enumerate(headers)
            if name is not None
        }
        missing = [
            name for name in HEADERS[:5] if name not in column_indexes
        ]
        if missing:
            raise ValueError(
                "Cannot import legacy workbook; missing columns: "
                + ", ".join(missing)
            )

        records = []
        for values in iterator:
            def value(column):
                index = column_indexes.get(column)
                return values[index] if index is not None and index < len(values) else None

            testcase = value("TestCase_Name")
            if not testcase:
                continue
            records.append(
                {
                    "Environment_Name": value("Environment_Name") or "",
                    "Module_Name": value("Module_Name") or "",
                    "TestCase_Name": testcase,
                    "Result": value("Result") or "Unknown",
                    "StartTime": value("StartTime"),
                    "EndTime": value("EndTime"),
                    "CreatedBy": value("CreatedBy"),
                    "CreatedAt": value("CreatedAt"),
                }
            )
    finally:
        workbook.close()

    if records:
        save_execution_run(records, DATABASE_FILE)
        print(f"Imported {len(records)} legacy rows from Excel into local SQLite.")
    return len(records)


# ============================================================
# MAIN
# ============================================================

def main():

    try:

        print()
        print("=" * 70)
        print("TOSCA RAW DATA → EXECUTION RESULT")
        print("=" * 70)

        # ====================================================
        # STEP 1: READ RawData.txt
        # ====================================================

        lines = read_raw_data(
            INPUT_FILE
        )

        # ====================================================
        # STEP 2: PARSE DATA
        # ====================================================

        print()
        print("Parsing Tosca execution data...")

        records = parse_tosca_data(
            lines
        )

        # ====================================================
        # STEP 3: VALIDATE
        # ====================================================

        validate_records(
            records
        )

        import_legacy_excel_if_needed()

        # ====================================================
        # STEP 4: SAVE LOCALLY AND SYNC TO SUPABASE
        # ====================================================

        run_ids = save_new_executions(records, DATABASE_FILE)
        cloud_sync = sync_pending_runs()

        # ====================================================
        # COMPLETE
        # ====================================================

        print()
        print("=" * 70)
        print("PROCESS COMPLETED SUCCESSFULLY")
        print("=" * 70)

        print()
        print(f"Input  : {INPUT_FILE}")
        print(f"Local DB: {DATABASE_FILE}")
        print(f"New reports : {len(run_ids) or 'none - no new executions since the last import'}")
        for run_id in run_ids:
            print(f"  Run ID : {run_id}")
        print(f"Cloud sync: {cloud_sync['status']} ({cloud_sync['synced_runs']} run(s))")
        print(f"Rows read from Tosca : {len(records)}")
        if run_ids:
            print(f"New results were added as {len(run_ids)} new report(s).")
        else:
            print("All results were already imported; nothing was added.")
        print()

    except Exception as error:

        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)

        print()
        print(str(error))

        print()
        print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
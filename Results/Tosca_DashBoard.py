from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from datetime import datetime
from pathlib import Path


# ============================================================
# FILE PATHS
# ============================================================

BASE_DIR = Path(r"C:\Tosca\Batch\Results")

INPUT_FILE = BASE_DIR / "RawData.txt"
OUTPUT_FILE = BASE_DIR / "ExecutionResult.xlsx"


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
# CONVERT DATE/TIME
# ============================================================

def convert_datetime(value):

    if not value:
        return ""

    if isinstance(value, datetime):
        return value

    formats = [

        "%d-%m-%Y %H:%M:%S",

        "%d-%m-%Y %H:%M",

        "%d/%m/%Y %H:%M:%S",

        "%d/%m/%Y %H:%M",

        "%Y-%m-%d %H:%M:%S",

        "%Y-%m-%d %H:%M"
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                value,
                fmt
            )

        except ValueError:
            pass

    # If conversion fails,
    # keep original text.

    return value


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
# CREATE EXECUTION RESULT EXCEL
# ============================================================

def create_execution_result(
    records,
    output_file
):

    print()
    print("=" * 70)
    print("CREATING EXECUTION RESULT")
    print("=" * 70)

    # --------------------------------------------------------
    # Create new Excel workbook
    #
    # IMPORTANT:
    # We use Workbook(), NOT load_workbook().
    #
    # RawData.txt is a TEXT file.
    # We are creating a NEW Excel file.
    # --------------------------------------------------------

    workbook = Workbook()

    worksheet = workbook.active

    worksheet.title = "ExecutionResult"

    # ========================================================
    # HEADERS
    # ========================================================

    for column_number, header in enumerate(
        HEADERS,
        start=1
    ):

        cell = worksheet.cell(
            row=1,
            column=column_number,
            value=header
        )

        cell.font = Font(
            bold=True
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True
        )

    # ========================================================
    # DATA
    # ========================================================

    for row_number, record in enumerate(
        records,
        start=2
    ):

        for column_number, header in enumerate(
            HEADERS,
            start=1
        ):

            value = record.get(
                header,
                ""
            )

            # ------------------------------------------------
            # Convert date/time columns
            # ------------------------------------------------

            if header in [
                "StartTime",
                "EndTime",
                "CreatedAt"
            ]:

                value = convert_datetime(value)

            cell = worksheet.cell(
                row=row_number,
                column=column_number,
                value=value
            )

            cell.alignment = Alignment(
                vertical="center",
                wrap_text=True
            )

            # ------------------------------------------------
            # Excel date format
            # ------------------------------------------------

            if isinstance(value, datetime):

                cell.number_format = (
                    "dd-mm-yyyy hh:mm:ss"
                )

    # ========================================================
    # BORDERS
    # ========================================================

    border = Border(

        left=Side(style="thin"),

        right=Side(style="thin"),

        top=Side(style="thin"),

        bottom=Side(style="thin")
    )

    last_row = len(records) + 1

    for row in worksheet.iter_rows(

        min_row=1,

        max_row=last_row,

        min_col=1,

        max_col=len(HEADERS)
    ):

        for cell in row:

            cell.border = border

    # ========================================================
    # COLUMN WIDTHS
    # ========================================================

    column_widths = {

        "A": 22,

        "B": 35,

        "C": 70,

        "D": 15,

        "E": 22,

        "F": 22,

        "G": 35,

        "H": 22
    }

    for column, width in column_widths.items():

        worksheet.column_dimensions[
            column
        ].width = width

    # ========================================================
    # ROW HEIGHT
    # ========================================================

    worksheet.row_dimensions[
        1
    ].height = 30

    for row_number in range(
        2,
        last_row + 1
    ):

        worksheet.row_dimensions[
            row_number
        ].height = 45

    # ========================================================
    # FREEZE HEADER
    # ========================================================

    worksheet.freeze_panes = "A2"

    # ========================================================
    # FILTER
    # ========================================================

    worksheet.auto_filter.ref = (
        f"A1:H{last_row}"
    )

    # ========================================================
    # SAVE EXCEL
    # ========================================================

    workbook.save(
        output_file
    )

    print()
    print("Excel successfully created!")
    print()
    print(f"Output File : {output_file}")
    print(f"Total Rows  : {len(records)}")


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

        # ====================================================
        # STEP 4: CREATE EXCEL
        # ====================================================

        create_execution_result(
            records,
            OUTPUT_FILE
        )

        # ====================================================
        # COMPLETE
        # ====================================================

        print()
        print("=" * 70)
        print("PROCESS COMPLETED SUCCESSFULLY")
        print("=" * 70)

        print()
        print(f"Input  : {INPUT_FILE}")
        print(f"Output : {OUTPUT_FILE}")
        print(f"Rows   : {len(records)}")
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
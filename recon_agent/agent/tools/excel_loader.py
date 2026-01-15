import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any
from decimal import Decimal, InvalidOperation
from datetime import datetime


def discover_excel_file(data_dir: str = "data") -> str:
    """
    Automatically discover Excel file in the data directory.

    Args:
        data_dir: Directory to search for Excel files (default: "data")

    Returns:
        Path to the discovered Excel file

    Raises:
        FileNotFoundError: If no Excel files found
        ValueError: If multiple Excel files found (user must specify)
    """
    data_path = Path(data_dir)

    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}/")

    # Find all Excel files in data directory (.xlsx, .xls, .xlsm)
    excel_files = []
    for pattern in ['*.xlsx', '*.xls', '*.xlsm']:
        excel_files.extend(data_path.glob(pattern))

    if not excel_files:
        raise FileNotFoundError(
            f"No Excel files found in {data_dir}/\n"
            f"Please add an Excel file or specify path with --excel"
        )

    if len(excel_files) == 1:
        return str(excel_files[0])

    # Multiple files - list them for user to choose
    file_list = "\n".join([f"  - {f.name}" for f in excel_files])
    raise ValueError(
        f"Multiple Excel files found in {data_dir}/:\n{file_list}\n"
        f"Please specify one using --excel <filename>"
    )


# Russian to English header mapping
RUSSIAN_HEADER_MAP = {
    # Transaction identifiers
    "номер": "transaction_id",
    "номертранзакции": "transaction_id",
    "id": "transaction_id",
    "transactionid": "transaction_id",

    # Amounts
    "сумма": "amount",
    "суммa": "amount",
    "оборот": "amount",  # Turnover/Revenue
    "оборотeur": "amount",
    "amount": "amount",
    "amt": "amount",
    "sum": "amount",
    "transactionamount": "transaction_amount",

    # Commission/Fee
    "комиссия": "commission",
    "вознаграждение": "commission",  # Remuneration
    "commission": "commission",
    "fee": "commission",
    "charge": "commission",
    "комиссияeur": "commission",
    "commissioneur": "commission",

    # Rolling Reserve
    "резерв": "rolling_reserve",
    "резервфонд": "rolling_reserve",
    "rr": "rolling_reserve",
    "rollingreserve": "rolling_reserve",
    "rolling_reserve": "rolling_reserve",
    "reserve": "rolling_reserve",
    "rrамount": "rolling_reserve",

    # Chargeback
    "чарджбэк": "chargeback",
    "чарджбек": "chargeback",
    "чб": "chb",
    "chb": "chb",
    "chargeback": "chargeback",
    "cb": "chb",
    "chargebackfee": "chargeback_fee",
    "chbкол-во": "chargeback_qty",
    "chb_кол-во": "chargeback_qty",
    "chbfix50euro": "chargeback_fee_collected",
    "chb_fix_50_euro": "chargeback_fee_collected",

    # Refund
    "возврат": "refund",
    "refund": "refund",
    "refundкол-во": "refund_qty",
    "refund_кол-во": "refund_qty",
    "refundfix5euro": "refund_fee_collected",
    "refund_fix_5_euro": "refund_fee_collected",
    "refundfee": "refund_fee",
    "ref": "refund",

    # Date
    "дата": "date",
    "датa": "date",
    "date": "date",
    "created": "date",
    "timestamp": "date",
    "transactiondate": "transaction_date",

    # Status
    "статус": "status",
    "status": "status",
    "state": "status",
}


def normalize_header(header: str) -> str:
    """
    Normalize a column header to English.

    Args:
        header: Original column header (may be Russian)

    Returns:
        Normalized English header name
    """
    if not isinstance(header, str):
        return str(header)

    # Clean the header: lowercase, remove spaces/underscores
    clean = header.lower().strip().replace(' ', '').replace('_', '').replace('-', '')

    # Look up in mapping
    normalized = RUSSIAN_HEADER_MAP.get(clean)

    if normalized:
        return normalized

    # If not found, return original cleaned version
    return header.lower().strip().replace(' ', '_')


def detect_header_row(file_path: str, sheet_name: str) -> int:
    """
    Detect which row contains the actual column headers (0-indexed).

    Args:
        file_path: Path to Excel file
        sheet_name: Sheet name to check

    Returns:
        Row index (0 for first row, 1 for second row, etc.)
    """
    try:
        # Read first 3 rows without header
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=3)

        if len(df) == 0:
            return 0

        # Check row 0 (first row)
        row0_score = _score_header_row(df.iloc[0])

        # Check row 1 (second row) if it exists
        if len(df) > 1:
            row1_score = _score_header_row(df.iloc[1])

            # If row 1 has significantly better score, use it
            if row1_score > row0_score and row1_score >= 2:
                return 1

        return 0
    except Exception:
        return 0


def _score_header_row(row: pd.Series) -> int:
    """
    Score a row to determine if it looks like a header row.

    Args:
        row: Pandas Series representing a row

    Returns:
        Score (higher = more likely to be a header)
    """
    score = 0

    for value in row:
        if pd.isna(value):
            continue

        value_str = str(value).lower().strip()

        # Check if it matches known column patterns
        for pattern in ['date', 'amount', 'commission', 'fee', 'sum', 'id',
                        'transaction', 'refund', 'chargeback', 'reserve', 'qty',
                        'дата', 'сумма', 'комиссия', 'резерв', 'возврат', 'чарджбэк']:
            if pattern in value_str:
                score += 2
                break

        # Headers are usually strings, not numbers
        if isinstance(value, str) and not value.replace('.', '').replace(',', '').replace('-', '').isdigit():
            score += 1

    return score


def load_excel_structure(file_path: str) -> Dict[str, Any]:
    """
    Load Excel file structure for discovery mode.

    Args:
        file_path: Path to Excel file

    Returns:
        Dictionary with structure information:
        {
            "sheets": ["Sheet1", "Sheet2"],
            "columns_per_sheet": {"Sheet1": ["col1", "col2", ...]},
            "normalized_columns": {"Sheet1": {"original": "normalized"}},
            "row_counts": {"Sheet1": 1234},
            "detected_mappings": {"комиссия": "commission", ...}
        }

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file cannot be read
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    try:
        xl = pd.ExcelFile(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    structure = {
        "sheets": xl.sheet_names,
        "columns_per_sheet": {},
        "normalized_columns": {},
        "row_counts": {},
        "detected_mappings": {},
        "header_rows": {}  # Track which row has headers for each sheet
    }

    for sheet_name in xl.sheet_names:
        try:
            # Detect header row
            header_row = detect_header_row(file_path, sheet_name)
            structure["header_rows"][sheet_name] = header_row

            # Read with correct header row
            df_header = pd.read_excel(xl, sheet_name=sheet_name, header=header_row, nrows=0)
            original_columns = list(df_header.columns)

            # Normalize headers
            normalized = {}
            for orig_col in original_columns:
                norm_col = normalize_header(str(orig_col))
                normalized[orig_col] = norm_col

                # Track Russian mappings
                clean_orig = str(orig_col).lower().strip().replace(' ', '').replace('_', '')
                if clean_orig in RUSSIAN_HEADER_MAP:
                    structure["detected_mappings"][orig_col] = norm_col

            structure["columns_per_sheet"][sheet_name] = original_columns
            structure["normalized_columns"][sheet_name] = normalized

            # Count rows (excluding header rows)
            df_count = pd.read_excel(xl, sheet_name=sheet_name, header=header_row)
            structure["row_counts"][sheet_name] = len(df_count)

        except Exception as e:
            print(f"Warning: Could not read sheet '{sheet_name}': {e}")
            continue

    return structure


def fix_unnamed_columns(df: pd.DataFrame, file_path: str, sheet_name: str, header_row: int) -> pd.DataFrame:
    """
    Fix unnamed columns by reading sub-headers for EUR (F) and AUD (F) sheets.

    These sheets have multi-level headers where row 1 has main headers (Refund, CHB)
    and row 2 has sub-headers (кол-во, fix 5 euro, etc.)
    """
    if sheet_name not in ['EUR (F)', 'AUD (F)']:
        return df

    try:
        # Read row 2 (sub-header row) - row after the detected header
        df_subheader = pd.read_excel(file_path, sheet_name=sheet_name, header=None, skiprows=header_row+1, nrows=1)
        subheaders = df_subheader.iloc[0].tolist()

        # Create new column names by replacing unnamed columns with sub-headers
        new_columns = []
        subheader_idx = 0
        prev_col = None

        for i, col in enumerate(df.columns):
            if 'unnamed' in str(col).lower():
                # Use sub-header name with prefix from previous main column
                if i < len(subheaders):
                    subheader = str(subheaders[i]).strip()
                    if pd.notna(subheader) and subheader != 'nan':
                        # Prefix with previous main column name for context
                        if prev_col and prev_col in ['refund', 'chb']:
                            new_col = f"{prev_col}_{subheader.lower().replace(' ', '_')}"
                        else:
                            new_col = normalize_header(subheader)
                    else:
                        new_col = col
                else:
                    new_col = col
            else:
                new_col = col
                # Track main column names for context
                if col in ['refund', 'chb']:
                    prev_col = col

            new_columns.append(new_col)

        df.columns = new_columns
    except Exception:
        # If anything fails, keep original columns
        pass

    return df


def load_transactions(
    file_path: str,
    sheet_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Load transactions from Excel file.

    Args:
        file_path: Path to Excel file
        sheet_name: Specific sheet to load (default: first sheet)

    Returns:
        List of transaction dictionaries with normalized headers
        Each transaction includes:
        - _sheet_name: Source sheet name
        - _row_number: Excel row number (1-indexed)
        - All other columns from the sheet

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If sheet not found or cannot be read
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    try:
        xl = pd.ExcelFile(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    # Determine which sheet to load
    if sheet_name is None:
        if not xl.sheet_names:
            raise ValueError("No sheets found in Excel file")
        sheet_name = xl.sheet_names[0]
    elif sheet_name not in xl.sheet_names:
        raise ValueError(f"Sheet '{sheet_name}' not found. Available: {xl.sheet_names}")

    # Detect header row
    header_row = detect_header_row(file_path, sheet_name)

    try:
        df = pd.read_excel(xl, sheet_name=sheet_name, header=header_row)
    except Exception as e:
        raise ValueError(f"Failed to read sheet '{sheet_name}': {e}")

    # Normalize column headers
    df.columns = [normalize_header(str(col)) for col in df.columns]

    # Fix unnamed columns for EUR (F) and AUD (F) sheets
    df = fix_unnamed_columns(df, file_path, sheet_name, header_row)

    # Convert to list of dicts
    transactions = []
    for idx, row in df.iterrows():
        transaction = {}

        # Add metadata
        transaction['_sheet_name'] = sheet_name
        # Excel row number: data row index + header_row + 2 (1 for Excel 1-indexing, 1 for header row)
        transaction['_row_number'] = idx + header_row + 2

        # Store original row data
        for col, value in row.items():
            # Handle NaN/None
            if pd.isna(value):
                transaction[col] = None
            # Convert to appropriate type
            elif isinstance(value, (int, float)):
                # Try to preserve numeric types
                if col in ['transaction_id', 'status'] or 'id' in col.lower():
                    transaction[col] = str(value) if not pd.isna(value) else None
                else:
                    transaction[col] = value
            elif isinstance(value, datetime):
                transaction[col] = value
            else:
                transaction[col] = str(value)

        transactions.append(transaction)

    return transactions


def parse_decimal(value: Any) -> Optional[Decimal]:
    """
    Safely parse a value to Decimal.

    Args:
        value: Value to parse (can be string, int, float, etc.)

    Returns:
        Decimal value or None if cannot parse
    """
    if value is None or pd.isna(value):
        return None

    try:
        if isinstance(value, Decimal):
            return value
        elif isinstance(value, (int, float)):
            return Decimal(str(value))
        elif isinstance(value, str):
            # Clean string (remove currency symbols, spaces, etc.)
            cleaned = value.strip().replace('€', '').replace('EUR', '').replace(',', '').replace(' ', '')
            if cleaned:
                return Decimal(cleaned)
        return None
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: Any) -> Optional[datetime]:
    """
    Safely parse a value to datetime.

    Args:
        value: Value to parse

    Returns:
        datetime object or None if cannot parse
    """
    if value is None or pd.isna(value):
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        # Try common date formats
        for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue

    return None

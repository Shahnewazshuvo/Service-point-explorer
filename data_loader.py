"""
data_loader.py
----------------
Handles pulling the service-point data, cleaning it, and returning one
merged pandas DataFrame ready for filtering/mapping in app.py.

Two data sources are supported:
1. Google Sheets (production) — configured via .streamlit/secrets.toml
2. Local Excel file (testing) — used automatically if Google Sheets
   secrets are not found, so you can build/test the app before the
   Google Cloud service account is fully wired up.

NOTE: This file intentionally does NOT hardcode any real sheet links.
Real links live only in .streamlit/secrets.toml (which is gitignored).
"""

import re

import pandas as pd
import streamlit as st
from urllib.parse import quote

# Columns we expect in every district sheet
EXPECTED_COLUMNS = [
    "sl", "code", "service_point_name", "service_point_type", "run_by",
    "project", "services_list", "location_id", "division", "district",
    "upazila_thana", "union_ward", "area_type", "service_status",
    "latitude", "longitude", "coordinate_quality", "source",
    "address_details", "contact", "email", "website", "remarks",
]

LOCAL_TEST_FILE = "sample_data/Geo-Map-RURAL_PHC.xlsx"


def _format_contact(value):
    """Keep phone numbers as text and restore a lost local mobile prefix."""
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return pd.NA
    def normalize_number(match):
        number = re.sub(r"\.0+$", "", match.group(0))
        if re.fullmatch(r"1[0-9]{9}", number):
            return "0" + number
        international = re.fullmatch(r"(?:\+?880|00880)(1[0-9]{9})", number)
        if international:
            return "0" + international.group(1)
        return number

    # Normalize numbers even when the cell includes a contact name or multiple numbers.
    # Leave incomplete or ambiguous source numbers intact instead of inventing digits.
    return re.sub(r"(?<![0-9.])\+?[0-9]+(?:\.0+)?(?![0-9.])", normalize_number, text)



def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize casing/whitespace and fix data types."""
    df = df.copy()

    # Strip whitespace from all text/object columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace({"nan": pd.NA, "None": pd.NA})

    # Title-case fields that come in with inconsistent casing
    # (e.g. "DHAKA" vs "Dhaka", "Branch office" vs "Branch Office")
    for col in ["division", "district", "upazila_thana", "union_ward",
                "service_point_type"]:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().str.title()

    # Coordinates must be numeric for mapping; bad values become NaN
    # instead of crashing the app.
    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "contact" in df.columns:
        df["contact"] = df["contact"].map(_format_contact).astype("string")

    return df


@st.cache_data(ttl=600, show_spinner="Loading service point data...")
def load_local_excel(path: str = LOCAL_TEST_FILE) -> pd.DataFrame:
    """Load every sheet in the local Excel file and merge them into one
    DataFrame. Used for local testing before Google Sheets is wired up,
    and also works fine if you keep using a single multi-sheet Excel
    file instead of Google Sheets."""
    xls = pd.ExcelFile(path)
    frames = []
    for sheet_name in xls.sheet_names:
        sheet_df = pd.read_excel(xls, sheet_name=sheet_name, dtype={"contact": "string"})
        sheet_df["_source_sheet"] = sheet_name
        frames.append(sheet_df)
    merged = pd.concat(frames, ignore_index=True)
    return _clean(merged)


def _sheet_csv_url(spreadsheet_id: str, sheet_name: str) -> str:
    """Build the public CSV export URL for one tab of a Google Sheet.

    This only works if the sheet's sharing is set to
    "Anyone with the link can view" -- no login/API key needed. This is
    why the spreadsheet_id itself must stay out of the app's visible
    code/UI and live only in .streamlit/secrets.toml: anyone who got
    that ID could build this same URL and read the raw sheet.
    """
    encoded_name = quote(sheet_name)
    return (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={encoded_name}"
    )


@st.cache_data(ttl=120, show_spinner="Loading service point data from Google Sheets...")
def load_google_sheets() -> pd.DataFrame:
    """Load and merge all configured tabs from the Google Sheet listed
    in secrets.toml. Works for a publicly-viewable sheet with no
    service account / API key required."""
    sheets_cfg = st.secrets["sheets"]
    spreadsheet_id = sheets_cfg["spreadsheet_id"]

    frames = []
    for tab_name in sheets_cfg["tabs"]:
        url = _sheet_csv_url(spreadsheet_id, tab_name)
        sheet_df = pd.read_csv(url, dtype={"contact": "string"})
        sheet_df["_source_sheet"] = tab_name
        frames.append(sheet_df)

    merged = pd.concat(frames, ignore_index=True)
    return _clean(merged)


def load_data() -> pd.DataFrame:
    """Entry point used by app.py. Uses Google Sheets if configured,
    otherwise falls back to the local test Excel file.

    If no .streamlit/secrets.toml file exists at all yet (normal while
    still testing locally), accessing st.secrets raises an error instead
    of just being empty -- so we catch that and fall back safely.
    """
    try:
        has_google_config = "sheets" in st.secrets
    except Exception:
        has_google_config = False

    if has_google_config:
        return load_google_sheets()
    return load_local_excel()
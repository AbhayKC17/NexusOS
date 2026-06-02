import json
import pandas as pd
import uuid
import os
from database import get_db


COLUMN_ALIASES = {
    'company':        ['name', 'startup', 'company', 'company name', 'organisation', 'organization', 'employer', 'firm'],
    'position':       ['position', 'role', 'job title', 'title', 'designation', 'job role'],
    'contact_email':  ['email', 'contact email', 'e-mail', 'email address', 'contact_email', 'to', 'contact_email'],
    'contact_name':   ['contact name', 'contact person', 'hr name', 'recruiter', 'contact', 'hiring manager'],
    'applied_date':   ['date', 'applied date', 'applied on', 'application date', 'sent date'],
    'notes':          ['notes', 'note', 'comments', 'remark', 'remarks', 'description', 'about', 'short_description'],
    'uuid':           ['uuid', 'tracking id', 'track id', 'uid'],
}


def _map_columns(df_columns):
    mapping = {}
    cols_lower = {c.strip().lower(): c for c in df_columns}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in cols_lower:
                mapping[field] = cols_lower[alias]
                break
    return mapping


def process_excel(filepath, filename):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(filepath)
    elif ext == '.csv':
        df = pd.read_csv(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    df.columns = [str(c).strip() for c in df.columns]
    col_map = _map_columns(df.columns)

    results = {
        'total': len(df),
        'imported': 0,
        'duplicates_skipped': 0,
        'new_uuid_generated': 0,
        'errors': [],
        'columns': list(df.columns),
    }

    conn = get_db()
    for idx, row in df.iterrows():
        try:
            def get_col(field):
                mapped = col_map.get(field)
                if mapped and mapped in df.columns:
                    val = row.get(mapped)
                    return str(val).strip() if pd.notna(val) else None
                return None

            # Resolve UUID
            if 'uuid' in col_map and pd.notna(row.get(col_map['uuid'], None)):
                row_uuid = str(row[col_map['uuid']]).strip()
            else:
                row_uuid = str(uuid.uuid4())
                results['new_uuid_generated'] += 1

            # Check duplicate by UUID
            existing = conn.execute(
                "SELECT id FROM applications WHERE uuid = ?", (row_uuid,)
            ).fetchone()
            if existing:
                results['duplicates_skipped'] += 1
                continue

            # Also check duplicate by company + email (catches re-imports of same data)
            company_val = get_col('company')
            email_val   = get_col('contact_email')
            if company_val and email_val:
                dup_by_match = conn.execute(
                    "SELECT id FROM applications WHERE company=? AND contact_email=?",
                    (company_val, email_val),
                ).fetchone()
                if dup_by_match:
                    results['duplicates_skipped'] += 1
                    continue

            # Store ALL columns as raw JSON for the spreadsheet view
            raw = {}
            for col in df.columns:
                val = row.get(col)
                raw[col] = str(val).strip() if pd.notna(val) and str(val) != 'nan' else ""
            raw_data_json = json.dumps(raw, ensure_ascii=False)

            conn.execute('''
                INSERT INTO applications
                    (uuid, company, position, contact_email, contact_name,
                     applied_date, source_file, status, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            ''', (
                row_uuid,
                get_col('company'),
                get_col('position'),
                get_col('contact_email'),
                get_col('contact_name'),
                get_col('applied_date'),
                filename,
                raw_data_json,
            ))
            results['imported'] += 1

        except Exception as e:
            results['errors'].append(f"Row {idx + 2}: {str(e)}")

    conn.commit()
    conn.close()
    return results


def get_all_raw_columns():
    """Returns the union of all column names seen across all raw_data entries."""
    conn = get_db()
    rows = conn.execute(
        "SELECT raw_data FROM applications WHERE raw_data IS NOT NULL AND raw_data != ''"
    ).fetchall()
    conn.close()

    seen = []
    seen_set = set()
    for row in rows:
        try:
            data = json.loads(row[0])
            for k in data.keys():
                if k not in seen_set:
                    seen.append(k)
                    seen_set.add(k)
        except Exception:
            pass
    return seen

"""
Admin Reports module. Generates downloadable CSV, Excel (.xlsx), and PDF
exports of the core admin datasets: students, scholarships, applications,
and documents. Pure data-formatting layer — pulls data via the repo layer
so it works identically on SQLite or Supabase.
"""
import csv
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

REPORT_TYPES = {
    "students": {
        "title": "Students Report",
        "columns": [("id", "ID"), ("full_name", "Full Name"), ("email", "Email"),
                    ("mobile", "Mobile"), ("is_active", "Active"), ("created_at", "Joined")],
    },
    "scholarships": {
        "title": "Scholarships Report",
        "columns": [("id", "ID"), ("name", "Name"), ("provider", "Provider"),
                    ("scholarship_type", "Type"), ("amount", "Amount"), ("state", "State"),
                    ("status", "Status"), ("application_deadline", "Deadline")],
    },
    "applications": {
        "title": "Applications Report",
        "columns": [("reference_id", "Reference ID"), ("student_name", "Student"),
                    ("student_email", "Email"), ("scholarship_name", "Scholarship"),
                    ("status", "Status"), ("created_at", "Applied On"), ("updated_at", "Last Updated")],
    },
    "documents": {
        "title": "Documents Report",
        "columns": [("id", "ID"), ("student_name", "Student"), ("student_email", "Email"),
                    ("doc_type", "Document Type"), ("file_name", "File Name"),
                    ("status", "Status"), ("uploaded_at", "Uploaded On")],
    },
}


def get_report_rows(repo, report_type):
    """Fetches the underlying rows for a report type via the repo layer."""
    if report_type == "students":
        return repo.list_students("")
    if report_type == "scholarships":
        return repo.list_all_scholarships_admin()
    if report_type == "applications":
        return repo.list_all_applications_admin()
    if report_type == "documents":
        return repo.list_all_documents_admin()
    raise ValueError(f"Unknown report type: {report_type}")


def _cell(row, key):
    v = row.get(key)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return v


def generate_csv(report_type, rows):
    meta = REPORT_TYPES[report_type]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in meta["columns"]])
    for row in rows:
        writer.writerow([_cell(row, key) for key, _ in meta["columns"]])
    return buf.getvalue().encode("utf-8")


def generate_excel(report_type, rows):
    meta = REPORT_TYPES[report_type]
    wb = Workbook()
    ws = wb.active
    ws.title = meta["title"][:31]  # Excel sheet name length limit

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")

    for col_idx, (_, label) in enumerate(meta["columns"], start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, (key, _) in enumerate(meta["columns"], start=1):
            ws.cell(row=row_idx, column=col_idx, value=_cell(row, key))

    for col_idx, (key, label) in enumerate(meta["columns"], start=1):
        max_len = max([len(str(label))] + [len(str(_cell(r, key))) for r in rows]) if rows else len(label)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 4, 45)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def generate_pdf(report_type, rows):
    meta = REPORT_TYPES[report_type]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"ScholarAI — {meta['title']}", styles["Title"]),
        Paragraph(f"Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')} · {len(rows)} record(s)", styles["Normal"]),
        Spacer(1, 12),
    ]

    header = [label for _, label in meta["columns"]]
    table_data = [header]
    for row in rows:
        table_data.append([str(_cell(row, key)) for key, _ in meta["columns"]])

    if len(table_data) == 1:
        story.append(Paragraph("No records found.", styles["Normal"]))
    else:
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf.read()


GENERATORS = {"csv": generate_csv, "excel": generate_excel, "pdf": generate_pdf}
CONTENT_TYPES = {
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
EXTENSIONS = {"csv": "csv", "excel": "xlsx", "pdf": "pdf"}

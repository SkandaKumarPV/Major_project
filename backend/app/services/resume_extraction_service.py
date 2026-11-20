import re
import zipfile

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from docx import Document
from pypdf import PdfReader


PDF_MIME_TYPE = "application/pdf"

DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)

DEFAULT_MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024


class ResumeExtractionError(Exception):
    """Raised when a resume cannot be safely validated or extracted."""


@dataclass
class ExtractedResume:
    raw_text: str
    structured_data: dict[str, Any]


SECTION_ALIASES = {
    "education": {
        "education",
        "academic background",
        "academics",
    },
    "skills": {
        "skills",
        "technical skills",
        "technical expertise",
        "technologies",
    },
    "projects": {
        "projects",
        "personal projects",
        "academic projects",
    },
    "work_experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "internships",
    },
    "certifications": {
        "certifications",
        "certificates",
        "licenses and certifications",
    },
}


def empty_resume_schema() -> dict[str, Any]:
    """Return the standard resume extraction schema."""

    return {
        "candidate_name": None,
        "email": None,
        "phone": None,
        "education": [],
        "skills": [],
        "projects": [],
        "work_experience": [],
        "certifications": [],
    }


def normalize_heading(value: str) -> str:
    """Normalize a possible section heading."""

    return re.sub(
        r"[^a-z0-9 ]",
        "",
        value.lower(),
    ).strip()


def validate_resume_file(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    max_size_bytes: int = DEFAULT_MAX_RESUME_SIZE_BYTES,
) -> str:
    """
    Validate extension, MIME type, size and actual file structure.

    Returns:
        'pdf' or 'docx'
    """

    if not file_bytes:
        raise ResumeExtractionError("The uploaded file is empty.")

    if len(file_bytes) > max_size_bytes:
        raise ResumeExtractionError(
            "The resume exceeds the maximum allowed file size."
        )

    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if extension == "pdf":
        if content_type != PDF_MIME_TYPE:
            raise ResumeExtractionError("Invalid PDF content type.")

        if not file_bytes.startswith(b"%PDF-"):
            raise ResumeExtractionError("The uploaded file is not a valid PDF.")

        return "pdf"

    if extension == "docx":
        if content_type != DOCX_MIME_TYPE:
            raise ResumeExtractionError("Invalid DOCX content type.")

        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
                names = set(archive.namelist())

                if (
                    "[Content_Types].xml" not in names
                    or "word/document.xml" not in names
                ):
                    raise ResumeExtractionError(
                        "The uploaded file is not a valid DOCX document."
                    )

                if archive.testzip() is not None:
                    raise ResumeExtractionError(
                        "The DOCX document is corrupted."
                    )

        except (zipfile.BadZipFile, OSError) as exc:
            raise ResumeExtractionError(
                "The DOCX document is corrupted or unreadable."
            ) from exc

        return "docx"

    raise ResumeExtractionError(
        "Unsupported resume format. Upload a PDF or DOCX file."
    )


def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(file_bytes), strict=True)

        if reader.is_encrypted:
            raise ResumeExtractionError(
                "Password-protected PDFs are not supported."
            )

        pages = []

        for page in reader.pages:
            page_text = page.extract_text() or ""
            pages.append(page_text)

        text = "\n".join(pages).strip()

        if not text:
            raise ResumeExtractionError(
                "No readable text was found in the PDF. "
                "Scanned PDFs requiring OCR are not supported."
            )

        return text

    except ResumeExtractionError:
        raise
    except Exception as exc:
        raise ResumeExtractionError(
            "The PDF is corrupted or could not be read."
        ) from exc


def extract_docx_text(file_bytes: bytes) -> str:
    try:
        document = Document(BytesIO(file_bytes))

        content = []

        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                content.append(paragraph.text.strip())

        # Include table content because resumes often use tables.
        for table in document.tables:
            for row in table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                    if cell.text.strip()
                ]

                if cells:
                    content.append(" | ".join(cells))

        text = "\n".join(content).strip()

        if not text:
            raise ResumeExtractionError(
                "No readable text was found in the DOCX document."
            )

        return text

    except ResumeExtractionError:
        raise
    except Exception as exc:
        raise ResumeExtractionError(
            "The DOCX document is corrupted or could not be read."
        ) from exc


def extract_contact_information(text: str) -> dict[str, Any]:
    """Extract only explicit email, phone and labelled candidate name."""

    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text,
    )

    phone_match = re.search(
        r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)",
        text,
    )

    name_match = re.search(
        r"(?im)^\s*(?:name|candidate name)\s*:\s*(.+?)\s*$",
        text,
    )

    return {
        "candidate_name": name_match.group(1).strip() if name_match else None,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0).strip() if phone_match else None,
    }


def extract_structured_data(text: str) -> dict[str, Any]:
    """
    Extract conservative section-based information.

    This is a lightweight parser, not an AI inference system.
    It does not infer missing qualifications or experience.
    """

    result = empty_resume_schema()
    result.update(extract_contact_information(text))

    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        heading = normalize_heading(line.rstrip(":"))

        matched_section = None

        for section, aliases in SECTION_ALIASES.items():
            if heading in aliases:
                matched_section = section
                break

        if matched_section:
            current_section = matched_section
            continue

        # Do not treat unrelated text as a section item.
        if current_section is None:
            continue

        # Preserve the content as written, without inventing summaries.
        item = re.sub(r"^[•●▪\-*]\s*", "", line).strip()

        if item:
            result[current_section].append(item)

    return result


def extract_resume(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    max_size_bytes: int = DEFAULT_MAX_RESUME_SIZE_BYTES,
) -> ExtractedResume:
    """Validate and extract a PDF or DOCX resume."""

    file_type = validate_resume_file(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        max_size_bytes=max_size_bytes,
    )

    if file_type == "pdf":
        raw_text = extract_pdf_text(file_bytes)
    else:
        raw_text = extract_docx_text(file_bytes)

    structured_data = extract_structured_data(raw_text)

    return ExtractedResume(
        raw_text=raw_text,
        structured_data=structured_data,
    )
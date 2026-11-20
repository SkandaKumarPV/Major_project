
import re
import zipfile

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pymupdf
import pytesseract
from docx import Document
from PIL import Image
from pypdf import PdfReader
from pytesseract import TesseractNotFoundError


PDF_MIME_TYPE = "application/pdf"

DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)

DEFAULT_MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024

# Render scanned PDF pages at a resolution suitable for resume text.
OCR_DPI = 250

# Pages with fewer meaningful characters are treated as potentially scanned.
MIN_EMBEDDED_TEXT_CHARACTERS = 20


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

    extension = (
        filename.lower().rsplit(".", 1)[-1]
        if "." in filename
        else ""
    )

    if extension == "pdf":
        if content_type != PDF_MIME_TYPE:
            raise ResumeExtractionError("Invalid PDF content type.")

        if not file_bytes.startswith(b"%PDF-"):
            raise ResumeExtractionError(
                "The uploaded file is not a valid PDF."
            )

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

        except ResumeExtractionError:
            raise
        except (zipfile.BadZipFile, OSError) as exc:
            raise ResumeExtractionError(
                "The DOCX document is corrupted or unreadable."
            ) from exc

        return "docx"

    raise ResumeExtractionError(
        "Unsupported resume format. Upload a PDF or DOCX file."
    )


def _needs_ocr(text: str) -> bool:
    """
    Determine whether a PDF page needs OCR.

    This catches pages with no text layer and pages with only a very
    small amount of extracted text, which can happen with scanned PDFs.
    """

    meaningful_characters = len(
        re.sub(r"\s+", "", text or "")
    )

    return meaningful_characters < MIN_EMBEDDED_TEXT_CHARACTERS


def extract_pdf_page_with_ocr(
    file_bytes: bytes,
    page_index: int,
) -> str:
    """
    Render one PDF page and recognize its text using Tesseract OCR.

    This function is called automatically only when normal PDF text
    extraction does not produce enough meaningful text.
    """

    try:
        with pymupdf.open(
            stream=file_bytes,
            filetype="pdf",
        ) as pdf_document:
            if page_index < 0 or page_index >= len(pdf_document):
                raise ResumeExtractionError(
                    "The PDF contains an invalid page."
                )

            page = pdf_document.load_page(page_index)

            zoom = OCR_DPI / 72
            matrix = pymupdf.Matrix(zoom, zoom)

            pixmap = page.get_pixmap(
                matrix=matrix,
                alpha=False,
            )

            image_bytes = pixmap.tobytes("png")
            image = Image.open(BytesIO(image_bytes))

            return pytesseract.image_to_string(
                image,
                config="--psm 3",
            ).strip()

    except TesseractNotFoundError as exc:
        raise ResumeExtractionError(
            "This PDF appears to be scanned, but the OCR engine "
            "is not installed or could not be found. Install Tesseract "
            "OCR on the backend machine and try again."
        ) from exc

    except ResumeExtractionError:
        raise

    except Exception as exc:
        raise ResumeExtractionError(
            f"OCR could not process PDF page {page_index + 1}."
        ) from exc


def extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract text from every PDF page.

    Normal embedded text is preferred. OCR is automatically used for
    pages where embedded text is missing or insufficient.

    This supports:
    - Normal text-based PDFs.
    - Scanned/image-based PDFs.
    - Mixed PDFs containing both types of pages.
    """

    try:
        reader = PdfReader(
            BytesIO(file_bytes),
            strict=True,
        )

        if reader.is_encrypted:
            raise ResumeExtractionError(
                "Password-protected PDFs are not supported."
            )

        extracted_pages = []

        for page_index, page in enumerate(reader.pages):
            page_text = (page.extract_text() or "").strip()

            if _needs_ocr(page_text):
                ocr_text = extract_pdf_page_with_ocr(
                    file_bytes,
                    page_index,
                )

                # Use OCR output when available. Retain any embedded
                # text if OCR does not find additional readable content.
                if ocr_text:
                    page_text = ocr_text
                elif not page_text:
                    page_text = ""

            extracted_pages.append(page_text)

        text = "\n".join(
            page for page in extracted_pages if page
        ).strip()

        if not text:
            raise ResumeExtractionError(
                "No readable text was found in the PDF. "
                "The document may be blank, unreadable or contain "
                "images that OCR could not recognize."
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
        r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)",
        text,
    )

    name_match = re.search(
        r"(?im)^\s*(?:name|candidate name)\s*:\s*(.+?)\s*$",
        text,
    )

    return {
        "candidate_name": (
            name_match.group(1).strip()
            if name_match
            else None
        ),
        "email": (
            email_match.group(0)
            if email_match
            else None
        ),
        "phone": (
            phone_match.group(0).strip()
            if phone_match
            else None
        ),
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

        # Preserve content as written without inventing summaries.
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

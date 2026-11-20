
import io
import zipfile

import pytest
from docx import Document

from backend.app.services import resume_extraction_service as extraction
from backend.app.services.resume_extraction_service import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    ResumeExtractionError,
    extract_resume,
    validate_resume_file,
)


def create_docx_bytes():
    document = Document()

    document.add_paragraph("Name: Alex Kumar")
    document.add_paragraph("alex@example.com")
    document.add_paragraph("+91 9876543210")

    document.add_heading("Education", level=1)
    document.add_paragraph("B.Sc. Computer Science - RV University")

    document.add_heading("Technical Skills", level=1)
    document.add_paragraph("Python")
    document.add_paragraph("FastAPI")
    document.add_paragraph("SQL")

    document.add_heading("Projects", level=1)
    document.add_paragraph("AI Interview Simulator")

    document.add_heading("Work Experience", level=1)
    document.add_paragraph("Software Development Intern")

    document.add_heading("Certifications", level=1)
    document.add_paragraph("AWS Cloud Practitioner")

    buffer = io.BytesIO()
    document.save(buffer)

    return buffer.getvalue()


def fake_pdf_reader(monkeypatch, page_texts):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakePdfReader:
        is_encrypted = False

        def __init__(self, stream, strict=True):
            self.pages = [
                FakePage(text)
                for text in page_texts
            ]

    monkeypatch.setattr(
        extraction,
        "PdfReader",
        FakePdfReader,
    )


def test_extract_docx_resume():
    result = extract_resume(
        create_docx_bytes(),
        "resume.docx",
        DOCX_MIME_TYPE,
    )

    assert "Alex Kumar" in result.raw_text
    assert result.structured_data["candidate_name"] == "Alex Kumar"
    assert result.structured_data["email"] == "alex@example.com"
    assert (
        "B.Sc. Computer Science - RV University"
        in result.structured_data["education"]
    )
    assert result.structured_data["skills"] == [
        "Python",
        "FastAPI",
        "SQL",
    ]
    assert result.structured_data["projects"] == [
        "AI Interview Simulator",
    ]
    assert result.structured_data["work_experience"] == [
        "Software Development Intern",
    ]
    assert result.structured_data["certifications"] == [
        "AWS Cloud Practitioner",
    ]


def test_extract_pdf_resume_without_ocr(monkeypatch):
    page_text = (
        "Name: Alex Kumar\n"
        "alex@example.com\n"
        "Technical Skills\n"
        "Python"
    )

    fake_pdf_reader(monkeypatch, [page_text])

    def unexpected_ocr(*args, **kwargs):
        pytest.fail("OCR should not run for a text-based PDF.")

    monkeypatch.setattr(
        extraction,
        "extract_pdf_page_with_ocr",
        unexpected_ocr,
    )

    result = extract_resume(
        b"%PDF-1.4 test-pdf-content",
        "resume.pdf",
        PDF_MIME_TYPE,
    )

    assert "Alex Kumar" in result.raw_text
    assert result.structured_data["candidate_name"] == "Alex Kumar"
    assert result.structured_data["skills"] == ["Python"]


def test_extract_scanned_pdf_using_ocr(monkeypatch):
    fake_pdf_reader(monkeypatch, [""])

    monkeypatch.setattr(
        extraction,
        "extract_pdf_page_with_ocr",
        lambda file_bytes, page_index: (
            "Name: Alex Kumar\n"
            "alex@example.com\n"
            "Technical Skills\n"
            "Python"
        ),
    )

    result = extract_resume(
        b"%PDF-1.4 scanned-pdf",
        "scanned_resume.pdf",
        PDF_MIME_TYPE,
    )

    assert "Alex Kumar" in result.raw_text
    assert result.structured_data["candidate_name"] == "Alex Kumar"
    assert result.structured_data["email"] == "alex@example.com"
    assert result.structured_data["skills"] == ["Python"]


def test_extract_mixed_pdf_uses_ocr_only_for_scanned_pages(monkeypatch):
    normal_page = (
        "Name: Alex Kumar\n"
        "alex@example.com\n"
        "Education\n"
        "Computer Science degree"
    )

    fake_pdf_reader(
        monkeypatch,
        [
            normal_page,
            "",
        ],
    )

    ocr_calls = []

    def fake_ocr(file_bytes, page_index):
        ocr_calls.append(page_index)
        return "Projects\nAI Interview Simulator"

    monkeypatch.setattr(
        extraction,
        "extract_pdf_page_with_ocr",
        fake_ocr,
    )

    result = extract_resume(
        b"%PDF-1.4 mixed-pdf",
        "mixed_resume.pdf",
        PDF_MIME_TYPE,
    )

    assert "Alex Kumar" in result.raw_text
    assert "AI Interview Simulator" in result.raw_text
    assert ocr_calls == [1]
    assert result.structured_data["candidate_name"] == "Alex Kumar"
    assert result.structured_data["projects"] == [
        "AI Interview Simulator",
    ]


def test_extract_pdf_with_sparse_embedded_text_uses_ocr(monkeypatch):
    fake_pdf_reader(
        monkeypatch,
        ["Alex"],
    )

    ocr_calls = []

    def fake_ocr(file_bytes, page_index):
        ocr_calls.append(page_index)
        return (
            "Name: Alex Kumar\n"
            "alex@example.com\n"
            "Education\n"
            "Computer Science"
        )

    monkeypatch.setattr(
        extraction,
        "extract_pdf_page_with_ocr",
        fake_ocr,
    )

    result = extract_resume(
        b"%PDF-1.4 sparse-pdf",
        "resume.pdf",
        PDF_MIME_TYPE,
    )

    assert ocr_calls == [0]
    assert "Alex Kumar" in result.raw_text


def test_reject_empty_file():
    with pytest.raises(ResumeExtractionError, match="empty"):
        validate_resume_file(
            b"",
            "resume.pdf",
            PDF_MIME_TYPE,
        )


def test_reject_oversized_file():
    with pytest.raises(ResumeExtractionError, match="maximum"):
        validate_resume_file(
            b"%PDF-" + b"x" * 100,
            "resume.pdf",
            PDF_MIME_TYPE,
            max_size_bytes=20,
        )


def test_reject_pdf_with_invalid_signature():
    with pytest.raises(ResumeExtractionError, match="valid PDF"):
        validate_resume_file(
            b"NOT-A-PDF",
            "resume.pdf",
            PDF_MIME_TYPE,
        )


def test_reject_mismatched_pdf_mime_type():
    with pytest.raises(ResumeExtractionError, match="content type"):
        validate_resume_file(
            b"%PDF-1.4 test",
            "resume.pdf",
            "text/plain",
        )


def test_reject_unsupported_extension():
    with pytest.raises(ResumeExtractionError, match="Unsupported"):
        validate_resume_file(
            b"some content",
            "resume.txt",
            "text/plain",
        )


def test_reject_corrupted_docx():
    with pytest.raises(ResumeExtractionError, match="corrupted"):
        validate_resume_file(
            b"not-a-zip-file",
            "resume.docx",
            DOCX_MIME_TYPE,
        )


def test_reject_docx_with_invalid_document_structure():
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("some_other_file.xml", "<root/>")

    with pytest.raises(ResumeExtractionError, match="valid DOCX"):
        validate_resume_file(
            buffer.getvalue(),
            "resume.docx",
            DOCX_MIME_TYPE,
        )


def test_reject_password_protected_pdf(monkeypatch):
    class FakeEncryptedPdfReader:
        is_encrypted = True
        pages = []

        def __init__(self, stream, strict=True):
            pass

    monkeypatch.setattr(
        extraction,
        "PdfReader",
        FakeEncryptedPdfReader,
    )

    with pytest.raises(ResumeExtractionError, match="Password-protected"):
        extract_resume(
            b"%PDF-1.4 encrypted",
            "resume.pdf",
            PDF_MIME_TYPE,
        )


def test_reject_pdf_without_extractable_text_or_ocr(monkeypatch):
    fake_pdf_reader(monkeypatch, [""])

    monkeypatch.setattr(
        extraction,
        "extract_pdf_page_with_ocr",
        lambda file_bytes, page_index: "",
    )

    with pytest.raises(ResumeExtractionError, match="No readable text"):
        extract_resume(
            b"%PDF-1.4 blank",
            "resume.pdf",
            PDF_MIME_TYPE,
        )


def test_ocr_failure_is_reported(monkeypatch):
    fake_pdf_reader(monkeypatch, [""])

    def fail_ocr(file_bytes, page_index):
        raise ResumeExtractionError(
            "OCR could not process PDF page 1."
        )

    monkeypatch.setattr(
        extraction,
        "extract_pdf_page_with_ocr",
        fail_ocr,
    )

    with pytest.raises(ResumeExtractionError, match="OCR could not process"):
        extract_resume(
            b"%PDF-1.4 unreadable",
            "resume.pdf",
            PDF_MIME_TYPE,
        )


def test_missing_resume_information_is_not_invented():
    document = Document(io.BytesIO(create_docx_bytes()))

    document.paragraphs[0].text = (
        "A resume without a labelled name"
    )
    document.paragraphs[1].text = "No email address here"
    document.paragraphs[2].text = "No phone number here"

    buffer = io.BytesIO()
    document.save(buffer)

    result = extract_resume(
        buffer.getvalue(),
        "resume.docx",
        DOCX_MIME_TYPE,
    )

    assert result.structured_data["candidate_name"] is None
    assert result.structured_data["email"] is None
    assert result.structured_data["phone"] is None

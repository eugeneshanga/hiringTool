"""Shared validation for candidate-uploaded files: résumés (routes/apply.py,
routes/candidates.py) and onboarding documents (routes/status.py,
routes/candidates.py).

Three checks, in order:
  1. extension is on the allowlist
  2. the file's actual content matches that extension (magic bytes, or the
     internal archive layout for .docx) - a filename extension is trivially
     spoofable, and apply()/upload_status_document() are public
  3. size is under the cap

Check #2 is the security-critical one: without it, someone could upload an
HTML file named `resume.pdf`, and a recruiter opening it (the frontend
does window.open() on a blob URL, which inherits this app's origin) would
execute that HTML as us - stored XSS with the recruiter's session.
"""
import os
import zipfile

# Résumés: real documents only, nothing a browser will render as markup.
RESUME_EXTENSIONS = {'.pdf', '.docx'}
# Onboarding docs additionally allow a phone photo of an ID / certificate.
ONBOARDING_EXTENSIONS = {'.pdf', '.docx', '.jpg', '.jpeg', '.png'}

_FILE_SIGNATURES = {
    '.pdf': (b'%PDF',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
}


def _looks_like_docx(stream):
    """.docx is a ZIP archive with a specific internal layout - checking for
    word/document.xml is a real (if not airtight) distinction from an
    arbitrary renamed .zip, which a plain PK-signature match can't make
    (every ZIP-based format shares it)."""
    try:
        with zipfile.ZipFile(stream) as zf:
            return 'word/document.xml' in zf.namelist()
    except zipfile.BadZipFile:
        return False
    finally:
        stream.seek(0)


def _content_matches_extension(stream, ext):
    if ext == '.docx':
        return _looks_like_docx(stream)
    signatures = _FILE_SIGNATURES.get(ext, ())
    header = stream.read(max((len(s) for s in signatures), default=0))
    stream.seek(0)
    return any(header.startswith(sig) for sig in signatures)


def _size_of(stream):
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def _pretty(extensions):
    # ".jpeg" is the same format as ".jpg" - list it once.
    names = [e.lstrip('.').upper() for e in sorted(extensions) if e != '.jpeg']
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def reject_bad_upload(file_storage, *, allowed_extensions, max_size_bytes):
    """Returns an ``({"error": ...}, 400)`` tuple to return as-is from the
    view on the first problem found (Flask jsonifies the dict), or ``None``
    if the file passes every check.

    The caller owns the "a file is required" check (its wording differs by
    endpoint); this assumes ``file_storage`` is present and has a filename.
    """
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_extensions:
        return {"error": f"only {_pretty(allowed_extensions)} files are accepted"}, 400
    if not _content_matches_extension(file_storage.stream, ext):
        return {"error": f"that file doesn't look like a valid {ext.lstrip('.').upper()} file"}, 400
    if _size_of(file_storage.stream) > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        return {"error": f"that file is too large - please upload something under {max_mb}MB"}, 400
    return None

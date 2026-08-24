import os
import shutil
import uuid
from flask import current_app
from werkzeug.utils import secure_filename


def _candidate_dir(candidate_id, create=True):
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'candidates', str(candidate_id))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def delete_candidate_files(candidate_id):
    """Removes everything uploaded for a candidate (resume + documents), e.g.
    when the candidate record itself is deleted."""
    path = _candidate_dir(candidate_id, create=False)
    if os.path.isdir(path):
        shutil.rmtree(path)


def save_candidate_file(candidate_id, file_storage):
    """Writes an uploaded FileStorage to disk under a UUID-prefixed name (so two
    uploads with the same original filename never collide) and returns
    (original_filename, stored_filename)."""
    original_filename = secure_filename(file_storage.filename) or 'upload'
    stored_filename = f'{uuid.uuid4().hex}_{original_filename}'
    file_storage.save(os.path.join(_candidate_dir(candidate_id), stored_filename))
    return original_filename, stored_filename


def candidate_file_path(candidate_id, stored_filename):
    return os.path.join(_candidate_dir(candidate_id), stored_filename)


def delete_candidate_file(candidate_id, stored_filename):
    path = candidate_file_path(candidate_id, stored_filename)
    if os.path.exists(path):
        os.remove(path)


def _organization_dir(create=True):
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'organization')
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def save_organization_file(file_storage):
    """Same UUID-prefixed scheme as save_candidate_file, for the
    organization's logo/banner (there's only ever one org, so no id to key
    the directory by)."""
    original_filename = secure_filename(file_storage.filename) or 'upload'
    stored_filename = f'{uuid.uuid4().hex}_{original_filename}'
    file_storage.save(os.path.join(_organization_dir(), stored_filename))
    return original_filename, stored_filename


def organization_file_path(stored_filename):
    return os.path.join(_organization_dir(), stored_filename)


def delete_organization_file(stored_filename):
    path = organization_file_path(stored_filename)
    if os.path.exists(path):
        os.remove(path)

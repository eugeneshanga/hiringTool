"""The public careers landing page - what a visitor sees at the site's
root ('/' - see frontend/src/App.tsx) when they navigate to the domain
directly rather than arriving via a specific job's link (which goes
straight to PublicApplyPage instead, unaffected by any of this).

Distinct from apply.py (applying to a specific job once one's been picked)
and status.py (looking up an existing application) - this is purely "what
does a first-time visitor see": the organization's name/logo and the list
of open jobs to choose from.
"""
from flask import Blueprint, jsonify, send_file

from file_storage import organization_file_path
from models import Job, Organization

public_bp = Blueprint('public', __name__)


@public_bp.route('/api/public/organization', methods=['GET'])
def get_public_organization():
    """Name + whether a logo exists, for the landing page header. Reads
    Organization directly rather than via organization.py's
    _get_organization() - same reasoning as apply.py's get_public_job: a
    public, unauthenticated endpoint shouldn't be what first creates the
    org record, so a generic fallback name covers the not-yet-set-up case
    instead. Deliberately hand-picked fields rather than
    Organization.to_dict(), which also carries scheduling settings that
    have no reason to be public."""
    org = Organization.query.first()
    return jsonify({
        "name": org.name if org else "this organization",
        "has_logo": bool(org and org.logo_stored_filename),
    }), 200


@public_bp.route('/api/public/organization/logo', methods=['GET'])
def get_public_organization_logo():
    """No auth, unlike organization.py's download_logo - the landing page
    renders this in a plain <img src>, which can't carry an Authorization
    header (same reason candidate/organization document downloads
    elsewhere in the app go through an authenticated blob fetch instead of
    a plain URL - this just doesn't need auth at all, since a logo isn't
    sensitive)."""
    org = Organization.query.first()
    if not org or not org.logo_stored_filename:
        return jsonify({"error": "no logo uploaded"}), 404
    return send_file(organization_file_path(org.logo_stored_filename), download_name=org.logo_original_filename)


@public_bp.route('/api/public/jobs', methods=['GET'])
def list_public_jobs():
    """Every Published job, for the landing page's job list - same
    minimal, hand-picked contract as get_public_job in apply.py (not
    Job.to_dict(), which carries recruiter-only fields like
    candidate_count). Draft/Closed jobs are never included, same as
    they're not reachable via GET /api/apply/jobs/<id> either. Newest
    first, so a freshly published job doesn't get buried."""
    jobs = Job.query.filter_by(status='Published').order_by(Job.created_at.desc()).all()
    return jsonify([
        {
            "id": job.id,
            "title": job.title,
            "location": job.location,
            "job_type": job.job_type or [],
            "min_salary": job.min_salary,
            "max_salary": job.max_salary,
            "salary_period": job.salary_period,
        }
        for job in jobs
    ]), 200

"""Server-side verification of a Google reCAPTCHA v2 ("I'm not a robot"
checkbox) token submitted alongside the recruiter login form (routes/
auth.py) - see config.py's RECAPTCHA_SECRET_KEY/RECAPTCHA_SITE_KEY.

Split into its own module, same reasoning as microsoft_calendar.py/
ringcentral_video.py: isolates the one real network call so tests can
monkeypatch just this function rather than requests itself.
"""
import requests

RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'


def verify_recaptcha(secret_key, token, remote_ip=None):
    """True if Google confirms `token` as a real, unexpired, unused solve
    of our site's challenge. Raises requests.RequestException on a
    network-level failure - routes/auth.py's login() treats that as a
    reason to reject the attempt (fail closed) rather than silently
    skipping the check, since this guards a security-sensitive endpoint."""
    payload = {'secret': secret_key, 'response': token}
    if remote_ip:
        payload['remoteip'] = remote_ip
    resp = requests.post(RECAPTCHA_VERIFY_URL, data=payload, timeout=10)
    resp.raise_for_status()
    return bool(resp.json().get('success'))

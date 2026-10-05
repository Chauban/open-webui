"""用户自助改登录邮箱:必须验证当前密码,新邮箱要合法且未被占用。"""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from open_webui.models.auths import Auth
from open_webui.models.users import User
from open_webui.test.apps.webui.routers.test_student_signup_invite_gate import (
    INVITE_CODE,
    _signup,
    _signup_app,
)
from open_webui.test.util.database import migrated_database

PASSWORD = "Passw0rd!2345"
OLD_EMAIL = "old@example.com"


@pytest.fixture
def signed_in():
    with migrated_database() as sync_url, _signup_app(sync_url) as (
        client,
        SessionLocal,
    ):
        res = _signup(
            client, education_role="student", invite_code=INVITE_CODE, email=OLD_EMAIL
        )
        assert res.status_code == 200, res.text
        headers = {"Authorization": f"Bearer {res.json()['token']}"}
        yield client, SessionLocal, headers


def _update_email(client, headers, email, password=PASSWORD):
    return client.post(
        "/api/v1/auths/update/email",
        json={"email": email, "password": password},
        headers=headers,
    )


def _emails(SessionLocal):
    with SessionLocal() as session:
        users = {u.email for u in session.query(User).all()}
        auths = {a.email for a in session.query(Auth).all()}
        return users, auths


def test_update_email_changes_login_email(signed_in):
    """改完后用户表和凭据表同步,新邮箱能登录、旧邮箱不能。"""
    client, SessionLocal, headers = signed_in

    res = _update_email(client, headers, "  New@Example.com ")
    assert res.status_code == 200, res.text
    assert res.json() == {"email": "new@example.com"}

    users, auths = _emails(SessionLocal)
    assert "new@example.com" in users and OLD_EMAIL not in users
    assert "new@example.com" in auths and OLD_EMAIL not in auths

    signin = client.post(
        "/api/v1/auths/signin",
        json={"email": "new@example.com", "password": PASSWORD},
    )
    assert signin.status_code == 200, signin.text
    old_signin = client.post(
        "/api/v1/auths/signin", json={"email": OLD_EMAIL, "password": PASSWORD}
    )
    assert old_signin.status_code != 200


def test_update_email_requires_correct_password(signed_in):
    client, SessionLocal, headers = signed_in

    res = _update_email(client, headers, "new@example.com", password="wrong-pass")
    assert res.status_code == 400, res.text

    users, _ = _emails(SessionLocal)
    assert OLD_EMAIL in users


def test_update_email_rejects_invalid_format(signed_in):
    client, _, headers = signed_in

    res = _update_email(client, headers, "not-an-email")
    assert res.status_code == 400, res.text


def test_update_email_rejects_taken_email(signed_in):
    """教师种子账号已占用 teacher@example.com。"""
    client, SessionLocal, headers = signed_in

    res = _update_email(client, headers, "teacher@example.com")
    assert res.status_code == 400, res.text

    users, _ = _emails(SessionLocal)
    assert OLD_EMAIL in users

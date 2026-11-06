"""Courseware uses existing authentication and protects every media request."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from open_webui.routers import courseware
from open_webui.utils.auth import get_current_user


@pytest.fixture
def lesson(tmp_path, monkeypatch):
    (tmp_path / 'index.html').write_text('<h1>Lesson</h1>', encoding='utf-8')
    (tmp_path / '案例.mp4').write_bytes(b'0123456789')
    (tmp_path / 'private.txt').write_text('not published', encoding='utf-8')
    monkeypatch.setattr(courseware, 'COURSEWARE_DIR', str(tmp_path))
    app = FastAPI()
    app.include_router(courseware.router, prefix='/api/v1/courseware')
    with TestClient(app) as client:
        yield client, app


@pytest.mark.parametrize('path', ['/', '/content/index.html', '/content/案例.mp4'])
def test_anonymous_cannot_read_any_courseware(lesson, path):
    client, _ = lesson
    assert client.get('/api/v1/courseware' + path).status_code == 401


@pytest.mark.parametrize('role', ['user', 'admin'])
def test_all_active_roles_can_read_html_and_seek_video(lesson, role):
    client, app = lesson
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role)
    assert client.get('/api/v1/courseware/').json() == {'entry': 'index.html'}
    page = client.get('/api/v1/courseware/content/index.html')
    assert page.status_code == 200
    assert page.headers['content-type'].startswith('text/html')
    assert page.headers['cache-control'] == 'private, no-store'
    video = client.get('/api/v1/courseware/content/案例.mp4', headers={'Range': 'bytes=2-5'})
    assert video.status_code == 206
    assert video.content == b'2345'
    assert video.headers['content-range'] == 'bytes 2-5/10'
    assert client.get('/api/v1/courseware/content/案例.mp4', headers={'Range': 'bytes=99-'}).status_code == 416


def test_pending_accounts_and_disabled_instances_are_denied(lesson, monkeypatch):
    client, app = lesson
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role='pending')
    assert client.get('/api/v1/courseware/content/index.html').status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role='user')
    monkeypatch.setattr(courseware, 'COURSEWARE_DIR', '')
    assert not courseware.is_enabled()
    assert client.get('/api/v1/courseware/').status_code == 404
    assert client.get('/api/v1/courseware/content/index.html').status_code == 404


@pytest.mark.parametrize('filename', ['private.txt', 'missing.mp4', '..%5Cindex.html', '..%2Findex.html'])
def test_unpublished_and_traversal_paths_are_denied(lesson, filename):
    client, app = lesson
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role='user')
    assert client.get('/api/v1/courseware/content/' + filename).status_code == 404


def test_logout_removes_access_even_for_range_requests(lesson):
    client, app = lesson
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role='user')
    assert client.get('/api/v1/courseware/content/index.html').status_code == 200
    app.dependency_overrides.clear()
    assert client.get('/api/v1/courseware/content/案例.mp4', headers={'Range': 'bytes=0-2'}).status_code == 401

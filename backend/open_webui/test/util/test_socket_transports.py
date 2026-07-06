from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from open_webui.socket.main import get_socketio_transports, sio


def test_socketio_transports_accept_polling_when_websocket_enabled():
    assert get_socketio_transports(True) == ["polling", "websocket"]


def test_socketio_transports_use_polling_when_websocket_disabled():
    assert get_socketio_transports(False) == ["polling"]


def test_socketio_server_accepts_polling_transport():
    assert "polling" in sio.eio.transports

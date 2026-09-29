"""Capture security and lifecycle tests using an isolated Flask app."""
from html.parser import HTMLParser

from flask import Flask
from flask_login import LoginManager, UserMixin
import pytest

from language_engine.captures import init_captures
from language_engine.captures.content import sanitize_snapshot
from language_engine.captures.store import CaptureStore, CaptureTooLarge


class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test-only-secret", CAPTURE_MAX_BYTES=4096)
    login = LoginManager(app)

    @login.request_loader
    def load_user(request):
        user_id = request.headers.get("X-Test-User")
        return User(user_id) if user_id in {"alice", "bob"} else None

    init_captures(app)
    return app


def auth(client, user="alice"):
    headers = {"X-Test-User": user}
    token = client.get("/api/extension_capture_token", headers=headers).get_json()["csrfToken"]
    return {**headers, "X-CSRF-Token": token}


def upload(client, headers, html="<p>မြန်မာ <b>reader</b></p>"):
    return client.post("/api/extension_capture", headers=headers,
                       json={"html": html, "url": "https://example.org/source", "title": "Sample"})


def test_anonymous_upload_and_read_are_rejected(app):
    client = app.test_client()
    assert upload(client, {}).status_code == 401
    assert client.get("/api/extension_capture_token").status_code == 401
    assert client.get("/extension/snapshot/not-a-token").status_code == 401


def test_upload_requires_session_csrf_token(app):
    client = app.test_client()
    assert upload(client, {"X-Test-User": "alice"}).status_code == 403
    headers = auth(client)
    assert upload(client, {**headers, "X-CSRF-Token": "wrong"}).status_code == 403
    assert upload(client, headers).status_code == 200


def test_private_document_and_payload_preserve_readable_text(app):
    client = app.test_client()
    headers = auth(client)
    record = upload(client, headers).get_json()
    view = client.get(record["viewerUrl"], headers=headers)
    assert view.status_code == 200
    assert "မြန်မာ" in view.get_data(as_text=True)
    assert "<b>reader</b>" in view.get_data(as_text=True)
    assert "sandbox" in view.headers["Content-Security-Policy"]
    assert "script-src 'none'" in view.headers["Content-Security-Policy"]
    assert "no-store" in view.headers["Cache-Control"]
    assert view.headers["X-Content-Type-Options"] == "nosniff"
    payload = client.get(record["snapshotPayloadUrl"], headers=headers).get_json()["page"]
    assert payload["html"] == view.get_data(as_text=True)
    assert payload["snapshot"]["requestedUrl"] == "https://example.org/source"
    for url in (record["viewerUrl"], record["snapshotPayloadUrl"]):
        assert client.get(url, headers={"X-Test-User": "bob"}).status_code == 404


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.mark.parametrize("attack", [
    '<script>parent.document.body.innerHTML="owned"</script><p onclick="alert(1)">safe</p>',
    '<svg><a xlink:href="javascript:alert(1)">attack</a></svg><math><mtext>attack</mtext></math>',
    '<iframe srcdoc="<script>alert(1)</script>"></iframe><object data="/account"></object>',
    '<form action="/payments/change"><input name="plan"></form><a href="javascript:alert(1)">link</a>',
    '<meta http-equiv="refresh" content="0;url=https://attacker.invalid"><base href="https://attacker.invalid">',
    '<img src="/account"><img src="https://attacker.invalid/pixel"><img src="data:image/svg+xml,attack">',
    '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=alert(1)>">',
])
def test_active_content_and_external_references_are_removed(attack):
    document = sanitize_snapshot(attack)
    for tag, attributes in Elements(document).elements:
        assert tag not in {"script", "iframe", "object", "embed", "svg", "math", "base", "form", "input"}
        assert not any(key.startswith("on") for key in attributes)
        assert "href" not in attributes
        if "src" in attributes:
            assert attributes["src"].startswith("data:image/")
        if tag == "meta":
            assert attributes.get("http-equiv", "").lower() != "refresh"


def test_styles_and_embedded_raster_images_remain_available():
    document = sanitize_snapshot('<style>p{color:red}</style><p style="font-size:20px">text</p>'
                                 '<img alt="figure" src="data:image/png;base64,iVBORw0KGgo=">')
    assert "p{color:red}" in document
    assert 'style="font-size:20px"' in document
    assert 'src="data:image/png;base64,iVBORw0KGgo="' in document
    assert "default-src &#x27;none&#x27;" in document


def test_size_limits_apply_to_decoded_html_and_raw_request(app):
    client = app.test_client()
    headers = auth(client)
    assert upload(client, headers, "က" * 2000).status_code == 413
    assert client.post("/api/extension_capture", headers=headers, content_type="application/json",
                       data=b" " * 80000).status_code == 413


def test_upload_throttling(app):
    client = app.test_client()
    headers = auth(client)
    for _ in range(4):
        assert upload(client, headers).status_code == 200
    assert upload(client, headers).status_code == 429


def test_store_expiry_byte_budget_and_owner_isolation():
    now = [0]
    store = CaptureStore(max_bytes=10, total_bytes=12, max_items=2, ttl=60,
                         uploads_per_minute=1, clock=lambda: now[0])
    first = store.put("alice", "12345678", "", "")
    assert store.get("bob", first) is None
    second = store.put("alice", "abcdefgh", "", "")
    assert store.get("alice", first) is None
    assert store.get("alice", second) is not None
    with pytest.raises(CaptureTooLarge):
        store.put("alice", "x" * 11, "", "")
    assert store.allow_upload("alice")
    assert not store.allow_upload("alice")
    now[0] = 60
    assert store.get("alice", second) is None  # expiry applies even without new writes
    assert store.allow_upload("alice")


def test_expiry_does_not_slide_on_read():
    now = [0]
    store = CaptureStore(max_bytes=10, total_bytes=20, max_items=2, ttl=60,
                         uploads_per_minute=4, clock=lambda: now[0])
    token = store.put("alice", "text", "", "")
    now[0] = 59
    assert store.get("alice", token) is not None
    now[0] = 60
    assert store.get("alice", token) is None

from pathlib import Path

from helpers import requires_postgres


@requires_postgres
def test_create_session_creates_output_dir(client, tmp_path, monkeypatch) -> None:
    root = tmp_path / "sessions"
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(root))

    create = client.post(
        "/sessions",
        json={"user_id": "user-demo", "title": "PO extraction"},
    )
    assert create.status_code == 201
    body = create.json()
    output_dir = Path(body["output_dir"])
    assert output_dir.is_dir()
    assert output_dir.parts[-2] == "user-demo"
    assert output_dir.name == body["id"]

from wizard_api.models import WizardSession


def test_wizard_sessions_table_columns() -> None:
    columns = {c.name for c in WizardSession.__table__.columns}
    assert columns == {
        "id",
        "user_id",
        "step",
        "gate_statuses",
        "metadata",
        "output_dir",
        "created_at",
        "updated_at",
    }


def test_default_gate_statuses() -> None:
    session = WizardSession(user_id="user-1", output_dir="/tmp/wizard/out")
    assert session.gate_statuses["gate_1"] == "pending"
    assert session.step == 1

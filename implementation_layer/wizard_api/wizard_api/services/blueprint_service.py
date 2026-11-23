import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from wizard_api.models import BlueprintVersion, WizardSession
from wizard_api.schemas.blueprint import BlueprintContent


class InvalidBlueprintContentError(ValueError):
    """A blueprint body that SessionDetailResponse could not have served.

    Until now the body was stored as given and validated only when read, so
    one bad PATCH (``{"steps": "x"}``) made every GET of the session a 500 for
    good. The check belongs where the version is written.
    """

    def __init__(self, errors: list[dict]):
        self.errors = errors
        where = ", ".join(".".join(str(p) for p in e.get("loc", ())) or "body" for e in errors)
        super().__init__(f"blueprint content is not valid: {where}")


def validate_content(content: dict) -> dict:
    """Return ``content`` unchanged if it is a blueprint the API can serve.

    Validation only; the stored body keeps every key the caller sent (BPMN sync
    fields and anything newer than the schema), as before.
    """
    try:
        BlueprintContent.model_validate(content)
    except ValidationError as exc:
        raise InvalidBlueprintContentError(
            [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors(include_url=False, include_input=False)
            ]
        ) from exc
    return content


def default_blueprint_content(title: str) -> dict:
    """Dummy blueprint so new sessions have editable BPMN/JSON before schema design.

    It has no goal. A session is created with a title only, so nothing is known
    of its use case yet, and a sentence written here reached the Blueprint tab
    as the solution's goal. The goal comes with the agent's draft
    (``business_spec.poc_goal``, artifact_sync.blueprint_from_draft) or from the
    user in the Blueprint form.
    """
    name = title.strip() or "Nimetön sessio"
    return {
        "name": name,
        "description": (
            "Placeholder blueprint until schema design — replace with the agreed output fields."
        ),
        "goal": "",
        "steps": [
            {
                "id": "input",
                "name": "Input",
                "type": "io",
                "description": "User or system input (placeholder)",
            },
            {
                "id": "process",
                "name": "Process",
                "type": "ai",
                "component": "LLM",
                "description": "Core GenAI step (placeholder)",
            },
            {
                "id": "review",
                "name": "Human review",
                "type": "human_review",
                "description": "Optional check before output (placeholder)",
            },
            {
                "id": "output",
                "name": "Output",
                "type": "io",
                "description": "Returned result (placeholder)",
            },
        ],
    }


def is_placeholder(content: dict | None) -> bool:
    """True while the blueprint is still the seed nobody has designed anything into.

    The seed exists so BPMN and JSON are editable from the first session; it is
    not a design. Generating a PoC from it produced a skeleton that wired nothing
    and said nothing about why (#181).
    """
    if not isinstance(content, dict):
        return False
    return content.get("steps") == default_blueprint_content("x")["steps"]


def create_initial_version(
    db: Session,
    session: WizardSession,
    *,
    title: str,
    note: str = "Alustava blueprint",
) -> BlueprintVersion:
    version = BlueprintVersion(
        session_id=session.id,
        version=1,
        note=note,
        content=default_blueprint_content(title),
    )
    db.add(version)
    session.active_version = 1
    return version


def add_version(
    db: Session,
    session: WizardSession,
    *,
    note: str,
    content: dict | None = None,
) -> BlueprintVersion:
    latest = get_latest_version(db, session.id)
    next_version = 1 if latest is None else latest.version + 1
    body = (
        validate_content(content)
        if content is not None
        else (latest.content if latest else default_blueprint_content(""))
    )
    version = BlueprintVersion(
        session_id=session.id,
        version=next_version,
        note=note,
        content=body,
    )
    db.add(version)
    session.active_version = next_version
    return version


def list_versions(db: Session, session_id: uuid.UUID) -> list[BlueprintVersion]:
    stmt = (
        select(BlueprintVersion)
        .where(BlueprintVersion.session_id == session_id)
        .order_by(BlueprintVersion.version.asc())
    )
    return list(db.scalars(stmt).all())


def get_latest_version(db: Session, session_id: uuid.UUID) -> BlueprintVersion | None:
    stmt = (
        select(BlueprintVersion)
        .where(BlueprintVersion.session_id == session_id)
        .order_by(BlueprintVersion.version.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def get_active_version(db: Session, session: WizardSession) -> BlueprintVersion | None:
    stmt = select(BlueprintVersion).where(
        BlueprintVersion.session_id == session.id,
        BlueprintVersion.version == session.active_version,
    )
    return db.scalars(stmt).first()

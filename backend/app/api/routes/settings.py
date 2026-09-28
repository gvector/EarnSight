from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.crypto import encrypt_secret
from app.models.setting import AppSetting
from app.schemas.settings import SettingsIn, SettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])

VALID_PROVIDERS = ("", "ollama", "openai")


async def _get_setting(db, user) -> AppSetting:  # noqa: ANN001
    """Fetch the per-user LLM settings row, if one exists.

    Parameters
    ----------
    db : DB
        Async database session.
    user : User
        Authenticated user whose settings are being looked up.

    Returns
    -------
    AppSetting | None
        The user's settings row, or ``None`` when it has never been
        saved (the caller treats that as default settings).
    """
    result = await db.execute(select(AppSetting).where(AppSetting.user_id == user.id))
    return result.scalar_one_or_none()


def _to_out(row: AppSetting | None) -> SettingsOut:
    """Project a settings row onto the outbound schema.

    The stored OpenAI key is never returned: the API only reports whether
    one has been set, so the secret stays server-side.

    Parameters
    ----------
    row : AppSetting | None
        Persisted settings row, or ``None`` for defaults.

    Returns
    -------
    SettingsOut
        Response-shaped settings with ``openai_api_key_set`` as a boolean
        presence flag instead of the encrypted value.
    """
    if row is None:
        return SettingsOut()
    return SettingsOut(
        llm_provider=row.llm_provider,
        ollama_base_url=row.ollama_base_url,
        ollama_model=row.ollama_model,
        openai_model=row.openai_model,
        openai_api_key_set=row.openai_api_key_encrypted is not None,
    )


@router.get("", response_model=SettingsOut)
async def get_settings(db: DB, user: CurrentUser) -> SettingsOut:
    """Read the current user's LLM gateway settings (GET /settings).

    Returns defaults when the user has never saved a configuration; the
    OpenAI API key is exposed only as a "was set" boolean.

    Parameters
    ----------
    db : DB
        Async database session.
    user : CurrentUser
        Authenticated owner of the settings.

    Returns
    -------
    SettingsOut
        Current provider, model and endpoint settings.

    Dependencies
    -----------
    - db : get_db session for the AppSetting lookup.
    - user : get_current_user authentication.
    """
    return _to_out(await _get_setting(db, user))


@router.put("", response_model=SettingsOut)
async def update_settings(body: SettingsIn, db: DB, user: CurrentUser) -> SettingsOut:
    """Create or replace the current user's LLM gateway settings (PUT /settings).

    Upserts the per-user ``AppSetting`` row: creates it on first save, then
    applies the submitted values. An empty provider clears the selection;
    an explicitly non-empty ``openai_api_key`` is stored encrypted via
    ``encrypt_secret`` while an empty string clears the stored key.

    Parameters
    ----------
    body : SettingsIn
        Desired provider (``""``, ``"ollama"``, ``"openai"``), endpoint,
        models and optional OpenAI API key.
    db : DB
        Async database session.
    user : CurrentUser
        Authenticated owner of the settings row.

    Returns
    -------
    SettingsOut
        The persisted settings as returned by ``_to_out``.

    Raises
    ------
    HTTPException
        400 — ``llm_provider`` not in ``VALID_PROVIDERS``.

    Dependencies
    -----------
    - db : get_db session for the upsert.
    - user : get_current_user authentication.
    - encrypt_secret : at-rest encryption of the OpenAI key.
    """
    if body.llm_provider not in VALID_PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provider LLM non valido")
    row = await _get_setting(db, user)
    if row is None:
        row = AppSetting(user_id=user.id)
        db.add(row)
    row.llm_provider = body.llm_provider or None
    row.ollama_base_url = body.ollama_base_url or None
    row.ollama_model = body.ollama_model or None
    row.openai_model = body.openai_model or None
    if body.openai_api_key is not None:
        row.openai_api_key_encrypted = (
            encrypt_secret(body.openai_api_key) if body.openai_api_key else None
        )
    await db.commit()
    return _to_out(row)

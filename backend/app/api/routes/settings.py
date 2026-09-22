from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.crypto import encrypt_secret
from app.models.setting import AppSetting
from app.schemas.settings import SettingsIn, SettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])

VALID_PROVIDERS = ("", "ollama", "openai")


async def _get_setting(db, user) -> AppSetting:  # noqa: ANN001
    result = await db.execute(select(AppSetting).where(AppSetting.user_id == user.id))
    return result.scalar_one_or_none()


def _to_out(row: AppSetting | None) -> SettingsOut:
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
    return _to_out(await _get_setting(db, user))


@router.put("", response_model=SettingsOut)
async def update_settings(body: SettingsIn, db: DB, user: CurrentUser) -> SettingsOut:
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

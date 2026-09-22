"""Importa tutti i modelli: qualsiasi import di app.models registra tutte le
tabelle su Base.metadata (evita FK irrisolti in processi parziali, es. worker)."""

from app.models.payslip import PayslipDocument, PayslipEntry
from app.models.setting import AppSetting
from app.models.user import User

__all__ = ["PayslipDocument", "PayslipEntry", "AppSetting", "User"]

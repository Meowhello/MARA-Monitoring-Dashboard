from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(slots=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    secret_key: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    data_dir: Path = ROOT_DIR / os.getenv("DATA_DIR", "data")
    dashboard_file: str = os.getenv("DASHBOARD_FILE", "mara_dashboard.json")
    refresh_token: str = os.getenv("REFRESH_TOKEN", "change-me")
    date_range_days: int = int(os.getenv("DATE_RANGE_DAYS", "365"))
    company_name: str = os.getenv("COMPANY_NAME", "MARA Holdings")
    company_symbol: str = os.getenv("COMPANY_SYMBOL", "MARA")
    sec_cik: str = os.getenv("SEC_CIK", "0001507605")
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "MARA-Dashboard research@example.com")

    coingecko_plan: str = os.getenv("COINGECKO_PLAN", "demo").lower()
    coingecko_api_key: str = os.getenv("COINGECKO_API_KEY", "")
    coingecko_entity_id: str = os.getenv("COINGECKO_ENTITY_ID", "mara-holdings")
    treasury_coin_id: str = os.getenv("TREASURY_COIN_ID", "bitcoin")

    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    alpha_vantage_symbol: str = os.getenv("ALPHA_VANTAGE_SYMBOL", "MARA")

    auto_refresh_if_missing: bool = os.getenv("AUTO_REFRESH_IF_MISSING", "false").lower() == "true"

    @property
    def dashboard_path(self) -> Path:
        return self.data_dir / self.dashboard_file

    @property
    def coingecko_base_url(self) -> str:
        if self.coingecko_plan == "pro":
            return "https://pro-api.coingecko.com/api/v3"
        return "https://api.coingecko.com/api/v3"

    @property
    def coingecko_header_name(self) -> str:
        if self.coingecko_plan == "pro":
            return "x-cg-pro-api-key"
        return "x-cg-demo-api-key"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)

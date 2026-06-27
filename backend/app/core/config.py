from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10兼容；3.11+内置tomllib。
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"])


@dataclass
class DatabaseConfig:
    path: str = "backend/data/stock_picker.sqlite3"


@dataclass
class MarketDataConfig:
    provider: str = "auto"
    fallback_to_demo: bool = True
    clear_factor_cache_on_sync: bool = True


@dataclass
class AkshareConfig:
    enabled: bool = True
    adjust: str = "qfq"
    request_interval_seconds: float = 0.4
    default_start_date: str = "20240101"
    default_end_date: str = ""
    max_history_symbols: int = 80
    max_financial_symbols: int = 80
    max_news_symbols: int = 50
    max_metadata_symbols: int = 80


@dataclass
class TushareConfig:
    enabled: bool = True
    token: str = ""
    request_interval_seconds: float = 0.35
    default_start_date: str = "20240101"
    default_trade_date: str = ""


@dataclass
class LlmConfig:
    provider: str = "heuristic"
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.1
    max_tokens: int = 4000
    timeout_seconds: int = 30
    num_retries: int = 3
    local_model_path: str = ""


@dataclass
class SearchConfig:
    enabled: bool = True
    base_url: str = "https://open.feedcoopapi.com/search_api/web_search"
    api_key: str = ""
    model: str = "volc-search"
    timeout_seconds: int = 30
    default_count: int = 8
    max_count: int = 20
    default_search_type: str = "web"
    need_summary: bool = True
    need_content: bool = False


@dataclass
class WorkflowConfig:
    enabled: bool = True
    default_path: str = ""
    trace_payload_preview: bool = True


@dataclass
class FilterConfig:
    exclude_st: bool = True
    exclude_paused: bool = True
    new_stock_days: int = 180
    min_market_cap: float = 0


@dataclass
class WeightConfig:
    fundamental: float = 35
    technical: float = 30
    capital: float = 20
    sentiment: float = 15


@dataclass
class SchedulerConfig:
    enabled: bool = True
    daily_sync_cron: str = "30 18 * * 1-5"


@dataclass
class Settings:
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    market_data: MarketDataConfig = field(default_factory=MarketDataConfig)
    akshare: AkshareConfig = field(default_factory=AkshareConfig)
    tushare: TushareConfig = field(default_factory=TushareConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    weights: WeightConfig = field(default_factory=WeightConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    @property
    def db_path(self) -> Path:
        raw = Path(self.database.path)
        return raw if raw.is_absolute() else PROJECT_ROOT / raw


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> Any:
    for key, value in values.items():
        if hasattr(instance, key):
            setattr(instance, key, value)
    return instance


def get_config_path() -> Path:
    return Path(os.getenv("A_STOCK_CONFIG", str(DEFAULT_CONFIG_PATH))).expanduser().resolve()


def load_settings() -> Settings:
    path = get_config_path()
    settings = Settings()
    if not path.exists():
        return settings

    with path.open("rb") as file:
        raw = tomllib.load(file)

    _merge_dataclass(settings.server, raw.get("server", {}))
    _merge_dataclass(settings.database, raw.get("database", {}))
    _merge_dataclass(settings.market_data, raw.get("market_data", {}))
    _merge_dataclass(settings.akshare, raw.get("akshare", {}))
    _merge_dataclass(settings.tushare, raw.get("tushare", {}))
    _merge_dataclass(settings.llm, raw.get("llm", {}))
    _merge_dataclass(settings.search, raw.get("search", {}))
    _merge_dataclass(settings.workflow, raw.get("workflow", {}))
    _merge_dataclass(settings.filters, raw.get("filters", {}))
    _merge_dataclass(settings.weights, raw.get("weights", {}))
    _merge_dataclass(settings.scheduler, raw.get("scheduler", {}))
    return settings


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_settings(settings: Settings) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sections = asdict(settings)
    lines: list[str] = []
    for section, values in sections.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def update_settings(patch: dict[str, Any]) -> Settings:
    settings = load_settings()
    for section, values in patch.items():
        current = getattr(settings, section, None)
        if current is not None and isinstance(values, dict):
            _merge_dataclass(current, values)
    save_settings(settings)
    return settings

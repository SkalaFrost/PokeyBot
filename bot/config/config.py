from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int = 213
    API_HASH: str = ''

    TAP_COUNT: list = [20,70]

    SLEEP: list = [5,10]
    AUTO_TASK: bool = True 
    AUTO_UPGRAGE: bool = True
    UPGRADE_LEVEL: int = 10
    REF_ID: str = ''
    USE_PROXY_FROM_FILE: bool = False

settings = Settings()



import os
import re
from functools import lru_cache
from pathlib import Path
from threading import RLock

from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
_ENGINE_LOCK = RLock()


def is_local_config(config: dict | URL | None = None) -> bool:
    if config is None:
        config = get_connection_config()
    host = config.host if isinstance(config, URL) else config.get("host")
    return host in LOCAL_HOSTS


def get_connection_config(*, require_database: bool = False) -> dict:
    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": os.getenv("MYSQL_PORT", "3306"),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "chachacha"),
        "ssl_ca": os.getenv("MYSQL_SSL_CA", ""),
    }
    database_configured = "MYSQL_DATABASE" in os.environ
    ssl_configured = "MYSQL_SSL_CA" in os.environ
    try:
        import streamlit as st
        from streamlit.errors import StreamlitSecretNotFoundError
    except ModuleNotFoundError as exc:
        if exc.name != "streamlit":
            raise RuntimeError("Streamlit 설치를 확인하세요.") from None
    else:
        try:
            secret = st.secrets["mysql"]
        except KeyError:
            secret = {}
        except StreamlitSecretNotFoundError as exc:
            # Streamlit 1.50은 파일 부재와 TOML 오류를 같은 예외로 알려 주므로 구분한다.
            if exc.__cause__ is not None or not str(exc).startswith("No secrets found."):
                raise RuntimeError("MySQL 비밀 설정 파일의 형식을 확인하세요.") from None
            secret = {}
        except Exception:
            raise RuntimeError("MySQL 비밀 설정 파일의 형식을 확인하세요.") from None
        if not hasattr(secret, "items"):
            raise ValueError("mysql 설정은 키와 값으로 구성해야 합니다.")
        database_configured = database_configured or "database" in secret
        ssl_configured = ssl_configured or "ssl_ca" in secret
        config.update({key: value for key, value in secret.items() if key in config})
    port_value = config["port"]
    invalid_config = "MySQL 설정의 자료형과 포트 범위를 확인하세요."
    if (isinstance(port_value, bool) or not isinstance(port_value, (int, str))
            or (isinstance(port_value, str) and not re.fullmatch(r"[0-9]+", port_value))
            or any(not isinstance(config[key], str) for key in config if key != "port")
            or any(not str(config[key]).strip() for key in ("host", "user", "database"))):
        raise ValueError(invalid_config)
    try:
        port = int(port_value)
    except ValueError:
        raise ValueError(invalid_config) from None
    if not 1 <= port <= 65535:
        raise ValueError(invalid_config)
    if require_database and not database_configured:
        raise ValueError("원격 스키마 적용에는 secrets 또는 MYSQL_DATABASE의 명시적인 DB 이름이 필요합니다.")
    config["port"] = port
    config["ssl_enabled"] = not is_local_config(config) or ssl_configured
    return config


def _require_tls(dbapi_connection, connection_record) -> None:
    # 드라이버의 평문 연결 폴백을 막기 위해 협상된 TLS 암호군을 확인한다.
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
        row = cursor.fetchone()
    if not row or not row[1]:
        dbapi_connection.close()
        raise RuntimeError("MySQL TLS 연결이 성립하지 않았습니다.")


def get_engine() -> Engine:
    # lru_cache만 쓰면 최초 호출이 겹칠 때 생성 함수가 여러 번 실행될 수 있다.
    with _ENGINE_LOCK:
        return _cached_engine()


def _clear_engine_cache() -> None:
    with _ENGINE_LOCK:
        _cached_engine.cache_clear()


@lru_cache(maxsize=1)
def _cached_engine() -> Engine:
    config = get_connection_config()
    url = URL.create(
        "mysql+pymysql",
        username=config["user"],
        password=config["password"],
        host=config["host"],
        port=config["port"],
        database=config["database"],
        query={"charset": "utf8mb4"},
    )
    connect_args = {"connect_timeout": 5, "read_timeout": 15, "write_timeout": 15}
    if config["ssl_enabled"]:
        # 빈 dict는 PyMySQL에서 TLS를 끄므로 비어 있지 않은 옵션을 전달한다.
        ssl_options = {"check_hostname": False}
        ca_path = Path(config["ssl_ca"]).expanduser() if config["ssl_ca"] else None
        if ca_path is not None and ca_path.is_file():
            ssl_options = {"ca": str(ca_path), "check_hostname": True}
        connect_args["ssl"] = ssl_options
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
        hide_parameters=True,
        connect_args=connect_args,
    )
    if config["ssl_enabled"]:
        event.listen(engine, "connect", _require_tls)
    return engine

"""Passwordless ODBC connections for Azure SQL / Synapse.

The Entra handshake lives here once so the provider and the emulator migration
runner cannot drift apart.
"""

from __future__ import annotations

import re
import struct
from typing import Any, Callable

import pyodbc
from azure.identity import DefaultAzureCredential

SQL_COPT_SS_ACCESS_TOKEN = 1256
AZURE_GOVERNMENT_SQL_SCOPE = "https://database.usgovcloudapi.net/.default"

_AUTHENTICATION_ATTRIBUTE = re.compile(r";?\s*Authentication=[^;]+", flags=re.IGNORECASE)
_USER_ATTRIBUTE = re.compile(r";?\s*(?:Uid|User ID)=[^;]+", flags=re.IGNORECASE)


def token_struct(token: str) -> bytes:
    """Convert an access token to the layout pyodbc expects for SQL Server."""
    token_bytes = token.encode("utf-16-le")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


class OdbcConnector:
    """Opens ODBC connections, injecting an Entra token when the DSN asks for one."""

    def __init__(
        self,
        connection_string: str,
        *,
        credential: Any | None = None,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        self._connect = connect or pyodbc.connect
        if "authentication=activedirectory" in connection_string.lower():
            self.credential = credential or DefaultAzureCredential()
            connection_string = _USER_ATTRIBUTE.sub(
                "", _AUTHENTICATION_ATTRIBUTE.sub("", connection_string)
            )
        else:
            self.credential = credential
        self.connection_string = connection_string.strip("; ")

    def open(self, **kwargs: Any) -> Any:
        if self.credential is not None:
            token = self.credential.get_token(AZURE_GOVERNMENT_SQL_SCOPE)
            kwargs["attrs_before"] = {SQL_COPT_SS_ACCESS_TOKEN: token_struct(token.token)}
        return self._connect(self.connection_string, **kwargs)

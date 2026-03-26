import json
import os

from datetime import datetime
from typing import Any


class PersistentHashTable:
    """
    Hashtable com persistência em disco usando append-only log (JSONL).

    Cada operação de escrita adiciona uma linha ao arquivo em vez de
    reescrever tudo — custo O(1) por operação.

    Na inicialização, o estado é reconstruído lendo os eventos em ordem.
    O cleanup compacta o arquivo removendo entradas expiradas.

    Formato do arquivo (.jsonl):
        {"key": "<hash>", "value": "<iso_datetime>", "op": "add"}
        {"key": "<hash>", "value": "<iso_datetime>", "op": "remove"}
    """

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._table: dict[str, Any] = {}

        self._ensureFile()
        self._load()


    # ── Interface pública ──────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Adiciona ou atualiza uma entrada e persiste o evento."""
        self._table[key] = value
        self._appendEvent(key, value, "add")


    def get(self, key: str) -> Any | None:
        """Retorna o valor associado à chave ou None se não existir."""
        return self._table.get(key)


    def exists(self, key: str) -> bool:
        """Verifica se a chave existe na tabela."""
        return key in self._table


    def delete(self, key: str) -> None:
        """Remove uma entrada e persiste o evento de remoção."""
        if key in self._table:
            del self._table[key]
            self._appendEvent(key, None, "remove")


    def cleanup(self, isExpired: callable) -> None:
        """
        Remove entradas expiradas da memória e compacta o arquivo.

        Args:
            isExpired: função que recebe o valor e retorna True se expirado.
                       Ex: lambda exp: datetime.fromisoformat(exp) < datetime.utcnow()
        """
        self._table = {
            key: value
            for key, value in self._table.items()
            if not isExpired(value)
        }

        self._rewrite()


    # ── Persistência ──────────────────────────────────────────────────────────

    def _ensureFile(self) -> None:
        """Cria o arquivo e diretórios necessários se não existirem."""
        dirPath = os.path.dirname(self._filepath)

        if dirPath:
            os.makedirs(dirPath, exist_ok=True)

        if not os.path.exists(self._filepath):
            open(self._filepath, 'w').close()


    def _load(self) -> None:
        """
        Reconstrói o estado atual lendo todos os eventos do arquivo em ordem.
        Eventos 'add' inserem, eventos 'remove' deletam.
        Linhas corrompidas são ignoradas silenciosamente.
        """
        with open(self._filepath, 'r') as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    event = json.loads(line)
                    op    = event.get("op")
                    key   = event.get("key")
                    value = event.get("value")

                    if op == "add" and key:
                        self._table[key] = value

                    elif op == "remove" and key:
                        self._table.pop(key, None)

                except (json.JSONDecodeError, KeyError):
                    continue


    def _appendEvent(self, key: str, value: Any, op: str) -> None:
        """
        Acrescenta um evento ao final do arquivo — O(1).
        Nunca reescreve o arquivo inteiro.
        """
        event = json.dumps({
            "key":   key,
            "value": value,
            "op":    op
        })

        with open(self._filepath, 'a') as file:
            file.write(event + '\n')


    def _rewrite(self) -> None:
        """
        Reescreve o arquivo com apenas o estado atual limpo.
        Chamado somente pelo cleanup — O(n), mas raro.
        """
        with open(self._filepath, 'w') as file:
            for key, value in self._table.items():
                event = json.dumps({
                    "key":   key,
                    "value": value,
                    "op":    "add"
                })
                file.write(event + '\n')
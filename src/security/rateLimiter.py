from datetime import datetime, timedelta
from typing import Optional


class IpRateLimiter:
    """
    Rate limiter por IP usando sliding window.

    Limita o número de requisições por IP em uma janela de tempo
    e bloqueia temporariamente IPs que excedem o limite.

    Uso:
        limiter = IpRateLimiter()

        allowed, reason = limiter.check("192.168.1.1")
        if not allowed:
            raise HTTPException(429, reason)
    """

    _WINDOW_SECONDS  = 60
    _MAX_REQUESTS    = 60
    _BLOCK_MINUTES   = 60


    def __init__(self):
        self._windows: dict[str, list[datetime]] = {}
        self._blocked: dict[str, datetime]       = {}


    # ── Interface pública ──────────────────────────────────────────────────────

    def check(self, ip: str) -> tuple[bool, Optional[str]]:
        """
        Verifica se o IP pode fazer uma requisição.
        Registra a tentativa internamente.

        Args:
            ip: endereço IP do cliente

        Returns:
            (True, None)           se permitido
            (False, mensagem)      se bloqueado ou limite excedido
        """
        if self._isBlocked(ip):
            remaining = self._blockedSecondsRemaining(ip)
            return False, f"IP bloqueado. Tente novamente em {remaining}s"

        self._cleanWindow(ip)
        self._windows.setdefault(ip, []).append(datetime.utcnow())

        if len(self._windows[ip]) > self._MAX_REQUESTS:
            self._block(ip)
            return False, f"Muitas requisições. IP bloqueado por {self._BLOCK_MINUTES} minutos"

        return True, None


    # ── Interno ───────────────────────────────────────────────────────────────

    def _isBlocked(self, ip: str) -> bool:
        if ip not in self._blocked:
            return False

        if datetime.utcnow() >= self._blocked[ip]:
            del self._blocked[ip]
            return False

        return True


    def _blockedSecondsRemaining(self, ip: str) -> int:
        return int((self._blocked[ip] - datetime.utcnow()).total_seconds())


    def _block(self, ip: str) -> None:
        self._blocked[ip] = datetime.utcnow() + timedelta(minutes=self._BLOCK_MINUTES)
        self._windows.pop(ip, None)


    def _cleanWindow(self, ip: str) -> None:
        """Remove timestamps fora da janela de tempo atual."""
        if ip not in self._windows:
            return

        cutoff = datetime.utcnow() - timedelta(seconds=self._WINDOW_SECONDS)
        self._windows[ip] = [ts for ts in self._windows[ip] if ts > cutoff]


class LoginRateLimiter:
    """
    Rate limiter por username para proteção contra brute force.

    Após 5 tentativas falhas em 15 minutos, bloqueia a conta
    por 30 minutos. Tentativas bem-sucedidas limpam o histórico.

    Uso:
        limiter = LoginRateLimiter()

        allowed, reason = limiter.check(username)
        if not allowed:
            raise HTTPException(429, reason)

        # após autenticar:
        limiter.onSuccess(username)
    """

    _WINDOW_MINUTES  = 15
    _MAX_ATTEMPTS    = 5
    _LOCKOUT_MINUTES = 30


    def __init__(self):
        self._attempts: dict[str, list[datetime]] = {}
        self._locked:   dict[str, datetime]       = {}


    # ── Interface pública ──────────────────────────────────────────────────────

    def check(self, username: str) -> tuple[bool, Optional[str]]:
        """
        Verifica se o username pode tentar login.
        Registra a tentativa internamente.

        Args:
            username: identificador da conta (email ou username)

        Returns:
            (True, None)           se permitido
            (False, mensagem)      se conta bloqueada ou limite excedido
        """
        if self._isLocked(username):
            remaining = self._lockedSecondsRemaining(username)
            return False, f"Conta bloqueada. Tente novamente em {remaining}s"

        self._cleanWindow(username)
        self._attempts.setdefault(username, []).append(datetime.utcnow())

        attempts = len(self._attempts[username])

        if attempts >= self._MAX_ATTEMPTS:
            self._lock(username)
            return False, f"Conta bloqueada após {self._MAX_ATTEMPTS} tentativas. Tente em {self._LOCKOUT_MINUTES} minutos"

        remaining = self._MAX_ATTEMPTS - attempts
        return True, None


    def onSuccess(self, username: str) -> None:
        """
        Limpa o histórico de tentativas após login bem-sucedido.
        Deve ser chamado pelo authService após autenticar o usuário.

        Args:
            username: identificador da conta
        """
        self._attempts.pop(username, None)


    def attemptsRemaining(self, username: str) -> int:
        """
        Retorna quantas tentativas restam antes do bloqueio.
        Útil para o authService incluir na resposta de erro.

        Args:
            username: identificador da conta
        """
        self._cleanWindow(username)
        attempts = len(self._attempts.get(username, []))
        return max(0, self._MAX_ATTEMPTS - attempts)


    # ── Interno ───────────────────────────────────────────────────────────────

    def _isLocked(self, username: str) -> bool:
        if username not in self._locked:
            return False

        if datetime.utcnow() >= self._locked[username]:
            del self._locked[username]
            self._attempts.pop(username, None)
            return False

        return True


    def _lockedSecondsRemaining(self, username: str) -> int:
        return int((self._locked[username] - datetime.utcnow()).total_seconds())


    def _lock(self, username: str) -> None:
        self._locked[username] = datetime.utcnow() + timedelta(minutes=self._LOCKOUT_MINUTES)
        self._attempts.pop(username, None)


    def _cleanWindow(self, username: str) -> None:
        """Remove tentativas fora da janela de tempo atual."""
        if username not in self._attempts:
            return

        cutoff = datetime.utcnow() - timedelta(minutes=self._WINDOW_MINUTES)
        self._attempts[username] = [ts for ts in self._attempts[username] if ts > cutoff]
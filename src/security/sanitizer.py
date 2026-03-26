import bleach
import re


class Sanitizer:
    """
    Módulo de sanitização para prevenção de XSS e Injeções (SQL/NoSQL).
    Seguindo as diretrizes do docs/security.md do projeto NoHarm.
    """
    
    # Lista de tags permitidas (se houver necessidade de algum HTML básico)
    
    ALLOWED_TAGS = {}

    @staticmethod
    def cleanHtml(text: str) -> str:
        """
        Remove tags HTML perigosas (Prevenção de XSS).
        """
        if not isinstance(text, str):
            return text
        
        # Bleach remove scripts, onmouseover, onerror, etc.
        return bleach.clean(
            text, 
            strip=True,
            tags=Sanitizer.ALLOWED_TAGS
        )

    @staticmethod
    def isValidUsername(username: str) -> bool:
        """
        Validação por Whitelist (Apenas alfanuméricos e underscore).
        Mencionado em docs/security.md como medida preventiva.
        """
        pattern = r'^[a-zA-Z0-9_-]{3,30}$'
        return bool(re.match(pattern, username))
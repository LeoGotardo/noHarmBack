import bleach
import re


class Sanitizer:
    """
    Sanitization module for XSS and Injection (SQL/NoSQL) prevention.
    Following the guidelines from docs/security.md of the NoHarm project.
    """

    # Allowed HTML tags (empty — NoHarm does not allow any HTML in user input)
    ALLOWED_TAGS: set = set()

    @staticmethod
    def cleanHtml(text: str) -> str:
        """
        Removes dangerous HTML tags to prevent XSS attacks.

        Args:
            text (str): Raw input string from the user.

        Returns:
            str: Sanitized string with all HTML tags stripped.
        """
        if not isinstance(text, str):
            return text

        # Bleach strips scripts, event handlers (onerror, onmouseover, etc.) and other dangerous markup
        return bleach.clean(
            text,
            strip=True,
            tags=Sanitizer.ALLOWED_TAGS
        )

    @staticmethod
    def isValidUsername(username: str) -> bool:
        """
        Validates a username against a strict whitelist pattern.

        Only alphanumeric characters, underscores, and hyphens are allowed.
        Referenced in docs/security.md as a preventive input-validation measure.

        Args:
            username (str): Username string to validate.

        Returns:
            bool: True if the username matches the allowed pattern, False otherwise.
        """
        pattern = r'^[a-zA-Z0-9_-]{3,30}$'
        return bool(re.match(pattern, username))
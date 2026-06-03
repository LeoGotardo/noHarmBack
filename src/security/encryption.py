import base64, argon2, sys

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from hashlib import sha256
from Crypto.Cipher import AES


def _exc_location() -> str:
    tb = sys.exc_info()[2]
    if tb is None:
        return "unknown location"
    return f"line {tb.tb_lineno} in file {tb.tb_frame.f_code.co_filename}"


class Encryption:
    """Class used to encrypt or decrypt data with both OneWay encryption and BothWays encryption
    """

    def __init__(self) -> None:
        load_dotenv()
        self.ph = argon2.PasswordHasher()


    @staticmethod
    def keyGenerator(key: str) -> tuple[bool, bytes] | tuple[bool, str]:
        """Generates a key based on some string

        Args:
            key (str): Base string for key generation

        Returns:
            tuple[bool, bytes] | tuple[bool, str]: [bool = success or error, str = success message or error message]
        """
        try:
            hash_bytes = sha256(key.encode('utf-8')).digest()
            base64_key = base64.urlsafe_b64encode(hash_bytes)
            return True, base64_key
        except Exception as e:
            return False, f'{type(e).__name__}: {e} in {_exc_location()}'


    def isValidPass(self, hash: str, password: str) -> tuple[bool, str]:
        """Compares a string with a given hash generated with the encryptPass method

        Args:
            hash (str): hash string
            password (str): string in plain text

        Returns:
            tuple[bool, str]: [bool = success or error, str = success message or error message]
        """
        try:
            return self.ph.verify(hash, password), "Valid user."
        except Exception as e:
            return False, f'{type(e).__name__}: {e} in {_exc_location()}'


    @staticmethod
    def encryptSentence(message: str, key: bytes | str) -> tuple[bool, bytes] | tuple[bool, str]:
        """Encrypt a string in a BothWays encryption, with means that you can decrypt it

        Args:
            message (str): message to decrypt
            key (bytes | str): key generated with keyGenerator method

        Returns:
            tuple[bool, bytes] | tuple[bool, str]: [bool = True, bytes = encrypted text] or [bool = False, str = error message]
        """
        try:
            key_bytes = key if isinstance(key, bytes) else key.encode('utf-8')
            cipher = Fernet(key_bytes)
            encrypted_message = cipher.encrypt(message.encode('utf-8'))
            return True, encrypted_message
        except Exception as e:
            return False, f'{type(e).__name__}: {e} in {_exc_location()}'


    @staticmethod
    def decryptSentence(encrypted_string: bytes | str, key: bytes | str) -> tuple[bool, str]:
        """Decrypt an given hash generated with the encryptSentence method

        Args:
            encrypted_string (bytes | str): encrypted sentence
            key (bytes | str): key used to encrypt the sentence, genereted with the keyGenerator method

        Returns:
            tuple[bool, str]: [bool = True, bytes = decrypted text] or [bool = False, str = error message]
        """
        try:
            key_bytes = key if isinstance(key, bytes) else key.encode('utf-8')
            enc_bytes = encrypted_string if isinstance(encrypted_string, bytes) else encrypted_string.encode('utf-8')
            cipher = Fernet(key_bytes)
            decrypted_message = cipher.decrypt(enc_bytes)
            decrypted_message = decrypted_message.decode('utf-8')
            return True, decrypted_message
        except Exception as e:
            return False, f'{type(e).__name__}: {e} in {_exc_location()}'


    def encryptPass(self, password: str) -> tuple[bool, str]:
        """Generates a hash of a given string with a OneWay encryption, with means that you can't decrypt it just compare it with a string

        Args:
            password (str): the string to encrypt

        Returns:
            tuple[bool, str]: [bool = True, str = hashed password] or [bool = False, str = error message]
        """
        try:
            hash = self.ph.hash(password)
            return True, hash
        except Exception as e:
            return False, f'{type(e).__name__}: {e} in {_exc_location()}'


    @staticmethod
    def encrypt(message: str, key: bytes | str) -> tuple[bool, bytes] | tuple[bool, str]:
        return Encryption.encryptSentence(message, key)


    @staticmethod
    def decrypt(encrypted_string: bytes | str, key: bytes | str) -> tuple[bool, str]:
        return Encryption.decryptSentence(encrypted_string, key)


    @staticmethod
    def hash(value: str) -> str:
        return sha256(value.encode('utf-8')).hexdigest()
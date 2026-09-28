"""Fernet-based encryption for securing Plaid access tokens at rest."""

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    """Raised when decryption fails due to invalid key or corrupted data."""

    pass


class TokenEncryption:
    """Handles encryption and decryption of access tokens using Fernet.

    Fernet guarantees that a message encrypted using it cannot be manipulated
    or read without the key. It uses AES-128-CBC with PKCS7 padding and HMAC
    using SHA256 for authentication.
    """

    def __init__(self, key: str | bytes) -> None:
        """Initialize the encryption handler with a Fernet key.

        Args:
            key: A URL-safe base64-encoded 32-byte key. Can be generated using
                 Fernet.generate_key() or cryptography's Fernet key generation.

        Raises:
            ValueError: If the key is invalid or improperly formatted.
        """
        if isinstance(key, str):
            key = key.encode("utf-8")

        try:
            self._fernet = Fernet(key)
        except Exception as e:
            raise ValueError(f"Invalid Fernet key: {e}") from e

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext token.

        Args:
            plaintext: The token to encrypt (e.g., Plaid access token).

        Returns:
            URL-safe base64-encoded encrypted string.
        """
        plaintext_bytes = plaintext.encode("utf-8")
        encrypted_bytes = self._fernet.encrypt(plaintext_bytes)
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted token.

        Args:
            ciphertext: The URL-safe base64-encoded encrypted string.

        Returns:
            The original plaintext token.

        Raises:
            DecryptionError: If decryption fails (wrong key or corrupted data).
        """
        try:
            ciphertext_bytes = ciphertext.encode("utf-8")
            decrypted_bytes = self._fernet.decrypt(ciphertext_bytes)
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as e:
            raise DecryptionError(
                "Failed to decrypt: invalid key or corrupted ciphertext"
            ) from e
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}") from e

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key.

        Returns:
            A URL-safe base64-encoded 32-byte key suitable for use with this class.
        """
        return Fernet.generate_key().decode("utf-8")

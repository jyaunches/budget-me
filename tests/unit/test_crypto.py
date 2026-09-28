"""Tests for token encryption module."""

import pytest
from cryptography.fernet import Fernet

from budget_me.crypto import DecryptionError, TokenEncryption


class TestTokenEncryption:
    """Tests for TokenEncryption class."""

    @pytest.fixture
    def valid_key(self) -> str:
        """Generate a valid Fernet key for testing."""
        return Fernet.generate_key().decode("utf-8")

    @pytest.fixture
    def encryption(self, valid_key: str) -> TokenEncryption:
        """Create a TokenEncryption instance with a valid key."""
        return TokenEncryption(valid_key)

    def test_encrypt_then_decrypt_returns_original(self, encryption: TokenEncryption):
        """Encrypt then decrypt returns the original plaintext."""
        plaintext = "access-sandbox-abc123"

        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypted_output_is_different_from_input(
        self, encryption: TokenEncryption
    ):
        """Encrypted output is different from the input."""
        plaintext = "access-sandbox-abc123"

        encrypted = encryption.encrypt(plaintext)

        assert encrypted != plaintext

    def test_decrypt_with_wrong_key_raises_error(self, valid_key: str):
        """Decrypting with a different key raises DecryptionError."""
        encryption_a = TokenEncryption(valid_key)
        key_b = Fernet.generate_key().decode("utf-8")
        encryption_b = TokenEncryption(key_b)

        plaintext = "access-sandbox-abc123"
        encrypted_with_a = encryption_a.encrypt(plaintext)

        with pytest.raises(DecryptionError) as exc_info:
            encryption_b.decrypt(encrypted_with_a)

        assert "invalid key or corrupted" in str(exc_info.value).lower()

    def test_decrypt_invalid_ciphertext_raises_error(self, encryption: TokenEncryption):
        """Decrypting random invalid base64 raises DecryptionError."""
        invalid_ciphertext = "not-a-valid-encrypted-string"

        with pytest.raises(DecryptionError) as exc_info:
            encryption.decrypt(invalid_ciphertext)

        assert "decrypt" in str(exc_info.value).lower()

    def test_encrypt_empty_string(self, encryption: TokenEncryption):
        """Empty string can be encrypted and decrypted."""
        plaintext = ""

        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypted_output_is_url_safe_base64(self, encryption: TokenEncryption):
        """Encrypted output is URL-safe base64."""
        plaintext = "access-sandbox-abc123"

        encrypted = encryption.encrypt(plaintext)

        # URL-safe base64 only contains these characters
        url_safe_chars = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="
        )
        assert all(c in url_safe_chars for c in encrypted)

    def test_generate_key_returns_valid_key(self):
        """generate_key returns a key that works for encryption."""
        key = TokenEncryption.generate_key()

        # Should be able to create an instance with the generated key
        encryption = TokenEncryption(key)
        plaintext = "test-token"

        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_invalid_key_raises_value_error(self):
        """Creating TokenEncryption with invalid key raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            TokenEncryption("not-a-valid-fernet-key")

        assert "invalid" in str(exc_info.value).lower()

    def test_accepts_bytes_key(self):
        """TokenEncryption accepts key as bytes."""
        key_bytes = Fernet.generate_key()
        encryption = TokenEncryption(key_bytes)

        plaintext = "test-token"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_different_encryptions_produce_different_ciphertext(
        self, encryption: TokenEncryption
    ):
        """Same plaintext encrypted twice produces different ciphertext.

        This is expected behavior because Fernet includes a timestamp
        and uses a random IV.
        """
        plaintext = "access-sandbox-abc123"

        encrypted_1 = encryption.encrypt(plaintext)
        encrypted_2 = encryption.encrypt(plaintext)

        # Due to timestamp/IV, encryptions should differ
        assert encrypted_1 != encrypted_2

        # But both should decrypt to the same value
        assert encryption.decrypt(encrypted_1) == plaintext
        assert encryption.decrypt(encrypted_2) == plaintext


import base64
import os


def generate_encryption_key() -> bytes:
    """Generate a random encryption key using only standard libraries"""
    return os.urandom(32)  # 256-bit key


def simple_encrypt(data: str, key: bytes) -> str:
    """Simple XOR-based encryption for basic obfuscation"""
    data_bytes = data.encode('utf-8')
    encrypted = bytearray()
    key_len = len(key)
    for i in range(len(data_bytes)):
        encrypted.append(data_bytes[i] ^ key[i % key_len])
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')


def simple_decrypt(encrypted: str, key: bytes) -> str:
    """Decrypt data encrypted with simple_encrypt"""
    encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode('utf-8'))
    decrypted = bytearray()
    key_len = len(key)
    for i in range(len(encrypted_bytes)):
        decrypted.append(encrypted_bytes[i] ^ key[i % key_len])
    return decrypted.decode('utf-8')

# In your config setup:


def setup_encryption(config):
    """Ensure encryption key exists for sensitive data"""
    if "encryption_key" not in config.get("meta", {}):
        key = generate_encryption_key()
        config.setdefault("meta", {})["encryption_key"] = base64.b64encode(
            key).decode('utf-8')


def encrypt_data(config, data: str) -> str:
    """Encrypt sensitive data"""
    key = base64.b64decode(config["meta"]["encryption_key"])
    return simple_encrypt(data, key)


def decrypt_data(config, encrypted: str) -> str:
    """Decrypt sensitive data"""
    key = base64.b64decode(config["meta"]["encryption_key"])
    return simple_decrypt(encrypted, key)

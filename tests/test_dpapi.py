# tests/test_dpapi.py
# Tests the DPAPI helper functions and secure atomic file storage.

import os
import tempfile
import pytest

from dpapi_storage import (
    protect_data, unprotect_data,
    save_secure_file, load_secure_file,
    save_secure_json, load_secure_json
)

def test_dpapi_encrypt_decrypt():
    # Test encryption and decryption with raw bytes
    raw_data = b"Hello DPAPI Windows Protection Layer"
    encrypted = protect_data(raw_data)
    assert encrypted != raw_data
    
    decrypted = unprotect_data(encrypted)
    assert decrypted == raw_data

def test_dpapi_with_entropy():
    # Test encryption and decryption with optional entropy
    raw_data = b"Sensitive Data Value"
    entropy = b"CustomEntropyKey"
    
    encrypted = protect_data(raw_data, entropy)
    decrypted = unprotect_data(encrypted, entropy)
    assert decrypted == raw_data
    
    # Decryption should fail or raise when wrong entropy is used
    with pytest.raises(OSError):
        unprotect_data(encrypted, b"WrongEntropyKey")

def test_secure_file_saving():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_file.dat")
        data = b"Secure Encrypted Content Bytes"
        
        save_secure_file(path, data)
        assert os.path.exists(path)
        
        loaded = load_secure_file(path)
        assert loaded == data

def test_secure_json_saving():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_json.dat")
        data = {
            "key1": "value1",
            "number": 42,
            "unicode": "Tiếng Việt có dấu"
        }
        entropy = "TestEntropyJSON"
        
        save_secure_json(path, data, entropy)
        assert os.path.exists(path)
        
        loaded = load_secure_json(path, entropy)
        assert loaded == data
        
        # Load with wrong entropy should return None instead of crashing
        loaded_wrong = load_secure_json(path, "WrongEntropy")
        assert loaded_wrong is None

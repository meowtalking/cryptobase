#!/usr/bin/env python3
"""
Simple manual test for backup restoration
"""

import os
import tempfile
from pathlib import Path

def create_test_file():
    """Create a simple test file"""
    test_content = "This is a test file for restoration.\nLine 2\nLine 3"
    test_file = Path(tempfile.mktemp(suffix=".txt"))
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_content)
    return test_file, test_content

def test_hex_encoding():
    """Test hex encoding/decoding works correctly"""
    print("=== Testing Hex Encoding ===")
    
    test_file, original_content = create_test_file()
    
    # Read file as bytes
    with open(test_file, "rb") as f:
        file_bytes = f.read()
    
    print(f"Original content: {repr(original_content)}")
    print(f"File bytes: {file_bytes}")
    print(f"File bytes length: {len(file_bytes)}")
    
    # Convert to hex and back
    hex_content = file_bytes.hex()
    decoded_bytes = bytes.fromhex(hex_content)
    
    print(f"Hex content: {hex_content[:50]}...")
    print(f"Decoded bytes match original: {file_bytes == decoded_bytes}")
    
    # Convert back to string
    decoded_content = decoded_bytes.decode('utf-8')
    print(f"Decoded content: {repr(decoded_content)}")
    print(f"Content match: {original_content == decoded_content}")
    
    # Cleanup
    test_file.unlink()
    
    return file_bytes == decoded_bytes and original_content == decoded_content

def test_encryption_decryption():
    """Test encryption/decryption logic"""
    print("\n=== Testing Encryption/Decryption ===")
    
    try:
        from app.services.security import encrypt_file, decrypt_file, decrypt_file_from_bytes
        import tempfile
        
        # Create test file
        test_file, original_content = create_test_file()
        password = "TestPassword123!"
        
        print(f"Test file: {test_file}")
        print(f"Original content: {repr(original_content)}")
        
        # Read original
        with open(test_file, "rb") as f:
            original_bytes = f.read()
        
        # Encrypt file
        encrypt_file(str(test_file), password)
        print("File encrypted")
        
        # Read encrypted
        with open(test_file, "rb") as f:
            encrypted_bytes = f.read()
        
        print(f"Encrypted bytes length: {len(encrypted_bytes)}")
        print(f"Encrypted bytes preview: {encrypted_bytes[:50]}")
        
        # Decrypt file
        decrypted_bytes = decrypt_file(str(test_file), password)
        print("File decrypted")
        
        print(f"Decrypted bytes match original: {decrypted_bytes == original_bytes}")
        
        # Test decrypt_from_bytes (simulating container restoration)
        try:
            decrypted_from_bytes = decrypt_file_from_bytes(encrypted_bytes, password)
            print(f"Decrypted from bytes match original: {decrypted_from_bytes == original_bytes}")
        except Exception as e:
            print(f"Decrypt from bytes failed: {e}")
            return False
        
        # Cleanup
        test_file.unlink()
        
        return decrypted_bytes == original_bytes and decrypted_from_bytes == original_bytes
        
    except Exception as e:
        print(f"Encryption test failed: {e}")
        return False

def test_container_storage():
    """Test container storage format"""
    print("\n=== Testing Container Storage ===")
    
    try:
        from app.services.backup_container import BackupContainer
        
        # Create test master key (normally derived from password)
        master_key = b"0123456789abcdef0123456789abcdef"  # 32 bytes
        
        # Create container
        container = BackupContainer(master_key)
        
        # Test data
        test_content = b"This is test content for container storage."
        file_id = "test_file_1"
        
        version_data = {
            "version_id": 1,
            "created_at": "2026-03-12T21:30:00",
            "hash": "abc123",
            "comment": "Test version",
            "content": test_content.hex()  # Store as hex (plaintext)
        }
        
        # Add version
        container.add_version(file_id, version_data)
        print("Version added to container")
        
        # Retrieve version
        versions = container.get_all_versions(file_id)
        print(f"Retrieved {len(versions)} versions")
        
        if versions:
            retrieved_content = bytes.fromhex(versions[0]["content"])
            print(f"Retrieved content matches original: {retrieved_content == test_content}")
            print(f"Retrieved content: {retrieved_content.decode('utf-8')}")
            return retrieved_content == test_content
        else:
            print("No versions retrieved")
            return False
            
    except Exception as e:
        print(f"Container test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Manual Backup Restoration Tests ===")
    
    tests = [
        ("Hex Encoding", test_hex_encoding),
        ("Encryption/Decryption", test_encryption_decryption),
        ("Container Storage", test_container_storage),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"{test_name}: {status}\n")
        except Exception as e:
            print(f"{test_name}: ✗ ERROR - {e}\n")
            results.append((test_name, False))
    
    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print("=== Summary ===")
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

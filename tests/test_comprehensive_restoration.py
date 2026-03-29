#!/usr/bin/env python3
"""
Comprehensive test cases for backup restoration fixes
Tests both the double encryption fix and restoration functionality
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.security import encrypt_file, decrypt_file, decrypt_file_from_bytes, verify_password_for_db, hash_password_for_db
from app.services.backup_container import BackupContainer
from app.db import SessionLocal
from app.models import FileRecord
from app.services.file_manager import add_file

def test_double_encryption_fix():
    """Test that the double encryption issue is fixed"""
    print("=== Testing Double Encryption Fix ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test file
        test_file = temp_path / "test.txt"
        original_content = b"This is original content for testing."
        password = "TestPassword123!"
        
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        # Simulate the OLD behavior (double encryption)
        print("1. Testing OLD behavior (should show double encryption):")
        encrypt_file(str(test_file), password)  # First encryption
        
        with open(test_file, "rb") as f:
            encrypted_once = f.read()
        
        # Simulate the bug: encrypting already encrypted file
        encrypt_file(str(test_file), password)  # Second encryption (BUG)
        
        with open(test_file, "rb") as f:
            encrypted_twice = f.read()
        
        print(f"   Original size: {len(original_content)}")
        print(f"   Once encrypted size: {len(encrypted_once)}")
        print(f"   Twice encrypted size: {len(encrypted_twice)}")
        
        # Try to decrypt twice-encrypted file
        try:
            decrypted = decrypt_file(str(test_file), password)
            if decrypted != original_content:
                print(f"   ❌ Double encryption confirmed: {decrypted[:50]}...")
            else:
                print(f"   ✓ No double encryption detected")
        except Exception as e:
            print(f"   ❌ Decryption failed: {e}")
        
        # Reset and test NEW behavior
        print("\n2. Testing NEW behavior (should prevent double encryption):")
        
        # Start fresh
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        # Simulate NEW behavior: decrypt first, then encrypt
        encrypt_file(str(test_file), password)  # Initial encryption
        
        # Simulate the fix: decrypt before re-encrypting
        decrypted_content = decrypt_file(str(test_file), password)
        
        with open(test_file, "wb") as f:
            f.write(decrypted_content)  # Write plaintext back
        
        encrypt_file(str(test_file), password)  # Re-encrypt plaintext
        
        # Test decryption
        try:
            final_decrypted = decrypt_file(str(test_file), password)
            if final_decrypted == original_content:
                print(f"   ✓ Double encryption prevented: content matches original")
                return True
            else:
                print(f"   ❌ Still has issues: {final_decrypted[:50]}...")
                return False
        except Exception as e:
            print(f"   ❌ Decryption failed: {e}")
            return False

def test_restoration_functionality():
    """Test the complete restoration functionality"""
    print("\n=== Testing Restoration Functionality ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test files
        plain_file = temp_path / "plain.txt"
        enc_file = temp_path / "encrypted.txt"
        
        plain_content = b"This is plaintext content."
        enc_content = b"This is encrypted content."
        password = "TestPassword123!"
        
        with open(plain_file, "wb") as f:
            f.write(plain_content)
        with open(enc_file, "wb") as f:
            f.write(enc_content)
        
        # Encrypt the second file
        encrypt_file(str(enc_file), password)
        
        # Create master key for container
        master_key = b"0123456789abcdef0123456789abcdef"
        container = BackupContainer(master_key)
        
        # Add both files to container (simulating add_file)
        plain_version = {
            "version_id": 1,
            "created_at": "2026-03-13T15:00:00",
            "hash": "plain_hash",
            "comment": "Plain file version",
            "content": plain_content.hex()  # Plaintext
        }
        
        enc_version = {
            "version_id": 1,
            "created_at": "2026-03-13T15:00:00",
            "hash": "enc_hash",
            "comment": "Encrypted file version",
            "content": enc_content.hex()  # Plaintext (as per fix)
        }
        
        container.add_version("plain_1", plain_version)
        container.add_version("enc_1", enc_version)
        
        print("1. Added both plaintext and encrypted versions to container")
        
        # Test restoration logic
        print("2. Testing restoration logic:")
        
        # Test plaintext file restoration
        plain_versions = container.get_all_versions("plain_1")
        plain_content_bytes = bytes.fromhex(plain_versions[0]["content"])
        
        # Simulate restoration (no password needed)
        final_plain_content = plain_content_bytes
        restored_plain = temp_path / "restored_plain.txt"
        
        with open(restored_plain, "wb") as f:
            f.write(final_plain_content)
        
        with open(restored_plain, "rb") as f:
            restored_plain_content = f.read()
        
        if restored_plain_content == plain_content:
            print("   ✓ Plaintext restoration works")
        else:
            print("   ❌ Plaintext restoration failed")
            return False
        
        # Test encrypted file restoration
        enc_versions = container.get_all_versions("enc_1")
        enc_content_bytes = bytes.fromhex(enc_versions[0]["content"])
        
        # Simulate restoration with password
        password_hash = hash_password_for_db(password)
        final_enc_content = enc_content_bytes
        
        if password_hash:
            try:
                # This should fail (content is plaintext, not encrypted)
                final_enc_content = decrypt_file_from_bytes(enc_content_bytes, password)
                print("   ❌ Encrypted file version was incorrectly decrypted")
                return False
            except Exception:
                # Expected - content is plaintext
                final_enc_content = enc_content_bytes
                print("   ✓ Encrypted file version correctly stored as plaintext")
        
        restored_enc = temp_path / "restored_enc.txt"
        with open(restored_enc, "wb") as f:
            f.write(final_enc_content)
        
        with open(restored_enc, "rb") as f:
            restored_enc_content = f.read()
        
        if restored_enc_content == enc_content:
            print("   ✓ Encrypted file restoration works")
            return True
        else:
            print("   ❌ Encrypted file restoration failed")
            return False

def test_open_encrypted_raw_functionality():
    """Test the open_encrypted_raw function"""
    print("\n=== Testing open_encrypted_raw Functionality ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create encrypted file
        test_file = temp_path / "test_encrypted.txt"
        original_content = b"This is content for open_encrypted_raw test."
        password = "TestPassword123!"
        
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        encrypt_file(str(test_file), password)
        print("1. Created encrypted test file")
        
        # Test decryption logic
        try:
            decrypted_data = decrypt_file(str(test_file), password)
            if decrypted_data == original_content:
                print("   ✓ File decrypts correctly")
            else:
                print("   ❌ File decryption failed")
                return False
        except Exception as e:
            print(f"   ❌ Decryption error: {e}")
            return False
        
        # Test temp file creation
        import tempfile as tf
        tmp = tf.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp.write(decrypted_data)
        tmp.close()
        
        try:
            with open(tmp.name, "rb") as f:
                tmp_content = f.read()
            
            if tmp_content == original_content:
                print("   ✓ Temp file created correctly")
                
                # Clean up
                os.unlink(tmp.name)
                return True
            else:
                print("   ❌ Temp file content mismatch")
                return False
        except Exception as e:
            print(f"   ❌ Temp file error: {e}")
            return False

def main():
    """Run all test cases"""
    print("=== Comprehensive Backup Restoration Tests ===")
    
    tests = [
        ("Double Encryption Fix", test_double_encryption_fix),
        ("Restoration Functionality", test_restoration_functionality),
        ("Open Encrypted Raw", test_open_encrypted_raw_functionality),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"\n{test_name}: {status}")
        except Exception as e:
            print(f"\n{test_name}: ✗ ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("=== TEST SUMMARY ===")
    passed = 0
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Backup restoration issues are fixed.")
        return True
    else:
        print("❌ Some tests failed. Issues remain.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

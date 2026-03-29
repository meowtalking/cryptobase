#!/usr/bin/env python3
"""
Test to reproduce the open_encrypted_raw issue
"""

import os
import sys
import tempfile
import platform
import subprocess
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.security import encrypt_file, decrypt_file

def test_open_encrypted_raw():
    """Test the open_encrypted_raw functionality"""
    print("=== Testing open_encrypted_raw functionality ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test file
        test_file = temp_path / "test_encrypted.txt"
        original_content = b"This is test content for encrypted file.\nLine 2\nLine 3"
        password = "TestPassword123!"
        
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        print(f"1. Original content: {original_content}")
        print(f"   Original file size: {len(original_content)}")
        
        # Encrypt the file
        encrypt_file(str(test_file), password)
        print("2. File encrypted")
        
        with open(test_file, "rb") as f:
            encrypted_content = f.read()
        print(f"   Encrypted file size: {len(encrypted_content)}")
        
        # Simulate open_encrypted_raw logic
        print("\n3. Simulating open_encrypted_raw:")
        try:
            # Step 1: Decrypt file
            data = decrypt_file(str(test_file), password)
            print(f"   ✓ Decrypted data size: {len(data)}")
            print(f"   ✓ Decrypted data matches original: {data == original_content}")
            
            # Step 2: Create temp file
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmp.write(data)
            tmp.close()
            print(f"   ✓ Temp file created: {tmp.name}")
            
            # Step 3: Check temp file content
            with open(tmp.name, "rb") as f:
                tmp_content = f.read()
            print(f"   ✓ Temp file content matches original: {tmp_content == original_content}")
            
            # Step 4: Simulate opening (but don't actually open to avoid GUI)
            print(f"   ✓ Would open with system: {platform.system()}")
            
            # Step 5: Clean up (this is where the bug might be)
            try:
                os.unlink(tmp.name)
                print(f"   ✓ Temp file cleaned up: {tmp.name}")
            except Exception as cleanup_err:
                print(f"   ❌ Temp file cleanup failed: {cleanup_err}")
                return False
            
            return True
            
        except Exception as e:
            print(f"   ❌ Error in open_encrypted_raw simulation: {e}")
            return False

def test_potential_double_encryption():
    """Test if there's a double encryption issue"""
    print("\n=== Testing Potential Double Encryption ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create and encrypt file
        test_file = temp_path / "test.txt"
        original_content = b"Original content"
        password = "TestPassword123!"
        
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        encrypt_file(str(test_file), password)
        
        # Read encrypted content
        with open(test_file, "rb") as f:
            encrypted_once = f.read()
        
        # Try to encrypt again (simulating double encryption)
        try:
            encrypt_file(str(test_file), password)
            with open(test_file, "rb") as f:
                encrypted_twice = f.read()
            
            print(f"1. Single encryption size: {len(encrypted_once)}")
            print(f"2. Double encryption size: {len(encrypted_twice)}")
            
            # Try to decrypt
            try:
                decrypted_once = decrypt_file(str(test_file), password)
                print(f"3. After double encryption, decrypt_once result: {decrypted_once}")
                
                if decrypted_once != original_content:
                    print("   ❌ Double encryption detected!")
                    return False
                else:
                    print("   ✓ No double encryption issue")
                    return True
                    
            except Exception as decrypt_err:
                print(f"   ❌ Decryption failed after double encryption: {decrypt_err}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error in double encryption test: {e}")
            return False

if __name__ == "__main__":
    test1_result = test_open_encrypted_raw()
    test2_result = test_potential_double_encryption()
    
    if test1_result and test2_result:
        print("\n🎉 All tests passed - no issues found with open_encrypted_raw")
    else:
        print("\n❌ Issues found with open_encrypted_raw functionality")
    
    sys.exit(0 if (test1_result and test2_result) else 1)

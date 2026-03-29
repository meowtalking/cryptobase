#!/usr/bin/env python3
"""
Simple test to demonstrate the restoration issue
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.security import encrypt_file, decrypt_file_from_bytes, verify_password_for_db, hash_password_for_db
from app.services.backup_container import BackupContainer

def test_restoration_logic():
    """Test the restoration logic directly"""
    print("=== Testing Restoration Logic ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test file
        test_file = temp_path / "test.txt"
        original_content = b"This is original content."
        file_password = "TestPassword123!"
        
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        print(f"1. Original content: {original_content}")
        
        # Encrypt the file (simulating what happens when file is added)
        encrypt_file(str(test_file), file_password)
        print("2. File encrypted")
        
        # Read encrypted file
        with open(test_file, "rb") as f:
            encrypted_content = f.read()
        
        print(f"3. Encrypted content length: {len(encrypted_content)}")
        
        # Create master key and container
        master_key = b"0123456789abcdef0123456789abcdef"
        container = BackupContainer(master_key)
        
        # Simulate what happens in add_file - store ORIGINAL content in container
        file_id = "test_file_1"
        version_data = {
            "version_id": 1,
            "created_at": "2026-03-13T15:00:00",
            "hash": "dummy_hash",
            "comment": "Initial version",
            "content": original_content.hex()  # Store ORIGINAL content (plaintext)
        }
        
        container.add_version(file_id, version_data)
        print("4. Version stored in container (plaintext)")
        
        # Test restoration logic (from restore_file_dialog)
        versions = container.get_all_versions(file_id)
        selected_version = versions[0]
        content_bytes = bytes.fromhex(selected_version["content"])
        
        print(f"5. Retrieved content length: {len(content_bytes)}")
        print(f"6. Content matches original: {content_bytes == original_content}")
        
        # Simulate the restoration logic
        password_hash = hash_password_for_db(file_password)  # Simulate DB record
        final_content = content_bytes
        
        if password_hash is not None and password_hash.strip():
            print("7. File is encrypted in DB - trying to decrypt version...")
            try:
                if verify_password_for_db(file_password, password_hash):
                    final_content = decrypt_file_from_bytes(content_bytes, file_password)
                    print("   ❌ Version was decrypted (DOUBLE ENCRYPTION!)")
                    print(f"   Final content length: {len(final_content)}")
                    return False
                else:
                    print("   Password verification failed")
                    return False
            except Exception as decrypt_err:
                print(f"   ✓ Decryption failed (expected for plaintext): {str(decrypt_err)[:50]}...")
                final_content = content_bytes  # Keep plaintext
        
        # Write restored file
        restored_file = temp_path / "restored.txt"
        with open(restored_file, "wb") as f:
            f.write(final_content)
        
        # Verify restored content
        with open(restored_file, "rb") as f:
            restored_content = f.read()
        
        print(f"8. Restored content: {restored_content}")
        
        if restored_content == original_content:
            print("   ✓ Restored content matches original")
            return True
        else:
            print("   ❌ Restored content doesn't match original")
            return False

if __name__ == "__main__":
    success = test_restoration_logic()
    if success:
        print("\n🎉 Test passed - restoration logic works correctly")
    else:
        print("\n❌ Test failed - restoration issue confirmed")
    sys.exit(0 if success else 1)

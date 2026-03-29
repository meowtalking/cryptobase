#!/usr/bin/env python3
"""
Test to demonstrate the double encryption issue in backup restoration
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
from app.services.file_manager import add_file
from app.db import SessionLocal
from app.models import FileRecord

def test_restoration_issue():
    """Test the restoration issue"""
    print("=== Testing Restoration Issue ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test file
        test_file = temp_path / "test_encrypted.txt"
        original_content = b"This is original content for encrypted file."
        
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        # Create master key for container
        master_key = b"0123456789abcdef0123456789abcdef"
        
        # Add encrypted file to system
        print(f"1. Adding encrypted file: {test_file}")
        file_password = "TestPassword123!"
        file_record = add_file(str(test_file), password=file_password, master_key=master_key)
        file_id = file_record.id  # Store ID before session closes
        
        # Get file record with fresh session to avoid DetachedInstanceError
        session = SessionLocal()
        try:
            file_record = session.query(FileRecord).filter(FileRecord.id == file_id).first()
            print(f"   File record ID: {file_record.id}")
            print(f"   File password hash: {file_record.password_hash is not None}")
        finally:
            session.close()
        
        # Check what's actually stored in container
        print("\n2. Checking container content:")
        container = BackupContainer(master_key)
        versions = container.get_all_versions(str(file_record.id))
        
        if versions:
            version_content = bytes.fromhex(versions[0]["content"])
            print(f"   Version content length: {len(version_content)}")
            print(f"   Version content preview: {version_content[:50]}")
            
            # Try to decrypt version content (should fail if it's plaintext)
            try:
                decrypted = decrypt_file_from_bytes(version_content, file_password)
                print(f"   ❌ Version content is ENCRYPTED (double encryption problem!)")
                return False
            except Exception as e:
                print(f"   ✓ Version content is PLAINTEXT (correct): {str(e)[:50]}...")
                
                # Verify it matches original
                if version_content == original_content:
                    print(f"   ✓ Version content matches original plaintext")
                else:
                    print(f"   ❌ Version content doesn't match original")
                    return False
        else:
            print("   ❌ No versions found")
            return False
        
        # Test restoration logic (simulating restore_file_dialog)
        print("\n3. Testing restoration logic:")
        selected_version = versions[0]
        content_bytes = bytes.fromhex(selected_version["content"])
        
        print(f"   File password hash exists: {file_record.password_hash is not None}")
        print(f"   Content bytes length: {len(content_bytes)}")
        
        # This is the logic from restore_file_dialog
        final_content = content_bytes
        
        if file_record.password_hash is not None and file_record.password_hash.strip():
            print("   File is encrypted - trying to decrypt version...")
            try:
                if verify_password_for_db(file_password, file_record.password_hash):
                    final_content = decrypt_file_from_bytes(content_bytes, file_password)
                    print(f"   ❌ Version was decrypted (double encryption!)")
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
        
        if restored_content == original_content:
            print(f"   ✓ Restored content matches original")
            return True
        else:
            print(f"   ❌ Restored content doesn't match original")
            print(f"   Expected: {original_content}")
            print(f"   Got: {restored_content}")
            return False

if __name__ == "__main__":
    success = test_restoration_issue()
    if success:
        print("\n🎉 Test passed - no double encryption issue found")
    else:
        print("\n❌ Test failed - double encryption issue confirmed")
    sys.exit(0 if success else 1)

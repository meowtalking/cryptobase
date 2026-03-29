#!/usr/bin/env python3
"""
Test to understand what open_encrypted_raw is supposed to handle
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.security import encrypt_file, decrypt_file
from app.services.backup_container import BackupContainer

def test_backup_formats():
    """Test different backup formats"""
    print("=== Testing Backup Formats ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test content
        original_content = b"This is test content for backup."
        password = "TestPassword123!"
        master_key = b"0123456789abcdef0123456789abcdef"
        
        # Test 1: Individual encrypted file
        print("\n1. Testing individual encrypted file:")
        test_file = temp_path / "test.txt"
        with open(test_file, "wb") as f:
            f.write(original_content)
        
        encrypt_file(str(test_file), password)
        print(f"   Encrypted file size: {test_file.stat().st_size}")
        
        # Try to decrypt with decrypt_file
        try:
            decrypted = decrypt_file(str(test_file), password)
            print(f"   ✓ decrypt_file works: {decrypted == original_content}")
        except Exception as e:
            print(f"   ❌ decrypt_file failed: {e}")
        
        # Test 2: Container backup
        print("\n2. Testing container backup:")
        container = BackupContainer(master_key)
        file_id = "test_1"
        version_data = {
            "version_id": 1,
            "created_at": "2026-03-13T15:00:00",
            "hash": "dummy_hash",
            "comment": "Test backup",
            "content": original_content.hex()
        }
        container.add_version(file_id, version_data)
        
        container_path = Path.home() / ".cryptobase" / "backups.enc"
        if container_path.exists():
            print(f"   Container size: {container_path.stat().st_size}")
            
            # Try to decrypt container with decrypt_file (should fail)
            try:
                decrypted = decrypt_file(str(container_path), password)
                print(f"   ❌ Container should not be decryptable with decrypt_file")
            except Exception as e:
                print(f"   ✓ Container correctly not decryptable with decrypt_file: {type(e).__name__}")
        
        print("\n=== Conclusion ===")
        print("open_encrypted_raw should handle individual encrypted files, NOT container backups")
        print("The function name is misleading - it opens encrypted files, not container backups")

if __name__ == "__main__":
    test_backup_formats()

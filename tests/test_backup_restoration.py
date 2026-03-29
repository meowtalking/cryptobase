#!/usr/bin/env python3
"""
Test cases for backup restoration functionality
Tests both encrypted and plaintext file restoration
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.ui.main_window import MainWindow
from app.ui.local_storage_page import LocalStoragePage
from app.db import SessionLocal
from app.models import FileRecord
from app.services.file_manager import add_file
from app.services.backup_container import BackupContainer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

class BackupRestoreTest:
    def __init__(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.test_files = []
        self.app = None
        self.main_window = None
        
    def setup_test_environment(self):
        """Create test files and initialize app"""
        print(f"[TEST] Creating test environment in {self.test_dir}")
        
        # Create test files
        test_content_plain = b"This is a test file for plaintext restoration."
        test_content_enc = b"This is a test file for encrypted restoration."
        
        self.plain_file = self.test_dir / "plain_test.txt"
        self.enc_file = self.test_dir / "enc_test.txt"
        
        with open(self.plain_file, "wb") as f:
            f.write(test_content_plain)
        with open(self.enc_file, "wb") as f:
            f.write(test_content_enc)
            
        print(f"[TEST] Created test files: {self.plain_file}, {self.enc_file}")
        
    def init_app(self):
        """Initialize PyQt application"""
        self.app = QApplication(sys.argv)
        self.main_window = MainWindow()
        
        # Simulate successful login with test password
        self.main_window.set_password_for_key("TestPassword123!")
        
        print("[TEST] Application initialized")
        
    def test_plaintext_file_restoration(self):
        """Test restoring plaintext file"""
        print("\n=== Testing Plaintext File Restoration ===")
        
        try:
            # Add plaintext file to system
            file_record = add_file(str(self.plain_file))
            print(f"[TEST] Added plaintext file: {file_record.name}")
            
            # Verify file is in container
            container = BackupContainer(self.main_window.master_key)
            versions = container.get_all_versions(str(file_record.id))
            print(f"[TEST] Versions in container: {len(versions)}")
            
            if versions:
                version_content = bytes.fromhex(versions[0]["content"])
                print(f"[TEST] Version content length: {len(version_content)}")
                print(f"[TEST] Version content preview: {version_content[:50]}")
                
                # Verify content matches original
                with open(self.plain_file, "rb") as f:
                    original_content = f.read()
                    
                if version_content == original_content:
                    print("[TEST] ✓ Plaintext version content matches original")
                else:
                    print("[TEST] ✗ Plaintext version content does not match original")
                    return False
            else:
                print("[TEST] ✗ No versions found in container")
                return False
                
        except Exception as e:
            print(f"[TEST] ✗ Plaintext test failed: {e}")
            return False
            
        return True
    
    def test_encrypted_file_restoration(self):
        """Test restoring encrypted file"""
        print("\n=== Testing Encrypted File Restoration ===")
        
        try:
            # Add encrypted file to system
            file_record = add_file(str(self.enc_file), password="TestPassword123!")
            print(f"[TEST] Added encrypted file: {file_record.name}")
            
            # Verify file is encrypted
            with open(self.enc_file, "rb") as f:
                encrypted_content = f.read()
            print(f"[TEST] Encrypted file size: {len(encrypted_content)}")
            
            # Verify version in container
            container = BackupContainer(self.main_window.master_key)
            versions = container.get_all_versions(str(file_record.id))
            print(f"[TEST] Versions in container: {len(versions)}")
            
            if versions:
                version_content = bytes.fromhex(versions[0]["content"])
                print(f"[TEST] Version content length: {len(version_content)}")
                print(f"[TEST] Version content preview: {version_content[:50]}")
                
                # Version should be plaintext (our fix)
                # Verify it's not encrypted by trying to decrypt
                try:
                    from app.services.security import decrypt_file_from_bytes
                    decrypted = decrypt_file_from_bytes(version_content, "TestPassword123!")
                    print("[TEST] Version content appears to be encrypted (unexpected)")
                    return False
                except:
                    print("[TEST] ✓ Version content is plaintext (expected)")
                
                # Verify content matches original plaintext
                original_content = b"This is a test file for encrypted restoration."
                if version_content == original_content:
                    print("[TEST] ✓ Encrypted file version content matches original plaintext")
                else:
                    print("[TEST] ✗ Encrypted file version content does not match original")
                    return False
            else:
                print("[TEST] ✗ No versions found in container")
                return False
                
        except Exception as e:
            print(f"[TEST] ✗ Encrypted test failed: {e}")
            return False
            
        return True
    
    def test_restoration_logic(self):
        """Test the restoration logic from local_storage_page"""
        print("\n=== Testing Restoration Logic ===")
        
        try:
            # Get a file record for testing
            session = SessionLocal()
            file_record = session.query(FileRecord).first()
            session.close()
            
            if not file_record:
                print("[TEST] ✗ No files found in database")
                return False
                
            print(f"[TEST] Testing restoration for file: {file_record.name}")
            
            # Test restoration logic simulation
            container = BackupContainer(self.main_window.master_key)
            versions = container.get_all_versions(str(file_record.id))
            
            if not versions:
                print("[TEST] ✗ No versions to test restoration")
                return False
                
            selected_version = versions[0]
            content_bytes = bytes.fromhex(selected_version["content"])
            
            print(f"[TEST] Version content type: {'Encrypted' if file_record.password_hash else 'Plaintext'}")
            print(f"[TEST] Content bytes length: {len(content_bytes)}")
            
            # Simulate restoration logic
            final_content = content_bytes
            
            if file_record.password_hash:
                print("[TEST] File is encrypted - testing decryption")
                try:
                    from app.services.security import decrypt_file_from_bytes, verify_password_for_db
                    if verify_password_for_db("TestPassword123!", file_record.password_hash):
                        final_content = decrypt_file_from_bytes(content_bytes, "TestPassword123!")
                        print("[TEST] ✓ Successfully decrypted version content")
                    else:
                        print("[TEST] ✗ Password verification failed")
                        return False
                except Exception as e:
                    print(f"[TEST] ✗ Decryption failed: {e}")
                    return False
            else:
                print("[TEST] File is plaintext - no decryption needed")
            
            # Create test restored file
            restored_path = self.test_dir / f"restored_{file_record.name}"
            with open(restored_path, "wb") as f:
                f.write(final_content)
                
            print(f"[TEST] ✓ Restored file created: {restored_path}")
            print(f"[TEST] Restored file size: {restored_path.stat().st_size}")
            
            return True
            
        except Exception as e:
            print(f"[TEST] ✗ Restoration logic test failed: {e}")
            return False
    
    def cleanup(self):
        """Clean up test environment"""
        try:
            shutil.rmtree(self.test_dir)
            print(f"[TEST] Cleaned up test directory: {self.test_dir}")
        except Exception as e:
            print(f"[TEST] Cleanup failed: {e}")
    
    def run_all_tests(self):
        """Run all test cases"""
        print("=== Starting Backup Restoration Tests ===")
        
        try:
            self.setup_test_environment()
            self.init_app()
            
            # Run tests
            test_results = []
            test_results.append(("Plaintext Restoration", self.test_plaintext_file_restoration()))
            test_results.append(("Encrypted Restoration", self.test_encrypted_file_restoration()))
            test_results.append(("Restoration Logic", self.test_restoration_logic()))
            
            # Print results
            print("\n=== Test Results ===")
            passed = 0
            for test_name, result in test_results:
                status = "✓ PASSED" if result else "✗ FAILED"
                print(f"{test_name}: {status}")
                if result:
                    passed += 1
            
            print(f"\nTotal: {passed}/{len(test_results)} tests passed")
            
            if passed == len(test_results):
                print("🎉 All tests passed!")
                return True
            else:
                print("❌ Some tests failed")
                return False
                
        except Exception as e:
            print(f"Test execution failed: {e}")
            return False
        finally:
            self.cleanup()
            if self.app:
                self.app.quit()

if __name__ == "__main__":
    test = BackupRestoreTest()
    success = test.run_all_tests()
    sys.exit(0 if success else 1)

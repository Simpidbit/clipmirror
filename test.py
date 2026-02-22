"""
Test suite for the spclipbd module.

This module provides comprehensive tests for ClipboardContent class
and copy_to_clipboard function across different platforms.
"""

import os
import subprocess
import tempfile
import time
from spclipbd import ClipboardContent, copy_to_clipboard, TempFile


def test_text_clipboard():
    """Test reading and writing text content to/from clipboard."""
    print("Testing text clipboard operations...")

    # Test writing text
    test_text = "Hello, World!\nThis is a test for clipboard."
    test_bytes = test_text.encode("utf-8")
    copy_to_clipboard("_plaintext", test_bytes)
    print("  - Wrote text to clipboard")

    # Test reading text
    time.sleep(0.1)  # Small delay to ensure clipboard is ready
    content = ClipboardContent()
    suffix = content.get_suffix()
    raw = content.get_raw()

    print(f"  - Read content suffix: {suffix}")
    print(f"  - Read content length: {len(raw)} bytes")
    print(f"  - Read content: {raw.decode('utf-8')}")

    assert suffix == "_plaintext", f"Expected '_plaintext', got '{suffix}'"
    assert raw == test_bytes, "Text content mismatch"
    print("  - Text test PASSED!")


def test_image_clipboard():
    """Test reading and writing image content to/from clipboard."""
    print("\nTesting image clipboard operations...")

    # Create a simple 1x1 PNG image
    # PNG header + IHDR + IDAT + IEND for a 1x1 red pixel
    png_data = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00"
        b"\x00\x00\x00IEND\xaeB`\x82"
    )

    # Test writing image
    try:
        copy_to_clipboard("png", png_data)
        print("  - Wrote PNG to clipboard")
    except Exception as e:
        print(f"  - Note: Image write not fully supported on this platform: {e}")
        print("  - Skipping image read test")
        return

    # Test reading image
    time.sleep(0.1)  # Small delay to ensure clipboard is ready
    content = ClipboardContent()
    suffix = content.get_suffix()
    raw = content.get_raw()

    print(f"  - Read content suffix: {suffix}")
    print(f"  - Read content length: {len(raw)} bytes")

    # Note: Image clipboard support varies by platform
    if suffix == "png":
        assert raw == png_data, "Image content mismatch"
        print("  - Image test PASSED!")
    else:
        print(f"  - Image type not detected (got {suffix}), this may be platform-dependent")


def test_empty_clipboard():
    """Test handling of empty clipboard."""
    print("\nTesting empty clipboard handling...")

    # Write empty text
    empty_bytes = b""
    copy_to_clipboard("_plaintext", empty_bytes)
    print("  - Wrote empty content to clipboard")

    time.sleep(0.1)
    content = ClipboardContent()
    raw = content.get_raw()

    print(f"  - Read content length: {len(raw)} bytes")
    print("  - Empty clipboard test PASSED!")


def test_unicode_text():
    """Test reading and writing Unicode text to/from clipboard."""
    print("\nTesting Unicode text operations...")

    # Test with various Unicode characters
    test_text = "Hello 世界 🌍 Привет"
    test_bytes = test_text.encode("utf-8")

    copy_to_clipboard("_plaintext", test_bytes)
    print("  - Wrote Unicode text to clipboard")

    time.sleep(0.1)
    content = ClipboardContent()
    raw = content.get_raw()
    decoded = raw.decode("utf-8")

    print(f"  - Read content: {decoded}")

    assert raw == test_bytes, "Unicode text content mismatch"
    assert decoded == test_text, "Unicode text decoding mismatch"
    print("  - Unicode test PASSED!")


def test_file_copy():
    """Test reading file content from clipboard (when file is copied)."""
    print("\nTesting file copy operations...")

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        test_content = "This is a test file for clipboard copy test."
        f.write(test_content)
        temp_file = f.name

    try:
        # Simulate file copy by writing file URI to clipboard
        file_uri = f"file://{temp_file}"
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
            input=file_uri.encode("utf-8"),
            timeout=30,
            check=True,
        )
        print("  - Copied file to clipboard (using text/uri-list)")

        time.sleep(0.1)
        content = ClipboardContent()
        suffix = content.get_suffix()
        raw = content.get_raw()

        print(f"  - Read content suffix: {suffix}")
        print(f"  - Read content length: {len(raw)} bytes")
        print(f"  - Read content: {raw.decode('utf-8')}")

        assert suffix == "txt", f"Expected 'txt', got '{suffix}'"
        assert raw.decode("utf-8") == test_content, "File content mismatch"
        print("  - File copy test PASSED!")
    finally:
        os.unlink(temp_file)


def test_tempfile():
    """Test TempFile object functionality."""
    print("\nTesting TempFile object...")

    # Test with file type (should create temp file)
    test_data = b'Test content for TempFile'
    temp_file = copy_to_clipboard("txt", test_data)
    print(f"  - Created TempFile for 'txt' content")
    print(f"  - TempFile.path: {temp_file.path}")

    assert temp_file.path is not None, "TempFile.path should not be None for file types"
    assert os.path.exists(temp_file.path), "Temp file should exist"

    # Verify clipboard content
    content = ClipboardContent()
    assert content.get_suffix() == "txt", "Clipboard should have 'txt' suffix"
    assert content.get_raw() == test_data, "Clipboard content should match"

    # Test delete method
    temp_file.delete()
    print(f"  - Deleted temp file")
    assert not os.path.exists(temp_file.path), "Temp file should not exist after delete"

    # Test with plain text (should not create temp file)
    temp_file_text = copy_to_clipboard("_plaintext", b"plain text")
    print(f"  - Created TempFile for '_plaintext' content")
    print(f"  - TempFile.path: {temp_file_text.path}")

    assert temp_file_text.path is None, "TempFile.path should be None for plain text"

    # Verify delete doesn't error when path is None
    temp_file_text.delete()  # Should not raise
    print("  - TempFile test PASSED!")


def test_empty_content_type():
    """Test with empty string as content_type (should be treated as file)."""
    print("\nTesting empty content type...")

    test_data = b"Test data with empty content type"
    temp_file = copy_to_clipboard("", test_data)
    print(f"  - Created TempFile with empty content_type")
    print(f"  - TempFile.path: {temp_file.path}")

    # Empty content_type should create a temp file (no extension)
    assert temp_file.path is not None, "Empty content_type should create temp file"
    assert os.path.exists(temp_file.path), "Temp file should exist"

    # Verify clipboard content
    content = ClipboardContent()
    assert content.get_raw() == test_data, "Content should match"

    temp_file.delete()
    print("  - Empty content type test PASSED!")


def test_large_data():
    """Test with large data (1MB+)."""
    print("\nTesting large data...")

    # Create 1MB of data
    large_data = b"0123456789abcdef" * (1024 * 64)  # ~1MB
    print(f"  - Data size: {len(large_data)} bytes")

    temp_file = copy_to_clipboard("bin", large_data)
    print(f"  - Created TempFile for large data")
    print(f"  - TempFile.path: {temp_file.path}")

    assert temp_file.path is not None, "Large data should create temp file"
    assert os.path.exists(temp_file.path), "Temp file should exist"

    # Verify clipboard content
    content = ClipboardContent()
    assert len(content.get_raw()) == len(large_data), "Content size should match"
    assert content.get_raw() == large_data, "Content should match"

    temp_file.delete()
    print("  - Large data test PASSED!")


def test_special_characters():
    """Test with special characters in data."""
    print("\nTesting special characters...")

    special_data = (
        b"Special chars: \x00\x01\x02\x1f\x7f\x80\xfe\xff\n"
        b"Unicode: \xe4\xb8\xad\xe6\x96\x87\n"  # 中文
        b"Emoji: \xf0\x9f\x8c\x80\xf0\x9f\x8c\xb3\xf0\x9f\x8f\x86\n"  # emoji
        b"Quotes: \"single\" 'double' `backtick`\n"
        b"Newlines: \r\n\r\n\n"
        b"Tabs: \t\t\t"
    )

    temp_file = copy_to_clipboard("txt", special_data)
    print(f"  - Created TempFile with special characters")

    assert temp_file.path is not None, "Special chars should create temp file"

    # Verify clipboard content
    content = ClipboardContent()
    assert content.get_raw() == special_data, "Special chars should be preserved"

    temp_file.delete()
    print("  - Special characters test PASSED!")


def test_multiple_same_content():
    """Test that same content creates same temp file (MD5-based naming)."""
    print("\nTesting multiple writes of same content...")

    test_data = b"Same content multiple times"

    # Write same content twice
    temp_file1 = copy_to_clipboard("txt", test_data)
    temp_file2 = copy_to_clipboard("txt", test_data)

    print(f"  - First write: {temp_file1.path}")
    print(f"  - Second write: {temp_file2.path}")

    # Should use same file path (based on MD5)
    assert temp_file1.path == temp_file2.path, "Same content should use same temp file"

    # Clean up
    temp_file1.delete()
    print("  - Multiple same content test PASSED!")


def test_different_extensions():
    """Test with various file extensions."""
    print("\nTesting various file extensions...")

    extensions_to_test = [
        ("txt", b"text file"),
        ("json", b'{"key": "value"}'),
        ("xml", b'<root><item>test</item></root>'),
        ("md", b"# Markdown test"),
        ("py", b'print("Hello")'),
        ("js", b'console.log("test");'),
        ("csv", b"name,value\njohn,100\njane,200"),
        ("log", b"[INFO] Test log entry"),
    ]

    for ext, data in extensions_to_test:
        temp_file = copy_to_clipboard(ext, data)
        print(f"  - Extension {ext}: {temp_file.path}")

        assert temp_file.path is not None, f"Extension {ext} should create temp file"
        assert temp_file.path.endswith(f".{ext}"), f"File should have .{ext} extension"

        content = ClipboardContent()
        assert content.get_raw() == data, f"Content mismatch for {ext}"

        temp_file.delete()

    print("  - Various extensions test PASSED!")


def test_double_delete():
    """Test that deleting a file twice doesn't cause errors."""
    print("\nTesting double delete...")

    test_data = b"Test double delete"
    temp_file = copy_to_clipboard("txt", test_data)

    # First delete
    temp_file.delete()
    assert not os.path.exists(temp_file.path), "File should not exist after first delete"

    # Second delete (should not raise error)
    temp_file.delete()
    print("  - Double delete test PASSED!")


def test_image_types():
    """Test various image types."""
    print("\nTesting various image types...")

    # Minimal PNG header
    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    # Minimal JPEG header (SOI marker)
    jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    # Minimal BMP header
    bmp_data = b"BM" + b"\x00" * 20

    image_tests = [
        ("png", png_data),
        ("jpg", jpeg_data),
        ("bmp", bmp_data),
    ]

    for img_type, data in image_tests:
        temp_file = copy_to_clipboard(img_type, data)
        print(f"  - Image type {img_type}: {temp_file.path}")

        # Images should not create temp files
        assert temp_file.path is None, f"Image type {img_type} should not create temp file"

    print("  - Image types test PASSED!")


def test_archive_types():
    """Test archive file types (zip, tar, gz)."""
    print("\nTesting archive file types...")

    archive_tests = [
        ("zip", b"PK\x03\x04" + b"\x00" * 20),
        ("tar", b"ustar" + b"\x00" * 20),
        ("gz", b"\x1f\x8b" + b"\x00" * 20),
        ("7z", b"7z\xbc\xaf\x27\x1c" + b"\x00" * 20),
        ("rar", b"Rar!\x1a\x07" + b"\x00" * 20),
    ]

    for archive_type, data in archive_tests:
        temp_file = copy_to_clipboard(archive_type, data)
        print(f"  - Archive type {archive_type}: {temp_file.path}")

        assert temp_file.path is not None, f"Archive type {archive_type} should create temp file"
        assert temp_file.path.endswith(f".{archive_type}"), f"File should have .{archive_type} extension"

        content = ClipboardContent()
        # Note: suffix might be different based on actual file extension
        assert content.get_raw()[:4] == data[:4], f"Content should match for {archive_type}"

        temp_file.delete()

    print("  - Archive types test PASSED!")


def test_zero_byte_file():
    """Test with zero-byte data."""
    print("\nTesting zero-byte data...")

    zero_data = b""
    temp_file = copy_to_clipboard("dat", zero_data)

    # Zero-byte file should still be created
    assert temp_file.path is not None, "Zero-byte data should create temp file"

    # Verify file exists and is empty
    assert os.path.exists(temp_file.path), "Temp file should exist"
    assert os.path.getsize(temp_file.path) == 0, "File should be zero bytes"

    content = ClipboardContent()
    assert content.get_raw() == b"", "Content should be empty"

    temp_file.delete()
    print("  - Zero-byte data test PASSED!")


def test_newline_handling():
    """Test different newline formats."""
    print("\nTesting newline handling...")

    newline_tests = [
        ("unix", b"line1\nline2\nline3"),
        ("windows", b"line1\r\nline2\r\nline3"),
        ("old_mac", b"line1\rline2\rline3"),
        ("mixed", b"line1\r\nline2\nline3\r"),
    ]

    for name, data in newline_tests:
        temp_file = copy_to_clipboard("txt", data)
        print(f"  - {name} newlines")

        content = ClipboardContent()
        assert content.get_raw() == data, f"{name} newlines should be preserved"

        temp_file.delete()

    print("  - Newline handling test PASSED!")


def test_long_extension():
    """Test with a very long file extension."""
    print("\nTesting long extension...")

    test_data = b"Test with long extension"
    long_ext = "verylongextension"

    temp_file = copy_to_clipboard(long_ext, test_data)
    print(f"  - Extension: {long_ext}")
    print(f"  - TempFile.path: {temp_file.path}")

    assert temp_file.path is not None, "Long extension should create temp file"
    assert temp_file.path.endswith(f".{long_ext}"), f"File should have .{long_ext} extension"

    content = ClipboardContent()
    assert content.get_raw() == test_data, "Content should match"

    temp_file.delete()
    print("  - Long extension test PASSED!")


def test_concurrent_tempfiles():
    """Test multiple TempFile objects operating simultaneously."""
    print("\nTesting concurrent TempFile operations...")

    # Create multiple temp files at once
    temp_files = []
    for i in range(5):
        data = f"Concurrent test file {i}".encode("utf-8")
        temp_file = copy_to_clipboard("txt", data)
        temp_files.append(temp_file)
        print(f"  - Created temp file {i}: {temp_file.path}")

    # All should have unique paths (different content)
    paths = [tf.path for tf in temp_files]
    assert len(set(paths)) == len(paths), "Each file should have unique path"

    # Clean up all
    for tf in temp_files:
        tf.delete()

    # Verify all files are deleted
    for path in paths:
        assert not os.path.exists(path), f"File {path} should be deleted"

    print("  - Concurrent TempFile test PASSED!")


def test_repeated_delete():
    """Test calling delete multiple times on same TempFile."""
    print("\nTesting repeated delete...")

    test_data = b"Test repeated delete"
    temp_file = copy_to_clipboard("txt", test_data)

    # Delete multiple times
    for i in range(5):
        temp_file.delete()
        print(f"  - Delete call {i+1}")

    print("  - Repeated delete test PASSED!")


def main():
    """Run all clipboard tests."""
    print("=" * 50)
    print("Clipboard Module Test Suite")
    print(f"Platform: {__import__('platform').system()}")
    print("=" * 50)

    try:
        test_text_clipboard()
    except Exception as e:
        print(f"  - Text test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_image_clipboard()
    except Exception as e:
        print(f"  - Image test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_empty_clipboard()
    except Exception as e:
        print(f"  - Empty clipboard test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_unicode_text()
    except Exception as e:
        print(f"  - Unicode test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_file_copy()
    except Exception as e:
        print(f"  - File copy test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_tempfile()
    except Exception as e:
        print(f"  - TempFile test FAILED: {e}")
        import traceback

        traceback.print_exc()

    # Additional edge case tests
    try:
        test_empty_content_type()
    except Exception as e:
        print(f"  - Empty content type test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_large_data()
    except Exception as e:
        print(f"  - Large data test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_special_characters()
    except Exception as e:
        print(f"  - Special characters test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_multiple_same_content()
    except Exception as e:
        print(f"  - Multiple same content test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_different_extensions()
    except Exception as e:
        print(f"  - Different extensions test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_double_delete()
    except Exception as e:
        print(f"  - Double delete test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_image_types()
    except Exception as e:
        print(f"  - Image types test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_archive_types()
    except Exception as e:
        print(f"  - Archive types test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_zero_byte_file()
    except Exception as e:
        print(f"  - Zero-byte file test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_newline_handling()
    except Exception as e:
        print(f"  - Newline handling test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_long_extension()
    except Exception as e:
        print(f"  - Long extension test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_concurrent_tempfiles()
    except Exception as e:
        print(f"  - Concurrent TempFile test FAILED: {e}")
        import traceback

        traceback.print_exc()

    try:
        test_repeated_delete()
    except Exception as e:
        print(f"  - Repeated delete test FAILED: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 50)
    print("Test suite completed!")
    print("=" * 50)


if __name__ == "__main__":
    main()

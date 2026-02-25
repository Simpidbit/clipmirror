# Memory - Clipboard Mirror Project

## Project Overview
Cross-platform clipboard access module (`spclipbd.py`) that provides a unified interface for reading from and writing to system clipboard across Windows, macOS, and Linux platforms.

## Key Components

### `ClipboardContent` Class
- Reads clipboard content at construction time
- `get_suffix()`: Returns file extension without dot (e.g., "png", "txt", "zip") or "_plaintext"
- `get_raw()`: Returns binary content (UTF-8 encoded for text)

### `TempFile` Class
- Handle for temporary files created during clipboard operations
- `path`: Property returning the temp file path (None if no file created)
- `delete()`: Method to delete the temp file from disk

### `copy_to_clipboard()` Function
- Returns `TempFile` object
- Behavior by `content_type`:
  - `"_plaintext"` → Plain text (no temp file)
  - Image types (`png`, `jpg`, `jpeg`, `bmp`, `gif`, `webp`, `tiff`, `svg`) → Image data (no temp file for most types, except jpg/jpeg on Linux)
  - Other types (`txt`, `zip`, `json`, etc.) → File with temp created

## Platform Dependencies

### Windows
- PowerShell (built-in)
- .NET Framework (built-in)

### macOS
- osascript (built-in)
- **Optional but recommended**: PyObjC (`pip install pyobjc-core pyobjc-framework-AppKit pyobjc-framework-Cocoa`)
  - Provides NSPasteboard, NSURL, NSData, etc.
  - Required for proper file paste to Finder
  - Falls back to AppleScript if not available

### Linux
- xclip (`sudo apt-get install xclip` or equivalent)
- Background daemon `linux_uri_loop` runs automatically

## Platform Implementations

### Windows
- **Read**: PowerShell + .NET API
  - Check image → Check files (GetFileDropList) → Fallback to text
  - **Important**: PowerShell adds trailing newline to output, must strip it when reading text
- **Write**: PowerShell + .NET API
  - Plain text: SetText (use Clear() for empty text)
  - Images: Write to temp file first, then load with Image.FromFile() + SetImage()
  - Files: Create temp file + SetFileDropList
  - **Limitation**: Windows clipboard converts all image formats to PNG when reading back

### macOS
- **Read**: NSPasteboard (PyObjC) + AppleScript fallback
  - Check file types (NSFilenamesPboardType, public.file-url) → Check image (PNGf) → Fallback to text
  - UTI mapping for images: public.png, public.jpeg, com.microsoft.bmp, etc.
- **Write**: NSPasteboard (PyObjC) + AppleScript fallback
  - Plain text: AppleScript `set the clipboard to "..."`
  - Images: NSPasteboard.setData_forType_() with UTI types
  - Files: NSPasteboard.writeObjects_() with NSURL + bookmark data for Finder

### Linux
- **Read**: xclip
  - Check TARGETS → text/uri-list (files, checked first) → image → text
  - Files: Read URI, verify file exists, read content
  - Images: Check for JPEG, PNG, BMP signatures in order
- **Write**: xclip
  - Plain text: `xclip -selection clipboard`
  - All other types (images, files): Create temp file + `xclip -selection clipboard -t text/uri-list`
- **Background process**: `linux_uri_loop` daemon monitors clipboard and converts file:// URIs to text/uri-list format
  - Run in background as daemon process (started automatically on Linux)
  - Checks clipboard every 0.05 seconds
  - When clipboard contains `file://` in UTF8_STRING but no `text/uri-list` format:
    - Converts and sets the content as `text/uri-list`
  - Ensures proper file paste operation when using copy_to_clipboard()

## CRITICAL BUGS & SOLUTIONS

### Bug: PowerShell adds trailing newline to text output (Windows)
- **Environment**: Windows with PowerShell
- **Symptoms**:
  - Reading clipboard text returns content with extra `\n` at the end
  - `GetText()` output is correct, but PowerShell console adds newline
- **Root cause**: PowerShell's Write-Output always appends a newline to string output
- **Solution**: Strip trailing newline when reading text
  ```python
  text_content = result.stdout
  if text_content.endswith("\n"):
      text_content = text_content[:-1]
  self._raw = text_content.encode("utf-8")
  ```

### Bug: PowerShell command line too long for images (Windows)
- **Environment**: Windows with large images (>8KB base64)
- **Symptoms**:
  - `[WinError 206] 文件名或扩展名太长` (The filename or extension is too long)
  - Image copy fails for files larger than a few KB
- **Root cause**: Passing base64-encoded image data in command line exceeds Windows limit
- **Solution**: Write image to temp file, then load with .NET
  ```python
  # Write image to temp file first
  temp_image_file = os.path.join(_TEMP_DIR, f"{hash_obj}.{content_type}")
  with open(temp_image_file, "wb") as f:
      f.write(data)

  # Load from file and set to clipboard
  script = (
      f'Add-Type -AssemblyName System.Windows.Forms; '
      f'Add-Type -AssemblyName System.Drawing; '
      f'$img = [System.Drawing.Image]::FromFile("{temp_image_file}"); '
      f'[System.Windows.Forms.Clipboard]::SetImage($img); '
      f'$img.Dispose()'
  )
  # Clean up temp file after setting clipboard
  os.unlink(temp_image_file)
  ```

### Bug: SetText fails with empty string (Windows)
- **Environment**: Windows with empty text
- **Symptoms**:
  - `CalledProcessError` when trying to set empty text to clipboard
- **Root cause**: `[System.Windows.Forms.Clipboard]::SetText()` throws exception for empty string
- **Solution**: Use `Clear()` for empty text
  ```python
  if not text:
      script = (
          "Add-Type -AssemblyName System.Windows.Forms; "
          "[System.Windows.Forms.Clipboard]::Clear()"
      )
  ```

### Bug: File paste not working in Explorer (Windows)
- **Environment**: Windows Explorer, QQ, etc.
- **Symptoms**:
  - After `copy_to_clipboard('txt', ...)`, pasting in Explorer shows no response
  - FileDropList is set correctly but applications can't paste the file
- **Root cause**: Mixed path format `/tmp/spclipbd_files\...` - Git Bash's `/tmp` mapped to Windows temp, but path separators were inconsistent
- **Solution**: Use Windows-native temp directory path with `tempfile.gettempdir()`
  ```python
  import tempfile
  # Use Windows-native temp directory path for proper Explorer compatibility
  _win_temp_dir = os.path.join(tempfile.gettempdir(), "spclipbd_files")
  # Results in: C:\Users\xxx\AppData\Local\Temp\spclipbd_files\...
  ```

### Bug: xclip 0.13 image/jpeg timeout
- **Environment**: Linux with xclip version 0.13
- **Symptoms**:
  - Reading clipboard with `xclip -t image/jpeg -o` times out after copying JPEG
  - Even checking `TARGETS` times out after copying JPEG with MIME type
- **Root cause**: xclip 0.13 has a severe bug when handling image/jpeg MIME type
- **Solution**: Use file URI method (`text/uri-list`) instead of `image/jpeg` MIME type
  ```python
  # For jpg/jpeg on Linux, create temp file and use text/uri-list
  os.makedirs(_TEMP_DIR, exist_ok=True)
  hash_obj = hashlib.md5(data).hexdigest()
  temp_file = os.path.join(_TEMP_DIR, f"{hash_obj}.jpg")
  with open(temp_file, "wb") as f:
      f.write(data)
  file_uri = f"file://{quote(temp_file)}"
  subprocess.run(
      ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
      input=file_uri.encode("utf-8"),
      timeout=30,
      check=True,
  )
  ```
- **Note**: This approach works correctly with GNOME's clipboard manager and applications

### Bug: Python local import scope issue
- **Symptoms**: `UnboundLocalError: cannot access local variable 'quote' where it is not associated with a value`
- **Root cause**: In Python, when a variable is assigned anywhere in a function (including `import` statement), it becomes a **local variable for the entire function scope**, not just after the assignment
- **Example of problem**:
  ```python
  def _copy_linux(content_type: str, data: bytes) -> TempFile:
      if content_type in image_mime_types:
          # This import makes 'quote' local for the entire function!
          from urllib.parse import quote
          file_uri = f"file://{quote(temp_file)}"
          ...
      else:
          # This line fails because 'quote' is considered local but not yet assigned
          file_uri = f"file://{quote(temp_file)}"  # UnboundLocalError!
  ```
- **Solution**: Use module-level imports instead of local imports
  ```python
  # At top of file
  from urllib.parse import quote

  def _copy_linux(content_type: str, data: bytes) -> TempFile:
      if condition:
          file_uri = f"file://{quote(temp_file)}"  # Works!
      else:
          file_uri = f"file://{quote(temp_file)}"  # Also works!
  ```

## Important Implementation Details

### File Path Handling
- **Bug fixed**: Was using `lstrip('file://')` which stripped characters individually
- **Solution**: Use `uri.startswith("file://")` check and `uri[7:]` to remove prefix

### Temporary File Management
- **Linux/Windows**: `/tmp/spclipbd_files/` (or platform equivalent)
- **macOS**: `/tmp/` directly (Finder may have issues with subdirectories in /tmp)
- Naming: MD5 hash of content + extension (macOS uses first 12 chars only)
- No auto-deletion: Files persist until user calls `TempFile.delete()`

### MD5-based Naming
- Same content creates same temp file path
- Different content creates different temp file paths
- Efficient for repeated operations

### Image Signature Verification
- **JPEG**: Check for `b'\xff\xd8'` at start of file
- **PNG**: Check for `b'\x89PNG'` at start of file
- **BMP**: Check for `b'BM'` at start of file
- Always verify signature when reading images to avoid false positives

## Testing Strategy

### Windows
When testing on Windows, verify:
1. **Plaintext copy/paste**: `_plaintext` content_type works correctly
2. **Text file copy/paste**: `txt`, `json`, `zip` etc. create temp files correctly
3. **Image copy/paste**: Test `png`, `jpg` formats
   - Note: Windows clipboard converts all image formats to PNG when reading back
   - This is a Windows API limitation, not a bug
4. **ClipboardContent reading**: Ensure suffix is correct (no leading dot)
5. **File drop list**: Verify `SetFileDropList` works for pasting files
6. **TempFile cleanup**: Verify `delete()` works correctly
7. **PowerShell timeout**: Verify clipboard operations complete within timeout (10s read, 30s write)
8. **Empty text**: Verify empty text is handled correctly (uses Clear())
9. **Large images**: Verify large images (>100KB) work correctly (uses temp file method)

### Linux
When testing on Linux, verify:
1. **Plaintext copy/paste**: `_plaintext` content_type with xclip
2. **Text file copy/paste**: Files use `text/uri-list` format correctly
3. **Image copy/paste**: Test `png`, `bmp` formats (avoid `image/jpeg` MIME type on xclip 0.13)
4. **File URI conversion**: Background daemon correctly converts `file://` to `text/uri-list`
5. **ClipboardContent reading**: Check TARGETS before reading specific format
6. **TempFile cleanup**: Verify `delete()` works correctly
7. **xclip version check**: Handle xclip 0.13 JPEG bug properly

### macOS
When testing on macOS, verify:
1. **Plaintext copy/paste**: `_plaintext` content_type with AppleScript
2. **Text file copy/paste**: Files use NSPasteboard with NSURL and bookmark API for Finder
3. **Image copy/paste**: Test `png`, `jpg` formats with UTI types via NSPasteboard
4. **ClipboardContent reading**: Check NSFilenamesPboardType, public.file-url, then images
5. **TempFile cleanup**: Verify `delete()` works correctly
6. **Finder compatibility**: Files pasted to Finder work correctly (bookmark API)
7. **PyObjC dependency**: Ensure `AppKit` and `Foundation` are installed

### Common pitfalls to avoid:
- Don't use `lstrip()` for removing prefixes - use `startswith()` + slicing
- Don't use local imports inside functions if the name is used elsewhere in the function
- Always handle empty content gracefully
- Check for file existence before reading from URI

## Common Issues & Solutions

### Issue: File suffix with dot
- **Problem**: `get_suffix()` returned `.png`, `.txt` instead of `png`, `txt`
- **Solution**: Remove dot using `ext[1:].lower()` or `lstrip(".")`

### Issue: File content not read
- **Problem**: Copying files returned file path as text content instead of reading file
- **Solution**: Check for `text/uri-list` in targets BEFORE checking for images

### Issue: File path parsing incorrect
- **Problem**: `lstrip('file://')` removed characters individually instead of prefix
- **Solution**: Use `uri.startswith("file://")` check and `uri[7:]` slicing

### Issue: Wrong content type handling
- **Problem**: `copy_to_clipboard('txt', ...)` was treated as image
- **Solution**: Only treat known image types as images, everything else as files

### Issue: xclip timeout on JPEG (Linux specific)
- **Problem**: Reading clipboard after copying JPEG causes timeout
- **Solution**: Use `text/uri-list` method instead of `image/jpeg` MIME type for JPEG

### Issue: UnboundLocalError with imports
- **Problem**: Variable used before assignment when import is in different branch
- **Solution**: Use module-level imports, not local imports inside functions

## Files
- `spclipbd.py` - Main module
- `test.py` - Comprehensive test suite
- `sptest.py` - User's test script (do not modify)
- `prompt.md` - Original requirements
- `README.md` - Project documentation
- `client.py`, `server.py` - Network clipboard implementation (separate from spclipbd.py)

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

## Platform Implementations

### Windows
- **Read**: PowerShell + .NET API
  - Check image → Check files (GetFileDropList) → Fallback to text
- **Write**: PowerShell + .NET API
  - Plain text: SetText
  - Images: Base64 encoding + SetImage
  - Files: Create temp file + SetFileDropList

### macOS
- **Read**: AppleScript
  - Check image (PNGf) → Fallback to text
- **Write**: AppleScript
  - Plain text: `set the clipboard to "..."`
  - Images: Base64 encoding
  - Files: Create temp file + Finder alias

### Linux
- **Read**: xclip
  - Check TARGETS → text/uri-list (files, checked first) → image → text
  - Files: Read URI, verify file exists, read content
  - Images: Check for JPEG, PNG, BMP signatures in order
- **Write**: xclip
  - Plain text: `xclip -selection clipboard`
  - Images (except JPEG): `xclip -selection clipboard -t <mime_type>`
  - JPEG: Create temp file + `xclip -selection clipboard -t text/uri-list` (see CRITICAL BUGS below)
  - Files: Create temp file + `xclip -selection clipboard -t text/uri-list`

## CRITICAL BUGS & SOLUTIONS

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
- Directory: `/tmp/spclipbd_files/` (or platform equivalent)
- Naming: MD5 hash of content + extension
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

## Testing Strategy for macOS

### When testing on macOS, verify:
1. **Plaintext copy/paste**: `_plaintext` content_type
2. **Text file copy/paste**: `txt` content_type should create file, not paste as text
3. **Image copy/paste**: Test `png`, `jpg` formats
4. **ClipboardContent reading**: Ensure suffix is correct (no leading dot)
5. **TempFile cleanup**: Verify `delete()` works correctly

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

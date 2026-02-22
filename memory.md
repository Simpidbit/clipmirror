# Memory - Clipboard Mirror Project

## Project Overview
Cross-platform clipboard access module (`spclipbd.py`) that provides a unified interface for reading from and writing to the system clipboard across Windows, macOS, and Linux platforms.

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
  - Image types (`png`, `jpg`, `jpeg`, `bmp`, `gif`, `webp`, `tiff`, `svg`) → Image data (no temp file)
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
  - Images: Check for PNG signature
- **Write**: xclip
  - Plain text: `xclip -selection clipboard`
  - Images: `xclip -selection clipboard -t <mime_type>`
  - Files: Create temp file + `xclip -selection clipboard -t text/uri-list`

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

## Testing

### Test Coverage
1. Text clipboard (read/write)
2. Image clipboard (read/write)
3. Empty clipboard handling
4. Unicode text support
5. File copy operations
6. TempFile object functionality
7. Edge cases:
   - Empty content_type
   - Large data (1MB+)
   - Special characters
   - Same content multiple writes
   - Various file extensions
   - Double delete
   - Image types (png, jpg, bmp)
   - Archive types (zip, tar, gz, 7z, rar)
   - Zero-byte data
   - Newline handling
   - Long extension
   - Concurrent TempFile operations
   - Repeated delete

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

## Files
- `spclipbd.py` - Main module
- `test.py` - Comprehensive test suite
- `prompt.md` - Original requirements
- `README.md` - Project documentation
- `client.py`, `server.py` - Network clipboard implementation (separate from spclipbd.py)

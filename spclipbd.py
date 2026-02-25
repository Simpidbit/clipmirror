"""
Cross-platform clipboard access module.

This module provides a unified interface for reading from and writing to the
system clipboard across Windows, macOS, and Linux platforms.
"""

import os
import platform
import subprocess
import hashlib
import multiprocessing
import time
from typing import Optional
from urllib.parse import quote

# Directory for temporary clipboard files
# Use /tmp/spclipbd_files for shorter paths (important for macOS alias records)
_TEMP_DIR = "/tmp/spclipbd_files"


class TempFile:
    """
    Handle for temporary files created during clipboard operations.

    When content is copied to the clipboard as a file (not as plain text or image),
    a temporary file is created. This object provides a handle to manage that file.
    """

    def __init__(self, path: Optional[str]) -> None:
        """
        Initialize a TempFile handle.

        Args:
            path: The path to the temporary file, or None if no file was created
                   (e.g., for plain text or image content).
        """
        self._path = path

    @property
    def path(self) -> Optional[str]:
        """
        Get the path to the temporary file.

        Returns:
            Optional[str]: The path to the temporary file, or None if no file
                         was created (e.g., for plain text or image content).
        """
        return self._path

    def delete(self) -> None:
        """
        Delete the temporary file from disk.

        If no file was created (path is None), this method does nothing.
        If the file has already been deleted, this method does nothing.
        """
        if self._path and os.path.exists(self._path):
            os.unlink(self._path)


class ClipboardContent:
    """
    Represents the content of the system clipboard.

    This class reads clipboard content at construction time and provides
    methods to access the raw bytes and determine the content type via file suffix.
    Supports text, images, and files across Windows, macOS, and Linux platforms.
    """

    def __init__(self) -> None:
        """
        Initialize and read the current clipboard content.

        The content is read immediately upon construction using platform-specific
        methods (PowerShell/.NET on Windows, AppleScript on macOS, xclip on Linux).
        """
        self._raw: bytes = b""
        self._suffix: str = "_plaintext"
        system = platform.system()

        if system == "Windows":
            self._read_windows()
        elif system == "Darwin":
            self._read_macos()
        elif system == "Linux":
            self._read_linux()
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

    def _read_windows(self) -> None:
        """Read clipboard content using PowerShell and .NET API on Windows."""
        # Check if image is available (PNG format)
        image_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$img = [System.Windows.Forms.Clipboard]::GetImage(); "
            "if ($img) { "
            "$ms = [System.IO.MemoryStream]::new(); "
            "$img.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); "
            "$bytes = $ms.ToArray(); "
            "[System.Convert]::ToBase64String($bytes) "
            "} else { $null }"
        )
        result = subprocess.run(
            ["powershell", "-Command", image_script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.stdout.strip():
            import base64

            self._raw = base64.b64decode(result.stdout.strip())
            self._suffix = "png"
            return

        # Check for files
        file_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$files = [System.Windows.Forms.Clipboard]::GetFileDropList(); "
            "if ($files.Count -gt 0) { "
            "foreach ($f in $files) { Write-Output $f } "
            "} else { $null }"
        )
        result = subprocess.run(
            ["powershell", "-Command", file_script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.stdout.strip():
            files = result.stdout.strip().split("\n")
            if files:
                import os

                filepath = files[0].strip()
                if os.path.isfile(filepath):
                    _, ext = os.path.splitext(filepath)
                    if ext:
                        self._suffix = ext[1:].lower()  # Remove the dot
                    else:
                        self._suffix = ""
                    with open(filepath, "rb") as f:
                        self._raw = f.read()
                    return

        # Fall back to text
        text_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Clipboard]::GetText()"
        )
        result = subprocess.run(
            ["powershell", "-Command", text_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # PowerShell adds a trailing newline to output, remove it
        text_content = result.stdout
        if text_content.endswith("\n"):
            text_content = text_content[:-1]
        self._raw = text_content.encode("utf-8")

    def _read_macos(self) -> None:
        """Read clipboard content using AppleScript on macOS."""
        # First, try using NSPasteboard to check for file list types
        try:
            from AppKit import NSPasteboard
            import plistlib
        except ImportError:
            pasteboard = None
        else:
            pasteboard = NSPasteboard.generalPasteboard()

            # Check for NSFilenamesPboardType (file list)
            file_list_data = pasteboard.dataForType_('NSFilenamesPboardType')
            if file_list_data:
                try:
                    file_list = plistlib.loads(file_list_data.bytes().tobytes())
                    if file_list and isinstance(file_list, list) and file_list:
                        filepath = file_list[0]
                        if os.path.isfile(filepath):
                            # Read file content
                            _, ext = os.path.splitext(filepath)
                            if ext:
                                self._suffix = ext[1:].lower()  # Remove the dot
                            else:
                                self._suffix = ""
                            with open(filepath, "rb") as f:
                                self._raw = f.read()
                            return
                except Exception:
                    pass

            # Check for public.file-url
            file_url_data = pasteboard.dataForType_('public.file-url')
            if file_url_data:
                try:
                    file_url_str = file_url_data.bytes().tobytes().decode('utf-8')
                    if file_url_str.startswith('file://'):
                        filepath = file_url_str[7:]  # Remove "file://"
                        if os.path.isfile(filepath):
                            # Read file content
                            _, ext = os.path.splitext(filepath)
                            if ext:
                                self._suffix = ext[1:].lower()
                            else:
                                self._suffix = ""
                            with open(filepath, "rb") as f:
                                self._raw = f.read()
                            return
                except Exception:
                    pass

        # Check for file (alias) - fallback method
        text_script = 'tell application "System Events" to get the clipboard'
        result = subprocess.run(
            ["osascript", "-e", text_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        clipboard_content = result.stdout.strip()

        # Check if clipboard contains a file reference (starts with "alias ")
        if clipboard_content.startswith("alias "):
            # Extract the alias path (remove "alias " prefix)
            alias_path = clipboard_content[6:]  # Remove "alias "
            # Convert alias path to POSIX path
            script = f'POSIX path of alias "{alias_path}"'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            posix_path = result.stdout.strip()

            # Fix for "Macintosh HD:" volume name being converted to "/HD/" instead of "/"
            # This happens when POSIX path of alias "Macintosh HD:..." returns "/HD/private/..."
            if posix_path.startswith("/HD/") or posix_path.startswith("/HD:"):
                # Replace "/HD/" with "/"
                posix_path = "/" + posix_path[len("/HD/"):]

            if os.path.isfile(posix_path):
                # Read file content
                _, ext = os.path.splitext(posix_path)
                if ext:
                    self._suffix = ext[1:].lower()  # Remove the dot
                else:
                    self._suffix = ""
                with open(posix_path, "rb") as f:
                    self._raw = f.read()
                return

        # Check for image (PNGf)
        # Note: This requires pngpaste to be installed via Homebrew
        # Without pngpaste, we can only read images that were copied as file references
        image_script = '''
            tell application "System Events"
                try
                    set theData to the clipboard as «class PNGf»
                    return "HAS_IMAGE"
                on error
                    return "NO_IMAGE"
                end try
            end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", image_script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if "HAS_IMAGE" in result.stdout:
            # Try to use PyObjC to read image data
            try:
                from AppKit import NSPasteboard, NSData
            except ImportError:
                # Fallback to pngpaste if PyObjC is not available
                result = subprocess.run(
                    ["pngpaste", "-"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    self._raw = result.stdout
                    self._suffix = "png"
                    return

            # Use NSPasteboard to read image data
            pasteboard = NSPasteboard.generalPasteboard()
            available_types = pasteboard.types()

            # Map UTI to file extensions
            uti_to_ext = {
                "public.png": "png",
                "public.jpeg": "jpg",
                "com.microsoft.bmp": "bmp",
                "com.compuserve.gif": "gif",
                "public.tiff": "tiff",
                "org.webmproject.webp": "webp",
                "public.svg-image": "svg",
            }

            # Try each type in order
            for uti_type, ext in uti_to_ext.items():
                if uti_type in available_types:
                    data = pasteboard.dataForType_(uti_type)
                    if data and data.bytes():
                        self._raw = data.bytes().tobytes()
                        self._suffix = ext
                        return

        # Fall back to text (clipboard already contains text)
        self._raw = clipboard_content.encode("utf-8")

    def _read_linux(self) -> None:
        """Read clipboard content using xclip on Linux."""
        # First, check available targets
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        targets = result.stdout
        has_image = "image/png" in targets or "image/bmp" in targets or "image/jpeg" in targets

        # Check for files (text/uri-list) - check this first, before images
        has_files = "text/uri-list" in targets

        # Check for files first (takes priority over images)
        if has_files:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            uris = result.stdout.strip().split("\n")
            if uris and uris[0]:
                import os
                from urllib.parse import unquote

                uri = uris[0].strip()
                # Properly remove file:// prefix
                if uri.startswith("file://"):
                    filepath = unquote(uri[7:])  # Remove "file://"
                else:
                    filepath = unquote(uri)
                if os.path.isfile(filepath):
                    _, ext = os.path.splitext(filepath)
                    if ext:
                        self._suffix = ext[1:].lower()  # Remove the dot
                    else:
                        self._suffix = ""
                    with open(filepath, "rb") as f:
                        self._raw = f.read()
                    return

        # Only read as image if we actually have image data available
        if has_image:
            # Check for JPEG first (xclip 0.13 bug causes data truncation, but we try anyway)
            if "image/jpeg" in targets:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/jpeg", "-o"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    # Verify it's actually a JPEG (starts with JPEG signature)
                    if result.stdout[:2] == b"\xff\xd8":
                        self._raw = result.stdout
                        self._suffix = "jpg"
                        return

            # Check for PNG
            if "image/png" in targets:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    # Verify it's actually a PNG (starts with PNG signature)
                    if result.stdout.startswith(b"\x89PNG"):
                        self._raw = result.stdout
                        self._suffix = "png"
                        return

            # Check for BMP
            if "image/bmp" in targets:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/bmp", "-o"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    # Verify it's actually a BMP (starts with "BM")
                    if result.stdout[:2] == b"BM":
                        self._raw = result.stdout
                        self._suffix = "bmp"
                        return

        # Fall back to text
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            self._raw = result.stdout

    def get_suffix(self) -> str:
        """
        Get the file suffix of the clipboard content.

        Returns:
            str: The file extension without the dot (e.g., "png", "txt", "zip"),
                 or "_plaintext" for plain text content.
        """
        return self._suffix

    def get_raw(self) -> bytes:
        """
        Get the raw binary content of the clipboard.

        Returns:
            bytes: The binary content of the clipboard. For text content,
                   the bytes are UTF-8 encoded.
        """
        return self._raw


def copy_to_clipboard(content_type: str, data: bytes) -> TempFile:
    """
    Copy content to the system clipboard.

    Args:
        content_type: A string indicating the type of content, which should be
                      the same format as returned by ClipboardContent.get_suffix()
                      (e.g., "png", "txt", "zip", or "_plaintext").
        data: The binary content to copy to the clipboard. For text content,
              this should be UTF-8 encoded bytes.

    Returns:
        TempFile: A handle to the temporary file created for the operation.
                   If no temporary file was created (e.g., for plain text or
                   image content), the returned TempFile will have path=None.

    Raises:
        RuntimeError: If the current platform is not supported.
        subprocess.TimeoutExpired: If the clipboard operation times out.
    """
    system = platform.system()

    if system == "Windows":
        return _copy_windows(content_type, data)
    elif system == "Darwin":
        return _copy_macos(content_type, data)
    elif system == "Linux":
        return _copy_linux(content_type, data)
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def _copy_windows(content_type: str, data: bytes) -> TempFile:
    """Copy content to clipboard using PowerShell on Windows."""
    import tempfile

    # Use Windows-native temp directory path for proper Explorer compatibility
    _win_temp_dir = os.path.join(tempfile.gettempdir(), "spclipbd_files")

    if content_type == "_plaintext":
        # For plain text
        text = data.decode("utf-8")
        # Handle empty text - SetText doesn't work with empty string
        if not text:
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Clipboard]::Clear()"
            )
        else:
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.Clipboard]::SetText(@'\n{text}\n'@)"
            )
        subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return TempFile(None)

    # Check if it's an image type
    image_types = {"png", "jpg", "jpeg", "bmp", "gif", "webp", "tiff", "svg"}
    if content_type in image_types:
        # For images, write to temp file first to avoid command line length limit
        os.makedirs(_win_temp_dir, exist_ok=True)
        import hashlib

        hash_obj = hashlib.md5(data).hexdigest()
        ext = f".{content_type}" if content_type else ".png"
        temp_image_file = os.path.join(_win_temp_dir, f"{hash_obj}{ext}")

        with open(temp_image_file, "wb") as f:
            f.write(data)

        # Read image from temp file and set to clipboard
        script = (
            f'Add-Type -AssemblyName System.Windows.Forms; '
            f'Add-Type -AssemblyName System.Drawing; '
            f'$img = [System.Drawing.Image]::FromFile("{temp_image_file}"); '
            f'[System.Windows.Forms.Clipboard]::SetImage($img); '
            f'$img.Dispose()'
        )
        subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True,
            timeout=30,
            check=True,
        )

        # Remove temp image file (image is now in clipboard)
        os.unlink(temp_image_file)
        return TempFile(None)
    else:
        # For files (txt, zip, etc.), create a file in temp directory
        os.makedirs(_win_temp_dir, exist_ok=True)

        import hashlib

        hash_obj = hashlib.md5(data).hexdigest()
        ext = f".{content_type}" if content_type else ""
        temp_file = os.path.join(_win_temp_dir, f"{hash_obj}{ext}")

        with open(temp_file, "wb") as f:
            f.write(data)

        # Use FileDropList to copy file to clipboard
        script = (
            f'Add-Type -AssemblyName System.Windows.Forms; '
            f'$files = @("{temp_file}"); '
            f'[System.Windows.Forms.Clipboard]::SetFileDropList($files)'
        )
        subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return TempFile(temp_file)


def _copy_macos(content_type: str, data: bytes) -> TempFile:
    """Copy content to clipboard using AppleScript and NSPasteboard on macOS."""
    if content_type == "_plaintext":
        # For plain text, escape quotes and backslashes properly
        text = data.decode("utf-8")
        # Escape backslashes first, then quotes
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'set the clipboard to "{escaped_text}"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return TempFile(None)

    # Check if it's an image type
    image_types = {"png", "jpg", "jpeg", "bmp", "gif", "webp", "tiff", "svg"}
    if content_type in image_types:
        # For images, use PyObjC NSPasteboard API
        try:
            from AppKit import NSPasteboard, NSData
        except ImportError:
            # Fallback to file method if PyObjC is not available
            return _copy_macos_fallback(content_type, data)

        # Map image types to UTI (Uniform Type Identifier)
        uti_map = {
            "png": "public.png",
            "jpg": "public.jpeg",
            "jpeg": "public.jpeg",
            "bmp": "com.microsoft.bmp",
            "gif": "com.compuserve.gif",
            "webp": "org.webmproject.webp",
            "tiff": "public.tiff",
            "svg": "public.svg-image",
        }
        uti = uti_map.get(content_type, "public.png")

        # Create NSData from image data
        ns_data = NSData.alloc().initWithBytes_length_(data, len(data))

        # Get pasteboard and set data
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()

        # Declare only the original format type
        # This helps prevent macOS from auto-generating PNG format
        pasteboard.declareTypes_owner_([uti], None)
        pasteboard.setData_forType_(ns_data, uti)

        # For JPEG, also declare additional types to ensure compatibility
        # but don't set PNG data to prevent auto-conversion
        if content_type in ("jpg", "jpeg"):
            # Declare additional common image types but don't set their data
            # This tells the system these types are available but empty
            pass

        return TempFile(None)
    else:
        # For files (txt, zip, etc.), use NSPasteboard with NSURL
        # This is the proper way to copy files to clipboard for Finder
        try:
            from AppKit import NSPasteboard, NSURL, NSArray
            from Foundation import NSURLBookmarkCreationMinimalBookmark
        except ImportError:
            # Fallback to AppleScript if PyObjC is not available
            return _copy_macos_fallback(content_type, data)

        # Create a temporary file directly in /tmp for better Finder compatibility
        import hashlib

        hash_obj = hashlib.md5(data).hexdigest()
        ext = f".{content_type}" if content_type else ""
        # Use /tmp directly instead of /tmp/spclipbd_files subdirectory
        # Finder may have issues with subdirectories in /tmp
        temp_file = f"/tmp/{hash_obj[:12]}{ext}"

        with open(temp_file, "wb") as f:
            f.write(data)

        # Create NSURL from file path
        file_url = NSURL.fileURLWithPath_(temp_file)

        # Get pasteboard and set file URLs
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()

        # Use writeObjects with NSURL array - this sets NSFilenamesPboardType and public.file-url
        url_array = NSArray.arrayWithObject_(file_url)
        pasteboard.writeObjects_(url_array)

        # Also create and set alias record for Finder compatibility
        # Finder uses com.apple.alias-record for file paste operations
        bookmark_result = file_url.bookmarkDataWithOptions_includingResourceValuesForKeys_relativeToURL_error_(
            NSURLBookmarkCreationMinimalBookmark, None, None, None
        )
        bookmark_data, error = bookmark_result

        if bookmark_data and error is None:
            # Set the bookmark as alias record
            pasteboard.setData_forType_(bookmark_data, 'com.apple.alias-record')

        return TempFile(temp_file)

def linux_uri_loop():
    def query_targets(target: str = "TARGETS"):
        return subprocess.run(
            ["xclip", "-sel", "c", "-t", target, "-o"],
            timeout=30,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    while True:
        result = query_targets()
        if (not 'text/uri-list' in result) and ('UTF8_STRING' in result):
            result = query_targets("UTF8_STRING")
            if result[:len('file://')] == 'file://':
                subprocess.run(
                    ["xclip", "-sel", "c", "-t", "text/uri-list"],
                    input=result.encode("utf-8"),
                    timeout=30,
                    check=True
                )
        time.sleep(0.05)
if platform.system() == 'Linux':
    linux_uri_loop_process = multiprocessing.Process(target = linux_uri_loop, daemon = True)
    linux_uri_loop_process.daemon = True
    linux_uri_loop_process.start()

def _copy_macos_fallback(content_type: str, data: bytes) -> TempFile:
    """Fallback method for copying files when PyObjC is not available."""
    # Use /tmp directly for better Finder compatibility
    import hashlib

    hash_obj = hashlib.md5(data).hexdigest()
    ext = f".{content_type}" if content_type else ""
    temp_file = f"/tmp/spclipbd_{hash_obj[:8]}{ext}"

    with open(temp_file, "wb") as f:
        f.write(data)

    # Use AppleScript to copy file to clipboard
    script = f'''
        tell application "Finder"
            set theFile to POSIX file "{temp_file}"
            set the clipboard to (theFile as alias)
        end tell
    '''
    subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        timeout=30,
        check=True,
    )
    return TempFile(temp_file)

def _copy_linux(content_type: str, data: bytes) -> TempFile:
    if content_type == "_plaintext":
        # For plain text
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=data,
            timeout=30,
            check=True,
        )
        return TempFile(None)
    else:
        os.makedirs(_TEMP_DIR, exist_ok=True)

        # Create unique filename based on content
        hash_obj = hashlib.md5(data).hexdigest()
        ext = f".{content_type}" if content_type else ""
        temp_file = os.path.join(_TEMP_DIR, f"{hash_obj}{ext}")

        with open(temp_file, "wb") as f:
            f.write(data)

        # Convert to file URI and copy to clipboard
        file_uri = f"file://{quote(temp_file)}"

        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
            input=file_uri.encode("utf-8"),
            timeout=30,
            check=True
        )
        return TempFile(temp_file)


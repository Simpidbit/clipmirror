"""
Cross-platform clipboard access module.

This module provides a unified interface for reading from and writing to the
system clipboard across Windows, macOS, and Linux platforms.
"""

import os
import platform
import subprocess
import tempfile
from typing import Optional
from urllib.parse import quote

# Directory for temporary clipboard files
_TEMP_DIR = os.path.join(tempfile.gettempdir(), "spclipbd_files")


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
        self._raw = result.stdout.encode("utf-8")

    def _read_macos(self) -> None:
        """Read clipboard content using AppleScript on macOS."""
        # Check for image
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
            # Use pngpaste to get image data
            result = subprocess.run(
                ["pngpaste", "-"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._raw = result.stdout
                self._suffix = "png"
                return

        # Check for text
        text_script = 'tell application "System Events" to get the clipboard'
        result = subprocess.run(
            ["osascript", "-e", text_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self._raw = result.stdout.encode("utf-8")

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
    if content_type == "_plaintext":
        # For plain text
        text = data.decode("utf-8")
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
        # For images, use base64 encoding
        import base64

        b64_data = base64.b64encode(data).decode("ascii")
        script = (
            f"$bytes = [System.Convert]::FromBase64String('{b64_data}'); "
            "$stream = [System.IO.MemoryStream]::new($bytes); "
            "$img = [System.Drawing.Image]::FromStream($stream); "
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Clipboard]::SetImage($img)"
        )
        subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return TempFile(None)
    else:
        # For files (txt, zip, etc.), create a file in temp directory
        os.makedirs(_TEMP_DIR, exist_ok=True)

        import hashlib

        hash_obj = hashlib.md5(data).hexdigest()
        ext = f".{content_type}" if content_type else ""
        temp_file = os.path.join(_TEMP_DIR, f"{hash_obj}{ext}")

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
    """Copy content to clipboard using AppleScript on macOS."""
    if content_type == "_plaintext":
        # For plain text
        text = data.decode("utf-8")
        script = f'set the clipboard to "{text}"'
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
        # For images, use osascript
        import base64

        b64_data = base64.b64encode(data).decode("ascii")
        script = f'''
            set theData to do shell script "echo '{b64_data}' | base64 -D"
            set theClipboard to (theData)
            tell application "System Events" to set the clipboard to theClipboard
        '''
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return TempFile(None)
    else:
        # For files (txt, zip, etc.), create a file in temp directory
        os.makedirs(_TEMP_DIR, exist_ok=True)

        import hashlib

        hash_obj = hashlib.md5(data).hexdigest()
        ext = f".{content_type}" if content_type else ""
        temp_file = os.path.join(_TEMP_DIR, f"{hash_obj}{ext}")

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
    """Copy content to clipboard using xclip on Linux."""
    if content_type == "_plaintext":
        # For plain text
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=data,
            timeout=30,
            check=True,
        )
        return TempFile(None)

    # Map image types to their MIME types
    image_mime_types = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "bmp": "image/bmp",
        "gif": "image/gif",
        "webp": "image/webp",
        "tiff": "image/tiff",
        "svg": "image/svg+xml",
    }

    # Special handling for JPEG: use file URI instead of image data
    # This is because xclip 0.13 has a bug with image/jpeg that causes timeouts
    if content_type in ("jpg", "jpeg"):
        # Use file URI method (text/uri-list) for JPEG compatibility
        os.makedirs(_TEMP_DIR, exist_ok=True)

        import hashlib

        hash_obj = hashlib.md5(data).hexdigest()
        ext = ".jpg"
        temp_file = os.path.join(_TEMP_DIR, f"{hash_obj}{ext}")

        with open(temp_file, "wb") as f:
            f.write(data)

        # Convert to file URI and copy to clipboard
        file_uri = f"file://{quote(temp_file)}"
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
            input=file_uri.encode("utf-8"),
            timeout=30,
            check=True,
        )
        return TempFile(temp_file)

    # For other image types (PNG, BMP, GIF, etc.), use image data directly
    if content_type in image_mime_types:
        mime_type = image_mime_types[content_type]
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", mime_type],
            input=data,
            timeout=30,
            check=True,
        )
        return TempFile(None)

    # For files (txt, zip, etc.), create a file in temp directory and copy its URI
    os.makedirs(_TEMP_DIR, exist_ok=True)

    # Create unique filename based on content
    import hashlib

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
        check=True,
    )
    return TempFile(temp_file)

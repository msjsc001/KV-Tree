import os
import stat
import tempfile

def atomic_write(filepath, content, encoding="utf-8"):
    """
    Safely writes content to filepath using a temporary file and atomic replace.
    Prevents truncation and 0-byte files if process is interrupted.
    """
    # Create temp file in the same directory to ensure they are on the same filesystem
    dir_name = os.path.dirname(filepath)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".md", text=True)
    
    try:
        with os.fdopen(fd, 'w', encoding=encoding) as f:
            f.write(content)
            
        # If target file exists and is read-only, we must change its permissions first
        if os.path.exists(filepath):
            try:
                os.chmod(filepath, stat.S_IWRITE)
            except Exception:
                pass # Best effort
                
        # Atomic replace
        os.replace(tmp_path, filepath)
        
        # Set file to read-only as per application logic
        try:
            os.chmod(filepath, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        except Exception:
            pass # Best effort
    except Exception as e:
        # Cleanup temp file on failure
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise e

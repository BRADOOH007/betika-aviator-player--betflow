"""
Resource Path Helper for PyInstaller
Handles resource paths for both development and bundled EXE
"""
import os
import sys

def ensure_assets():
    base = os.path.abspath(".")
    assets_dir = os.path.join(base, "Assets")
    try:
        os.makedirs(assets_dir, exist_ok=True)
    except Exception:
        pass
    icon_path = os.path.join(assets_dir, "betflow_icon.ico")
    logo_path = os.path.join(assets_dir, "betflow_logo.png")
    try:
        from PIL import Image, ImageDraw, ImageFont
        if not os.path.exists(logo_path):
            img = Image.new("RGBA", (512, 512), (30, 30, 30, 255))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle((40, 40, 472, 472), radius=60, fill=(0, 180, 0, 255))
            font = None
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            text = "BetFlow"
            w, h = draw.textlength(text, font=font), 12
            tx = (512 - w) / 2 if isinstance(w, (int, float)) else 180
            ty = 240
            draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
            img.save(logo_path)
        if not os.path.exists(icon_path):
            ico = Image.new("RGBA", (256, 256), (30, 30, 30, 255))
            draw = ImageDraw.Draw(ico)
            draw.ellipse((32, 32, 224, 224), fill=(0, 180, 0, 255))
            font = None
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            text = "BF"
            w = draw.textlength(text, font=font)
            tx = int((256 - (w if isinstance(w, (int, float)) else 32)) / 2)
            ty = 110
            draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
            sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            ico.save(icon_path, format="ICO", sizes=sizes)
    except Exception:
        try:
            if not os.path.exists(logo_path):
                open(logo_path, "wb").close()
            if not os.path.exists(icon_path):
                open(icon_path, "wb").close()
        except Exception:
            pass

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller bundle
    
    When running as a bundled EXE, PyInstaller extracts resources to a temp folder.
    This function returns the correct path whether running from source or as EXE.
    
    Args:
        relative_path: Path relative to the script/exe (e.g., 'Assets/icon.ico')
        
    Returns:
        Absolute path to the resource
    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


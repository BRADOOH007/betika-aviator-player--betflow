"""
Fix the taskbar icon by creating a proper .ico file from PNG
"""
import os
from PIL import Image

print("🔧 Fixing taskbar icon...")

# Load the PNG logo
png_path = "Assets/betflow_logo.png"
ico_path = "Assets/betflow_icon.ico"

if not os.path.exists(png_path):
    print(f"❌ PNG not found: {png_path}")
    exit(1)

try:
    # Load PNG
    img = Image.open(png_path)
    print(f"✅ Loaded PNG: {img.size}")
    
    # Convert to RGBA if needed
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create multiple sizes for Windows (16x16, 32x32, 48x48, 64x64, 128x128, 256x256)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Create a white background for transparency
    icon_images = []
    for size in sizes:
        # Resize image
        resized = img.resize(size, Image.Resampling.LANCZOS)
        
        # Create white background
        background = Image.new('RGBA', size, (255, 255, 255, 255))
        
        # Paste image on white background (handles transparency)
        background.paste(resized, (0, 0), resized)
        
        # Convert to RGB (ICO doesn't need alpha for opaque images)
        rgb_img = background.convert('RGB')
        icon_images.append(rgb_img)
    
    # Save as ICO with multiple sizes
    icon_images[0].save(
        ico_path,
        format='ICO',
        sizes=sizes,
        append_images=icon_images[1:]
    )
    
    print(f"✅ Created ICO with {len(sizes)} sizes: {ico_path}")
    print(f"📏 Sizes: {', '.join([f'{s[0]}x{s[1]}' for s in sizes])}")
    print("\n✅ Icon fixed! Restart the GUI to see the change.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

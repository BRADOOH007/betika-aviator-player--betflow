#!/usr/bin/env python3
"""
AVIATOR BY BETFLOW - Complete Application Builder
Builds the full-featured Aviator automation app with AI, stability systems, and GUI
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).parent.absolute()

def print_header():
    print("\n" + "="*80)
    print("  [X] AVIATOR BY BETFLOW - COMPLETE APPLICATION BUILDER")
    print("  [X] AI-Powered Aviator Automation with Ultra-Stability")
    print("="*80)
    print("  Features:")
    print("  [X] AI Visual Recognition (68 training images)")
    print("  [X] Ultra-Stable 1000+ Account Processing")
    print("  [X] Playwright Headless Automation")
    print("  [X] Adaptive Rate Limiting & Circuit Breakers")
    print("  [X] Enterprise-Grade GUI")
    print("  [X] Real-time System Monitoring")
    print("  [X] Proxy Rotation & Anti-Detection")
    print("="*80 + "\n")

def check_dependencies():
    """Check if all required dependencies are available"""
    print("[X] Checking build dependencies...")

    required_modules = [
        'PyInstaller',
        'PIL',
        'cv2',
        'sklearn',
        'selenium',
        'playwright',
        'tkinter',
        'requests',
        'psutil'
    ]

    missing = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"  [X] {module}")
        except ImportError:
            print(f"  [X] {module} - MISSING")
            missing.append(module)

    if missing:
        print(f"\n[X] Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False

    print("[X] All dependencies available\n")
    return True

def prepare_build_environment():
    """Prepare the build environment"""
    print("[X] Preparing build environment...")

    # Ensure VISUAL_TRAINING_DATA exists
    if not os.path.exists('VISUAL_TRAINING_DATA'):
        print("  [X] VISUAL_TRAINING_DATA directory not found!")
        return False

    # Count training images
    total_images = 0
    for root, dirs, files in os.walk('VISUAL_TRAINING_DATA'):
        total_images += len([f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))])

    print(f"  [X] Found {total_images} training images")

    # Ensure Assets directory exists
    if not os.path.exists('Assets'):
        print("  [X]  Assets directory not found - creating...")
        os.makedirs('Assets', exist_ok=True)

    # Check for icon
    icon_path = 'Assets/betflow_icon.ico'
    if not os.path.exists(icon_path):
        print(f"  [X]  Icon not found at {icon_path} - EXE will not have custom icon")

    print("[X] Build environment ready\n")
    return True

def build_executable():
    """Build the executable using PyInstaller"""
    print("[X]  Building Aviator by BetFlow executable...")

    spec_file = 'BetFlowPro_V5_Simple.spec'

    if not os.path.exists(spec_file):
        print(f"[X] Spec file not found: {spec_file}")
        return False

    try:
        # Build command
        cmd = [
            sys.executable, '-m', 'PyInstaller',
            spec_file,
            '--clean',      # Clean cache
            '--noconfirm',  # Don't ask for confirmation
        ]

        print("Executing build command...")
        print(f"Command: {' '.join(cmd)}")

        start_time = time.time()
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        build_time = time.time() - start_time

        # Check if build succeeded
        exe_path = PROJECT_ROOT / "dist" / "Aviator by BetFlow.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)

            print("\n[X] BUILD SUCCESSFUL!")
            print("="*50)
            print(f"[X] Executable: {exe_path}")
            print(f"[X] Size: {size_mb:.2f} MB")
            print(f"[X]  Build Time: {build_time:.1f} seconds")
            print(f"[X] Version: 5.0.0 - Ultra-Stable")
            print("="*50)

            return True
        else:
            print("[X] Build completed but EXE not found!")
            print("Build output:")
            print(result.stdout)
            if result.stderr:
                print("Errors:")
                print(result.stderr)
            return False

    except subprocess.CalledProcessError as e:
        print(f"[X] Build failed with error code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False
    except Exception as e:
        print(f"[X] Build failed with exception: {e}")
        return False

def create_distribution_package():
    """Create a distribution package with all necessary files"""
    print("[X] Creating distribution package...")

    dist_dir = PROJECT_ROOT / "Aviator_by_BetFlow_Distribution"
    exe_dir = PROJECT_ROOT / "dist"

    if not exe_dir.exists():
        print("[X] Dist directory not found!")
        return False

    try:
        # Create distribution directory
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        dist_dir.mkdir()

        # Copy executable
        exe_source = exe_dir / "Aviator by BetFlow.exe"
        exe_dest = dist_dir / "Aviator by BetFlow.exe"

        if exe_source.exists():
            shutil.copy2(exe_source, exe_dest)
            print(f"  [X] Copied executable: {exe_dest.name}")
        else:
            print("[X] Executable not found in dist directory!")
            return False

        # Copy essential data files
        essential_files = [
            'proxies.txt',
            'README_Aviator_by_BetFlow.md',
            'LICENSE',
        ]

        for file in essential_files:
            if os.path.exists(file):
                shutil.copy2(file, dist_dir)
                print(f"  [X] Copied: {file}")

        # Create README
        readme_content = """# Aviator by BetFlow v5.0.0

## [X] AI-Powered Aviator Automation Tool

### Features:
- [X] **AI Visual Recognition**: Automatically detects freebets and betting interfaces
- [X] **Ultra-Stable Processing**: Handles 1000+ accounts without crashes
- [X] **Intelligent Automation**: Playwright-based headless betting
- [X] **Adaptive Rate Limiting**: Prevents bans with smart delays
- [X] **Real-time Monitoring**: System health and performance tracking
- [X] **Proxy Rotation**: Built-in proxy support for account protection

### Quick Start:
1. Double-click "Aviator by BetFlow.exe"
2. Add your account numbers (one per line)
3. Enter password (same for all accounts)
4. Click "Start Aviator Automation"
5. Watch the AI work!

### System Requirements:
- Windows 10/11
- 4GB RAM minimum
- Internet connection
- Administrator privileges recommended

### Safety Notes:
- Use only with accounts you own
- Freebet mode uses no real money
- AI ensures safe, controlled automation

---

**Built with enterprise-grade stability systems**
**Handles massive scale operations with zero crashes**

For support: Ensure all accounts have Aviator access
"""

        readme_path = dist_dir / "README_Aviator_by_BetFlow.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)

        print(f"  [X] Created README: {readme_path.name}")

        # Create version info
        version_info = f"""Aviator by BetFlow
Version: 5.0.0 - Ultra-Stable
Build Date: {time.strftime('%Y-%m-%d %H:%M:%S')}
Features: AI Visual Recognition, Ultra-Stable Processing, Playwright Automation
"""

        version_path = dist_dir / "version.txt"
        with open(version_path, 'w', encoding='utf-8') as f:
            f.write(version_info)

        print(f"  [X] Created version info: {version_path.name}")

        # Calculate total size
        total_size = sum(f.stat().st_size for f in dist_dir.rglob('*') if f.is_file())
        total_size_mb = total_size / (1024 * 1024)

        print("\n[X] DISTRIBUTION PACKAGE CREATED")
        print("="*40)
        print(f"[X] Location: {dist_dir}")
        print(f"[X] Total Size: {total_size_mb:.2f} MB")
        print(f"[X] Files: {len(list(dist_dir.rglob('*')))}")
        print("="*40)

        return True

    except Exception as e:
        print(f"[X] Failed to create distribution package: {e}")
        return False

def main():
    """Main build process"""
    print_header()

    # Step 1: Check dependencies
    if not check_dependencies():
        print("[X] Dependency check failed - cannot proceed")
        sys.exit(1)

    # Step 2: Prepare build environment
    if not prepare_build_environment():
        print("[X] Build environment preparation failed - cannot proceed")
        sys.exit(1)

    # Step 3: Build executable
    if not build_executable():
        print("[X] Executable build failed")
        sys.exit(1)

    # Step 4: Create distribution package
    if not create_distribution_package():
        print("[X] Distribution package creation failed")
        sys.exit(1)

    # Success message
    print("\n" + "[X]"*20)
    print("  AVIATOR BY BETFLOW - BUILD COMPLETE!")
    print("[X]"*20)
    print("\n[X] Your AI-powered Aviator automation tool is ready!")
    print("[X] Distribution package: Aviator_by_BetFlow_Distribution/")
    print("[X] Double-click the EXE to start automating!")
    print("\n[X] Pro Tips:")
    print("  [X] Add proxy servers to proxies.txt for better anonymity")
    print("  [X] Test with 1-2 accounts first")
    print("  [X] Monitor the AI status indicator in the GUI")
    print("  [X] The system is designed for 1000+ accounts but start small")
    print("\n" + "="*80)

if __name__ == "__main__":
    main()

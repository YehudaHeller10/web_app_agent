#!/usr/bin/env python3
"""
Wrapper script to run the web app builder with CPU-only mode
"""

import os
import sys
from pathlib import Path

# Set environment variables to force CPU mode
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # Disable CUDA
os.environ['OMP_NUM_THREADS'] = '4'      # Limit OpenMP threads
os.environ['MKL_NUM_THREADS'] = '4'      # Limit MKL threads

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

if __name__ == "__main__":
    print("Starting Web App Builder in CPU-only mode...")
    print("CUDA disabled, using CPU for model inference")
    
    try:
        from web_app_builder import main
        main()
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
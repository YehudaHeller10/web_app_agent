#!/usr/bin/env python3
"""
Test script to verify model loading and generation
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from llm_manager import LLMManager, ModelInfo

def test_model_loading():
    print("Testing model loading...")
    
    llm = LLMManager()
    
    # List available models
    models = llm.list_available_models()
    print(f"Found {len(models)} models")
    
    for i, model in enumerate(models[:5]):  # Show first 5
        print(f"{i+1}. {model.name} ({model.filename}) - {'Cached' if llm.is_downloaded(model) else 'Not cached'}")
    
    # Test with first available model
    if models:
        model = models[0]
        print(f"\nTesting with model: {model.name}")
        
        if not llm.is_downloaded(model):
            print("Model not downloaded, skipping test")
            return
            
        try:
            result = llm.generate_site("Create a simple portfolio website", model)
            print("✅ Generation successful!")
            print(f"HTML length: {len(result.get('html', ''))}")
            print(f"CSS length: {len(result.get('css', ''))}")
            print(f"JS length: {len(result.get('js', ''))}")
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("No models found")

if __name__ == "__main__":
    test_model_loading()
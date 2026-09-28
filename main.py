#!/usr/bin/env python3
"""
Entry point for SmartAPI Index Options Algorithmic Engine & Operator Dashboard.
"""
import sys
import os

# Add workspace directory to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smartapi_trader.main import main

if __name__ == "__main__":
    main()

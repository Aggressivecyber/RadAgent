#!/usr/bin/env python3
"""一键运行 RadG4-Agent"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from radagent.main import main
main()

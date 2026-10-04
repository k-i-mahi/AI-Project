"""Pygame front-end. Only ``app`` and ``scenes`` import pygame at module level."""

import os

# Keep the console clean, including in worker processes that re-import the main module.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

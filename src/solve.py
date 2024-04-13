"""
Given a path to processed piece data, finds a solution
"""

import os
import time

from common import board, connect, dedupe, util
from common.config import *


def solve(path):
    start_time = time.time()

    _deduplicate(input_path=os.path.join(path, VECTOR_DIR), output_path=os.path.join(path, DEDUPED_DIR))
    _find_connectivity(input_path=os.path.join(path, DEDUPED_DIR), output_path=os.path.join(path, CONNECTIVITY_DIR))
    _build_board(input_path=os.path.join(path, CONNECTIVITY_DIR), output_path=os.path.join(path, SOLUTION_DIR))

    duration = time.time() - start_time
    print(f"\n\n{util.GREEN}### Puzzle solved in {round(duration, 2)} sec ###{util.WHITE}\n")


def _deduplicate(input_path, output_path):
    """
    Often times the same piece was successfully extracted from multiple photos
    We do this on vectorized pieces to ignore noise in BMPs
    """
    print(f"\n{util.RED}### 3 - Deduplicating vector pieces ###{util.WHITE}\n")
    count = dedupe.deduplicate(input_path, output_path)
    if count != PUZZLE_NUM_PIECES:
        raise Exception(f"Expected {PUZZLE_NUM_PIECES} pieces, but found {count}")


def _find_connectivity(input_path, output_path):
    """
    Opens each piece data and finds how each piece could connect to others
    """
    print(f"\n{util.RED}### 4 - Building connectivity ###{util.WHITE}\n")
    start_time = time.time()
    connect.build(input_path, output_path)
    duration = time.time() - start_time
    print(f"Building the graph took {round(duration, 2)} seconds")


def _build_board(input_path, output_path):
    """
    Searches connectivity to find the solution
    """
    print(f"\n{util.RED}### 5 - Build board ###{util.WHITE}\n")
    start_time = time.time()
    board.build(input_path, output_path)
    duration = time.time() - start_time
    print(f"Building the board took {round(duration, 2)} seconds")


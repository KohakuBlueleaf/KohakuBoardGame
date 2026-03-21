"""Data file I/O: record dtypes, memory-mapped multi-file data source.

Mmap handles are opened lazily per-process so the DataSource can be
pickled across DataLoader workers without hitting Windows handle limits.
"""

import glob
import os
import struct
import sys
from typing import List, Tuple

import numpy as np

from .game_config import (
    HEADER_FMT,
    HEADER_SIZE,
    V4_HEADER_FMT,
    V4_HEADER_SIZE,
    V5_HEADER_FMT,
    V5_HEADER_SIZE,
    read_data_header,
)

SCORE_FILTER = 10000
NO_MOVE = 0xFFFF


def make_record_dtype(board_cells: int, version: int, hand_cells: int = 0) -> np.dtype:
    """Create numpy dtype for one data record."""
    fields = [("board", np.int8, (board_cells,))]
    if version >= 5:
        fields.append(("hand", np.int8, (hand_cells,)))
    if version == 1:
        fields += [("player", np.int8), ("score", "<i2")]
    elif version == 2:
        fields += [
            ("player", np.int8),
            ("score", "<i2"),
            ("result", np.int8),
            ("ply", "<u2"),
        ]
    elif version >= 3:
        fields += [
            ("player", np.int8),
            ("score", "<i2"),
            ("result", np.int8),
            ("ply", "<u2"),
            ("best_move", "<u2"),
        ]
    else:
        raise ValueError(f"Unknown data version {version}")
    return np.dtype(fields)


class FileMeta:
    """Serializable metadata for one .bin file (no mmap handle)."""

    __slots__ = (
        "path",
        "version",
        "count",
        "header_end",
        "record_size",
        "dtype",
        "num_hand",
        "file_size",
    )


class MmapDataSource:
    """Memory-mapped, multi-file data source.

    Mmap handles are opened lazily per-process (thread-local) so this
    object can be safely pickled to DataLoader workers.
    """

    def __init__(self, pattern: str, gcfg: dict, min_ply: int = 0):
        files = sorted(glob.glob(pattern))
        if not files:
            print(f"Error: no files match '{pattern}'")
            sys.exit(1)

        self.gcfg = gcfg
        board_cells = gcfg["board_cells"]

        self.metas: List[FileMeta] = []
        file_indices = []
        record_indices = []

        for fp in files:
            print(f"  Indexing {fp} ...", end="", flush=True)
            hdr = read_data_header(fp)
            version = hdr["version"]
            count = hdr["count"]
            num_hand = hdr.get("num_hand", 0) or 0

            if version >= 5:
                header_end = V5_HEADER_SIZE
            elif version >= 4:
                header_end = V4_HEADER_SIZE
            else:
                header_end = HEADER_SIZE

            hand_cells = 2 * num_hand if num_hand > 0 else 2
            dt = make_record_dtype(board_cells, version, hand_cells)

            m = FileMeta()
            m.path = fp
            m.version = version
            m.count = count
            m.header_end = header_end
            m.record_size = dt.itemsize
            m.dtype = dt
            m.num_hand = num_hand
            m.file_size = os.path.getsize(fp)

            # Validate
            expected = header_end + count * dt.itemsize
            if m.file_size < expected:
                count = (m.file_size - header_end) // dt.itemsize
                m.count = count
                print(f" [truncated to {count}]", end="")

            file_id = len(self.metas)
            self.metas.append(m)

            # Quick filter pass: mmap temporarily just for indexing
            mmap = np.memmap(fp, dtype=np.uint8, mode="r")
            data = np.frombuffer(
                mmap[header_end : header_end + count * dt.itemsize],
                dtype=dt,
            )
            mask = np.abs(data["score"].astype(np.int32)) <= SCORE_FILTER
            if min_ply > 0 and version >= 2:
                mask &= data["ply"] >= min_ply

            valid = np.where(mask)[0].astype(np.int32)
            file_indices.append(np.full(len(valid), file_id, dtype=np.int32))
            record_indices.append(valid)
            del mmap, data  # release the temporary mmap

            print(f" {count} records, kept {len(valid)}")

        self.file_idx = np.concatenate(file_indices)
        self.rec_idx = np.concatenate(record_indices)
        self.total = len(self.file_idx)
        filtered = sum(m.count for m in self.metas) - self.total
        print(
            f"  Total: {self.total + filtered} records, "
            f"filtered {filtered}, kept {self.total}"
        )

        # Lazy mmap cache: dict, rebuilt per-worker after pickle
        self._mmaps: dict = {}

    def __getstate__(self):
        """Drop mmap cache for pickling (DataLoader workers)."""
        state = self.__dict__.copy()
        state["_mmaps"] = {}
        return state

    def _get_mmap(self, file_id: int) -> np.ndarray:
        """Get or create mmap for a file (lazy, per-process)."""
        if file_id not in self._mmaps:
            m = self.metas[file_id]
            self._mmaps[file_id] = np.memmap(m.path, dtype=np.uint8, mode="r")
        return self._mmaps[file_id]

    def __len__(self):
        return self.total

    def get_record(self, idx: int) -> dict:
        """Read a single record by global index."""
        fid = self.file_idx[idx]
        rid = self.rec_idx[idx]
        m = self.metas[fid]
        mmap = self._get_mmap(fid)

        offset = m.header_end + rid * m.record_size
        raw = bytes(mmap[offset : offset + m.record_size])
        rec = np.frombuffer(raw, dtype=m.dtype)[0]

        board_h = self.gcfg["board_h"]
        board_w = self.gcfg["board_w"]
        result = {
            "board": np.array(rec["board"]).reshape(2, board_h, board_w),
            "player": int(rec["player"]),
            "score": int(rec["score"]),
        }
        if m.version >= 5 and m.num_hand > 0:
            result["hand"] = np.array(rec["hand"]).reshape(2, m.num_hand)
        else:
            result["hand"] = None
        if m.version >= 2:
            result["result"] = int(rec["result"])
            result["ply"] = int(rec["ply"])
        else:
            result["result"] = 0
            result["ply"] = 0
        if m.version >= 3:
            result["best_move"] = int(rec["best_move"])
        else:
            result["best_move"] = NO_MOVE
        return result

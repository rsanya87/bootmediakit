"""RAW/DD write against a loop device that carries a stale GPT."""

from __future__ import annotations

import os
import random
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop_helpers import MIB, LoopIntegrationCase, run, signatures, worker  # noqa: E402

DISK_SIZE = 128 * MIB
IMAGE_SIZE = 40 * MIB


def make_mbr_image(path: Path, size: int) -> None:
    """Deterministic pseudo-random "ISO" whose first sector is a valid MBR."""
    sectors = size // 512
    mbr = bytearray(512)
    # One bootable Linux (0x83) partition from sector 2048 to the end.
    mbr[446:462] = struct.pack(
        "<B3sB3sII", 0x80, b"\xfe\xff\xff", 0x83, b"\xfe\xff\xff", 2048, sectors - 2048
    )
    mbr[510:512] = b"\x55\xaa"
    body = random.Random(0x424D4B).randbytes(size - 512)
    path.write_bytes(bytes(mbr) + body)


class LoopRawWriteTests(LoopIntegrationCase):
    WORKDIR_SIZE_MIB = 256

    def test_raw_write_replaces_stale_gpt_and_matches_source(self):
        self.write_over_stale_gpt(hold_partition=False)

    def test_raw_write_succeeds_while_a_stale_partition_is_held_open(self):
        """An exclusive holder (a prober, an automounter) makes wipefs need --force.

        Without ``wipefs --force`` the signature cleanup fails with EBUSY here,
        so this test notices if the flag is ever dropped from the RAW writer.
        """
        self.write_over_stale_gpt(hold_partition=True)

    def write_over_stale_gpt(self, *, hold_partition: bool) -> None:
        disk = self.workdir / "disk.img"
        with disk.open("wb") as stream:
            stream.truncate(DISK_SIZE)
        run(["sfdisk", "--quiet", str(disk)], input_text="label: gpt\n,64MiB,L\n,,L\n")
        device = self.attach_loop(disk)
        first, _second = self.wait_for_partitions(device, 2)
        run(["mkfs.ext4", "-q", "-F", first])
        run(["udevadm", "settle"], check=False)

        # Precondition: the old GPT is visible at the start AND at the end.
        before = signatures(device)
        gpt_offsets = sorted(offset for offset, kind in before if kind == "gpt")
        self.assertEqual(len(gpt_offsets), 2, msg=f"várt: elsődleges és tartalék GPT, kapott: {before}")
        self.assertEqual(gpt_offsets[0], 512)
        self.assertGreater(gpt_offsets[1], IMAGE_SIZE, msg="a tartalék GPT-nek a kiírt kép mögött kell lennie")

        image = self.workdir / "linux.iso"
        make_mbr_image(image, IMAGE_SIZE)

        holder = os.open(first, os.O_RDONLY | os.O_EXCL) if hold_partition else None
        try:
            with self.loop_as_usb_disk(device):
                identity = worker.device_identity(device)
                worker.write_raw(image, device, True, identity)
        finally:
            if holder is not None:
                os.close(holder)

        run(["udevadm", "settle"], check=False)
        # 1. Every written byte equals the source.
        run(["cmp", "--bytes", str(IMAGE_SIZE), str(image), device])
        # 2. No GPT signature is left, neither the primary nor the backup one;
        #    only the partition table of the source image remains.
        after = signatures(device)
        self.assertEqual([kind for _offset, kind in after], ["dos"], msg=f"wipefs: {after}")
        with open(device, "rb") as stream:
            stream.seek(DISK_SIZE - 512)
            self.assertNotEqual(stream.read(8), b"EFI PART", msg="a tartalék GPT fejléc megmaradt")
        table = run(["sfdisk", "--json", device]).stdout
        self.assertIn('"label": "dos"', table)
        # 3. The kernel re-read the table: the stale second partition is gone.
        #    (A kernel without an MS-DOS partition parser reports none at all.)
        #    Not checked with a held partition: the kernel refuses to re-read
        #    a busy table until the holder is gone.
        if not hold_partition:
            remaining = self.kernel_partitions(device)
            self.assertLessEqual(len(remaining), 1, msg=remaining)
            self.assertNotIn(f"{Path(device).name}p2", remaining)
        # 4. State reported by the worker and cleanup.
        self.assertTrue(worker.TARGET_MODIFIED)
        self.assertEqual(self.events[-1]["percent"], 100)
        self.assert_worker_left_no_mounts_or_temp_dirs(device)


if __name__ == "__main__":
    unittest.main()

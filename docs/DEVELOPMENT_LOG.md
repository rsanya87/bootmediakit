# Development log

## 2026-11-01 — 0.1.1-alpha repository baseline

- Project identity changed from the internal name CachyUSB to BootMediaKit.
- Git baseline is the 0.1.1-alpha source snapshot. The app version stays `0.1.1-alpha`; branding and installed path/command names are the only intended code/package changes in this import.
- The Windows ESD conversion and WIM splitting work is part of the baseline.
- The GUI uses a scrollable content area to improve behavior on smaller displays.

## Known field report

Reported by user: a Windows 10 IoT Enterprise LTSC 2021 x64 ISO (Hungarian, integrated October 2025) was written by BootMediaKit 0.1.1-alpha to USB using GPT/FAT32 and ESD-to-WIM conversion/SWM splitting. On the same target PC, Windows Setup displayed a dialog stating that a required media driver was missing. The same ISO written with Rufus reportedly boots and proceeds correctly on that PC.

This is a confirmed failure report for one ISO/device/firmware combination. The root cause is not yet known. Do not mark the Windows creation workflow as reliable until the cause is identified and a real Windows Setup test passes.

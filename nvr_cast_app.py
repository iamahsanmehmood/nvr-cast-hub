"""
NVR Cast Hub — Universal NVR & CCTV Media, Multi-Monitor & Web Caster
Version: 0.1.0-beta
Author: Ahsan Mehmood (https://github.com/iamahsanmehmood)

Unified entry point that starts:
  1. Universal RTSP Media Server (/main and /sub streams for Hikvision, Dahua, Uniview, Reolink, ONVIF)
  2. Native Windows Desktop GUI Control Center (desktop_app)
  3. Browser Web Cast Studio & Mobile Remote (web_studio on http://localhost:8090)
"""

import tkinter as tk
from desktop_app.engine import attach_thread_to_default_desktop, NVRCastEngine, APP_VERSION
from desktop_app.gui import NVRCastDesktopApp
from web_studio.server import WebRemoteHandler

__all__ = [
    "APP_VERSION",
    "NVRCastEngine",
    "NVRCastDesktopApp",
    "WebRemoteHandler",
    "attach_thread_to_default_desktop",
]


def main():
    attach_thread_to_default_desktop()
    root = tk.Tk()
    NVRCastDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

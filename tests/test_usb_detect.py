#!/usr/bin/env python3
"""
Test script for Epson L1110 USB Detection and Status Query.
Tests:
1. Low-level USB device enumeration
2. IEEE 1284 Device ID retrieval via USB Control Transfer
3. Bulk IN / OUT endpoints discovery
4. ESC/P-R status communication
"""

import sys
import os
import usb.core
import usb.util

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.usb_device import EpsonUSBDevice, EPSON_VENDOR_ID, EPSON_L1110_PRODUCT_ID


def test_device_detection():
    print("=" * 60)
    print("STEP 1: Scanning for Epson USB Printer...")
    print("=" * 60)

    dev = usb.core.find(idVendor=EPSON_VENDOR_ID, idProduct=EPSON_L1110_PRODUCT_ID)
    if not dev:
        print(f"[FAIL] Epson printer VID:0x{EPSON_VENDOR_ID:04x} PID:0x{EPSON_L1110_PRODUCT_ID:04x} not found.")
        # Check any Epson
        any_epson = list(usb.core.find(find_all=True, idVendor=EPSON_VENDOR_ID))
        if any_epson:
            print(f"[INFO] Found {len(any_epson)} other Epson device(s):")
            for d in any_epson:
                print(f"  - VID:0x{d.idVendor:04x} PID:0x{d.idProduct:04x}")
        return False

    print(f"[SUCCESS] Epson L1110 found: Bus {dev.bus:03d} Device {dev.address:03d}")
    try:
        mfg = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else 'N/A'
    except Exception as e:
        mfg = f"Tidak dapat dibaca tanpa izin write USB ({e.__class__.__name__})"
    try:
        prod = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else 'N/A'
    except Exception as e:
        prod = f"Tidak dapat dibaca tanpa izin write USB ({e.__class__.__name__})"
    try:
        serial = usb.util.get_string(dev, dev.iSerialNumber) if dev.iSerialNumber else 'N/A'
    except Exception as e:
        serial = f"Tidak dapat dibaca tanpa izin write USB ({e.__class__.__name__})"

    print(f"  - Manufacturer : {mfg}")
    print(f"  - Product      : {prod}")
    print(f"  - Serial Number: {serial}")

    print("\n" + "=" * 60)
    print("STEP 2: Reading IEEE 1284 Device ID via USB Control Transfer...")
    print("=" * 60)
    try:
        # Standard USB Printer Class GET_DEVICE_ID request (bRequestType=0xa1, bRequest=0)
        device_id_raw = dev.ctrl_transfer(0xA1, 0, 0, 0, 1024, timeout=3000)
        # First 2 bytes are length in big endian
        if len(device_id_raw) >= 2:
            id_len = (device_id_raw[0] << 8) | device_id_raw[1]
            device_id_str = bytes(device_id_raw[2:id_len]).decode('ascii', errors='replace')
            print(f"[SUCCESS] IEEE 1284 Device ID:\n  {device_id_str}")
        else:
            print(f"[WARN] Raw device ID returned fewer than 2 bytes: {bytes(device_id_raw)}")
    except Exception as e:
        print(f"[WARN] Failed to get Device ID via control transfer: {e}")

    print("\n" + "=" * 60)
    print("STEP 3: Testing EpsonUSBDevice Connect & Endpoint Acquisition...")
    print("=" * 60)
    epson = EpsonUSBDevice()
    try:
        epson.connect()
        print("[SUCCESS] Connected successfully!")
        print(f"  - Bulk OUT Endpoint: 0x{epson.ep_out.bEndpointAddress:02x} (Packet Size: {epson.ep_out.wMaxPacketSize})")
        if epson.ep_in:
            print(f"  - Bulk IN Endpoint : 0x{epson.ep_in.bEndpointAddress:02x} (Packet Size: {epson.ep_in.wMaxPacketSize})")
        else:
            print("  - Bulk IN Endpoint : Not available")

        print("\n" + "=" * 60)
        print("STEP 4: Probing Status Communication (ESC/P-R Remote / BDC)...")
        print("=" * 60)
        if epson.ep_in:
            # Query status command: \x1b\x01@BDC ST\r\n
            query_cmd = b"\x1b\x01@BDC ST\r\n"
            print(f"Sending probe query: {query_cmd!r}")
            resp = epson.query_printer(query_cmd, delay_s=0.2)
            if resp:
                print(f"[SUCCESS] Received {len(resp)} bytes response from printer:")
                print(f"  Raw bytes: {resp!r}")
                print(f"  Decoded  : {resp.decode('latin1', errors='replace')}")
            else:
                print("[INFO] No immediate response to BDC ST, testing ESC/P-R Remote query...")
                # ESC ( R \x08\x00 REMOTE1 \x1b\x00\x00\x00
                remote_enter = b"\x1b(R\x08\x00REMOTE1"
                resp_remote = epson.query_printer(remote_enter, delay_s=0.2)
                if resp_remote:
                    print(f"[SUCCESS] Remote mode response ({len(resp_remote)} bytes): {resp_remote!r}")
                else:
                    print("[INFO] Communication channel open and ready for standard print stream.")

    except PermissionError as pe:
        print(f"[PERMISSION ERROR] {pe}")
        print("Tip: Install udev rule: sudo cp udev/99-epson-l1110.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules")
        return False
    except Exception as e:
        print(f"[ERROR] Connection test failed: {e}")
        return False
    finally:
        epson.disconnect()
        print("\n[INFO] Device disconnected and interface released cleanly.")

    print("\n" + "=" * 60)
    print("ALL HARDWARE CHECKS COMPLETED!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_device_detection()
    sys.exit(0 if success else 1)

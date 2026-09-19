"""
Epson L1110 USB Communication Core Module
Handles low-level USB connection, kernel driver detachment (usblp),
endpoint discovery (Bulk IN/OUT), and raw bidirectional communication.
"""

import sys
import time
import logging
from typing import Optional, Tuple
import usb.core
import usb.util

logger = logging.getLogger(__name__)

# Epson USB Constants
EPSON_VENDOR_ID = 0x04b8
EPSON_L1110_PRODUCT_ID = 0x00a8

# Default timeouts (ms)
DEFAULT_READ_TIMEOUT = 5000
DEFAULT_WRITE_TIMEOUT = 10000


class EpsonUSBDevice:
    """Manages USB communication with Epson L1110 Series printers."""

    def __init__(self, vendor_id: int = EPSON_VENDOR_ID, product_id: Optional[int] = EPSON_L1110_PRODUCT_ID):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.device: Optional[usb.core.Device] = None
        self.interface_number: int = 0
        self.ep_out: Optional[usb.core.Endpoint] = None
        self.ep_in: Optional[usb.core.Endpoint] = None
        self._kernel_detached = False

    def is_connected(self) -> bool:
        """Check if device is connected and endpoints are acquired."""
        return self.device is not None and self.ep_out is not None

    def find_device(self) -> usb.core.Device:
        """Locate the Epson printer device on USB bus."""
        if self.product_id:
            dev = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        else:
            dev = usb.core.find(idVendor=self.vendor_id)

        if dev is None:
            raise DeviceNotFoundError(
                f"Epson printer not found (VID: 0x{self.vendor_id:04x}, "
                f"PID: 0x{self.product_id:04x} if specified). Ensure printer is powered on and connected via USB."
            )
        return dev

    def connect(self) -> bool:
        """
        Connect to printer:
        1. Find USB device
        2. Detach kernel driver (usblp) if active
        3. Set configuration
        4. Claim interface
        5. Discover Bulk IN and Bulk OUT endpoints
        """
        self.device = self.find_device()

        # Detach kernel driver (usblp) if necessary
        try:
            if self.device.is_kernel_driver_active(self.interface_number):
                logger.info("Kernel driver 'usblp' is active. Detaching...")
                self.device.detach_kernel_driver(self.interface_number)
                self._kernel_detached = True
                logger.info("Kernel driver detached successfully.")
        except NotImplementedError:
            # Some OS/backends do not implement is_kernel_driver_active
            pass
        except usb.core.USBError as e:
            logger.warning(f"Could not detach kernel driver (might need permissions or already free): {e}")

        # Set the active configuration (usually first config)
        try:
            self.device.set_configuration()
        except usb.core.USBError as e:
            logger.debug(f"set_configuration info/warning: {e}")

        # Claim interface
        try:
            usb.util.claim_interface(self.device, self.interface_number)
            logger.info(f"Interface {self.interface_number} claimed.")
        except usb.core.USBError as e:
            raise PermissionError(
                f"Failed to claim USB interface {self.interface_number}: {e}. "
                f"Check udev rules or user permissions (group 'lp')."
            ) from e

        # Discover endpoints
        cfg = self.device.get_active_configuration()
        intf = cfg[(self.interface_number, 0)]

        self.ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            )
        )

        self.ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            )
        )

        if not self.ep_out:
            raise IOError("Bulk OUT endpoint not found on Epson USB interface.")

        logger.info(
            f"Connected to Epson device: OUT EP=0x{self.ep_out.bEndpointAddress:02x}, "
            f"IN EP={f'0x{self.ep_in.bEndpointAddress:02x}' if self.ep_in else 'None'}"
        )
        return True

    def write(self, data: bytes, timeout: int = DEFAULT_WRITE_TIMEOUT) -> int:
        """Send raw bytes (ESC/P-R commands or raster data) to Bulk OUT."""
        if not self.is_connected() or self.ep_out is None:
            raise IOError("Device not connected or Bulk OUT endpoint missing.")
        return self.ep_out.write(data, timeout=timeout)

    def read(self, length: int = 1024, timeout: int = DEFAULT_READ_TIMEOUT) -> bytes:
        """Read raw bytes (status response) from Bulk IN."""
        if not self.is_connected() or self.ep_in is None:
            raise IOError("Device not connected or Bulk IN endpoint missing.")
        try:
            return bytes(self.ep_in.read(length, timeout=timeout))
        except usb.core.USBTimeoutError:
            return b""

    def query_printer(self, command: bytes, read_length: int = 1024, delay_s: float = 0.1) -> bytes:
        """Send a query command and return the immediate response bytes."""
        self.write(command)
        if delay_s > 0:
            time.sleep(delay_s)
        return self.read(length=read_length)

    def disconnect(self):
        """Release claimed interface and cleanup resources."""
        if self.device:
            try:
                usb.util.release_interface(self.device, self.interface_number)
                logger.info(f"Interface {self.interface_number} released.")
            except Exception as e:
                logger.debug(f"Error releasing interface: {e}")

            # Reattach kernel driver if we detached it
            if self._kernel_detached:
                try:
                    self.device.attach_kernel_driver(self.interface_number)
                    logger.info("Kernel driver reattached.")
                except Exception as e:
                    logger.debug(f"Error reattaching kernel driver: {e}")
                self._kernel_detached = False

            try:
                usb.util.dispose_resources(self.device)
            except Exception:
                pass

            self.device = None
            self.ep_out = None
            self.ep_in = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class DeviceNotFoundError(Exception):
    """Raised when the specified USB printer is not found."""
    pass

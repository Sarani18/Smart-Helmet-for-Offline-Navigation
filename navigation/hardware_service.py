import logging
import httpx
import asyncio
from typing import Optional

logger = logging.getLogger("navigation_hardware")

class HardwareService:
    """
    Manages communication with the Smart Helmet ESP32 LED hardware.
    Maps navigation instructions and system states to specific LED patterns.
    """

    def __init__(self, esp32_ip: str = "10.100.30.164"):
        self.esp32_ip = esp32_ip
        self.base_url = f"http://{esp32_ip}/command"
        self.last_command: Optional[str] = None
        self._disabled = False

    async def update_from_instruction(self, instruction: str, is_gps_failed: bool = False):
        """
        Maps a text instruction (e.g., 'Turn Right') to an ESP32 command.
        """
        if is_gps_failed:
            command = "HAZARD"
        else:
            command = "CLEAR"
            instr_upper = instruction.upper()
            
            # Key-word matching for natural navigation text
            if "RIGHT" in instr_upper:
                command = "RIGHT_NOW"
            elif "LEFT" in instr_upper:
                command = "LEFT_NOW"
            elif "ARRIVE" in instr_upper or "DESTINATION" in instr_upper:
                command = "ARRIVED"

        # Suppress redundant commands
        if command == self.last_command:
            return

        await self.send_command(command)

    async def send_command(self, cmd: str):
        """Dispatches the command to the ESP32 hardware via HTTP."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                params = {"cmd": cmd}
                resp = await client.get(self.base_url, params=params)
                
                if resp.status_code == 200:
                    logger.info(f"[HW] Signal Sent: {cmd}")
                    self.last_command = cmd
                else:
                    logger.warning(f"[HW] ESP32 rejected command {cmd}: HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"[HW] ESP32 unreachable at {self.esp32_ip}. Error: {e}")
            # We don't log errors at 'warning' level here because 
            # the hardware might not be connected during every test.

    def set_ip(self, ip: str):
        self.esp32_ip = ip
        self.base_url = f"http://{ip}/command"
        logger.info(f"[HW] ESP32 Target Updated: {ip}")

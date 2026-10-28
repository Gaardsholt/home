# Beam

Wirelessly share and install badge applications peer-to-peer by holding badges back-to-back.

## Overview

Beam lets Universe 2026 badge users share applications directly over Bluetooth Low Energy (BLE) proximity without a computer or Wi-Fi network. Select an installed app to broadcast, hold two badges back-to-back to establish a high-proximity link, and transfer the application files directly into the badge's writable storage (`/apps/<slug>`). Once received, the app can be launched immediately or launched at any time from the badge home menu.

## How to use

1. Open **Beam** on both badges.
2. On the sending badge, highlight the app you want to share and press **SELECT** (⮐).
3. Hold the two badges back-to-back so the wireless antennas touch.
4. When the proximity bar fills, the transfer will begin automatically.
5. The receiving badge saves the files and prompts you to launch the newly installed app immediately.

## Controls

- **UP / DOWN**: Scroll through the list of shareable applications.
- **LEFT / RIGHT**: Switch between shareable apps and installed sideloaded apps.
- **SELECT**: Choose an app to send, or launch a received app.
- **BACK**: Cancel active transfer or return to the app list.

## Hardware requirements

- Requires the onboard Raspberry Pi RM2 wireless module for BLE proximity linking (`badgeware.link`).
- Transferred apps are stored on the internal flash filesystem under `/apps/`.

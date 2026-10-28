# Mona Teleporter

Emits infrared beacon signals to simulate Mona's Expedition locations for nearby badges.

Mona Teleporter turns your GitHub Universe 2026 badge into an interactive location beacon. Select any of the 9 official expedition locations to transmit its 38 kHz NEC infrared signal from the onboard IR LEDs (GPIO 16). When another attendee taps or points their badge toward yours, their badge will instantly detect and unlock that location in the official "Mona's Expedition" app.

## Features

- **All 9 Expedition Locations**: Cycle through Mo's Diner, Under the Hood, Creator Cabana, Open Source Records, Makerspace, Hack Your Badge, Demos & Donuts, Level Up Lounge, and CAB Member.
- **Tour Guide Mode (Unlock All)**: Emits a rapid-fire sequence of all 9 location codes in one go, granting instant 100% expedition completion.
- **Expedition Reset Mode**: Sends official reset code `0xF0` to wipe expedition progress on a target badge (ideal for testing).
- **Auto-Broadcast & Instant Burst**: Continuously broadcasts a pulse every second in Auto mode, with instant burst on button press.
- **Hardware-Calibrated IR**: Uses 38 kHz carrier frequency and precise NEC modulation on GPIO 16 via RP2350 PIO state machines.
- **Visual Radar & Case Lighting**: Displays a radiating radar animation on screen and blinks the white case LEDs during transmission.

## Controls

| Button                | Action                              |
| --------------------- | ----------------------------------- |
| **Left (<)**          | Previous location                   |
| **Right (>)**         | Next location                       |
| **Select (⮐)**        | Fire immediate high-power IR burst  |
| **Up (^) / Down (⌄)** | Toggle Auto-Broadcast mode ON / OFF |

## How to Tap

1. Select the desired location on your badge.
2. Ensure **Auto: ON** is active (or press **Select**).
3. Hold the top edge of your badge (where the dual IR LEDs are located) facing the top edge of the recipient's badge (where the IR receiver is located).
4. The recipient's badge will immediately play the celebratory unlock animation!

## Technical Specifications

- **IR Transmitter**: Dual IR LEDs via DMN3731U MOSFET on GPIO 16
- **Modulation**: 38 kHz NEC protocol (9ms start burst, 4.5ms start space, 560µs pulse distance encoding)
- **Target Receiver**: VSOP38338 demodulator on GPIO 17
- **Target Address**: `0x45` (Github Universe Beacon Address)

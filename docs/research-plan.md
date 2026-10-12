# Research notes

Checked 12 October 2026. These are options to test, not a validated capture procedure.

## Starting approach

Keep the object and lights stationary; move the camera. Start with one object and a few views. Expand to metal and transparent objects after a successful renderer comparison.

An end-effector Pi can keep camera cabling short and save files locally. It still needs power. Test the actual camera, SDK, power supply and storage together before printing the final mount. For stationary captures, software triggering may be sufficient; verify it rather than assuming hardware synchronization is necessary.

## Open decisions

| Question | Next check |
|---|---|
| Which cameras do we own? | Read model labels and interfaces. JAI is only a possibility. |
| Can a Pi control them? | Run the vendor's capture example on the Pi. |
| Battery or robot-tool power? | Measure demand and check the actual robot's supply limits. |
| Which lens? | Test framing and focus at reachable working distances. |
| Which enclosure size? | Measure the full planned motion envelope, not just the table. |
| What does “known light” require? | Agree relative camera-RGB calibration versus absolute radiometry. |
| How accurate are robot-derived poses? | Validate against an independent calibration target. |
| Which glass objects are practical? | Start simple; inspect whether background/refraction needs additional capture. |

## Useful methods and references

- **Camera and hand–eye calibration:** OpenCV provides standard methods. Robot repeatability alone does not establish camera-pose accuracy. [OpenCV calibration](https://docs.opencv.org/4.1.2/d2/d28/calib3d_8hpp.html).
- **Near-field lights:** position alone is insufficient; output and angular emission matter. Small LEDs may need a finite-area model for polished reflections. [LED-based Photometric Stereo](https://arxiv.org/abs/1707.01018), [code](https://github.com/yqueau/near_ps).
- **Area-light procurement:** request unit-specific radiance calibration, uncertainty, spatial/angular measurements and control details. Lux/CRI specifications alone are insufficient. See [shopping list](shopping-list.md).
- **Transparent objects:** background, refraction and internal geometry can matter. Treat these as a separate pilot question. [NeTO](https://arxiv.org/abs/2303.11219).
- **Dataset examples:** inspect [OpenIllumination's processing code](https://github.com/oppo-us-research/OpenIlluminationCapture) and [LUCES-MV](https://arxiv.org/abs/2412.16737), particularly calibration and reference captures.

## Hardware facts to verify against our equipment

- UR10e nominal reach is 1.3 m; our robot model is unconfirmed. [UR specifications](https://www.universal-robots.com/manuals/EN/HTML/SW10_10/Content/prod-usr-man/complianceUR10e/H_g5_sections/appendix_g5/tech_spec_sheet.htm).
- The supplied QC75 catalogue describes the ISO 9409-1-50-4-M6 interface. The Rhino model has not been validated here.
- JAI lists Pi 4/5 ARM64 SDK packages for supported cameras. This does not establish compatibility with our unidentified cameras. [JAI downloads](https://www.jai.com/support-software/jetson-ubuntu).

Record RAW images where supported, actual exposure/light settings, coordinate conventions and calibration versions. Keep independent validation captures; choose tolerances after measuring the pilot's noise and repeatability.

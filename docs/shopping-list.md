# Pilot shopping shortlist

Checked **12 October 2026**. Candidates, not approved purchases. Prices are displayed listings, not delivered quotes; currencies and tax treatment are kept as listed. Reconfirm availability and Denmark shipping before ordering.

**First: identify and test the cameras/lenses we already own.** Tent size and light calibration requirements are also unresolved.

## Camera, lens and Pi

| Candidate | Price evidence | Decision |
|---|---|---|
| Existing cameras + lenses | No new camera purchase | Preferred if Pi control and image quality pass a bench test. Models unknown. |
| [Raspberry Pi HQ Camera, C/CS mount](https://thepihut.com/products/raspberry-pi-high-quality-camera-lens) | Retailer lists camera at **£48 incl. VAT** | Inexpensive fallback; needs lens and Pi. Supports RAW through [official software](https://www.raspberrypi.com/documentation/computers/camera_software.html). |
| [Raspberry Pi 16 mm C-mount lens, SC0123](https://thepihut.com/products/raspberry-pi-high-quality-camera-lens?variant=31811254222910) | **£48 incl. VAT** | HQ-camera pilot option; check framing/working distance first. |
| [Kowa LM16FC24M, 16 mm C-mount](https://www.kowa-lenses.com/LM16FC24M-1.1-16mm-24MP-C-mount-Lens/12115) | **€893 excl. VAT**, plus shipping | Higher-cost industrial option; only consider after confirming sensor/mount requirements and testing existing lenses. |
| [Raspberry Pi 5, 4 GB](https://thepihut.com/products/raspberry-pi-5?country=GB&currency=GBP&variant=42531604922563) | **£105.60 incl. VAT; listed sold out** | Reuse a lab Pi first. Check a local reseller if needed. |
| [Raspberry Pi SSD Kit, 512 GB](https://www.raspberrypi.com/products/ssd-kit/) | Local reseller quote needed | Specific local-storage option; includes M.2 HAT+. Capacity depends on actual frame size/session length. |

Also allow for cooling, a short camera cable, mounting hardware and a suitable power supply. **Do not select a battery/converter until camera and Pi demand are measured.** Pi-local storage removes the long data cable, not the need for power. GigE cameras may need separate power/PoE; the Pi Ethernet port does not supply it.

If the cameras are JAI, check exact model support in the [Pi ARM64 SDK downloads](https://www.jai.com/support-software/jetson-ubuntu). Camera Link models may need different acquisition hardware.

## Lighting

Start with **one small emitter and one area source** for bench testing; decide quantities after that.

| Candidate | Price evidence | What is / is not established |
|---|---|---|
| [Thorlabs MCWHL7 mounted white LED](https://www.thorlabs.com/newgrouppage9.cfm?objectgroup_id=2692&partnumber=MCWHL7) + [DC2200 driver](https://punchout.thorlabs.com/newgrouppage9.cfm?objectgroup_id=9117) | Current package quote needed | Controllable small-emitter candidate. Requires our light calibration; not an ideal point source or a confirmed radiometric standard. Confirm driver/channel needs before ordering multiples. |
| [amaran P60x](https://help.aputure.com/en/amaran-p60c-p60x/photometrics-and-technical-specifications) | Current dealer quote needed | Ordinary photographic panel to borrow/test. Published photometrics are averaged, not unit-specific radiance calibration. Manual/app control may limit automation. |
| [Imatest LED Light Panel, ILP-A or ILP-B](https://www.imatest.com/product/imatest-led-light-panel/) | Product family **US$1,290–12,320**, excluding import taxes/fees; selected variant quote needed | Rectangular diffusers: A 229 × 152 mm; B 260 × 220 mm. Uniformity specification does not establish traceable radiance calibration. Ask what calibration can be supplied. Listed A–D lead time: 6–8 weeks. |
| [Imatest LED Lightbox, Size B](https://www.imatest.com/product/imatest-led-lightbox/) | Product family **US$5,950–24,580**, excluding import taxes/fees; selected variant quote needed | 260 × 220 mm diffuser, USB control. More expensive rectangular option; request unit-specific radiometric data. Listed standard-output lead time: 4–6 weeks. |
| [Gamma Scientific RS-7-1](https://gamma-sci.com/products/spectralled-tunable-light-sources/rs-7-1-benchtop-uniform-light-source/) | **Quote only** | Vendor explicitly specifies a 75 mm output with radiance calibration. Circular source, not a rectangular panel; confirm usable illumination at our working distance. |
| [Labsphere sources through SphereOptics](https://sphereoptics.de/products-services-index/light-measurement/light-sources/) | **Quote only** | Ask for an appropriate calibrated area source or calibration service for a chosen panel. No particular configuration or price verified. |

**Request before choosing an area light:** emitting dimensions, unit-specific spectral radiance and uncertainty, spatial/angular output data, stability, control interface, delivery time and delivered price. A lux value or CRI rating alone is not sufficient. Confirm that calibration applies to the final diffuser/aperture assembly and intended angles.

Practical choice: compare a borrowed/stable panel plus calibration with a supplier-calibrated source. We do not yet have evidence that the expensive source is necessary.

## Larger blackout tents

Prices below were checked by selecting each size in Sheerspeed's product page, with no paid bag/access extras. **All exclude VAT and delivery.** Dimensions are advertised sizes; clear internal dimensions and fit remain unconfirmed.

| Construction | Advertised L × W × H | Listed price | Pilot assessment |
|---|---|---:|---|
| [Single skin, grey exterior](https://www.sheerspeed.com/sound-and-film-production-single-skin-blackout-tent---grey-exterior-51938-p.asp) | 3 × 3 × 2.5 m | **£1,065** | Lowest-cost large candidate checked |
| Same | 3.6 × 3.6 × 2.5 m | **£1,205** | More room; check actual clearance |
| [Double skin, black exterior](https://www.sheerspeed.com/sound-and-film-production-complete-blackout-tent---black-51988-p.asp) | 3 × 3 × 2.5 m | **£1,415** | More robust construction; fits only if measured envelope allows |
| Same | 3.5 × 3.5 × 2.5 m | **£1,570** | Worth comparing with the 3 m version |
| Same | 4 × 4 × 2.5 m | **£2,045** | Largest checked; requires sufficient room footprint |

The vendor advertises blackout performance for both constructions. This does not guarantee low internal reflectance or acceptable leakage at our exposures. Confirm floor sealing, vents/cable entry, unobstructed interior and indoor anchoring; request a fabric sample if possible. Test with the camera after installation.

**Alternative:** blackout the room's windows and add secured matte drapes; obtain a local materials quote. **Exclude the Ilford pop-up darkroom** for this layout: its [1.3 × 1.3 m working space](https://www.ilfordphoto.com/popup-darkroom) is too tight for the table plus useful arm movement.

## Buy / defer

- **Test or borrow first:** existing camera/lens, Pi, one light, storage and power.
- **Quote now:** suitable-size tent and calibrated area-source/calibration-service options.
- **Buy after measurements:** camera replacement, lens, battery/converter and final tent size.
- **No reliable complete budget yet:** lighting configuration/calibration, power and available lab equipment remain unknown.

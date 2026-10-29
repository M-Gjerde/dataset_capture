# Radiometric capture protocol and measurement chain

Status: implementation plus experimental protocol, not a calibration certificate.
Updated 2026-10-20. Physical acquisition and live preview were verified on
Basler serial **40747855**, using Ubuntu ARM64, Python 3.14.4 and pypylon 26.8.
The deployment test `connection-check-20261020` is not calibration data.
Absolute calibration and unprocessed sensor response remain unverified.
Simulator and SDK emulator data are tests.

## Instrument and evidence register

Operator reports Basler **a2A3536-31ucBAS** and **JAI JCH-C43-1628A** lens.
The SDK confirmed model and serial; the Pi runs Ubuntu 26.04.1 LTS.
Physical filter condition, aperture, focus, camera orientation and mounting
geometry await inspection. There is currently **no calibrated radiance reference**.
The first hardware capture used BayerRG8 with BalanceWhiteAuto=Continuous and
LUTEnable=true in readback. Those settings are recorded evidence, not proof of
which processing stages affect Bayer output. Establish and validate a deliberate
measurement configuration before collecting calibration data.

Basler identifies the camera as a color Sony IMX676-AACR1-C rolling-shutter
sensor, 2 µm pixels, default 3536×3536 and full 3536×3552 resolution, C-mount,
USB 3.0. Its published relative spectral response includes the camera IR-cut
filter but excludes the lens. This is not an absolute response calibration.
Verify the installed filter rather than assuming the published configuration.
[Model documentation](https://docs.baslerweb.com/a2a3536-31ucbas)

JAI lists this lens as 16 mm, C-mount, 4/3-inch image format, f/2.8–f/22.
Record the actual aperture and focus mechanically: this application cannot
read their positions from the lens. The lens's image-format designation is
coverage, not the camera sensor size. Megapixel marketing is not a measured
system MTF, transmission or radiometric calibration.
[JAI lens specifications](https://news.jai.com/hubfs/Blogs-News%20files/Lenses-for-JAI%20cameras.pdf)

Keep three distinct evidence classes: operator-entered facts; observed device
readback with exact node names; and independently measured/validated behavior.
A missing node is UNKNOWN, never evidence that an operation is disabled.

## Research claims and what would identify them

For a single-bounce Lambertian surface, outgoing radiance is
`L_o = rho * E / pi`, with dimensionless reflectance rho and incident irradiance
E. Even if L_o is measured absolutely, `(a*rho, E/a)` produces the same value
where physical bounds allow it. Thus camera calibration anchors observations
but does not by itself identify reflectance and illumination separately.
This example is not a claim of an exact symmetry for every multi-bounce scene.

Analogous channel-wise ambiguity can trade material color against illuminant
color under simplified RGB models. Real spectra add metamerism: three camera
channels do not uniquely determine arbitrary spectral reflectance and emission.
White balance or an unconstrained learned color transform does not solve this.

AEGIR initializes emitter geometry from bright image regions, then optimizes
emission and other scene parameters. That initialization is useful evidence
about emitter location, but is not an independent SI radiance measurement.
Our conclusion: to claim an absolute emitter anchor, constrain the optimization
with calibrated emitter observations (and uncertainties), rather than relying
on initialization alone. [AEGIR, section 3.2](https://arxiv.org/html/2606.28635v1)

A practical experiment must provide an independent lighting/material constraint:
for example, known spectral radiance of directly observed emitters, or known
reflectance plus sufficient incident-light information and geometry. Saturated
emitters, unseen angular emission and unobserved sources remain ambiguities.
Test separately: illumination/material color accuracy; absolute scale accuracy;
and cross-asset transfer with no per-asset gain or color alignment at evaluation.

## Entire acquisition and transfer loop

| Stage | Physical/data operation | Recorded evidence and unresolved boundary |
|---|---|---|
| Scene to entrance pupil | Spectral radiance varies with position/direction; aperture, focus, lens transmission, flare, filters and vignetting map it to sensor irradiance | Operator optical setup, metric geometry and reference IDs; lens transmission/stray light remain to measure |
| Sensor exposure | CFA-filtered photons generate charge; dark current, shot noise and rolling exposure contribute | Requested exposure, camera readback, optional actual frame chunks, temperature if exposed; row timing needs model confirmation/measurement |
| Sensor analog/readout | Charge handling, offsets, read noise, possible correlated sampling, gain, ADC and clipping | Exact sensor-internal order and fixed corrections are not established by the public camera feature list; obtain manufacturer clarification and test response |
| Camera firmware | Possible digital gain/black compensation, correction maps, LUT/gamma, color operations, demosaic, spatial operations and packing | Exposed settings, selected banks, feature inventory and pylon feature-persistence text; hidden processing remains unknown |
| USB3 Vision | Device transmits image payload and optional chunks over USB | SDK success, block ID, payload length, PFNC type, CRC presence/result when available; no USB packet trace is archived |
| Pi pylon SDK | Driver receives buffers; GetArray exposes/unpacks image values | payload.bin copied before array extraction; array copied before buffer release; SDK/runtime versions, dtype and padding metadata |
| Pi application | Preserves pixels; separately makes previews, statistics and metadata | image.npy has the SDK array without application dark subtraction, WB, demosaic or tone mapping; preview conversions are separate |
| Pi storage | Write temporary directory, flush/fsync files, rename, fsync parent | Complete directory plus manifest checksums; ACK means Pi save completed, not host transfer completed |
| Pi to host | rsync over SSH, checksum comparison and interrupted-transfer resume | Incomplete capture directories excluded, host verifies saved file hashes; Pi originals retained |
| Offline analysis | Mask invalid samples and apply explicitly versioned calibration transforms | Preserve originals, coefficient files/hashes, units, validity domain and uncertainties; no absolute-unit fitter is implemented yet |
| Reconstruction/export | Fit scene against a specified measurement operator; export emitter/material conventions | Camera spectral/linear response, scene units, emission units and angular model must be consistent across renderers |

Conceptual forward expectation for pixel i:
`mean_electrons_i = t * A_pixel * integral[QE_i(lambda) * E_lambda_i * lambda/(h*c) d_lambda] + dark_rate_i*t`.
Here E_lambda is irradiance at the sensor, including the optics and CFA response
according to the chosen definition of QE. Do not count either twice. Random
shot/read noise, gain, offsets, quantization and clipping follow; the real
sensor/camera order is model dependent. DN is a digital code, not electrons or
scene radiance. The forward optical operator is necessary for either inverse
rendering or physical units. [Radiometry definitions](https://pbr-book.org/4ed/Radiometry%2C_Spectra%2C_and_Color/Radiometry)

## Processing controls and raw boundary

Prefer the highest useful supported single-plane Bayer format for this color
camera, after measuring bandwidth/response. Enumerate actual available formats
on connection; do not infer support from another ace model. Sensor bit depth,
internal transfer depth, output format and uint16 container size are distinct.
Basler documents that Bayer output avoids color interpolation, while sensor and
transfer depth may differ from output depth. Bayer does not prove absence of
black correction, defect replacement or other fixed operations.
[Pixel format](https://docs.baslerweb.com/pixel-format)
[Sensor bit depth](https://docs.baslerweb.com/sensor-bit-depth)

Before measurements, inspect and save:

- ExposureAuto, GainAuto, BalanceWhiteAuto, BlackLevelAuto; disable available auto modes.
- ExposureTime, Gain plus selector banks, black level/compensation, white-balance ratios.
- Sensor/transfer bit depth, pixel format, CFA, ROI offsets, mirroring, binning and decimation.
- Gamma enable/selector/value, color space, LUT, color transform and its matrix bank.
- PGI/demosaic, denoising, sharpening, defect/shading/spatial corrections, HDR/contrast.
- Shutter/readout mode, temperature and selector, frame-rate and throughput settings.
- Trigger configuration and frame metadata/chunk availability.

Gamma 1 and an explicitly disabled feature are only evidence for that particular
control. Optional black compensation has its own switch on supporting models.
Do not blindly set BlackLevel=0: clipping the dark distribution destroys data
needed to estimate bias and noise. Record a stable offset and subtract matched
darks offline. [Gamma](https://docs.baslerweb.com/gamma)
[Black level](https://docs.baslerweb.com/black-level)

Snapshots enumerate scalar features, save pylon persistence text, and visit
supported gain/black/balance/color-matrix selector banks before restoring them.
They do not exhaust arbitrary LUT entries, every selector combination, hidden
registers or sensor circuitry. An all-green exposed audit would still not prove
untouched sensor output. The application deliberately retains an unverified flag.

payload.bin is the SDK-delivered payload, including chunks if delivered, without
USB wire headers. image.npy is the SDK unpacked array, including its original
numeric dtype; these are two different representations. Packed Bayer must not
be decoded by assuming payload bytes equal uint16 values. Save PFNC, byte count,
row padding, ROI, chunk state, dtype endianness and SDK version with both.

Per-frame chunk exposure/gain/timestamp data, where supported, are preferable
to post-acquisition settings readback. A setting read after acquisition is not
an exposure timestamp. Enable available chunks explicitly before starting a
series; absence of CRC is recorded as unknown, not passed.
[Basler chunks](https://docs.baslerweb.com/data-chunks)

RGB preview: pylon RGB8 conversion (may demosaic/reduce depth), thumbnail, JPEG.
Raw-window preview: single-plane DN, fixed black/white window, clipping/rounding,
thumbnail, JPEG. Neither preview is a measurement file. Numeric inspection reads
original array values from the latest acquired frame; while running it may be a
different frame from the displayed JPEG. Pause preview to inspect a stable frame.
The nominal format maximum is not a measured saturation threshold.

## Timing and robot coordination

Current implementation owns one camera and uses software FrameStart triggering,
with no free-running image queue. One lock serializes settings, preview and
captures. A series owns that lock across its sweep. For robot use: command pose,
verify settled state externally, submit pose/lighting context and a unique ID,
wait for saved ACK, then move. Robot motion integration is not implemented.
Repeating the same ID/context returns the existing frame; changing context with
that ID is a conflict. Do not generate a new ID merely because an ACK timed out.

Software requests over Wi-Fi are not deterministic exposure synchronization.
Pi wall-clock trigger/receipt timestamps bracket software activity, not all row
exposures. Camera timestamp ticks are not UTC and require documented tick rate,
event definition, wrap/reset behavior and clock mapping before clock comparison.
No NTP/PTP synchronization accuracy or simultaneous trigger guarantee is claimed.
Use measured hardware triggers/photodiode timing if the experiment requires it.

Because this camera has rolling shutter, every row does not expose at the same
instant. Keep the scene and light stationary over the full readout/exposure
interval; measure LED/PWM/mains flicker and row artifacts. Exposure brackets
under varying light do not establish linearity. Resolve row timing and trigger
delays for the installed firmware and bit-depth mode before time-critical work.
[Shutter timing](https://docs.baslerweb.com/electronic-shutter-types)

## Measurement sequence

1. **Inventory and stability.** Read physical camera serial/firmware and USB link;
   record lens/filter/aperture/focus/pose. Select fixed manual settings, save the
   processing audit and enable chunks. Monitor temperature and signal stability
   to determine warm-up empirically, not by an assumed universal duration.
2. **Dark characterization.** Fully occlude light; capture repeats across intended
   exposure/gain/temperature ranges. Estimate bias, dark current, temporal noise
   and bad-pixel masks. Start with 16–32 repeats for exploratory statistics, then
   choose sample counts from required precision. This is not EMVA certification.
3. **Response and saturation.** Use a stable uniform source and independent source
   monitoring if possible. Capture repeated exposure levels without changing
   optics/gain. Fit only the experimentally linear interval, excluding dark-floor
   and clipped samples; determine saturation empirically, not from bit depth.
4. **Temporal noise and flat field.** For independent equal-mean repeated frames,
   `variance(frameA-frameB)/2` estimates temporal variance without static PRNU.
   Subtract corresponding dark variance when estimating shot-noise behavior.
   The photon-transfer slope in variance-DN² versus mean-DN has units DN/electron
   under its assumptions; its reciprocal is electrons/DN. This is not a radiance
   calibration. Derive relative flat fields from dark-subtracted uniform exposures,
   separately for CFA phases/channels. Mask defects; record normalization and source
   geometry. Source nonuniformity and lens shading can otherwise be confounded.
5. **Spectral and absolute response (blocked on reference).** Obtain traceable
   spectral radiance at the camera viewing geometry, with certificate, uncertainty,
   wavelength sampling, stability and spatial uniformity. A calibrated integrating
   sphere or characterized source measured by a suitable calibrated instrument is
   one route. A white card alone, a lux reading, or a manufacturer's relative QE
   plot is insufficient for general spectral radiance calibration.
6. **Fit and validate independently.** Fit response coefficients for each valid
   optics/gain/format configuration, and test held-out radiance/exposure levels,
   positions, spectra and temperatures. Save residuals, masks, coefficient hashes
   and uncertainty covariance. Do not claim general spectral accuracy from one
   broadband lamp: three integrals cannot reconstruct arbitrary spectra.
7. **Emitter capture.** Use unsaturated exposure brackets within the calibrated
   range, source monitoring, metric geometry and angular/spatial sampling. Fix or
   constrain measured emission with uncertainty during reconstruction. An observed
   front view cannot alone determine unseen angular emission or total flux.
8. **Transfer validation.** Reconstruct assets independently; relight together
   using the same measured lighting with no per-object exposure/color correction.
   Report held-out image errors, reference material errors and absolute scale
   errors separately, including uncertainties and failure cases.

NIST describes spectral-radiance reference facilities based on characterized
sources and calibrated instruments; the needed traceability is a measurement
chain, not the mere presence of an integrating sphere.
[NIST reference calibration context](https://www.nist.gov/programs-projects/remote-sensing-laboratory)

## Reversible processing and differentiable measurement model

A restricted offline transform is `s=(DN-D)/(t*F)` where D is a matched dark
estimate in DN, t is exposure in seconds and F is a positive dimensionless
relative flat. It outputs DN/s. The algebraic inverse is `DN=s*t*F+D`.
Use floating-point inputs; preserve negative dark-subtracted values. With fixed
coefficients the derivative with respect to DN is `1/(t*F)`. Do not insert clipping,
gamma, automatic normalization or lossy compression into this measurement path.
Stored originals remain authoritative; numerical inversion is not recovery of
photons lost to shot noise, ADC quantization or sensor clipping.

Differentiable does not imply invertible: demosaicing, denoising and tone curves
can be differentiable yet discard information. Prefer comparing predicted
measurements directly in linear CFA space with the camera spectral/optical
operator. Keep display color/tone mapping outside the fitting objective.

Absolute response requires an explicit spectral/band definition and calibrated
coefficient(s), plus their domain of validity. Propagate uncertainty with the
measurement Jacobian and coefficient/reference covariance; do not assume all
errors independent. Include dark/flat estimates, exposure, source uncertainty,
spectral mismatch, nonlinearity, temperature, flare, geometry and repeatability.
No coefficients or SI-valued output are fabricated by this application.

## Renderer and smartphone contract

Specify radiance W m^-2 sr^-1 (or spectral radiance with wavelength units), versus
irradiance W m^-2, radiant intensity W sr^-1 and flux W. Luminance cd m^-2/lux are
photometric; converting them to radiometric quantities requires spectral data.
Export metric geometry, emitting area, sidedness, spectral/RGB basis, angular
function and its normalization. For a constant-radiance one-sided Lambertian
surface only, flux is pi*A*L; other angular models require the actual integral.
A renderer's arbitrary RGB emission multiplier is not automatically SI radiance.
Validate export with a known scene and matching camera/film convention.

The Basler rig can provide a controlled benchmark for a smartphone workflow.
It does not transfer its calibration coefficients to a smartphone. The phone
needs its own RAW-mode, lens, gain, exposure, spectral and processing validation;
computational RAW may contain processing. Record device/OS/app/mode metadata and
validate repeated captures independently.
[Consumer-camera calibration research](https://arxiv.org/abs/1906.04155)

## Files, reproducibility and current limits

Each schema-2 capture stores image.npy, payload.bin, camera-state.json,
metadata.json and previews when conversion succeeds. Metadata includes request
context, optical setup, file SHA-256/lengths, array statistics and configuration
fingerprint. Camera state contains runtime versions/source hashes, exposed
settings and audit. Hashes detect changes relative to the manifest; they are
not a signed provenance system, and metadata itself is not tamper-proof.

The board supports exposure sweeps with repeats, settling-frame discards, dark
occlusion confirmation, cancellation and starting-exposure restoration. Every
frame saves its own state. Series plans are bound to starting setup/configuration;
resubmission uses the same IDs. After a crash there is no automatic acquisition
resume: verify physical state, restore starting settings, then explicitly resume.
A calibration reference ID is a label, not proof a valid certificate was supplied.

Not yet implemented: calibrated-source fitting, uncertainty analysis UI,
calibration-file validation/selection, robot driver, hard real-time coordination,
phone capture, renderer export, physical throughput tests or physical sensor
processing validation. The present panel is an acquisition/evidence foundation.
Use a single process/worker; no second camera owner. USB bandwidth, Pi RAM/storage
and Wi-Fi sustained transfer must be measured before choosing a capture cadence.
At 3536², a uint16 image is about 25 MB before payload duplication and metadata;
this scientific snapshot path is intended for deliberate captures, not 31-fps
full-resolution archival streaming. Preview rate is an upper request rate, not
a guaranteed camera frame rate. Keep Pi originals until host verification and
independent backup are complete.

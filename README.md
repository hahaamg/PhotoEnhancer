# 📸 Auto Photo Enhancer

A lightweight and customizable Python-based image enhancement tool that performs **global brightness adjustment**, **dehaze (contrast boost)**, **natural saturation correction**, and **selective highlight suppression**.

It’s ideal for **landscape**, **backlight photography**, and **batch processing** of travel or documentation photos.

---

## ✨ Features

- ✅ **Exposure boost**: Brighten dark images while preserving details.
- ✅ **Dehaze enhancement**: Enhance contrast for a clearer, crisper look.
- ✅ **Natural saturation adjustment**: Make colors pop without oversaturation.
- ✅ **Highlight suppression (3 styles)**:
    - `'curve'`: Apply a global S-curve to soften overly bright areas.
    - `'limited'`: Precisely compress only extreme highlight regions (default).
    - `'blend'`: Soft masking + blur blend for the smoothest look.
- ✅ **Single image or batch folder processing**
- ✅ Fully configurable parameters: exposure, contrast, saturation strength, softness, etc.

---

## 📦 Requirements

```bash
pip install opencv-python numpy
```

## Usage

### 🔹 Single Image Enhancement

```python
from auto_photo_enhancer import auto_enhance_strong_style

auto_enhance_strong_style(
    image_path="input.jpg",
    output_path="output.jpg"
)
```

### 🔹 Batch Processing Folder

```python
from auto_photo_enhancer import batch_enhance_strong_style

batch_enhance_strong_style(
    input_dir="raw_photos",
    output_dir="enhanced_photos"
)
```

## Custom Parameters

You can tune the enhancement using these parameters:

| Parameter | Type | Description | Recommended |
| --- | --- | --- | --- |
| `exposure` | float | Brightness multiplier (>1 = brighter, <1 = darker) | `1.10` |
| `dehaze_ratio` | float | Dehaze intensity (boosts contrast) | `0.66` |
| `highlight_mode` | str | `'curve'`, `'limited'`, or `'blend'` | `'limited'` |
| `threshold` | int | Brightness threshold for highlight suppression | `210` |
| `softness` | float | S-curve softness for highlight compression | `0.15` |
| `blend_strength` | float | Intensity of blurred blend for `'blend'` mode | `0.4` |
| `sat_strength` | float | Strength of natural saturation correction | `0.25` |

## 💬 Use Cases

- 🌄 Backlit landscapes
- 🏛 White walls and washed-out buildings
- 🎉 Event documentation photos
- 🧳 Travel albums for blog or print

---

## 📘 How It Works

The pipeline performs:

1. Float-normalization and exposure scaling
2. Contrast enhancement using OpenCV’s `convertScaleAbs`
3. Optional highlight suppression (via curve, mask, or blend)
4. Natural HSV saturation realignment

All operations are pixel-wise and efficient—ideal for batch work.

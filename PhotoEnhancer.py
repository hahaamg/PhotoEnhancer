import gradio as gr
import cv2
import numpy as np
import os
import glob

# ---------- 影像處理邏輯 ----------
def apply_fixed_bright_and_dehaze(img, exposure=1.10, dehaze_ratio=0.66):
    img_float = img.astype(np.float32) / 255.0
    img_bright = np.clip(img_float * exposure, 0, 1)
    contrast_strength = 1 + exposure * dehaze_ratio
    return cv2.convertScaleAbs(img_bright * 255, alpha=contrast_strength, beta=0)

def suppress_highlights_curve(img, threshold=230, softness=0.15):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    v_norm = v / 255.0
    t_norm = threshold / 255.0
    v_compressed = v_norm / (1 + softness * ((v_norm - t_norm) ** 2))
    v_new = np.clip(v_compressed * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge([h.astype(np.uint8), s.astype(np.uint8), v_new]), cv2.COLOR_HSV2BGR)

def suppress_highlights_limited(img, threshold=230, softness=0.15):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    v_norm = v / 255.0
    t_norm = threshold / 255.0
    mask = v_norm > t_norm
    v_norm[mask] = v_norm[mask] / (1 + softness * ((v_norm[mask] - t_norm) ** 2))
    v_new = np.clip(v_norm * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge([h.astype(np.uint8), s.astype(np.uint8), v_new]), cv2.COLOR_HSV2BGR)

def suppress_highlights_blend(img, threshold=230, blend_strength=0.4, blur_radius=41):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    _, _, v = cv2.split(hsv)
    mask = (v > threshold).astype(np.float32)
    mask_blur = cv2.GaussianBlur(mask, (blur_radius, blur_radius), 0)
    soft = cv2.GaussianBlur(img, (blur_radius, blur_radius), 0)
    blended = img.astype(np.float32) * (1 - mask_blur[..., None] * blend_strength) + \
              soft.astype(np.float32) * (mask_blur[..., None] * blend_strength)
    return np.clip(blended, 0, 255).astype(np.uint8)

def enhance_saturation_natural(img, strength=0.25):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    s_mean = np.mean(s)
    s = s + (s_mean - s) * (-strength)
    s = np.clip(s, 0, 255)
    return cv2.cvtColor(cv2.merge([h, s, v]).astype(np.uint8), cv2.COLOR_HSV2BGR)

# ---------- 主處理流程 ----------
def process_single_image(input_img, exposure, dehaze_ratio, highlight_method,
                         curve_threshold, curve_softness,
                         limited_threshold, limited_softness,
                         blend_threshold, blend_strength, blend_radius,
                         sat_strength):
    
    img = cv2.cvtColor(input_img, cv2.COLOR_RGB2BGR)
    img = apply_fixed_bright_and_dehaze(img, exposure, dehaze_ratio)

    if highlight_method == "curve":
        img = suppress_highlights_curve(img, curve_threshold, curve_softness)
    elif highlight_method == "limited":
        img = suppress_highlights_limited(img, limited_threshold, limited_softness)
    elif highlight_method == "blend":
        img = suppress_highlights_blend(img, blend_threshold, blend_strength, blend_radius)

    img = enhance_saturation_natural(img, sat_strength)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def process_folder(input_folder, output_folder, exposure, dehaze_ratio,
                   highlight_method, curve_threshold, curve_softness,
                   limited_threshold, limited_softness,
                   blend_threshold, blend_strength, blend_radius,
                   sat_strength):
    
    os.makedirs(output_folder, exist_ok=True)
    image_paths = glob.glob(os.path.join(input_folder, "*.[jJpP]*[gGnN]*"))
    count = 0
    for path in image_paths:
        img = cv2.imread(path)
        if img is None: continue

        img = apply_fixed_bright_and_dehaze(img, exposure, dehaze_ratio)

        if highlight_method == "curve":
            img = suppress_highlights_curve(img, curve_threshold, curve_softness)
        elif highlight_method == "limited":
            img = suppress_highlights_limited(img, limited_threshold, limited_softness)
        elif highlight_method == "blend":
            img = suppress_highlights_blend(img, blend_threshold, blend_strength, blend_radius)

        img = enhance_saturation_natural(img, sat_strength)

        out_path = os.path.join(output_folder, os.path.basename(path))
        cv2.imwrite(out_path, img)
        count += 1

    return f"✅ 批次處理完成，共處理 {count} 張圖片。"

# ---------- Gradio UI ----------
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 📸 Photo Enhancer")

    mode = gr.Radio(choices=["單張處理", "資料夾批次"], value="單張處理", label="選擇模式")

    with gr.Row():
        with gr.Column():
            image_input = gr.Image(type="numpy", label="上傳圖片（單張模式）")
            input_dir = gr.Textbox(label="輸入資料夾", value="input_images", visible=False)
            output_dir = gr.Textbox(label="輸出資料夾", value="output_images", visible=False)
        output_img = gr.Image(label="處理後圖片", visible=True)
        output_msg = gr.Textbox(label="處理結果", visible=False)

    exposure = gr.Slider(0.7, 1.5, value=0.83, label="曝光倍率 exposure")
    dehaze_ratio = gr.Slider(0.0, 1.0, value=0.45, label="去霧強度 dehaze ratio")
    sat_strength = gr.Slider(0.0, 1.0, value=0.35, label="自然飽和度強度")

    highlight_method = gr.Radio(choices=["curve", "limited", "blend"], value="limited", label="亮部壓制方式")

    with gr.Tab("curve 參數"):
        curve_threshold = gr.Slider(180, 255, value=240, label="threshold")
        curve_softness = gr.Slider(0.05, 0.5, value=0.15, label="softness")

    with gr.Tab("limited 參數"):
        limited_threshold = gr.Slider(180, 255, value=240, label="threshold")
        limited_softness = gr.Slider(0.05, 0.5, value=0.15, label="softness")

    with gr.Tab("blend 參數"):
        blend_threshold = gr.Slider(180, 255, value=240, label="threshold")
        blend_strength = gr.Slider(0.0, 1.0, value=0.4, label="blend strength")
        blend_radius = gr.Slider(5, 61, step=2, value=41, label="模糊範圍 blur radius")

    

    run_btn = gr.Button("🚀 開始處理")

    def handle_run(mode, image_input, input_dir, output_dir, *params):
        if mode == "單張處理" and image_input is not None:
            result = process_single_image(image_input, *params)
            return result, gr.update(visible=True), gr.update(visible=False)
        elif mode == "資料夾批次":
            msg = process_folder(input_dir, output_dir, *params)
            return None, gr.update(visible=False), gr.update(value=msg, visible=True)
        else:
            return None, gr.update(visible=False), gr.update(value="❌ 請上傳圖片或確認資料夾", visible=True)

    run_btn.click(
        fn=handle_run,
        inputs=[
            mode, image_input, input_dir, output_dir,
            exposure, dehaze_ratio, highlight_method,
            curve_threshold, curve_softness,
            limited_threshold, limited_softness,
            blend_threshold, blend_strength, blend_radius,
            sat_strength
        ],
        outputs=[output_img, output_img, output_msg]
    )

    def toggle_mode(mode):
        return {
            image_input: gr.update(visible=(mode == "單張處理")),
            input_dir: gr.update(visible=(mode == "資料夾批次")),
            output_dir: gr.update(visible=(mode == "資料夾批次")),
            output_img: gr.update(visible=(mode == "單張處理")),
            output_msg: gr.update(visible=(mode == "資料夾批次"))
        }

    mode.change(toggle_mode, inputs=[mode], outputs=[image_input, input_dir, output_dir, output_img, output_msg])

demo.launch()

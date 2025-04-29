import os
import io
import sys
import contextlib
import tempfile # 依然需要
from PIL import Image, ExifTags
import gradio as gr

# === 1. 自動旋轉 JPEG 圖片 ===
def auto_orient_image(img):
    try:
        exif = img._getexif()
        if exif is not None:
            for tag, value in exif.items():
                if ExifTags.TAGS.get(tag) == 'Orientation':
                    if value == 3:
                        img = img.rotate(180, expand=True)
                    elif value == 6:
                        img = img.rotate(270, expand=True)
                    elif value == 8:
                        img = img.rotate(90, expand=True)
                    break
    except Exception:
        pass
    return img

# === 2. 計算並 *準備* 輸出壓縮資訊 ===
def get_compression_info_str(filename, original_kb, compressed_kb, target_kb):

    if original_kb == 0:
        ratio = 0
    else:
        ratio = 100 * (1 - compressed_kb / original_kb)
    status = "✅ 達標" if compressed_kb <= target_kb else "⚠️ 未達標"
    info = f"{status}：{filename}\n"
    info += f"  原始：{original_kb:.1f} KB → 壓縮後：{compressed_kb:.1f} KB（節省 {ratio:.1f}%）\n\n"
    return info

# === 3. 壓縮 PNG ===
def compress_png(input_path, output_path, target_kb=100, step=0.85):
    log_output = ""
    try:
        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            log_output += f"⚠️ 警告：檔案不存在或為空：{input_path}\n"
            return log_output, 0, 0

        img = Image.open(input_path)
        original_kb = os.path.getsize(input_path) / 1024
        display_filename = os.path.basename(output_path)
        log_output += f"處理中 (PNG)：{display_filename}\n"

        # 轉換為 RGBA 確保透明度保留
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        width, height = img.size
        min_size = 32  # 不壓得太小
        success = False

        while True:
            buffer = io.BytesIO()
            resized = img.resize((int(width), int(height)), Image.LANCZOS)
            # 儲存成 palette 模式，有助於壓縮
            paletted = resized.convert('P', palette=Image.ADAPTIVE)
            paletted.save(buffer, format="PNG", optimize=True)

            size_kb = buffer.getbuffer().nbytes / 1024
            log_output += f"  尺寸 {int(width)}x{int(height)} → {size_kb:.1f} KB\n"

            if size_kb <= target_kb:
                success = True
                break

            if width < min_size or height < min_size:
                log_output += f"  ⚠️ 已縮到最小尺寸仍未達目標。\n"
                break

            width *= step
            height *= step

        # 最終儲存
        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())

        final_kb = os.path.getsize(output_path) / 1024
        log_output += get_compression_info_str(display_filename, original_kb, final_kb, target_kb)

        return log_output, original_kb, final_kb

    except Exception as e:
        log_output += f"❌ 錯誤處理 PNG：{e}\n"
        return log_output, 0, 0


# === 4. 壓縮 JPEG ===
def compress_jpeg(input_path, output_path, target_kb=100, quality_step=5):
    # ... (代碼基本同前，加入類似 PNG 的錯誤處理和顯示文件名調整) ...
    log_output = ""
    original_kb = 0
    compressed_kb = 0
    try:
        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
             log_output += f"⚠️ 警告：輸入檔案 {os.path.basename(input_path)} 不存在或為空，跳過。\n"
             return log_output, 0, 0

        img = Image.open(input_path)
        original_kb = os.path.getsize(input_path) / 1024
        display_filename = os.path.basename(output_path)
        log_output += f"處理中 (JPEG)：{display_filename}\n"

        img = auto_orient_image(img)
        if img.mode in ('RGBA', 'P', 'LA'): # 轉換為 RGB
            img = img.convert('RGB')

        quality = 95
        best_quality = quality
        last_compressed_kb = float('inf')
        saved_successfully = False # 標記是否至少成功保存過一次

        while quality >= 10:
            try:
                img.save(output_path, format='JPEG', quality=quality, optimize=True, progressive=True)
                # 檢查文件是否真的寫入了
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    raise OSError("儲存後文件不存在或為空")

                compressed_kb_loop = os.path.getsize(output_path) / 1024
                log_output += f"  嘗試 Quality={quality} → {compressed_kb_loop:.1f} KB\n"
                last_compressed_kb = compressed_kb_loop
                best_quality = quality
                saved_successfully = True # 標記成功保存

                if compressed_kb_loop <= target_kb:
                    break # 達到目標

            except Exception as save_err:
                 log_output += f"  ❌ Quality={quality} 儲存失敗: {save_err}\n"
                 # 如果特定質量儲存失敗，可能意味著圖像本身或庫有問題
                 # 可以選擇在這裡 break 或者繼續嘗試更低質量
                 # 這裡選擇繼續嘗試
                 pass

            quality -= quality_step

        # 循環結束後，確定最終的 compressed_kb
        if saved_successfully:
            # 如果是因為 <= target_kb 跳出，last_compressed_kb 就是目標值
            # 如果是循環到底部，last_compressed_kb 是 quality=10 左右的值
            # 如果中途保存失敗但之前成功過，last_compressed_kb 是最後成功的大小
            compressed_kb = last_compressed_kb

            # 如果循環到底部仍未達標，記錄一下
            if compressed_kb > target_kb and quality < 10 :
                 log_output += f"  ⚠️ 未能在 Quality>=10 達到目標，使用 Quality={best_quality} 的結果。\n"
                 # 確保 output_path 內容是 best_quality 的 (理論上最後一次循環應該寫入了)
                 # 可以加個保險，但可能非必要
                 # try: img.save(output_path, format='JPEG', quality=best_quality, optimize=True, progressive=True)
                 # except: pass

            # 最後再次確認文件存在性
            if os.path.exists(output_path):
                 compressed_kb = os.path.getsize(output_path) / 1024
            else:
                 log_output += "  ❌ 最終檢查時輸出檔案不存在。\n"
                 compressed_kb = original_kb # 視為失敗
        else:
            # 如果一次都沒保存成功
             log_output += "  ❌ 所有 Quality 級別儲存均失敗。\n"
             compressed_kb = original_kb # 視為失敗

        log_output += get_compression_info_str(display_filename, original_kb, compressed_kb, target_kb)

    except FileNotFoundError:
        log_output += f"❌ 錯誤：找不到臨時輸入檔案 {os.path.basename(input_path)}\n\n"
        original_kb = 0
        compressed_kb = 0
    except Image.UnidentifiedImageError:
         display_filename = os.path.basename(output_path) if 'output_path' in locals() else "未知文件"
         log_output += f"❌ 錯誤：檔案 {display_filename} 不是有效的圖片格式或已損壞。\n\n"
         original_kb = os.path.getsize(input_path)/1024 if os.path.exists(input_path) else 0
         compressed_kb = original_kb
    except Exception as e:
        display_filename = os.path.basename(output_path) if 'output_path' in locals() else "未知文件"
        log_output += f"❌ 處理 JPEG {display_filename} 時發生錯誤：{e}\n\n"
        original_kb = os.path.getsize(input_path)/1024 if os.path.exists(input_path) else 0
        compressed_kb = original_kb
        log_output += get_compression_info_str(display_filename, original_kb, compressed_kb, target_kb)

    return log_output, original_kb, compressed_kb

def convert_to_webp(input_path, output_path, target_kb=100, quality_step=5):
    log_output = ""
    try:
        img = Image.open(input_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if img.mode == "P" else "RGB")

        # 建議縮圖處理（選配）
        img.thumbnail((2048, 2048), Image.LANCZOS)

        original_kb = os.path.getsize(input_path) / 1024
        quality = 95
        buffer = io.BytesIO()

        while quality >= 10:
            buffer.seek(0)
            buffer.truncate()
            img.save(buffer, format="WEBP", quality=quality)  # 拿掉 optimize=True 加速
            size_kb = buffer.tell() / 1024
            log_output += f"  嘗試 quality={quality} → {size_kb:.1f} KB\n"
            if size_kb <= target_kb:
                break
            quality -= quality_step

        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())

        final_kb = os.path.getsize(output_path) / 1024
        log_output += get_compression_info_str(os.path.basename(output_path), original_kb, final_kb, target_kb)
        return log_output, original_kb, final_kb

    except Exception as e:
        return f"❌ WebP 轉換錯誤：{e}\n", 0, 0



# === 5. Gradio 的主要處理函數 (修改為處理檔案列表輸入) ===
def run_batch_compression(input_files_list, output_folder_str, target_kb_str, convert_to_webp_flag):
    """
    處理批次壓縮。
    Args:
        input_files_list: Gradio gr.File(file_count="multiple") 元件的輸出，
                           是一個包含上傳文件臨時對象的列表。
        output_folder_str: 使用者在 gr.Textbox 中輸入的輸出資料夾路徑字符串。
        target_kb_str: 目標大小 (KB) 的字符串。
    Returns:
        包含處理日誌的字符串。
    """
    log_output = ""
    total_original_kb = 0
    total_compressed_kb = 0
    processed_files = 0
    failed_files = 0
    skipped_files = 0 # 計數非圖片或處理前檢查失敗的文件

    # --- 輸入驗證 ---
    # 1. 驗證是否選擇了檔案
    if not input_files_list:
        return "❌ 錯誤：請點擊上方按鈕選擇一個或多個圖片檔案。"
    if not isinstance(input_files_list, list):
        return "❌ 錯誤：輸入檔案格式不正確（預期為文件列表）。"

    # 2. 驗證輸出資料夾路徑
    if not output_folder_str:
        return "❌ 錯誤：請在下方文字框中提供輸出資料夾的路徑。"
    output_folder = os.path.abspath(output_folder_str.strip())
    if not output_folder:
         return "❌ 錯誤：輸出資料夾路徑不能為空。"

    # 3. 驗證目標大小
    try:
        target_kb = float(target_kb_str)
        if target_kb <= 0:
            raise ValueError("目標大小必須為正數")
    except ValueError as e:
        return f"❌ 錯誤：目標檔案大小 '{target_kb_str}' 無效。請輸入一個正數。({e})"

    # --- 建立輸出資料夾 ---
    try:
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            log_output += f"📁 已建立輸出資料夾：{output_folder}\n"
        elif not os.path.isdir(output_folder):
             return f"❌ 錯誤：輸出路徑 '{output_folder}' 已存在但不是一個資料夾。"
        else:
            log_output += f"📁 輸出資料夾已存在：{output_folder}\n"
    except OSError as e:
        if "Permission denied" in str(e):
             return f"❌ 錯誤：無法建立或寫入輸出資料夾 '{output_folder}'。權限不足，請檢查路徑或更換位置。({e})"
        else:
             return f"❌ 錯誤：無法建立輸出資料夾 '{output_folder}'。請檢查路徑是否有效。({e})"
    except Exception as e:
         return f"❌ 錯誤：處理輸出資料夾路徑 '{output_folder}' 時發生錯誤。 {e}"

    log_output += f"\n🚀 開始處理選擇的 {len(input_files_list)} 個檔案...\n"
    # 不再顯示來源資料夾，因為是多個檔案
    log_output += f"⬅️  輸出到：{output_folder}\n"
    log_output += f"🎯 目標檔案大小：{target_kb:.1f} KB\n"
    log_output += "------------------------------------\n\n"

    # --- 批次處理 (遍歷選擇的文件列表) ---
    for temp_file in input_files_list:
        try:
            # 獲取原始文件名和臨時文件路徑
            original_filename = getattr(temp_file, 'orig_name', None)
            input_path = temp_file.name # 臨時文件的路徑

            if not original_filename:
                original_filename = os.path.basename(input_path)
                log_output += f"⚠️ 警告：無法獲取文件 {input_path} 的原始名稱，將使用 {original_filename}。\n"

            if not original_filename: # 如果連推斷都失敗
                 log_output += f"❌ 無法確定檔案 {input_path} 的名稱，跳過。\n"
                 skipped_files += 1
                 continue

            # 檢查文件擴展名 (使用原始文件名) - 預先過濾
            ext_lower = os.path.splitext(original_filename)[1].lower()
            if ext_lower not in ['.png', '.jpg', '.jpeg']:
                log_output += f"⏭️ 跳過非 PNG/JPG/JPEG 檔案：{original_filename}\n"
                skipped_files += 1
                continue

            # 構造輸出路徑
            output_path = os.path.join(output_folder, original_filename)

            # 檢查輸出文件是否已存在 (可選：添加覆蓋邏輯或提示)
            # if os.path.exists(output_path):
            #     log_output += f"🟡 警告：輸出檔案 {original_filename} 已存在，將被覆蓋。\n"

            file_log = ""
            original_kb = 0
            compressed_kb = 0

            if convert_to_webp_flag:
                output_filename = os.path.splitext(original_filename)[0] + ".webp"
                output_path = os.path.join(output_folder, output_filename)
                file_log, original_kb, compressed_kb = convert_to_webp(input_path, output_path, target_kb)
            else:
                output_path = os.path.join(output_folder, original_filename)
                if ext_lower == '.png':
                    file_log, original_kb, compressed_kb = compress_png(input_path, output_path, target_kb)
                elif ext_lower in ['.jpg', '.jpeg']:
                    file_log, original_kb, compressed_kb = compress_jpeg(input_path, output_path, target_kb)

            log_output += file_log
            total_original_kb += original_kb

            # 統計成功/失敗
            if 0 < original_kb and 0 < compressed_kb < original_kb: # 必須原始和壓縮後都>0 且壓縮後更小
                total_compressed_kb += compressed_kb
                processed_files += 1
            elif original_kb > 0: # 處理了但失敗/未壓縮/變大
                total_compressed_kb += original_kb # 失敗計入原始大小
                failed_files += 1
            elif original_kb == 0 and file_log: # 函數返回了日誌但原始大小為0 (例如跳過的空文件)
                skipped_files += 1
            # else: 原始大小為0且無日誌，可能未進入處理


        except Exception as e:
            # 捕獲處理單個文件的意外循環外錯誤
            filename_for_error = getattr(temp_file, 'orig_name', temp_file.name)
            log_output += f"❌❌ 處理檔案 {filename_for_error} 時發生嚴重外部錯誤：{e}\n\n"
            failed_files += 1
            # 嘗試計入原始大小
            try:
                if os.path.exists(temp_file.name):
                   current_original_kb = os.path.getsize(temp_file.name) / 1024
                   total_original_kb += current_original_kb
                   total_compressed_kb += current_original_kb
            except: pass

    # --- 總結 ---
    log_output += "------------------------------------\n"
    log_output += "📊 壓縮總結：\n"
    total_files_selected = len(input_files_list)
    log_output += f"  共選擇檔案：{total_files_selected} 個\n"
    # 顯示的計數應基於實際處理情況
    log_output += f"     (圖片處理成功：{processed_files} 個)\n"
    log_output += f"     (圖片處理失敗/未壓縮：{failed_files} 個)\n"
    log_output += f"     (跳過非圖片/空檔/其他：{skipped_files} 個)\n"
    # 確保計數總和等於選擇的檔案數 (用於調試)
    # assert total_files_selected == processed_files + failed_files + skipped_files, "檔案計數不匹配!"


    if total_original_kb > 0 and processed_files > 0:
        total_ratio = 100 * (1 - total_compressed_kb / total_original_kb)
        log_output += f"  總原始大小 (已處理圖片)：{total_original_kb:.1f} KB\n"
        log_output += f"  總輸出大小 (含失敗)：{total_compressed_kb:.1f} KB\n"
        log_output += f"  總節省空間 (估算)：{total_ratio:.1f} %\n"
    elif failed_files > 0 or skipped_files > 0:
         if total_original_kb > 0:
             log_output += f"  總原始大小 (已處理圖片)：{total_original_kb:.1f} KB\n"
         log_output += "  沒有圖片成功壓縮，或所有圖片均被跳過/處理失敗。\n"
    elif total_files_selected == 0: # 應該在開始時就處理了，但再加個保險
        log_output += "  未選擇任何檔案。\n"
    else:
        log_output += "  未處理任何有效檔案。\n"

    log_output += "\n✅ 所有選擇的檔案處理流程結束。\n"

    return log_output

# === 6. 建立 Gradio 介面 (改為選擇檔案) ===
with gr.Blocks(theme=gr.themes.Soft()) as iface:
    gr.Markdown(
        """
        # 圖片壓縮工具 (PNG/JPEG)

        1.  點擊下方按鈕 **選擇一個或多個圖片檔案** (PNG, JPG, JPEG)。
        2.  在**輸出資料夾路徑** 文字框中，**輸入或貼上**希望儲存壓縮後圖片的資料夾路徑。
            *   如果該資料夾不存在，程式會嘗試自動建立。
        3.  設定壓縮後的**目標檔案大小** (KB)。
        4.  點擊**開始壓縮** 按鈕。
        5.  在右側**處理日誌**中查看詳細過程和結果。
        """
    )
    with gr.Row():
        with gr.Column(scale=1):
            # 修改為選擇多個檔案
            input_file_selector = gr.File(
                label="1. 點擊選擇圖片檔案 (可多選)",
                file_count="multiple", # 關鍵修改: 從 "directory" 改為 "multiple"
                file_types=["image", ".png", ".jpg", ".jpeg"], # 限制可選的文件類型 (前端提示)
            )
            convert_webp_checkbox = gr.Checkbox(label="是否轉換為 WebP 格式", value=False)

            output_dir_textbox = gr.Textbox(
                label="2. 輸入或貼上輸出資料夾路徑",
                placeholder="例如：C:/Users/Public/Output 或 ./output_images",
                value="./output_images"
            )
            target_size_kb = gr.Number(label="3. 目標檔案大小 (KB)", value=500, minimum=1)
            compress_button = gr.Button("🚀 開始壓縮", variant="primary")
        with gr.Column(scale=2):
             output_log = gr.Textbox(
                 label="處理日誌",
                 lines=20,
                 interactive=False,
                 autoscroll=True
            )

    compress_button.click(
    fn=run_batch_compression,
    inputs=[input_file_selector, output_dir_textbox, target_size_kb, convert_webp_checkbox],
    outputs=output_log
    )  


# === 7. 執行 Gradio 應用 ===
if __name__ == "__main__":
    print("Gradio 應用程式啟動中...")
    print("請在瀏覽器開啟提供的網址。")
    iface.launch()
